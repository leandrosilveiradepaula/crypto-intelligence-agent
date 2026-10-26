"""J4/AUTO1: offline order-state proof, NOT an integration with Binance/Bybit."""
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue, replay_paper_order,
)

T = 1_792_985_000_000
D = Decimal


def entry(**kw):
    fields = dict(
        intent_id="fixture_order_BTC_1", fixture_signal_id="fixture_signal_BTC_1",
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
        effect=PaperOrderEffect.OPEN, requested_units=D("10"), created_at_ms=T,
    )
    fields.update(kw)
    return PaperOrderIntent(**fields)


def event(name, kind, t=1, units="0"):
    return PaperOrderEvent("fixture_event_" + name, kind, T + t, D(units))


def replay(events=(), **kw):
    return replay_paper_order(entry(), tuple(events), as_of_ms=T + 20, **kw)


class PaperOrderLifecycleTests(unittest.TestCase):
    def test_pending_does_not_invent_submission_or_fill(self):
        order = entry()
        self.assertFalse(order.orders_sent)
        self.assertFalse(order.approved_for_live_use)
        self.assertFalse(order.persistent_idempotency_verified)
        snap = replay()
        self.assertEqual(snap.status, PaperOrderStatus.PENDING)
        self.assertEqual(snap.filled_total_units, D(0))
        self.assertEqual(snap.unfilled_units, D(10))
        self.assertTrue(snap.requires_reconciliation)
        self.assertFalse(snap.orders_sent)
        self.assertFalse(snap.approved_for_live_use)
        self.assertEqual(snap.quality, "synthetic_order_events_only")
        self.assertFalse(snap.persistent_idempotency_verified)

    def test_ack_is_not_fill(self):
        snap = replay([event("ack", PaperOrderEventKind.ACKNOWLEDGED)])
        self.assertEqual(snap.status, PaperOrderStatus.ACKNOWLEDGED)
        self.assertEqual(snap.filled_total_units, D(0))
        self.assertTrue(snap.requires_reconciliation)

    def test_unknown_never_assumed_rejected_or_resubmitted(self):
        snap = replay([event("timeout", PaperOrderEventKind.UNKNOWN)])
        self.assertEqual(snap.status, PaperOrderStatus.UNKNOWN)
        self.assertEqual(snap.filled_total_units, D(0))
        self.assertEqual(snap.unfilled_units, D(10))
        self.assertTrue(snap.requires_reconciliation)
        self.assertFalse(snap.orders_sent)

    def test_unknown_then_partial_and_full_fill_with_exact_duplicate(self):
        timeout = event("timeout", PaperOrderEventKind.UNKNOWN, 1)
        first = event("first", PaperOrderEventKind.FILL, 2, "4.0")
        done = event("done", PaperOrderEventKind.FILL, 3, "6")
        partial = replay([timeout, first, first])
        self.assertEqual(partial.status, PaperOrderStatus.PARTIALLY_FILLED)
        self.assertEqual(partial.filled_total_units, D("4.0"))
        self.assertEqual(partial.unfilled_units, D("6.0"))
        self.assertEqual(partial.unique_event_count, 2)
        self.assertEqual(partial.exact_duplicate_count, 1)
        full = replay([timeout, first, first, done])
        self.assertEqual(full.status, PaperOrderStatus.FILLED)
        self.assertEqual(full.filled_total_units, D(10))
        self.assertEqual(full.unfilled_units, D(0))
        self.assertFalse(full.requires_reconciliation)

    def test_late_ack_after_fill_is_not_an_additional_order(self):
        done = replay([
            event("fill", PaperOrderEventKind.FILL, 1, "10"),
            event("lateack", PaperOrderEventKind.ACKNOWLEDGED, 2),
        ])
        self.assertEqual(done.status, PaperOrderStatus.FILLED)
        self.assertEqual(done.filled_total_units, D(10))
        self.assertEqual(done.unique_event_count, 2)

    def test_rejection_and_cancellation_do_not_manufacture_fill(self):
        rejected = replay([event("rej", PaperOrderEventKind.REJECTED)])
        self.assertEqual(rejected.status, PaperOrderStatus.REJECTED)
        self.assertEqual(rejected.filled_total_units, D(0))
        partial_cancelled = replay([
            event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1),
            event("part", PaperOrderEventKind.FILL, 2, "4"),
            event("cancel", PaperOrderEventKind.CANCELLED, 3),
        ])
        self.assertEqual(partial_cancelled.status, PaperOrderStatus.CANCELLED)
        self.assertEqual(partial_cancelled.filled_total_units, D(4))
        self.assertEqual(partial_cancelled.unfilled_units, D(6))
        self.assertFalse(partial_cancelled.requires_reconciliation)
        with self.assertRaises(DataValidationError):
            replay([event("rej", PaperOrderEventKind.REJECTED, 1),
                    event("late", PaperOrderEventKind.FILL, 2, "1")])
        with self.assertRaises(DataValidationError):
            replay([event("all", PaperOrderEventKind.FILL, 1, "10"),
                    event("cancel", PaperOrderEventKind.CANCELLED, 2)])

    def test_out_of_order_fills_duplicate_id_and_overfill_fail_closed(self):
        with self.assertRaises(DataValidationError):
            replay([event("f1", PaperOrderEventKind.FILL, 2, "4"),
                    event("f2", PaperOrderEventKind.FILL, 1, "2")])
        dup = event("same", PaperOrderEventKind.FILL, 1, "4")
        with self.assertRaisesRegex(DataValidationError, "conflicting reuse"):
            replay([dup, replace(dup, filled_units=D("4.00"))])
        with self.assertRaises(DataValidationError):
            replay([event("f1", PaperOrderEventKind.FILL, 1, "11")])
        with self.assertRaises(DataValidationError):
            replay([event("f1", PaperOrderEventKind.FILL, 1, "10"),
                    event("f2", PaperOrderEventKind.FILL, 2, "1")])
        with self.assertRaises(DataValidationError):
            replay([event("f1", PaperOrderEventKind.FILL, 1, "1"),
                    event("rej", PaperOrderEventKind.REJECTED, 2)])

    def test_replay_is_pure_and_repeated_input_is_idempotent(self):
        events = (
            event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1),
            event("fill", PaperOrderEventKind.FILL, 2, "5"),
        )
        self.assertEqual(replay(events), replay(events))
        self.assertEqual(replay(events + (events[-1],)).filled_total_units, D("5"))
        self.assertEqual(replay(events + (events[-1],)).exact_duplicate_count, 1)

    def test_reject_future_earlier_and_invalid_event_timeline(self):
        for e in (event("before", PaperOrderEventKind.ACKNOWLEDGED, -1),
                  event("after", PaperOrderEventKind.ACKNOWLEDGED, 30)):
            with self.subTest(e=e), self.assertRaises(DataValidationError):
                replay([e])
        with self.assertRaises(DataValidationError):
            replay_paper_order(entry(), (), as_of_ms=T - 1)
        with self.assertRaises(DataValidationError):
            replay_paper_order(entry(), [event("ack", PaperOrderEventKind.ACKNOWLEDGED)],
                               as_of_ms=T + 2)

    def test_reduce_only_explicit_opposite_side_and_position_cap(self):
        exit_short = entry(
            effect=PaperOrderEffect.REDUCE_ONLY, side=PaperOrderSide.BUY,
            position_side=SyntheticSide.SHORT, max_reducible_units=D(12),
            venue=PaperVenue.BYBIT_V5,
        )
        self.assertEqual(exit_short.effect, PaperOrderEffect.REDUCE_ONLY)
        self.assertEqual(replay_paper_order(exit_short, (
            event("exit", PaperOrderEventKind.FILL, 1, "10"),
        ), as_of_ms=T + 10).filled_total_units, D(10))
        exit_long = replace(exit_short, position_side=SyntheticSide.LONG,
                            side=PaperOrderSide.SELL)
        self.assertIs(exit_long.side, PaperOrderSide.SELL)
        for kw in (
            dict(max_reducible_units=None),
            dict(max_reducible_units=D("9")),
            dict(side=PaperOrderSide.SELL),
            dict(position_side=True),
        ):
            with self.subTest(kw=kw), self.assertRaises(DataValidationError):
                replace(exit_short, **kw)

    def test_opening_has_no_reduce_balance_and_correct_direction(self):
        for change in (
            dict(effect=PaperOrderEffect.OPEN, max_reducible_units=D(10)),
            dict(side=PaperOrderSide.SELL),
            dict(position_side=SyntheticSide.SHORT),
            dict(effect=PaperOrderEffect.REDUCE_ONLY),
        ):
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                replace(entry(), **change)

    def test_invalid_fixture_inputs_fail_closed(self):
        for changes in (
            dict(venue="binance_usdm"),
            dict(venue=PaperVenue.BYBIT_V5, symbol="btcUSDT"),
            dict(intent_id="not_a_fixture"),
            dict(fixture_signal_id="not_a_fixture"),
            dict(requested_units=D(0)),
            dict(requested_units=D("NaN")),
            dict(requested_units=0.5),
            dict(created_at_ms=T + 0.5),
            dict(effect="OPEN"),
            dict(side="BUY"),
        ):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                replace(entry(), **changes)
        for kw in (
            dict(kind="FILL"),
            dict(filled_units=D("1")),
            dict(event_at_ms="yesterday"),
            dict(event_id="unsafe-id"),
        ):
            with self.subTest(kw=kw), self.assertRaises(DataValidationError):
                replace(event("ack", PaperOrderEventKind.ACKNOWLEDGED), **kw)
        with self.assertRaises(DataValidationError):
            event("bad", PaperOrderEventKind.FILL, 1, "0")
        with self.assertRaises(DataValidationError):
            replay_paper_order(entry(), (object(),), as_of_ms=T + 10)

    def test_paper_replay_cannot_touch_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            outcome = replay([event("ack", PaperOrderEventKind.ACKNOWLEDGED)])
        self.assertFalse(outcome.orders_sent)
        self.assertFalse(outcome.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
