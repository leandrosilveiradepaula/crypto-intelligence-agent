"""J4/PRE1: offline reference & adversarial synthetic percentage math.

No exchange client, account, order, execution prices, live fills or market data.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, MAX_TRANCHES, SyntheticExitAllocation, SyntheticExitPlan,
    SyntheticExitTranche, plan_synthetic_partial_exits,
)

I, R, D = ExitBasis.INITIAL_POSITION, ExitBasis.REMAINING_BALANCE, Decimal


def tranche(percent, basis=R):
    return SyntheticExitTranche(basis, D(str(percent)))


def schedule(*rows, initial="100", floor="0"):
    return plan_synthetic_partial_exits(SyntheticExitPlan(
        initial_units=D(str(initial)), tranches=tuple(rows),
        residual_floor_percent=D(str(floor)),
    ))


class SyntheticPartialExitsTests(unittest.TestCase):
    def test_required_50_60_70_of_remaining_reserves_six_percent(self):
        result = schedule(tranche(50), tranche(60), tranche(70))
        self.assertEqual(
            [x.exit_units for x in result.allocations],
            [D("50"), D("30"), D("14")],
        )
        self.assertEqual(result.remaining_units, D("6"))
        self.assertEqual(result.exited_total_units, D("94"))
        self.assertEqual(result.exited_total_units + result.remaining_units, D("100"))

    def test_initial_percent_never_applies_to_remaining(self):
        result = schedule(tranche(20, I), tranche(30, I), tranche(10, I))
        self.assertEqual([x.exit_units for x in result.allocations],
                         [D("20"), D("30"), D("10")])
        self.assertEqual(result.remaining_units, D("40"))

    def test_mixed_basis_has_exact_reference_results(self):
        r = schedule(tranche(25, I), tranche(50, R), tranche(10, I))
        self.assertEqual([s.exit_units for s in r.allocations],
                         [D("25"), D("37.5"), D("10")])
        self.assertEqual(r.remaining_units, D("27.5"))
        self.assertEqual(r.allocations[1].remaining_before_units, D("75"))
        self.assertEqual(r.allocations[2].remaining_before_units, D("37.5"))

    def test_reference_remaining_differs_from_initial(self):
        initial = schedule(tranche(50, I), tranche(25, I))
        balance = schedule(tranche(50, R), tranche(25, R))
        self.assertEqual(initial.remaining_units, D(25))
        self.assertEqual(balance.remaining_units, D("37.5"))

    def test_runner_floor_is_percent_of_original_not_current(self):
        result = schedule(tranche(50), tranche(60), tranche(70), floor="6")
        self.assertEqual(result.residual_floor_units, D("6"))
        self.assertEqual(result.remaining_units, result.residual_floor_units)
        self.assertFalse(result.approved_for_live_execution)

    def test_runner_floor_cannot_be_violated_or_silently_clipped(self):
        with self.assertRaisesRegex(DataValidationError, "runner reserve"):
            schedule(tranche(50), tranche(60), tranche(70), floor="7")
        with self.assertRaisesRegex(DataValidationError, "runner reserve"):
            schedule(tranche(99.999999, I), floor="0.000002")
        with self.assertRaisesRegex(DataValidationError, "runner reserve"):
            schedule(tranche(100, R), floor="1")

    def test_all_initial_percent_sum_over_one_hundred_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "exceed remaining"):
            schedule(tranche(60, I), tranche(50, I))
        with self.assertRaisesRegex(DataValidationError, "exceed remaining"):
            schedule(tranche(100, I), tranche(1, I))

    def test_zero_remainder_cannot_receive_another_exit(self):
        with self.assertRaises(DataValidationError):
            schedule(tranche(100, R), tranche(1, R))
        complete = schedule(tranche(100, R))
        self.assertEqual(complete.remaining_units, D(0))
        self.assertEqual(complete.exited_total_units, D("100"))

    def test_first_exit_could_be_the_entire_position(self):
        complete = schedule(tranche(100, I), initial="0.000000000001")
        self.assertEqual(complete.remaining_units, D(0))
        self.assertEqual(complete.exited_total_units, D("0.000000000001"))

    def test_tiny_fraction_has_exact_decimal_no_lot_quantization(self):
        result = schedule(tranche("0.000001", I), initial="0.000000000001")
        self.assertEqual(result.allocations[0].exit_units, D("0.00000000000000000001"))
        self.assertEqual(result.remaining_units + result.exited_total_units, result.initial_units)
        self.assertFalse(result.exchange_lot_size_verified)

    def test_conservation_and_monotonicity_at_each_step(self):
        rows = [tranche("0.000001", R)]*MAX_TRANCHES
        result = schedule(*rows, initial="987654321.123456789", floor="0")
        prev = result.initial_units
        cumulative = D(0)
        for i, allocation in enumerate(result.allocations, start=1):
            self.assertEqual(allocation.step_number, i)
            self.assertEqual(allocation.remaining_before_units, prev)
            self.assertGreater(allocation.exit_units, 0)
            self.assertGreater(allocation.remaining_after_units, 0)
            self.assertLess(allocation.remaining_after_units, prev)
            cumulative += allocation.exit_units
            self.assertEqual(cumulative, allocation.exited_cumulative_units)
            self.assertEqual(allocation.remaining_after_units + cumulative,
                             result.initial_units)
            prev = allocation.remaining_after_units
        self.assertEqual(result.remaining_units, prev)

    def test_no_early_roundoff_changes_conservation_or_runner(self):
        rows = [tranche("33.333333", R)] * 20
        result = schedule(*rows, initial="111.987654321098765432",
                          floor="0.000001")
        self.assertEqual(result.exited_total_units + result.remaining_units,
                         result.initial_units)
        self.assertGreater(result.remaining_units, result.residual_floor_units)

    def test_precision_does_not_depend_on_global_decimal_context(self):
        rows = (tranche("25.123456", R), tranche("13.210987", R),
                tranche("1.234567", I))
        with localcontext() as ctx:
            ctx.prec = 3
            small = schedule(*rows, initial="98.12345678901")
        with localcontext() as ctx:
            ctx.prec = 200
            large = schedule(*rows, initial="98.12345678901")
        self.assertEqual(small, large)
        self.assertEqual(small.initial_units, small.remaining_units + small.exited_total_units)

    def test_replay_deterministic_no_time_or_price_inputs(self):
        rows = (tranche("25", R), tranche("12.5", I), tranche("7", R))
        self.assertEqual(schedule(*rows), schedule(*rows))
        result = schedule(*rows)
        for prohibited in ("price", "market", "exchange", "pnl", "funding",
                           "leverage", "liquidation", "order_id", "filled_at"):
            self.assertFalse(hasattr(result, prohibited))

    def test_immutable_typed_output_cannot_authorize_execution(self):
        res = schedule(tranche(10, R))
        self.assertEqual(res.quality, "synthetic_percentage_research_only")
        self.assertFalse(res.orders_sent)
        self.assertFalse(res.position_accounting_verified)
        self.assertFalse(res.approved_for_live_execution)
        self.assertTrue(all(not x.order_capable for x in res.allocations))
        self.assertIsInstance(res.allocations[0], SyntheticExitAllocation)
        with self.assertRaises(FrozenInstanceError):
            res.remaining_units = D(0)
        with self.assertRaises(FrozenInstanceError):
            res.allocations[0].exit_units = D(0)
        for field in ("orders_sent", "approved_for_live_execution",
                      "exchange_lot_size_verified", "position_accounting_verified"):
            with self.subTest(field=field), self.assertRaises(TypeError):
                replace(res, **{field: True})
        with self.assertRaises(TypeError):
            replace(res.allocations[0], order_capable=True)

    def test_bad_basis_is_never_implicitly_interpreted(self):
        for x in ("INITIAL_POSITION", "REMAINING_BALANCE", None, 0, False):
            with self.subTest(x=x), self.assertRaises(DataValidationError):
                SyntheticExitTranche(x, D(50))

    def test_percentage_nan_infinity_zero_negative_and_over_hundred_rejected(self):
        for x in (D("NaN"), D("Infinity"), D("-Infinity"), D(0),
                  D(-1), D("100.000001"), D("1E-7"),
                  "20", 20.0, True, None):
            with self.subTest(value=str(x)), self.assertRaises(DataValidationError):
                SyntheticExitTranche(R, x)

    def test_percentage_minimum_and_maximum_are_explicit(self):
        self.assertEqual(tranche("0.000001").percent, D("0.000001"))
        self.assertEqual(tranche("100").percent, D("100"))
        with self.assertRaises(DataValidationError):
            SyntheticExitTranche(R, D("50.0000001"))

    def test_bad_runner_floor_values_are_rejected(self):
        for x in (D("-1"), D(100), D("100.000001"), D("NaN"),
                  D("Infinity"), D("0.0000001"), 1, "50", True, None):
            with self.subTest(value=str(x)), self.assertRaises(DataValidationError):
                SyntheticExitPlan(D(100), (tranche(10),), x)
        self.assertEqual(schedule(tranche(10), floor="0").residual_floor_units, D(0))

    def test_initial_requires_positive_bounded_decimal_not_margin(self):
        for x in (D(0), D(-1), D("NaN"), D("Infinity"), D("1E-19"),
                  D("1E+25"), D("1.1234567890123456789"),
                  D("12345678901234567890123456789012345678901"),
                  "5", 5.0, True, None):
            with self.subTest(value=str(x)), self.assertRaises(DataValidationError):
                SyntheticExitPlan(x, (tranche(50),))
        self.assertEqual(schedule(tranche(10), initial="0.000000000000000001").initial_units,
                         D("0.000000000000000001"))

    def test_plan_requires_bounded_immutable_nonempty_tranches(self):
        for x in ([], (), None, (tranche(10),)* (MAX_TRANCHES + 1),
                  ({"basis": R, "percent": D(10)},), (tranche(10), "bad")):
            with self.subTest(x=str(type(x))), self.assertRaises(DataValidationError):
                SyntheticExitPlan(D(100), x)
        with self.assertRaises(DataValidationError):
            plan_synthetic_partial_exits({"initial_units": D(100)})

    def test_tranche_and_plan_are_immutable(self):
        plan = SyntheticExitPlan(D(100), (tranche(30),))
        with self.assertRaises(FrozenInstanceError):
            plan.initial_units = D(200)
        with self.assertRaises(FrozenInstanceError):
            plan.tranches[0].percent = D(99)

    def test_valid_runner_can_stop_before_residual_floor(self):
        result = schedule(tranche(50, I), tranche(25, R), floor="10")
        self.assertEqual(result.remaining_units, D("37.5"))
        self.assertGreater(result.remaining_units, result.residual_floor_units)

    def test_mixed_100_percent_remaining_only_when_no_floor(self):
        schedule(tranche(10, I), tranche(100, R))
        with self.assertRaises(DataValidationError):
            schedule(tranche(10, I), tranche(100, R), floor="0.1")

    def test_ordering_changes_result_without_reordering(self):
        first = schedule(tranche(30, I), tranche(50, R))
        second = schedule(tranche(50, R), tranche(30, I))
        self.assertEqual(first.remaining_units, D(35))
        self.assertEqual(second.remaining_units, D(20))
        self.assertNotEqual(first.remaining_units, second.remaining_units)

    def test_resource_bound_is_not_fixed_position_count(self):
        lots = [tranche(1, R) for _ in range(MAX_TRANCHES)]
        self.assertEqual(len(schedule(*lots).allocations), MAX_TRANCHES)
        with self.assertRaises(DataValidationError):
            schedule(*(lots + [tranche(1, R)]))

    def test_module_has_no_trading_or_network_client_imports(self):
        source = (Path(__file__).resolve().parent.parent
                  / "crypto_intelligence_agent/synthetic_partial_exits.py").read_text()
        for forbidden in ("urllib.request", "requests.", "api.hyperliquid.xyz",
                          "futures.kraken.com", "create_order(", "send_order(",
                          "import sqlite3", "open("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
