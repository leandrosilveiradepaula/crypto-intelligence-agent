"""J4/PRE2: immutable, no-network fixture replay with explicit limitations."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_manual_exit_replay import (
    MAX_FIXTURE_EVENTS, SyntheticManualExitEvent, SyntheticManualExitReplay,
    replay_synthetic_manual_exits,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
    plan_synthetic_partial_exits,
)


D = Decimal
NOW = 1_800_000_000_000
START = NOW - 10_000


def plan(*steps, initial="100", floor="6"):
    if not steps:
        steps = ((50, ExitBasis.REMAINING_BALANCE),
                 (60, ExitBasis.REMAINING_BALANCE),
                 (70, ExitBasis.REMAINING_BALANCE))
    return SyntheticExitPlan(
        initial_units=D(str(initial)),
        tranches=tuple(SyntheticExitTranche(b, D(str(p))) for p, b in steps),
        residual_floor_percent=D(str(floor)),
    )


def event(id, step, qty, when=START+1):
    return SyntheticManualExitEvent(
        event_id=id, tranche_step=step,
        filled_units=D(str(qty)), event_at_ms=when,
    )


def replay(events=(), *, p=None, created=START, as_of=NOW):
    return replay_synthetic_manual_exits(
        plan() if p is None else p, events,
        plan_created_at_ms=created, as_of_ms=as_of,
    )


class SyntheticManualExitReplayTests(unittest.TestCase):
    def test_no_events_mean_no_fills_and_no_implicit_position_change(self):
        r = replay()
        self.assertIsInstance(r, SyntheticManualExitReplay)
        self.assertEqual(r.initial_units, D(100))
        self.assertEqual(r.filled_total_units, D(0))
        self.assertEqual(r.remaining_units, D(100))
        self.assertEqual(r.residual_floor_units, D(6))
        self.assertEqual([p.planned_units for p in r.progress],
                         [D(50), D(30), D(14)])
        self.assertTrue(all(p.filled_units == 0 for p in r.progress))
        self.assertIsNone(r.latest_unique_event_at_ms)

    def test_required_50_60_70_remaining_and_six_percent_runner(self):
        r = replay((
            event("evt1", 1, 50), event("evt2", 2, 30, START+2),
            event("evt3", 3, 14, START+3),
        ))
        self.assertEqual(r.filled_total_units, D(94))
        self.assertEqual(r.remaining_units, D(6))
        self.assertEqual(r.remaining_units, r.residual_floor_units)
        self.assertTrue(all(p.outstanding_units == 0 for p in r.progress))
        self.assertEqual(r.unique_event_count, 3)
        self.assertEqual(r.latest_unique_event_at_ms, START+3)

    def test_partial_fill_only_changes_actual_filled_balance(self):
        r = replay((event("p1", 1, 30),))
        self.assertEqual(r.filled_total_units, D(30))
        self.assertEqual(r.remaining_units, D(70))
        self.assertEqual(r.progress[0].filled_units, D(30))
        self.assertEqual(r.progress[0].outstanding_units, D(20))
        self.assertEqual(r.progress[1].outstanding_units, D(30))
        self.assertEqual(r.progress[2].outstanding_units, D(14))

    def test_two_partial_events_fill_one_tranche_then_next(self):
        r = replay((
            event("a", 1, 30), event("b", 1, 20, START+2),
            event("c", 2, 10, START+3),
        ))
        self.assertEqual(r.filled_total_units, D(60))
        self.assertEqual(r.remaining_units, D(40))
        self.assertEqual(r.progress[0].outstanding_units, D(0))
        self.assertEqual(r.progress[1].outstanding_units, D(20))
        self.assertEqual(r.unique_event_count, 3)

    def test_idempotent_exact_duplicate_counted_once(self):
        a = event("same", 1, 30)
        r = replay((a, a, a))
        self.assertEqual(r.filled_total_units, D(30))
        self.assertEqual(r.remaining_units, D(70))
        self.assertEqual(r.unique_event_count, 1)
        self.assertEqual(r.exact_duplicate_count, 2)

    def test_duplicate_replayed_after_later_unique_event_is_still_ignored(self):
        a = event("original", 1, 30)
        b = event("second", 1, 20, START+3)
        r = replay((a, b, a))
        self.assertEqual(r.filled_total_units, D(50))
        self.assertEqual(r.exact_duplicate_count, 1)
        self.assertEqual(r.latest_unique_event_at_ms, START+3)

    def test_same_event_id_conflicting_amount_is_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "conflicting"):
            replay((event("a", 1, 10), event("a", 1, 11)))

    def test_same_event_id_conflicting_decimal_representation_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "conflicting"):
            replay((event("a", 1, "10.0"), event("a", 1, "10")))

    def test_same_event_id_conflicting_timestamp_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "conflicting"):
            replay((event("a", 1, 10), event("a", 1, 10, START+5)))

    def test_same_event_id_conflicting_tranche_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "conflicting"):
            replay((event("a", 1, 10), event("a", 2, 10)))

    def test_same_economic_amount_with_different_ids_is_not_detectably_duplicate(self):
        r = replay((event("a", 1, 10), event("b", 1, 10, START+2)))
        self.assertEqual(r.unique_event_count, 2)
        self.assertEqual(r.filled_total_units, D(20))
        self.assertFalse(r.persistent_idempotency_verified)

    def test_cannot_jump_to_later_tranche_before_earlier_done(self):
        with self.assertRaisesRegex(DataValidationError, "prior tranche"):
            replay((event("early", 2, 1),))
        with self.assertRaisesRegex(DataValidationError, "prior tranche"):
            replay((event("p1", 1, 30), event("p2", 2, 1, START+2)))

    def test_cannot_overfill_planned_tranche(self):
        with self.assertRaisesRegex(DataValidationError, "exceeds allocated"):
            replay((event("too_large", 1, 51),))
        with self.assertRaisesRegex(DataValidationError, "exceeds allocated"):
            replay((event("a", 1, 30), event("b", 1, 21, START+2)))

    def test_cannot_add_fills_after_all_targets_are_complete(self):
        with self.assertRaises(DataValidationError):
            replay((
                event("one", 1, 50),
                event("two", 2, 30, START+2),
                event("three", 3, 14, START+3),
                event("extra", 3, 1, START+4),
            ))

    def test_cannot_reference_nonexistent_or_noninteger_tranche(self):
        with self.assertRaisesRegex(DataValidationError, "absent"):
            replay((event("x", 4, 1),))
        for val in (0, 65, True, 1.25, "1", None):
            with self.subTest(step=val), self.assertRaises(DataValidationError):
                SyntheticManualExitEvent("a", val, D(1), START+1)

    def test_chronological_unique_events_required(self):
        with self.assertRaisesRegex(DataValidationError, "chronological"):
            replay((event("a", 1, 10, START+5), event("b", 1, 10, START+2)))
        same_time = replay((event("a", 1, 10), event("b", 1, 20)))
        self.assertEqual(same_time.filled_total_units, D(30))

    def test_event_before_plan_or_after_as_of_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "outside"):
            replay((event("before", 1, 10, START-1),))
        with self.assertRaisesRegex(DataValidationError, "outside"):
            replay((event("future", 1, 10, NOW+1),))
        self.assertEqual(replay((event("on_plan", 1, 10, START),)).unique_event_count, 1)

    def test_invalid_plan_window_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "precedes"):
            replay(created=NOW, as_of=NOW-1)
        for value in (0, -1, True, None, "now", 1.5, 253_402_300_800_000):
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                replay(created=value)
            with self.subTest(asof=value), self.assertRaises(DataValidationError):
                replay(as_of=value)

    def test_id_must_be_bounded_ascii_and_is_not_reported(self):
        for val in ("", "a"*49, "space here", "a.b", "a/b", "évent", "🧪",
                    "secret@example.org", None, True, 123):
            with self.subTest(value=val), self.assertRaises(DataValidationError):
                SyntheticManualExitEvent(val, 1, D(10), START+1)
        result = replay((event("privateFixture", 1, 10),))
        self.assertFalse(hasattr(result, "event_id"))
        self.assertNotIn("privateFixture", repr(result))

    def test_quantity_accepts_exact_synthetic_decimal_not_float_nan_or_zero(self):
        for bad in (D(0), D(-1), D("NaN"), D("Infinity"),
                    D("1E-601"), D("1E+25"), D("1"*641),
                    "10", 10.0, True, None):
            with self.subTest(value=str(bad)[:40]), self.assertRaises(DataValidationError):
                SyntheticManualExitEvent("a", 1, bad, START+1)

    def test_bounds_must_use_immutable_tuple_not_generator(self):
        with self.assertRaises(DataValidationError):
            replay([event("a", 1, 10)])
        with self.assertRaises(DataValidationError):
            replay((e for e in (event("a", 1, 10),)))
        with self.assertRaises(DataValidationError):
            replay(({"id": "a", "fill": D(10)},))
        with self.assertRaises(DataValidationError):
            replay((event("a", 1, 10),) * (MAX_FIXTURE_EVENTS+1))
        with self.assertRaises(DataValidationError):
            replay((), p={"plan": "invalid"})

    def test_deterministic_replay_and_no_time_inference(self):
        history = (event("a", 1, 25), event("b", 1, 25, START+2))
        self.assertEqual(replay(history), replay(history))
        self.assertEqual(replay(history).as_of_ms, NOW)
        self.assertEqual(replay(history).plan_created_at_ms, START)

    def test_many_partial_events_complete_one_tranche_without_rounding(self):
        p = plan((100, ExitBasis.REMAINING_BALANCE), floor="0")
        quantity = D("0.1953125")  # 100 / 512 exactly
        events = tuple(event(f"e{i}", 1, quantity, START+i) for i in range(MAX_FIXTURE_EVENTS))
        result = replay(events, p=p)
        self.assertEqual(result.filled_total_units, D("100"))
        self.assertEqual(result.remaining_units, D(0))
        self.assertEqual(result.unique_event_count, MAX_FIXTURE_EVENTS)

    def test_replay_is_independent_of_global_decimal_precision(self):
        p = plan((12.345678, ExitBasis.REMAINING_BALANCE),
                 (23.456789, ExitBasis.INITIAL_POSITION), floor="2")
        target = plan_synthetic_partial_exits(p).allocations[0].exit_units
        with localcontext() as ctx:
            ctx.prec = 800
            a = D("0.00000000000000000000001")
            remainder = target - a
        events = (event("a", 1, a), event("b", 1, remainder, START+2))
        with localcontext() as ctx:
            ctx.prec = 3
            first = replay(events, p=p)
        with localcontext() as ctx:
            ctx.prec = 500
            second = replay(events, p=p)
        self.assertEqual(first, second)
        with localcontext() as ctx:
            ctx.prec = 2048
            self.assertEqual(first.filled_total_units + first.remaining_units, p.initial_units)

    def test_immutability_flags_and_origin_cannot_be_overridden(self):
        res = replay((event("a", 1, 10),))
        self.assertEqual(res.quality, "synthetic_fixture_only")
        self.assertFalse(res.orders_sent)
        self.assertFalse(res.approved_for_live_use)
        self.assertFalse(res.persistent_idempotency_verified)
        self.assertFalse(res.venue_lot_units_verified)
        with self.assertRaises(FrozenInstanceError):
            res.remaining_units = D(0)
        with self.assertRaises(FrozenInstanceError):
            res.progress[0].filled_units = D(500)
        with self.assertRaises(FrozenInstanceError):
            res.quality = "live"
        for field in ("orders_sent", "approved_for_live_use",
                      "persistent_idempotency_verified", "venue_lot_units_verified",
                      "quality"):
            with self.subTest(field=field), self.assertRaises(TypeError):
                replace(res, **{field: True})
        evt = event("a", 1, 10)
        with self.assertRaises(FrozenInstanceError):
            evt.filled_units = D(11)

    def test_plan_cannot_be_changed_silently_to_accept_overfill(self):
        tighter = plan((20, ExitBasis.INITIAL_POSITION), floor="0")
        looser = plan((30, ExitBasis.INITIAL_POSITION), floor="0")
        original = (event("a", 1, 25),)
        with self.assertRaisesRegex(DataValidationError, "exceeds allocated"):
            replay(original, p=tighter)
        self.assertEqual(replay(original, p=looser).filled_total_units, D(25))
        self.assertFalse(replay(original, p=looser).persistent_idempotency_verified)

    def test_reserve_floor_applies_after_actual_not_unfilled_planned(self):
        r = replay((event("a", 1, 45), event("b", 1, 5, START+2)))
        self.assertEqual(r.remaining_units, D(50))
        self.assertGreater(r.remaining_units, r.residual_floor_units)
        self.assertEqual(r.progress[2].planned_units, D(14))
        self.assertEqual(r.progress[2].filled_units, D(0))

    def test_stress_replay_of_64_planned_steps_exact(self):
        steps = ((1, ExitBasis.REMAINING_BALANCE),)*64
        p = plan(*steps, floor="0")
        allocations = plan_synthetic_partial_exits(p).allocations
        events = tuple(event(f"e{i}", i+1, row.exit_units, START+i)
                       for i, row in enumerate(allocations))
        r = replay(events, p=p)
        self.assertEqual(r.unique_event_count, 64)
        self.assertTrue(all(x.outstanding_units == 0 for x in r.progress))
        with localcontext() as ctx:
            ctx.prec = 2048
            self.assertEqual(r.remaining_units + r.filled_total_units, r.initial_units)


    def test_metamorphic_replay_prefix_conserves_residual_after_each_fill(self):
        history = (
            event("a", 1, 25, START+1),
            event("b", 1, 25, START+2),
            event("c", 2, 15, START+3),
            event("d", 2, 15, START+4),
            event("e", 3, 14, START+5),
        )
        previous = replay(())
        for count in range(1, len(history)+1):
            with self.subTest(prefix=count):
                current = replay(history[:count])
                self.assertEqual(current.filled_total_units + current.remaining_units,
                                 current.initial_units)
                self.assertGreaterEqual(current.remaining_units,
                                        current.residual_floor_units)
                self.assertGreaterEqual(current.filled_total_units,
                                        previous.filled_total_units)
                self.assertLessEqual(current.remaining_units,
                                     previous.remaining_units)
                self.assertEqual(current.unique_event_count, count)
                previous = current
        self.assertEqual(previous.remaining_units, D(6))

    def test_metamorphic_duplicate_events_never_deplete_runner(self):
        a = event("a", 1, 50, START+1)
        b = event("b", 2, 30, START+2)
        c = event("c", 3, 14, START+3)
        baseline = replay((a, b, c))
        duplicate = replay((a, b, c, a, b, c))
        self.assertEqual(baseline.remaining_units, D(6))
        self.assertEqual(duplicate.remaining_units, baseline.remaining_units)
        self.assertEqual(duplicate.filled_total_units, baseline.filled_total_units)
        self.assertEqual(duplicate.exact_duplicate_count, 3)
        self.assertFalse(duplicate.persistent_idempotency_verified)

    def test_no_market_or_trading_dependencies(self):
        module = (Path(__file__).resolve().parent.parent
                  / "crypto_intelligence_agent/synthetic_manual_exit_replay.py")
        source = module.read_text(encoding="utf-8")
        for forbidden in ("urllib.request", "api.hyperliquid.xyz", "futures.kraken.com",
                          "create_order(", "send_order(", "import sqlite3", "open("):
            self.assertNotIn(forbidden, source)
        r = replay()
        for prohibited in ("price", "margin", "leverage", "pnl", "fees", "funding",
                           "trade_id", "order_id", "exchange"):
            self.assertFalse(hasattr(r, prohibited))


if __name__ == "__main__":
    unittest.main()
