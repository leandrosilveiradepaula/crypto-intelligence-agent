"""PRE4 hypothetical lot-step unit tests; every value is synthetic."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_manual_exit_replay import (
    SyntheticManualExitEvent,
)
from crypto_intelligence_agent.synthetic_position_state import (
    SyntheticLeverageSettings, SyntheticPositionExitFill,
    SyntheticSide, open_synthetic_position,
)
from crypto_intelligence_agent.synthetic_lot_feasibility import (
    SyntheticLotFixture, SyntheticLotFeasibility,
    SyntheticTrancheLotCheck, SyntheticFillLotCheck,
    assess_synthetic_lot_feasibility,
)

D = Decimal
START = 1_800_000_000_000
NOW = START + 20_000
R = ExitBasis.REMAINING_BALANCE
I = ExitBasis.INITIAL_POSITION


def synthetic_plan(initial="100", floor="6", steps=None):
    if steps is None:
        steps = [(R, "50"), (R, "60"), (R, "70")]
    return SyntheticExitPlan(
        initial_units=D(str(initial)),
        tranches=tuple(SyntheticExitTranche(basis, D(str(pct)))
                       for basis, pct in steps),
        residual_floor_percent=D(str(floor)),
    )


def fixture_position(initial="100", floor="6", steps=None, id="fixture_BTC"):
    return open_synthetic_position(
        fixture_position_id=id, side=SyntheticSide.LONG,
        opened_at_ms=START,
        exit_plan=synthetic_plan(initial, floor, steps),
        synthetic_margin_units=D("3"),
        settings=SyntheticLeverageSettings(),
    )


def fictitious_fill(id="evt_1", step=1, units="10",
                    position_id="fixture_BTC", at=START+1):
    return SyntheticPositionExitFill(
        position_id,
        SyntheticManualExitEvent(id, step, D(str(units)), at),
    )


def lot(step="2", min_exit="1", min_remaining="0"):
    return SyntheticLotFixture(
        size_step_units=D(str(step)),
        minimum_exit_units=D(str(min_exit)),
        minimum_nonzero_remaining_units=D(str(min_remaining)),
    )


def assess(pos=None, rule=None, events=(), at=NOW):
    return assess_synthetic_lot_feasibility(
        fixture_position() if pos is None else pos,
        lot() if rule is None else rule,
        events, as_of_ms=at,
    )


class SyntheticLotFeasibilityTests(unittest.TestCase):
    def test_reference_50_60_70_runner_six_matches_two_unit_step(self):
        out = assess(rule=lot(step="2", min_exit="5", min_remaining="6"))
        self.assertIsInstance(out, SyntheticLotFeasibility)
        self.assertTrue(out.arithmetically_compatible)
        self.assertEqual(out.initial_units, D(100))
        self.assertEqual(out.planned_remaining_units, D(6))
        self.assertEqual(out.current_remaining_units, D(100))
        self.assertEqual(
            [x.planned_units for x in out.tranche_checks],
            [D(50), D(30), D(14)],
        )
        self.assertTrue(all(isinstance(x, SyntheticTrancheLotCheck)
                            for x in out.tranche_checks))
        self.assertEqual(out.fill_checks, ())
        self.assertEqual(out.unique_event_count, 0)
        self.assertFalse(out.approved_for_live_use)
        self.assertFalse(out.venue_lot_step_verified)

    def test_full_fictitious_fills_preserve_runner_and_lot_math(self):
        events = (
            fictitious_fill("one", 1, "50"),
            fictitious_fill("two", 2, "30", at=START+2),
            fictitious_fill("three", 3, "14", at=START+3),
        )
        out = assess(rule=lot("2", "2", "6"), events=events)
        self.assertTrue(out.arithmetically_compatible)
        self.assertEqual(out.current_remaining_units, D(6))
        self.assertEqual(out.unique_event_count, 3)
        self.assertTrue(all(x.exact_step_multiple for x in out.fill_checks))

    def test_incompatible_planned_tranche_is_flagged_no_clipping(self):
        out = assess(rule=lot(step="4", min_exit="1"))
        self.assertFalse(out.arithmetically_compatible)
        self.assertEqual([x.planned_units for x in out.tranche_checks],
                         [D(50), D(30), D(14)])
        self.assertEqual([x.exact_step_multiple for x in out.tranche_checks],
                         [False, False, False])
        self.assertEqual(out.planned_remaining_units, D(6))

    def test_initial_size_must_match_step_without_conversion(self):
        pos = fixture_position(initial="101", floor="6")
        out = assess(pos=pos, rule=lot("2"))
        self.assertFalse(out.initial_step_multiple)
        self.assertFalse(out.arithmetically_compatible)
        self.assertEqual(out.initial_units, D(101))

    def test_min_exit_threshold_is_per_planned_tranche(self):
        out = assess(rule=lot(step="2", min_exit="20"))
        self.assertFalse(out.arithmetically_compatible)
        self.assertTrue(out.tranche_checks[0].meets_fixture_exit_minimum)
        self.assertTrue(out.tranche_checks[1].meets_fixture_exit_minimum)
        self.assertFalse(out.tranche_checks[2].meets_fixture_exit_minimum)
        self.assertEqual(out.tranche_checks[2].planned_units, D(14))

    def test_residual_floor_may_be_below_minimum_even_when_venue_step_matches(self):
        out = assess(rule=lot(step="2", min_exit="1", min_remaining="7"))
        self.assertTrue(out.planned_remaining_step_multiple)
        self.assertFalse(out.planned_remaining_minimum_ok)
        self.assertFalse(out.arithmetically_compatible)
        self.assertTrue(out.current_remaining_minimum_ok)

    def test_nonzero_current_balance_must_match_step(self):
        e = fictitious_fill("part", 1, "1")
        out = assess(rule=lot("2"), events=(e,))
        self.assertFalse(out.current_remaining_step_multiple)
        self.assertFalse(out.fill_checks[0].exact_step_multiple)
        self.assertFalse(out.arithmetically_compatible)
        self.assertEqual(out.current_remaining_units, D(99))

    def test_two_invalid_parts_cannot_be_approved_by_compatible_sum(self):
        events = (
            fictitious_fill("one", 1, "25"),
            fictitious_fill("two", 1, "25", at=START+2),
        )
        out = assess(rule=lot("2", "1"), events=events)
        self.assertEqual(out.current_remaining_units, D(50))
        self.assertTrue(out.current_remaining_step_multiple)
        self.assertFalse(out.arithmetically_compatible)
        self.assertEqual([x.exact_step_multiple for x in out.fill_checks],
                         [False, False])

    def test_partially_filled_amount_can_be_on_step_and_above_minimum(self):
        e = fictitious_fill("one", 1, "20")
        out = assess(rule=lot("2", "10"), events=(e,))
        self.assertTrue(out.arithmetically_compatible)
        self.assertEqual(out.current_remaining_units, D(80))
        self.assertEqual(out.fill_checks[0].filled_units, D(20))

    def test_individual_partials_below_minimum_are_not_hid_by_later_fill(self):
        events = (
            fictitious_fill("one", 1, "2"),
            fictitious_fill("two", 1, "48", at=START+2),
        )
        out = assess(rule=lot("2", "5"), events=events)
        self.assertFalse(out.fill_checks[0].meets_fixture_exit_minimum)
        self.assertTrue(out.fill_checks[1].meets_fixture_exit_minimum)
        self.assertFalse(out.arithmetically_compatible)
        self.assertEqual(out.current_remaining_units, D(50))

    def test_exact_duplicate_does_not_repeat_lot_check_or_balance(self):
        e = fictitious_fill("same", 1, "20")
        out = assess(events=(e, e, e))
        self.assertEqual(out.unique_event_count, 1)
        self.assertEqual(out.exact_duplicate_count, 2)
        self.assertEqual(len(out.fill_checks), 1)
        self.assertEqual(out.current_remaining_units, D(80))
        self.assertTrue(out.arithmetically_compatible)

    def test_duplicate_after_other_unique_event_still_not_counted(self):
        a = fictitious_fill("a", 1, "10")
        b = fictitious_fill("b", 1, "10", at=START+2)
        out = assess(events=(a, b, a))
        self.assertEqual(len(out.fill_checks), 2)
        self.assertEqual(out.unique_event_count, 2)
        self.assertEqual(out.exact_duplicate_count, 1)
        self.assertEqual([e.unique_event_ordinal for e in out.fill_checks], [1, 2])

    def test_id_conflict_fails_before_feasibility_output(self):
        with self.assertRaisesRegex(DataValidationError, "conflicting"):
            assess(events=(
                fictitious_fill("same", 1, "10"),
                fictitious_fill("same", 1, "11"),
            ))

    def test_wrong_position_event_fails_before_feasibility(self):
        with self.assertRaisesRegex(DataValidationError, "different fixture"):
            assess(events=(fictitious_fill(position_id="fixture_OTHER"),))

    def test_earlier_step_unfinished_rejected_before_math_assessment(self):
        with self.assertRaisesRegex(DataValidationError, "prior tranche"):
            assess(events=(fictitious_fill("jump", 2, "10"),))

    def test_overfill_rejected_even_when_multiple_of_lot_step(self):
        with self.assertRaisesRegex(DataValidationError, "exceeds allocated"):
            assess(events=(fictitious_fill("big", 1, "52"),))

    def test_event_after_as_of_or_before_open_fails(self):
        with self.assertRaises(DataValidationError):
            assess(events=(fictitious_fill(at=START-1),))
        with self.assertRaises(DataValidationError):
            assess(events=(fictitious_fill(at=NOW+1),))

    def test_zero_residual_allows_full_close_without_remaining_minimum(self):
        pos = fixture_position(floor="0", steps=[(R, "100")])
        out = assess(pos=pos, rule=lot(step="2", min_exit="1", min_remaining="20"),
                     events=(fictitious_fill("close", 1, "100"),))
        self.assertTrue(out.arithmetically_compatible)
        self.assertEqual(out.planned_remaining_units, D(0))
        self.assertEqual(out.current_remaining_units, D(0))
        self.assertTrue(out.planned_remaining_minimum_ok)
        self.assertTrue(out.current_remaining_minimum_ok)

    def test_current_residual_minimum_can_be_violated_by_partial(self):
        pos = fixture_position(floor="0", steps=[(R, "100")])
        out = assess(pos=pos, rule=lot(step="2", min_exit="1", min_remaining="10"),
                     events=(fictitious_fill("p", 1, "98"),))
        self.assertFalse(out.current_remaining_minimum_ok)
        self.assertTrue(out.planned_remaining_minimum_ok)
        self.assertEqual(out.current_remaining_units, D(2))

    def test_no_rounding_or_tolerance_for_fractional_step(self):
        pos = fixture_position(initial="1", floor="0", steps=[(R, "50")])
        a = assess(pos=pos, rule=lot(step="0.1", min_exit="0.1"),
                   events=(fictitious_fill("one", 1, "0.3"),))
        self.assertTrue(a.arithmetically_compatible)
        b = assess(pos=pos, rule=lot(step="0.3", min_exit="0.1"),
                   events=(fictitious_fill("one", 1, "0.3"),))
        self.assertFalse(b.arithmetically_compatible)
        self.assertEqual(b.tranche_checks[0].planned_units, D("0.5"))
        self.assertFalse(b.tranche_checks[0].exact_step_multiple)

    def test_extremely_small_decimal_step_is_exact_not_float(self):
        pos = fixture_position(initial="0.000000000000000001", floor="0",
                               steps=[(R, "50")])
        out = assess(pos=pos, rule=lot(step="0.0000000000000000005",
                                      min_exit="0.0000000000000000005"))
        # Fixture rules intentionally limit step scale to 18 decimals.
        self.assertFalse(out.arithmetically_compatible)

    def test_reject_more_than_eighteen_decimal_places_in_fixture_rule(self):
        with self.assertRaises(DataValidationError):
            lot(step="0.0000000000000000001")
        with self.assertRaises(DataValidationError):
            lot(min_exit="0.0000000000000000001")

    def test_rule_type_nan_inf_zero_negative_and_bounds_fail_closed(self):
        for bad in (D(0), D(-1), D("NaN"), D("Infinity"),
                    D("-Infinity"), D("1E-19"), D("1E25"),
                    D("1"*41), 2, 2.0, True, "2", None):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(DataValidationError):
                SyntheticLotFixture(bad, D(1))
        for bad in (D(0), D("-1"), D("NaN"), D("Infinity"),
                    D("1E-19"), D("1E25"), "1", 1, False):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(DataValidationError):
                SyntheticLotFixture(D(1), bad)

    def test_optional_zero_minimum_requires_bounded_decimal(self):
        self.assertEqual(lot(min_remaining="0").minimum_nonzero_remaining_units, D(0))
        for bad in (D(-1), D("NaN"), D("Infinity"), D("1E-19"),
                    D("1E25"), False, "0", None):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(DataValidationError):
                SyntheticLotFixture(D(1), D(1), bad)

    def test_exact_precision_independent_of_global_decimal_context(self):
        pos = fixture_position(initial="98.123456789012345678", floor="0",
                               steps=[(R, "12.345678")])
        rule = lot(step="0.000001", min_exit="0.000001", min_remaining="0")
        with localcontext() as c:
            c.prec = 3
            low = assess(pos=pos, rule=rule)
        with localcontext() as c:
            c.prec = 600
            high = assess(pos=pos, rule=rule)
        self.assertEqual(low, high)

    def test_all_safety_flags_and_compatibility_are_non_overridable(self):
        result = assess()
        self.assertTrue(result.arithmetically_compatible)
        self.assertEqual(result.quality, "synthetic_lot_rule_fixture_only")
        for name in ("venue_lot_step_verified", "approved_for_live_use", "orders_sent",
                     "collateral_currency_verified", "external_rights_verified",
                     "persistent_idempotency_verified"):
            self.assertIs(getattr(result, name), False)
            with self.subTest(name=name), self.assertRaises(TypeError):
                replace(result, **{name: True})
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(result, name, True)
        for name in ("quality", "arithmetically_compatible"):
            with self.assertRaises(TypeError):
                replace(result, **{name: "live"})
        with self.assertRaises(FrozenInstanceError):
            result.initial_units = D(123)
        with self.assertRaises(FrozenInstanceError):
            result.tranche_checks[0].planned_units = D(123)

    def test_fixture_does_not_accept_verified_real_venue_claim(self):
        rule = lot()
        self.assertFalse(rule.venue_contract_verified)
        with self.assertRaises(TypeError):
            replace(rule, venue_contract_verified=True)
        with self.assertRaises(FrozenInstanceError):
            rule.size_step_units = D(1)

    def test_inputs_exact_types_required(self):
        with self.assertRaises(DataValidationError):
            assess_synthetic_lot_feasibility({}, lot(), as_of_ms=NOW)
        with self.assertRaises(DataValidationError):
            assess_synthetic_lot_feasibility(fixture_position(), {}, as_of_ms=NOW)
        with self.assertRaises(DataValidationError):
            assess_synthetic_lot_feasibility(fixture_position(), lot(), [], as_of_ms=NOW)

    def test_no_venue_data_or_network_dependencies(self):
        source = (Path(__file__).resolve().parent.parent
                  / "crypto_intelligence_agent/synthetic_lot_feasibility.py").read_text()
        for forbidden in ("urllib.request", "requests.", "open(", "sqlite3",
                          "create_order(", "send_order(", "api.hyperliquid.xyz",
                          "futures.kraken.com", "subprocess", "socket"):
            self.assertNotIn(forbidden, source)
        out = assess()
        for field in ("price", "pnl", "currency", "contract_multiplier",
                      "real_instrument", "venue_min_notional", "trade_id",
                      "margin", "leverage", "funding"):
            self.assertFalse(hasattr(out, field))


if __name__ == "__main__":
    unittest.main()
