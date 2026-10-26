"""J4/AUTO6: pending OPEN is derived from durable PAPER events under a lock."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_risk_gate import (
    PaperRiskLimits, PaperRiskObservation, PaperRiskReason,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

T = 1792985000000
D = Decimal


def intent(name="A", **changes):
    fields = dict(
        intent_id="fixture_intent_" + name,
        fixture_signal_id="fixture_signal_" + name,
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
        effect=PaperOrderEffect.OPEN, requested_units=D(10), created_at_ms=T,
    )
    fields.update(changes)
    return PaperOrderIntent(**fields)


def event(name, kind, offset, units="0"):
    return PaperOrderEvent(
        event_id="fixture_event_" + name, kind=kind,
        event_at_ms=T + offset, filled_units=D(units),
    )


def limits(**changes):
    fields = dict(
        max_order_notional_quote=D(100),
        max_symbol_exposure_quote=D(200),
        max_portfolio_exposure_quote=D(300),
        max_realized_loss_today_quote=D(10),
        max_pending_open_orders=1, max_market_age_ms=1000,
    )
    fields.update(changes)
    return PaperRiskLimits(**fields)


def observed(**changes):
    fields = dict(
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT", quote_currency="USDT",
        observed_at_ms=T, mark_price_quote=D(2),
        symbol_exposure_quote=D(0), portfolio_exposure_quote=D(0),
        realized_loss_today_quote=D(0), pending_open_orders=0,
        unresolved_open_exists=False, kill_switch_active=False,
    )
    fields.update(changes)
    return PaperRiskObservation(**fields)


class AtomicPaperRiskReserveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "paper-orders.sqlite"
        self.store = SQLitePaperOrderJournal(self.db)

    def preflight(self, key="A", *, item=None, rules=None, snapshot=None,
                  decision_at_ms=T):
        return self.store.reserve_open_if_paper_risk(
            intent(key) if item is None else item,
            limits() if rules is None else rules,
            observed() if snapshot is None else snapshot,
            decision_at_ms=decision_at_ms,
        )

    def test_first_open_has_one_atomic_paper_intent_and_no_live_authority(self):
        result = self.preflight()
        self.assertTrue(result.decision.allowed_for_paper_only)
        self.assertIsNotNone(result.entry)
        self.assertEqual(result.entry.snapshot.status, PaperOrderStatus.PENDING)
        self.assertEqual(result.local_pending_before, 0)
        self.assertFalse(result.local_unknown_before)
        self.assertFalse(result.orders_sent)
        self.assertFalse(result.approved_for_live_use)
        self.assertFalse(result.order_submission_enabled)
        self.assertEqual(SQLitePaperOrderJournal(self.db).load(
            intent().intent_id), result.entry)

    def test_client_claims_zero_but_durable_pending_blocks_second_open(self):
        self.preflight()
        denied = self.preflight("B", snapshot=observed(
            pending_open_orders=0, unresolved_open_exists=False,
        ))
        self.assertFalse(denied.decision.allowed_for_paper_only)
        self.assertEqual(denied.decision.reason, PaperRiskReason.PENDING_LIMIT)
        self.assertIsNone(denied.entry)
        self.assertEqual(denied.local_pending_before, 1)
        with self.assertRaises(DataValidationError):
            self.store.load(intent("B").intent_id)
        self.assertEqual(self.store.load(intent("A").intent_id).snapshot.status,
                         PaperOrderStatus.PENDING)

    def test_unknown_cannot_be_hidden_by_false_observation_or_restart(self):
        first = self.preflight()
        timeout = event("timeout", PaperOrderEventKind.UNKNOWN, 1)
        self.store.append_events(first.entry.intent.intent_id, (timeout,), as_of_ms=T + 1)
        restarted = SQLitePaperOrderJournal(self.db)
        result = restarted.reserve_open_if_paper_risk(
            intent("B"), limits(), observed(
                pending_open_orders=0, unresolved_open_exists=False,
            ), decision_at_ms=T + 1,
        )
        self.assertFalse(result.decision.allowed_for_paper_only)
        self.assertEqual(result.decision.reason, PaperRiskReason.UNRESOLVED_OPEN)
        self.assertEqual(result.local_pending_before, 1)
        self.assertTrue(result.local_unknown_before)
        self.assertIsNone(result.entry)

    def test_partially_filled_open_still_counts_as_pending(self):
        first = self.preflight()
        self.store.append_events(
            first.entry.intent.intent_id,
            (event("part", PaperOrderEventKind.FILL, 1, "4"),),
            as_of_ms=T + 1,
        )
        denied = self.preflight("B", decision_at_ms=T + 1)
        self.assertEqual(denied.decision.reason, PaperRiskReason.PENDING_LIMIT)
        self.assertIsNone(denied.entry)
        self.store.append_events(first.entry.intent.intent_id,
                                 (event("done", PaperOrderEventKind.FILL, 2, "6"),),
                                 as_of_ms=T + 2)
        allowed = self.preflight("B", decision_at_ms=T + 2)
        self.assertTrue(allowed.decision.allowed_for_paper_only)
        self.assertIsNotNone(allowed.entry)
        self.assertEqual(allowed.local_pending_before, 0)

    def test_cancelled_unknown_releases_pending_without_fabricating_fill(self):
        a = self.preflight()
        self.store.append_events(a.entry.intent.intent_id, (
            event("unknown", PaperOrderEventKind.UNKNOWN, 1),
            event("cancel", PaperOrderEventKind.CANCELLED, 2),
        ), as_of_ms=T + 2)
        old = self.store.load(a.entry.intent.intent_id)
        self.assertEqual(old.snapshot.status, PaperOrderStatus.CANCELLED)
        self.assertEqual(old.snapshot.filled_total_units, D(0))
        new = self.preflight("B", decision_at_ms=T + 2)
        self.assertTrue(new.decision.allowed_for_paper_only)
        self.assertIsNotNone(new.entry)
        with self.assertRaises(DataValidationError):
            self.preflight("A", decision_at_ms=T + 2)

    def test_larger_claimed_pending_or_unknown_remains_fail_closed(self):
        blocked = self.preflight(snapshot=observed(pending_open_orders=1))
        self.assertEqual(blocked.decision.reason, PaperRiskReason.PENDING_LIMIT)
        self.assertIsNone(blocked.entry)
        self.assertEqual(blocked.local_pending_before, 0)
        blocked_unknown = self.preflight(snapshot=observed(unresolved_open_exists=True))
        self.assertEqual(blocked_unknown.decision.reason, PaperRiskReason.UNRESOLVED_OPEN)
        self.assertIsNone(blocked_unknown.entry)

    def test_kill_switch_losses_and_staleness_not_bypassed_by_local_zero(self):
        cases = (
            (observed(kill_switch_active=True), T, PaperRiskReason.KILL_SWITCH),
            (observed(realized_loss_today_quote=D(10)), T, PaperRiskReason.LOSS_LIMIT),
            (observed(), T + 1001, PaperRiskReason.STALE_FEED),
        )
        for claim, ts, reason in cases:
            with self.subTest(reason=reason):
                result = self.preflight(snapshot=claim, decision_at_ms=ts)
                self.assertEqual(result.decision.reason, reason)
                self.assertIsNone(result.entry)
        self.assertEqual(self.preflight().entry.intent.intent_id,
                         "fixture_intent_A")

    def test_concurrent_distinct_signals_cannot_both_cross_pending_limit(self):
        def submit(name):
            try:
                result = SQLitePaperOrderJournal(self.db).reserve_open_if_paper_risk(
                    intent(name), limits(), observed(), decision_at_ms=T,
                )
                return "accepted" if result.entry is not None else "blocked"
            except DataValidationError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(submit, ("race_A", "race_B")))
        self.assertEqual(sorted(outcomes), ["accepted", "blocked"])
        with sqlite3.connect(self.db) as con:
            count = con.execute(
                "SELECT COUNT(*) FROM paper_order_intents WHERE effect='OPEN'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_tampered_index_or_payload_fails_preflight_instead_of_undercounting(self):
        self.preflight()
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE paper_order_intents SET effect='REDUCE_ONLY'")
        with self.assertRaises(DataValidationError):
            self.preflight("B")
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE paper_order_intents SET payload='{}'")
        with self.assertRaises(DataValidationError):
            self.preflight("C")

    def test_reduce_only_record_is_validated_but_not_counted_as_open(self):
        exit_intent = intent(
            "exit", effect=PaperOrderEffect.REDUCE_ONLY, side=PaperOrderSide.SELL,
            max_reducible_units=D(10),
        )
        self.store.reserve(exit_intent)
        result = self.preflight("new")
        self.assertEqual(result.local_pending_before, 0)
        self.assertTrue(result.decision.allowed_for_paper_only)

    def test_invalid_input_or_duplicate_intent_never_becomes_new_approval(self):
        with self.assertRaises(DataValidationError):
            self.store.reserve_open_if_paper_risk(
                intent("bad", effect=PaperOrderEffect.REDUCE_ONLY,
                       side=PaperOrderSide.SELL, max_reducible_units=D(10)),
                limits(), observed(), decision_at_ms=T,
            )
        accepted = self.preflight()
        self.assertIsNotNone(accepted.entry)
        with self.assertRaises(DataValidationError):
            self.preflight()
        with self.assertRaises(DataValidationError):
            self.store.reserve_open_if_paper_risk(
                intent("other"), {"mode": "live"}, observed(), decision_at_ms=T,
            )
        self.assertEqual(len(accepted.entry.events), 0)

    def test_legacy_paper_reserve_contract_still_idempotent(self):
        original = self.store.reserve(intent())
        self.assertEqual(self.store.reserve(intent()), original)
        self.assertFalse(original.orders_sent)
        self.assertFalse(original.approved_for_live_use)

    def test_no_network_or_real_trade_even_when_paper_preflight_passes(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                result = self.preflight()
        self.assertFalse(result.orders_sent)
        self.assertFalse(result.approved_for_live_use)
        self.assertFalse(result.order_submission_enabled)


if __name__ == "__main__":
    unittest.main()
