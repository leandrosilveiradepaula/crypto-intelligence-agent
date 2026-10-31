"""J3/PRE22: independent bounded OOS sensitivity and safety regressions."""
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch
import json
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_stress_sensitivity import (
    compare_costed_vision_oos_stress_scenarios,
)
from crypto_intelligence_agent.vision_stress_oos import (
    audit_costed_vision_intrabar_oos,
)
from test_vision_dynamic_replay import fixture
from test_vision_intrabar_stress import terms


class VisionStressSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = fixture("BTCUSDT")
        cls.b = fixture("ETHUSDT")
        cls.cutoff = cls.a[-1].end_open_exclusive_ms + 3_600_000

    def run_grid(self, grid=None, groups=None):
        return compare_costed_vision_oos_stress_scenarios(
            groups if groups is not None else (self.a, self.b),
            as_of_ms=self.cutoff, cost_bps_per_side=D("0"),
            assumptions_grid=grid if grid is not None else (terms(1), terms(50)),
        )

    def test_fixed_selection_different_leverages_numerical_reconciliation(self):
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            a = self.run_grid()
            b = self.run_grid()
        self.assertEqual(a, b)
        self.assertEqual(len(a.scenarios), 2)
        self.assertEqual([x.ordinal for x in a.scenarios], [1, 2])
        self.assertEqual(
            [x.assumptions.margin.leverage_at_intent for x in a.scenarios],
            [1, 50],
        )
        for case in a.scenarios:
            result = case.audit
            expected = audit_costed_vision_intrabar_oos(
                (self.a, self.b), as_of_ms=self.cutoff,
                cost_bps_per_side=D("0"), assumptions=case.assumptions)
            self.assertEqual(result, expected)
            self.assertEqual(case.sanitized_report()["strategy_exposures"],
                             result.stressed_count)
            self.assertEqual(
                result.strategy_worst_cumulative_net_over_margin,
                result.worst_net_quote / case.assumptions.margin.requested_margin_quote)
            for fold in result.fold_reports:
                self.assertEqual(
                    fold.strategy_worst_cumulative_net_over_margin,
                    fold.strategy_worst_net_quote / case.assumptions.margin.requested_margin_quote)
        x, y = a.scenarios
        self.assertEqual(
            [(f.test_month_number, f.bars_scored, f.strategy_exposures,
              f.strategy_abstention_count) for f in x.audit.fold_reports],
            [(f.test_month_number, f.bars_scored, f.strategy_exposures,
              f.strategy_abstention_count) for f in y.audit.fold_reports])
        self.assertEqual(x.audit.stressed_count, y.audit.stressed_count)
        self.assertLessEqual(x.audit.liquidation_possible_count,
                             x.audit.stressed_count)
        self.assertLessEqual(y.audit.liquidation_possible_count,
                             y.audit.stressed_count)
        payload = a.sanitized_report()
        self.assertEqual(payload["schema_version"], "j3_pre22_oos_sensitivity_v1")
        self.assertEqual(payload["scenario_count"], 2)
        self.assertTrue(payload["selection_fixed_across_scenarios"])
        self.assertNotIn("best_scenario", payload)
        self.assertNotIn("recommended_leverage", payload)
        for key in ("marketwide_top50_verified", "source_authenticated",
                    "financial_backtest_approved", "net_pnl_verified",
                    "liquidation_formula_verified", "live_trading_authorized",
                    "orders_sent", "data_stored"):
            self.assertFalse(payload[key])
        self.assertEqual(payload["network_requests"], 0)
        serialized = json.dumps(payload, sort_keys=True)
        for forbidden in ("BTCUSDT", "ETHUSDT", ".sqlite", "https://", "/home/"):
            self.assertNotIn(forbidden, serialized)

    def test_same_leverage_with_higher_costs_cannot_improve_results(self):
        cheap = terms(50, fee="0")
        dear = replace(cheap,
                       entry_fee_bps=D("10"), exit_fee_bps=D("10"),
                       entry_slippage_bps=D("3"), exit_slippage_bps=D("3"))
        a = self.run_grid((cheap, dear))
        first, second = (s.audit for s in a.scenarios)
        self.assertLessEqual(second.worst_net_quote, first.worst_net_quote)
        self.assertLessEqual(second.best_net_quote, first.best_net_quote)
        self.assertLessEqual(second.benchmark_worst_net_quote,
                             first.benchmark_worst_net_quote)
        self.assertLessEqual(second.benchmark_best_net_quote,
                             first.benchmark_best_net_quote)
        self.assertNotEqual(a.scenarios[0].audit.digest_sha256,
                            a.scenarios[1].audit.digest_sha256)
        self.assertEqual(
            a.scenarios[0].audit.stressed_count,
            a.scenarios[1].audit.stressed_count,
        )

    def test_determinism_under_asset_permutation_and_scenario_order_labels(self):
        pair = (terms(1), terms(50))
        one = self.run_grid(pair)
        two = self.run_grid(pair, groups=(self.b, self.a))
        self.assertEqual(one, two)
        reordered = self.run_grid(tuple(reversed(pair)))
        self.assertNotEqual(one.digest_sha256, reordered.digest_sha256)
        self.assertEqual(
            {x.assumptions.margin.leverage_at_intent: x.audit
             for x in one.scenarios},
            {x.assumptions.margin.leverage_at_intent: x.audit
             for x in reordered.scenarios},
        )

    def test_bad_grid_and_untrusted_financial_inputs_fail_closed(self):
        for invalid in (
            (), (terms(1),), (terms(1), terms(1)),
            tuple(terms(50, fee=str(k)) for k in range(7)),
            [terms(1), terms(50)],
            (terms(1), "50x"), (terms(1), 50.0),
        ):
            with self.subTest(grid=str(invalid)[:50]), self.assertRaises(DataValidationError):
                self.run_grid(invalid)
        with self.assertRaises(DataValidationError):
            self.run_grid((terms(1), terms(50)), groups=(self.a, self.a))
        with self.assertRaises(DataValidationError):
            compare_costed_vision_oos_stress_scenarios(
                (self.a, self.b), as_of_ms=self.cutoff,
                cost_bps_per_side=0.0,
                assumptions_grid=(terms(1), terms(50)))

    def test_divergent_oos_coverage_blocks_report_instead_of_ranking(self):
        from dataclasses import replace as clone
        valid = audit_costed_vision_intrabar_oos(
            (self.a, self.b), as_of_ms=self.cutoff,
            cost_bps_per_side=D("0"), assumptions=terms(1))
        bad = clone(valid, fold_reports=tuple(
            clone(f, strategy_abstention_count=f.strategy_abstention_count + 1)
            for f in valid.fold_reports))
        with patch(
            "crypto_intelligence_agent.vision_stress_sensitivity.audit_costed_vision_intrabar_oos",
            side_effect=(valid, bad),
        ), self.assertRaises(DataValidationError):
            self.run_grid((terms(1), terms(50)))


if __name__ == "__main__":
    unittest.main()
