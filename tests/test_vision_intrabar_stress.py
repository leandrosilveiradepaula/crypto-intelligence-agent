"""Numerical regressions for conditional intrabar research bounds."""
from dataclasses import replace
from decimal import Decimal as D
import unittest
from crypto_intelligence_agent.offline_vision_month import OfflineVisionCandle
from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
from crypto_intelligence_agent.vision_intrabar_stress import (
    VisionStressAssumptions,stress_vision_candle,
)
from crypto_intelligence_agent.market_data import DataValidationError

def terms(leverage=50, funding="0", fee="0"):
    return VisionStressAssumptions(
        SyntheticMarginBasis(D("2"),leverage,D(2*leverage),"SYNTHETIC_USDT"),
        D("0.01"),D("0.03"),D("0"),D(fee),D(fee),D("0"),D("0"),D(funding))

def bar(o="100",h="105",l="95",c="101"):
    return OfflineVisionCandle(1000,2000,D(o),D(h),D(l),D(c),D("20"),D("2000"))

class VisionIntrabarStressTests(unittest.TestCase):
    def test_long_multi_touch_not_automatic_win(self):
        x=stress_vision_candle(bar(),long=True,assumptions=terms())
        self.assertTrue(x.intrabar_ambiguous)
        self.assertTrue(x.touched_liquidation_proxy)
        self.assertTrue(x.touched_target)
        self.assertLess(x.worst_net_quote,D("0"))
        self.assertGreater(x.best_net_quote,D("0"))
        self.assertFalse(x.financial_backtest_approved)
        self.assertFalse(x.orders_sent)

    def test_short_and_low_leverage(self):
        x=stress_vision_candle(bar(),long=False,assumptions=terms())
        y=stress_vision_candle(bar(),long=True,assumptions=terms(1))
        self.assertTrue(x.touched_liquidation_proxy)
        self.assertFalse(y.touched_liquidation_proxy)
        self.assertTrue(y.touched_stop)

    def test_fee_and_funding_signs(self):
        z=stress_vision_candle(bar(),long=True,assumptions=terms())
        f=stress_vision_candle(bar(),long=True,assumptions=terms(fee="10"))
        self.assertLess(f.best_net_quote,z.best_net_quote)
        paid=stress_vision_candle(bar(),long=True,assumptions=terms(funding="5"))
        recv=stress_vision_candle(bar(),long=True,assumptions=terms(funding="-5"))
        self.assertLess(paid.best_net_quote,recv.best_net_quote)

    def test_liquidation_worst_branch_does_not_benefit_from_fees(self):
        for long in (True,False):
            with self.subTest(long=long):
                old=stress_vision_candle(bar(),long=long,assumptions=terms(fee="0"))
                new=stress_vision_candle(bar(),long=long,assumptions=terms(fee="10"))
                self.assertTrue(old.touched_liquidation_proxy)
                self.assertTrue(new.touched_liquidation_proxy)
                self.assertLess(new.worst_net_quote,old.worst_net_quote)
                self.assertLessEqual(new.best_net_quote,old.best_net_quote)
                self.assertLessEqual(new.worst_net_quote,D("-2"))
                self.assertFalse(new.liquidation_formula_verified)

    def test_bad_inputs_fail_closed(self):
        with self.assertRaises(DataValidationError):
            stress_vision_candle(bar(),long=1,assumptions=terms())
        with self.assertRaises(DataValidationError):
            stress_vision_candle(bar(h="90"),long=True,assumptions=terms())
        with self.assertRaises(DataValidationError):
            replace(terms(),stop_fraction=D("NaN"))
        with self.assertRaises(DataValidationError):
            replace(terms(),target_fraction=D("1"))
        with self.assertRaises(DataValidationError):
            replace(terms(),entry_fee_bps=D("-1"))

if __name__=="__main__":
    unittest.main()
