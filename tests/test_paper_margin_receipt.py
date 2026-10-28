"""J4/AUTO9 #282: durable atomic margin receipt without exchange orders.

All symbols, rules, amounts, marks and feeds are offline synthetic fixtures.
No API calls or privilege changes; unkeyed SHA is *not* provenance proof.
"""
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.causal_paper_open import reserve_causal_paper_open
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_margin_preflight import PaperMarginReason
from crypto_intelligence_agent.paper_margin_receipt import (
    PaperMarginIntentReceipt, VERSION,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderStatus, PaperVenue,
)
from test_paper_margin_preflight import D, T, assess, contract, limits, mark, order
from test_synthetic_research_cycle import candles, config


class AtomicPaperMarginReceiptTests(unittest.TestCase):
    def setUp(self):
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.orders_path = Path(root.name) / "orders.sqlite"
        self.positions_path = Path(root.name) / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.orders_path)
        SQLitePaperPositionJournal(self.positions_path)

    def values(self, *, unit=D("2.5"), margin=D(5)):
        intent = order(requested_units=unit)
        assessment = assess(intent=intent, margin=margin)
        return intent, assessment

    def reserve(self, *, intent=None, assessment=None, observation=None):
        if intent is None:
            intent, default_assessment = self.values()
        else:
            default_assessment = assess(intent=intent, margin=D(5))
        if assessment is None:
            assessment = default_assessment
        return self.orders.reserve_open_if_paper_risk_with_health(
            intent, limits(), mark() if observation is None else observation,
            decision_at_ms=T, position_journal_path=self.positions_path,
            margin_assessment=assessment,
        )

    def count_rows(self):
        with closing(sqlite3.connect(self.orders_path)) as conn:
            return (
                conn.execute("SELECT COUNT(*) FROM paper_order_intents").fetchone()[0],
                conn.execute(
                    "SELECT COUNT(*) FROM paper_order_meta WHERE key LIKE 'paper-margin-intent-v1:%'"
                ).fetchone()[0],
            )

    def test_canonical_receipt_version_sha_and_flags(self):
        intent, assessment = self.values()
        self.assertEqual(assessment.reason, PaperMarginReason.FEASIBLE_PAPER_ONLY)
        receipt = PaperMarginIntentReceipt.from_assessment(intent, assessment)
        raw = receipt.serialize()
        self.assertIn(VERSION, raw)
        self.assertEqual(PaperMarginIntentReceipt.deserialize(raw), receipt)
        self.assertEqual(receipt.requested_margin_quote, D(5))
        self.assertEqual(receipt.leverage_at_intent, 50)
        self.assertEqual(receipt.requested_units_base, D("2.5"))
        self.assertEqual(receipt.hypothetical_mark_quote, D(100))
        self.assertEqual(receipt.assumed_notional_quote, D(250))
        self.assertEqual(receipt.assessed_at_ms, intent.created_at_ms)
        for key in ("actual_venue_margin_verified", "leverage_installed_on_exchange",
                    "position_collateral_verified", "funding_liquidation_verified",
                    "live_trading_authorized", "orders_sent", "cross_file_atomic"):
            self.assertFalse(getattr(receipt, key))
        with self.assertRaises(FrozenInstanceError):
            receipt.leverage_at_intent = 1

    def test_receipt_cannot_bind_another_intent_even_same_quantity(self):
        intent, assessment = self.values()
        other = order(
            intent_id="fixture_other_margin",
            fixture_signal_id="fixture_other_signal",
            requested_units=intent.requested_units,
        )
        with self.assertRaises(DataValidationError):
            PaperMarginIntentReceipt.from_assessment(other, assessment)
        receipt = PaperMarginIntentReceipt.from_assessment(intent, assessment)
        with self.assertRaises(DataValidationError):
            receipt.verify_intent(other)
        for wrong in (replace(intent, requested_units=D("2")),
                      replace(intent, symbol="ETHUSDT"),
                      replace(intent, fixture_signal_id="fixture_another_signal")):
            with self.subTest(intent=wrong.intent_id), self.assertRaises(DataValidationError):
                receipt.verify_intent(wrong)

    def test_new_paper_pending_and_margin_receipt_commit_together_and_restart(self):
        intent, assessment = self.values()
        health, result = self.reserve(intent=intent, assessment=assessment)
        self.assertTrue(health.new_open_allowed)
        self.assertTrue(result.decision.allowed_for_paper_only)
        self.assertEqual(result.entry.snapshot.status, PaperOrderStatus.PENDING)
        self.assertEqual(result.entry.events, ())
        self.assertEqual(self.count_rows(), (1, 1))
        reopened = SQLitePaperOrderJournal(self.orders_path)
        receipt = reopened.read_margin_receipt(intent.intent_id)
        self.assertEqual(receipt.intent_id, intent.intent_id)
        self.assertEqual(receipt.intent_sha256, assessment.intent_sha256)
        self.assertEqual(receipt.leverage_at_intent, 50)
        self.assertEqual(receipt.contract_fixture_version,
                         assessment.contract_fixture_version)
        self.assertEqual(reopened.load(intent.intent_id), result.entry)
        self.assertFalse(receipt.leverage_installed_on_exchange)

    def test_legacy_without_optin_is_explicitly_missing_not_fifty_x(self):
        intent, assessment = self.values()
        legacy = self.orders.reserve(intent)
        self.assertEqual(legacy.snapshot.status, PaperOrderStatus.PENDING)
        self.assertIsNone(SQLitePaperOrderJournal(
            self.orders_path
        ).read_margin_receipt(intent.intent_id))
        self.assertEqual(self.count_rows(), (1, 0))

    def test_denied_risk_does_not_persist_open_or_receipt(self):
        intent, assessment = self.values()
        observation = mark(kill_switch_active=True)
        health, result = self.reserve(
            intent=intent, assessment=assessment, observation=observation,
        )
        self.assertTrue(health.new_open_allowed)
        self.assertIsNone(result.entry)
        self.assertEqual(self.count_rows(), (0, 0))

    def test_durable_kill_switch_denies_receipt_under_same_lock(self):
        self.orders.set_local_kill_switch(
            pause=True, expected_sequence=0, changed_at_ms=T,
        )
        intent, assessment = self.values()
        _, result = self.reserve(intent=intent, assessment=assessment)
        self.assertIsNone(result.entry)
        self.assertEqual(self.count_rows(), (0, 0))

    def test_rollback_on_receipt_serialization_error_leaves_no_open(self):
        intent, assessment = self.values()
        with patch.object(
            PaperMarginIntentReceipt, "serialize",
            side_effect=DataValidationError("synthetic disk encoding failure"),
        ):
            with self.assertRaisesRegex(DataValidationError, "encoding failure"):
                self.reserve(intent=intent, assessment=assessment)
        self.assertEqual(self.count_rows(), (0, 0))

    def test_receipt_json_rejects_corruption_duplicate_fields_and_recomputed_sha(self):
        intent, assessment = self.values()
        receipt = PaperMarginIntentReceipt.from_assessment(intent, assessment)
        raw = receipt.serialize()
        for bad in (
            raw.replace("paper-margin-intent-v1", "paper-margin-intent-v2"),
            raw.replace('"leverage_at_intent":50', '"leverage_at_intent":20'),
            raw.replace('"leverage_at_intent":50',
                        '"leverage_at_intent":50,"leverage_at_intent":50'),
            raw + "extra",
            "",
        ):
            with self.subTest(bad=bad[:50]), self.assertRaises(DataValidationError):
                PaperMarginIntentReceipt.deserialize(bad)
        envelope = json.loads(raw)
        envelope["payload"]["leverage_at_intent"] = 20
        import hashlib
        payload = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"))
        envelope["payload_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
        forged = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        with self.assertRaisesRegex(DataValidationError, "exact arithmetic"):
            PaperMarginIntentReceipt.deserialize(forged)

    def test_corrupt_receipt_blocks_ro_recovery_and_new_open(self):
        intent, assessment = self.values()
        self.reserve(intent=intent, assessment=assessment)
        with closing(sqlite3.connect(self.orders_path)) as conn:
            conn.execute(
                "UPDATE paper_order_meta SET value='{}' WHERE key=?",
                ("paper-margin-intent-v1:" + intent.intent_id,),
            )
            conn.commit()
        # Reopening itself is expected to fail closed: _initialize verifies
        # the full metadata schema, not only when inspecting one receipt.
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.orders_path)
        with self.assertRaises(DataValidationError):
            self.orders.read_margin_receipt(intent.intent_id)
        # A second intent cannot bypass the corrupt receipt via OPEN health.
        next_intent = order(
            intent_id="fixture_next_receipt",
            fixture_signal_id="fixture_next_signal",
            requested_units=D("2.5"),
        )
        with self.assertRaises(DataValidationError):
            self.orders.reserve_open_if_paper_risk_with_health(
                next_intent, limits(), mark(), decision_at_ms=T,
                position_journal_path=self.positions_path,
            )
        self.assertEqual(self.count_rows(), (1, 1))

    def test_orphan_or_mismatched_meta_receipt_blocks_health(self):
        intent, assessment = self.values()
        receipt = PaperMarginIntentReceipt.from_assessment(intent, assessment)
        with closing(sqlite3.connect(self.orders_path)) as conn:
            conn.execute(
                "INSERT INTO paper_order_meta (key,value) VALUES (?,?)",
                (receipt.key, receipt.serialize()),
            )
            conn.commit()
        with self.assertRaises(DataValidationError):
            self.orders.read_margin_receipt(intent.intent_id)
        with self.assertRaises(DataValidationError):
            self.reserve(intent=intent, assessment=assessment)
        self.assertEqual(self.count_rows(), (0, 1))

    def test_unknown_meta_key_still_fails_closed(self):
        with closing(sqlite3.connect(self.orders_path)) as conn:
            conn.execute(
                "INSERT INTO paper_order_meta VALUES (?,?)",
                ("paper_margin_approved_for_live", "true"),
            )
            conn.commit()
        intent, assessment = self.values()
        with self.assertRaises(DataValidationError):
            self.reserve(intent=intent, assessment=assessment)
        self.assertEqual(self.count_rows(), (0, 0))

    def test_no_network_or_exchange_in_causal_open_and_reserve_receipt(self):
        source = candles()[:6]
        at = source[-1].close_time_ms + 1000
        from crypto_intelligence_agent.paper_margin_preflight import (
            PaperLinearContractFixture, PaperMarginPreflightRequest,
        )
        from crypto_intelligence_agent.synthetic_position_state import SyntheticLeverageSettings
        rule = PaperLinearContractFixture(
            venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
            quote_currency="USDT", observed_at_ms=at,
            fixture_version="fixture_causal_receipt_v1",
            max_leverage_assumed=75, price_tick_quote=D("0.01"),
            quantity_step_base=D("0.01"), min_quantity_base=D("0.01"),
            min_notional_quote=D(100), max_notional_quote=D(1000),
        )
        request = PaperMarginPreflightRequest(
            settings=SyntheticLeverageSettings(),
            margin_quote=D(5), contract=rule,
            max_contract_age_ms=1000,
        )
        observation = mark(
            observed_at_ms=at, mark_price_quote=D(100),
        )
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                outcome = reserve_causal_paper_open(
                    source, strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
                    requested_units=D("2.5"), limits=limits(),
                    observation=observation, journal=self.orders,
                    position_journal_path=self.positions_path,
                    decision_at_ms=at, margin_preflight=request,
                )
        self.assertTrue(outcome.paper_intent_reserved)
        self.assertEqual(self.count_rows(), (1, 1))
        receipt = SQLitePaperOrderJournal(
            self.orders_path
        ).read_margin_receipt(outcome.intent.intent_id)
        self.assertEqual(receipt.leverage_at_intent, 50)
        self.assertEqual(receipt.assessed_at_ms, at)
        self.assertFalse(receipt.live_trading_authorized)
        self.assertFalse(outcome.orders_sent)


if __name__ == "__main__":
    unittest.main()
