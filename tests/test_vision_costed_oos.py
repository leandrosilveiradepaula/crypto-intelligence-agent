"""J2/J3 OOS proxy fail-closed contracts."""
from dataclasses import replace
from decimal import Decimal
import unittest
from test_vision_dynamic_replay import fixture
from crypto_intelligence_agent.vision_costed_oos import costed_vision_monthly_oos
from crypto_intelligence_agent.market_data import DataValidationError

class VisionCostedOOSTests(unittest.TestCase):
    def setUp(self):
        self.a=fixture("BTCUSDT")
        self.b=fixture("ETHUSDT")
        self.cutoff=self.a[-1].end_open_exclusive_ms+3600000

    def run_oos(self,groups=None,cost=Decimal("0")):
        return costed_vision_monthly_oos(
            groups or (self.a,self.b),
            as_of_ms=self.cutoff,cost_bps_per_side=cost)

    def test_determinism_abstain_and_negative_gates(self):
        a=self.run_oos()
        b=self.run_oos((self.b,self.a))
        self.assertEqual(a,b)
        self.assertEqual(len(a.folds),1)
        report=a.sanitized_report()
        for key in ("marketwide_top50_verified","source_authenticated",
                    "financial_backtest_approved","live_trading_authorized",
                    "orders_sent"):
            self.assertFalse(report[key])
        self.assertEqual(report["network_requests"],0)
        self.assertNotIn("BTCUSDT",str(report))

    def test_fees_reduce_or_eliminate_selection(self):
        zero=self.run_oos()
        expensive=self.run_oos(cost=Decimal("100"))
        self.assertEqual(zero.asset_count,expensive.asset_count)
        self.assertLessEqual(expensive.folds[0].observations,zero.folds[0].observations)
        self.assertNotEqual(zero.digest_sha256,expensive.digest_sha256)

    def test_test_month_mutation_does_not_change_rule(self):
        baseline=self.run_oos()
        later=list(self.a[-1].candles)
        later[50]=replace(later[50],close=later[50].close+Decimal("0.001"),
            high=later[50].high+Decimal("1"))
        updated=self.run_oos((self.a[:-1]+(replace(self.a[-1],candles=tuple(later)),),self.b))
        self.assertEqual(baseline.folds[0].selected_rule,updated.folds[0].selected_rule)
        self.assertEqual(baseline.folds[0].training_net_bps,updated.folds[0].training_net_bps)

    def test_strict_inputs(self):
        for c in ("0",0.1,Decimal("-1"),Decimal("NaN"),Decimal("1001"),Decimal("0.0000001"),True):
            with self.subTest(cost=str(c)),self.assertRaises(DataValidationError):
                self.run_oos(cost=c)
        with self.assertRaises(DataValidationError):
            self.run_oos((self.a,self.a))
        with self.assertRaises(DataValidationError):
            self.run_oos((self.a[:-1],self.b))
