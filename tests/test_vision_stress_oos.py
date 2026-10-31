"""Adversarial monthly OOS stress integration fixtures."""
from decimal import Decimal as D
import unittest
from test_vision_dynamic_replay import fixture
from test_vision_intrabar_stress import terms
from crypto_intelligence_agent.vision_stress_oos import audit_costed_vision_intrabar_oos
from crypto_intelligence_agent.market_data import DataValidationError

class VisionStressOOSTests(unittest.TestCase):
    def test_deterministic_frozen_months_privacy_and_gates(self):
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        end=a[-1].end_open_exclusive_ms+3600000
        def run(groups):
            return audit_costed_vision_intrabar_oos(groups,as_of_ms=end,
                        cost_bps_per_side=D("0"),assumptions=terms())
        first=run((a,b))
        self.assertEqual(first,run((b,a)))
        result=first.sanitized_report()
        self.assertFalse(result["financial_backtest_approved"])
        self.assertFalse(result["orders_sent"])
        self.assertNotIn("BTCUSDT",str(result))
        self.assertGreaterEqual(first.best_net_quote,first.worst_net_quote)
        self.assertLessEqual(first.liquidation_possible_count,first.stressed_count)
        self.assertLessEqual(first.ambiguous_count,first.stressed_count)
        self.assertEqual(len(first.fold_reports),1)
        self.assertGreater(first.fold_reports[0].bars_scored,0)
        self.assertEqual(first.fold_reports[0].strategy_exposures,first.stressed_count)
        self.assertLessEqual(first.worst_drawdown_proxy_quote,D("0"))
        self.assertLessEqual(first.best_drawdown_proxy_quote,D("0"))
        self.assertLessEqual(first.benchmark_worst_drawdown_proxy_quote,D("0"))
        self.assertGreaterEqual(first.benchmark_best_net_quote,
                                first.benchmark_worst_net_quote)
        self.assertIn("benchmark_worst_net_quote",result)
        self.assertEqual(first.fold_reports[0].benchmark_exposures,
                         first.fold_reports[0].bars_scored)
        self.assertEqual(first.fold_reports[0].strategy_ambiguous_count,
                         first.ambiguous_count)
        self.assertEqual(first.fold_reports[0].strategy_stop_touched_count,
                         first.stop_touched_count)
        self.assertEqual(first.fold_reports[0].strategy_target_touched_count,
                         first.target_touched_count)
        self.assertEqual(first.fold_reports[0].benchmark_stop_touched_count,
                         first.benchmark_stop_touched_count)
        self.assertEqual(first.fold_reports[0].benchmark_target_touched_count,
                         first.benchmark_target_touched_count)
        self.assertEqual(first.fold_reports[0].strategy_abstention_count,
                         first.abstention_count)
        self.assertEqual(first.fold_reports[0].strategy_exposures +
                         first.fold_reports[0].strategy_abstention_count,
                         first.fold_reports[0].bars_scored)
        self.assertGreaterEqual(first.strategy_max_single_bar_loss_over_margin,D("0"))
        self.assertGreaterEqual(first.benchmark_max_single_bar_loss_over_margin,D("0"))
        self.assertEqual(first.fold_reports[0].strategy_worst_net_quote,
                         first.worst_net_quote)
        self.assertEqual(first.fold_reports[0].benchmark_worst_net_quote,
                         first.benchmark_worst_net_quote)
        self.assertFalse(result["live_trading_authorized"])
        self.assertEqual(result["network_requests"],0)
        self.assertNotIn("ETHUSDT",str(result))


    def test_fee_deterioration_and_folds_are_sanitized(self):
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        end=a[-1].end_open_exclusive_ms+3600000
        baseline=audit_costed_vision_intrabar_oos(
            (a,b),as_of_ms=end,cost_bps_per_side=D("0"),assumptions=terms(fee="0"))
        stressed=audit_costed_vision_intrabar_oos(
            (a,b),as_of_ms=end,cost_bps_per_side=D("0"),assumptions=terms(fee="10"))
        self.assertLessEqual(stressed.benchmark_best_net_quote,baseline.benchmark_best_net_quote)
        self.assertLessEqual(stressed.benchmark_worst_net_quote,baseline.benchmark_worst_net_quote)
        self.assertLessEqual(stressed.best_net_quote,baseline.best_net_quote)
        self.assertLessEqual(stressed.worst_net_quote,baseline.worst_net_quote)
        self.assertNotEqual(stressed.digest_sha256,baseline.digest_sha256)
        report=stressed.sanitized_report()
        self.assertEqual(len(report["fold_coverage"]),len(stressed.fold_reports))
        self.assertNotIn("BTCUSDT",str(report))
        self.assertNotIn("ETHUSDT",str(report))
        self.assertFalse(report["financial_backtest_approved"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(report["network_requests"],0)

    def test_no_training_lookahead_in_fold_selection(self):
        from dataclasses import replace
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        end=a[-1].end_open_exclusive_ms+3600000
        baseline=audit_costed_vision_intrabar_oos(
            (a,b),as_of_ms=end,cost_bps_per_side=D("0"),assumptions=terms())
        changed=list(a[-1].candles)
        row=changed[50]
        changed[50]=replace(row,documented_quote_volume=row.documented_quote_volume+D("1"))
        other=a[:-1]+(replace(a[-1],candles=tuple(changed)),)
        later=audit_costed_vision_intrabar_oos(
            (other,b),as_of_ms=end,cost_bps_per_side=D("0"),assumptions=terms())
        self.assertEqual(baseline.fold_reports[0].bars_scored,
                         later.fold_reports[0].bars_scored)
        self.assertEqual(baseline.stressed_count,later.stressed_count)

    def test_requires_explicit_and_valid_stress_terms(self):
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        end=a[-1].end_open_exclusive_ms+3600000
        with self.assertRaises(DataValidationError):
            audit_costed_vision_intrabar_oos((a,b),as_of_ms=end,
                         cost_bps_per_side=D("0"),assumptions=None)
        with self.assertRaises(DataValidationError):
            audit_costed_vision_intrabar_oos((a,a),as_of_ms=end,
                         cost_bps_per_side=D("0"),assumptions=terms())
