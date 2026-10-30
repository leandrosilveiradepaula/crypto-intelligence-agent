"""J3 ROBUST1 stress sensitivity: causal OOS and adversarial guardrails."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
from unittest.mock import patch
import unittest

from test_vision_dynamic_replay import fixture
from test_vision_intrabar_stress import terms
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_risk_sensitivity import (
    VisionRiskShocks, audit_vision_risk_sensitivity,
)


def shocks(cost="5", maintenance="5", funding="20"):
    return VisionRiskShocks(D(cost), D(cost), D(cost), D(cost),
                            D(maintenance), D(funding))


class VisionRiskSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = fixture("BTCUSDT")
        cls.b = fixture("ETHUSDT")
        cls.cutoff = cls.a[-1].end_open_exclusive_ms + 3600000

    def evaluate(self, groups=None, **kw):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            return audit_vision_risk_sensitivity(
                groups if groups is not None else (self.a, self.b),
                as_of_ms=self.cutoff, cost_bps_per_side=D("0"),
                assumptions=kw.get("assumptions", terms()),
                shocks=kw.get("shocks", shocks()))

    def test_adverse_costs_do_not_improve_conditional_results(self):
        result = self.evaluate()
        base, worse = result.baseline, result.adverse_costs
        for key in ("worst_net_quote", "best_net_quote",
                    "benchmark_worst_net_quote", "benchmark_best_net_quote"):
            with self.subTest(key=key):
                self.assertLessEqual(getattr(worse,key),getattr(base,key))
        self.assertEqual(base.stressed_count,worse.stressed_count)
        self.assertEqual(result, self.evaluate((self.b, self.a)))
        report=result.sanitized_report()
        self.assertEqual(len(report["scenarios"]),4)
        self.assertFalse(report["funding_schedule_verified"])
        self.assertFalse(report["financial_backtest_approved"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(report["network_requests"],0)
        self.assertNotIn("BTCUSDT",str(report))
        self.assertNotIn("ETHUSDT",str(report))
        for scenario in report["scenarios"].values():
            self.assertNotIn("symbol",scenario)
            self.assertNotIn("price",scenario)

    def test_funding_shocks_are_two_conditional_alternatives(self):
        result=self.evaluate()
        self.assertNotEqual(result.funding_plus.digest_sha256,
                            result.funding_minus.digest_sha256)
        self.assertEqual(result.funding_plus.stressed_count,
                         result.funding_minus.stressed_count)
        self.assertEqual(result.funding_plus.fold_reports[0].bars_scored,
                         result.funding_minus.fold_reports[0].bars_scored)
        self.assertEqual(result.sanitized_report()["worst_conditional_strategy_quote"],
            str(min(r.worst_net_quote for r in (
                result.baseline,result.adverse_costs,
                result.funding_plus,result.funding_minus))))

    def test_context_independence_and_distinct_parameter_digest(self):
        original=self.evaluate()
        for prec in (2,5,28):
            with localcontext() as ctx:
                ctx.prec=prec
                self.assertEqual(original,self.evaluate())
        changed=self.evaluate(shocks=shocks(cost="6"))
        self.assertNotEqual(original.digest_sha256,changed.digest_sha256)

    def test_50x_vs_1x_is_not_homologated(self):
        x=self.evaluate()
        y=self.evaluate(assumptions=terms(leverage=1))
        self.assertFalse(x.sanitized_report()["live_trading_authorized"])
        self.assertFalse(y.sanitized_report()["live_trading_authorized"])
        self.assertNotEqual(x.digest_sha256,y.digest_sha256)
        self.assertGreaterEqual(x.baseline.strategy_max_single_bar_loss_over_margin,D("0"))
        self.assertGreaterEqual(y.baseline.strategy_max_single_bar_loss_over_margin,D("0"))

    def test_invalid_shocks_and_funding_bounds_fail_closed(self):
        invalid=[
            dict(extra_entry_fee_bps=D("NaN")),
            dict(extra_entry_fee_bps=D("-1")),
            dict(extra_entry_fee_bps=0.2),
            dict(extra_exit_fee_bps=D("10001")),
            dict(funding_shock_bps=D("0.0000001")),
        ]
        normal=shocks()
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                replace(normal,**change)
        with self.assertRaises(DataValidationError):
            VisionRiskShocks(*(D("0") for _ in range(6)))
        with self.assertRaises(DataValidationError):
            self.evaluate(assumptions=replace(terms(funding="9999"),
                signed_funding_bps=D("9999")),shocks=shocks(funding="2"))
        with self.assertRaises(DataValidationError):
            self.evaluate(shocks=None)

if __name__=="__main__":
    unittest.main()
