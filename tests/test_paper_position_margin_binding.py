"""J4/AUTO10 #284: PAPER position inherits only a confirmed AUTO2 margin receipt.

All data is synthetic and offline. A requested quote margin / 50x fixture
is NOT actual venue collateral, fills, liquidation math or live approval.
"""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_margin_receipt import PaperMarginIntentReceipt
from crypto_intelligence_agent.paper_open_health import (
    PaperProtectionState, audit_paper_open_health,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_paper_margin_preflight import D, T, assess, limits, mark, order

POS = "fixture_margin_position_A"


def exit_plan(size):
    return SyntheticExitPlan(
        initial_units=D(size),
        tranches=(
            SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(50)),
        ),
        residual_floor_percent=D(0),
    )


def fill_event(qty="2.5", *, when=1, name="open_fill"):
    return PaperOrderEvent(
        "fixture_margin_" + name, PaperOrderEventKind.FILL, T + when, D(qty),
    )


class FilledPaperPositionMarginBindingTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.orders_path = Path(tmp.name) / "orders.sqlite"
        self.position_path = Path(tmp.name) / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.orders_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        self.intent = order(requested_units=D("2.5"))

    def reserve(self, *, with_receipt=True):
        if with_receipt:
            evaluation = assess(intent=self.intent, margin=D(5))
            health, reservation = self.orders.reserve_open_if_paper_risk_with_health(
                self.intent, limits(), mark(),
                decision_at_ms=T,
                position_journal_path=self.position_path,
                margin_assessment=evaluation,
            )
            self.assertTrue(health.new_open_allowed)
            self.assertEqual(reservation.entry.snapshot.status, PaperOrderStatus.PENDING)
        else:
            self.orders.reserve(self.intent)
        return self.orders.read_margin_receipt(self.intent.intent_id)

    def append_open(self, events, *, as_of):
        self.orders.append_events(self.intent.intent_id, events, as_of_ms=as_of)

    def create(self, events, *, as_of, amount="2.5",
               position=POS, order_path=True):
        return self.positions.create_position(
            position_id=position,
            opening_intent=self.intent,
            opening_events=events,
            exit_plan=exit_plan(amount),
            plan_version="fixture-margin-exits-v1",
            synthetic_lot_step_units=D("0.25"),
            as_of_ms=as_of,
            opening_order_path=self.orders_path if order_path else None,
        )

    def position_count(self):
        with closing(sqlite3.connect(self.position_path)) as con:
            return con.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]

    def test_50x_receipt_bound_to_filled_position_and_restart(self):
        receipt = self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        result = self.create((event,), as_of=T+1)
        self.assertEqual(result.initial_confirmed_units, D("2.5"))
        self.assertEqual(result.leverage_at_intent, 50)
        self.assertEqual(result.requested_margin_quote, D(5))
        self.assertEqual(result.margin_quote_currency, "USDT")
        self.assertEqual(result.opening_margin_intent, receipt)
        for attr in ("actual_position_margin_verified", "leverage_accepted_by_venue",
                     "quote_to_usd_converted", "orders_sent", "live_trading_authorized"):
            self.assertFalse(getattr(result, attr))
        reopened = SQLitePaperPositionJournal(self.position_path)
        replay = reopened.load(POS)
        self.assertEqual(replay.opening_margin_intent, receipt)
        self.assertEqual(replay.leverage_at_intent, 50)
        cross = inspect_paper_position(
            self.position_path, POS, opening_order_path=self.orders_path,
        )
        self.assertTrue(cross.opening_order_cross_checked)
        self.assertEqual(cross.balance.requested_margin_quote, D(5))
        with self.assertRaises(FrozenInstanceError):
            replay.leverage_at_intent = 20

    def test_explicit_exit_partial_and_restart_never_recalculate_leverage(self):
        original = self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        initial = self.create((event,), as_of=T+1)
        close = PaperOrderIntent(
            intent_id="fixture_margin_close_1",
            fixture_signal_id="fixture_margin_close_signal_1",
            venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
            position_side=SyntheticSide.LONG,
            side=PaperOrderSide.SELL, effect=PaperOrderEffect.REDUCE_ONLY,
            requested_units=D("1.25"), max_reducible_units=D("2.5"),
            created_at_ms=T+2,
        )
        pending = self.positions.reserve_exit(
            POS, 1, close, as_of_ms=T+2,
        )
        self.assertEqual(pending.leverage_at_intent, 50)
        filled = self.positions.append_exit_events(
            POS, close.intent_id,
            (PaperOrderEvent(
                "fixture_margin_exit_fill_1", PaperOrderEventKind.FILL, T+3, D("1.25"),
            ),),
            as_of_ms=T+3,
        )
        self.assertEqual(filled.confirmed_remaining_units, D("1.25"))
        again = SQLitePaperPositionJournal(self.position_path).load(POS)
        self.assertEqual(again.leverage_at_intent, 50)
        self.assertEqual(again.requested_margin_quote, D(5))
        self.assertEqual(again.opening_margin_intent, original)
        self.assertEqual(self.position_count(), 1)
        # Idempotent replay must not discard existing exits/terms.
        self.assertEqual(
            self.create((event,), as_of=T+1).confirmed_remaining_units,
            D("1.25"),
        )

    def test_cancelled_after_partial_fill_keeps_requested_not_confirmed_quantity(self):
        receipt = self.reserve()
        partial = fill_event("1.0")
        cancel = PaperOrderEvent(
            "fixture_margin_cancel", PaperOrderEventKind.CANCELLED, T+2,
        )
        self.append_open((partial, cancel), as_of=T+2)
        result = self.create(
            (partial, cancel), as_of=T+2, amount="1.0",
        )
        self.assertEqual(result.initial_confirmed_units, D("1.0"))
        self.assertEqual(receipt.requested_units_base, D("2.5"))
        self.assertEqual(result.requested_margin_quote, D(5))
        self.assertEqual(result.leverage_at_intent, 50)
        self.assertFalse(result.actual_position_margin_verified)
        self.assertEqual(
            inspect_paper_position(
                self.position_path, POS, opening_order_path=self.orders_path,
            ).balance.confirmed_remaining_units, D("1.0"),
        )

    def test_ack_or_pending_cannot_become_position_even_with_margin_receipt(self):
        receipt = self.reserve()
        self.assertIsNotNone(receipt)
        with self.assertRaises(DataValidationError):
            self.create((), as_of=T)
        self.assertEqual(self.position_count(), 0)
        ack = PaperOrderEvent(
            "fixture_margin_ack", PaperOrderEventKind.ACKNOWLEDGED, T+1,
        )
        self.append_open((ack,), as_of=T+1)
        with self.assertRaises(DataValidationError):
            self.create((ack,), as_of=T+1)
        self.assertEqual(self.position_count(), 0)

    def test_legacy_position_without_receipt_keeps_original_payload_and_no_fake_50x(self):
        self.assertIsNone(self.reserve(with_receipt=False))
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        balance = self.create((event,), as_of=T+1)
        self.assertIsNone(balance.opening_margin_intent)
        self.assertIsNone(balance.leverage_at_intent)
        self.assertIsNone(balance.requested_margin_quote)
        self.assertIsNone(balance.margin_quote_currency)
        with closing(sqlite3.connect(self.position_path)) as conn:
            payload = conn.execute(
                "SELECT payload FROM paper_positions WHERE position_id=?",
                (POS,),
            ).fetchone()[0]
        self.assertNotIn("opening_margin_intent_v1", payload)
        self.assertIsNone(
            inspect_paper_position(
                self.position_path, POS, opening_order_path=self.orders_path,
            ).balance.opening_margin_intent
        )

    def test_legacy_registration_cannot_silently_backfill_requested_margin(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        # A caller using the old API can still create an old-style position,
        # but cannot claim it matches AUTO2 receipt if cross-checked later.
        bare = self.create((event,), as_of=T+1, order_path=False)
        self.assertIsNone(bare.leverage_at_intent)
        with self.assertRaisesRegex(DataValidationError, "receipt differs"):
            inspect_paper_position(
                self.position_path, POS, opening_order_path=self.orders_path,
            )
        health = audit_paper_open_health(
            self.orders_path, self.position_path, decision_at_ms=T+1,
        )
        self.assertFalse(health.new_open_allowed)
        self.assertEqual(health.fills[0].protection_state, PaperProtectionState.UNKNOWN)
        self.assertEqual(health.fills[0].reason,
                         "opening_margin_receipt_cross_journal_mismatch")
        with self.assertRaises(DataValidationError):
            self.create((event,), as_of=T+1, order_path=True)
        self.assertEqual(self.position_count(), 1)

    def test_missing_receipt_in_order_after_position_creation_fails_crosscheck(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        self.create((event,), as_of=T+1)
        with closing(sqlite3.connect(self.orders_path)) as conn:
            conn.execute(
                "DELETE FROM paper_order_meta WHERE key=?",
                ("paper-margin-intent-v1:" + self.intent.intent_id,),
            )
            conn.commit()
        with self.assertRaises(DataValidationError):
            inspect_paper_position(
                self.position_path, POS, opening_order_path=self.orders_path,
            )
        health = audit_paper_open_health(
            self.orders_path, self.position_path, decision_at_ms=T+1,
        )
        self.assertFalse(health.new_open_allowed)
        self.assertEqual(health.fills[0].protection_state, PaperProtectionState.UNKNOWN)

    def test_valid_rehashed_altered_margin_receipt_detected_between_files(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        self.create((event,), as_of=T+1)
        saved = self.orders.read_margin_receipt(self.intent.intent_id)
        altered = replace(
            saved, requested_margin_quote=D("12.5"), leverage_at_intent=20,
        )
        altered.verify_intent(self.intent)
        with closing(sqlite3.connect(self.orders_path)) as con:
            con.execute(
                "UPDATE paper_order_meta SET value=? WHERE key=?",
                (altered.serialize(), saved.key),
            )
            con.commit()
        # Local SHA and identity still validate. The other file does NOT.
        with self.assertRaisesRegex(DataValidationError, "receipt differs"):
            inspect_paper_position(
                self.position_path, POS, opening_order_path=self.orders_path,
            )
        health = audit_paper_open_health(
            self.orders_path, self.position_path, decision_at_ms=T+1,
        )
        self.assertFalse(health.new_open_allowed)
        self.assertEqual(health.fills[0].reason,
                         "opening_margin_receipt_cross_journal_mismatch")

    def test_position_record_tamper_recomputed_digest_fails_semantic_receipt_check(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        self.create((event,), as_of=T+1)
        with closing(sqlite3.connect(self.position_path)) as con:
            old = con.execute(
                "SELECT payload FROM paper_positions WHERE position_id=?",
                (POS,),
            ).fetchone()[0]
            data = json.loads(old)
            data["opening_margin_intent_v1"]["payload"]["leverage_at_intent"] = 20
            envelope = data["opening_margin_intent_v1"]
            nested = json.dumps(
                envelope["payload"], sort_keys=True, separators=(",", ":"),
                ensure_ascii=True,
            )
            envelope["payload_sha256"] = sha256(nested.encode()).hexdigest()
            encoded = json.dumps(data, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True)
            con.execute(
                "UPDATE paper_positions SET payload=?, digest=? WHERE position_id=?",
                (encoded, sha256(encoded.encode()).hexdigest(), POS),
            )
            con.commit()
        with self.assertRaises(DataValidationError):
            SQLitePaperPositionJournal(self.position_path).load(POS)
        with self.assertRaises(DataValidationError):
            inspect_paper_position(self.position_path, POS)

    def test_mismatched_verified_order_events_reject_before_position_insert(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        different = fill_event("2.5", when=2, name="different_fill")
        with self.assertRaises(DataValidationError):
            self.create((different,), as_of=T+2)
        self.assertEqual(self.position_count(), 0)
        with self.assertRaises(DataValidationError):
            self.positions.create_position(
                position_id=POS,
                opening_intent=self.intent,
                opening_events=(event,), exit_plan=exit_plan("2.5"),
                plan_version="fixture-margin-exits-v1",
                synthetic_lot_step_units=D("0.25"), as_of_ms=T+1,
                opening_order_path=self.position_path,
            )
        self.assertEqual(self.position_count(), 0)

    def test_attempt_to_change_leverage_on_reregister_fails_without_rewrite(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        saved = self.create((event,), as_of=T+1)
        with self.assertRaises(DataValidationError):
            self.create((event,), as_of=T+1, order_path=False)
        self.assertEqual(self.positions.load(POS), saved)

    def test_health_blocks_protected_paper_position_without_claiming_native_stop(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        saved = self.create((event,), as_of=T+1)
        check = audit_paper_open_health(
            self.orders_path, self.position_path, decision_at_ms=T+1,
        )
        self.assertFalse(check.new_open_allowed)
        self.assertFalse(check.native_stop_verified)
        self.assertFalse(check.cross_database_atomic_snapshot_available)
        self.assertEqual(check.fills[0].protection_state,
                         PaperProtectionState.PROTECTED_HYPOTHETICAL_ONLY)
        self.assertEqual(saved.leverage_at_intent, 50)

    def test_no_network_on_filled_position_restore_and_inspect(self):
        self.reserve()
        event = fill_event()
        self.append_open((event,), as_of=T+1)
        self.create((event,), as_of=T+1)
        with patch("socket.create_connection",
                   side_effect=AssertionError("network forbidden")):
            with patch("urllib.request.urlopen",
                       side_effect=AssertionError("network forbidden")):
                verified = inspect_paper_position(
                    self.position_path, POS, opening_order_path=self.orders_path,
                )
                journal = SQLitePaperPositionJournal(self.position_path)
                replayed = journal.load(POS)
        self.assertEqual(verified.balance.opening_margin_intent,
                         replayed.opening_margin_intent)
        self.assertFalse(verified.live_trading_authorized)
        self.assertFalse(replayed.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
