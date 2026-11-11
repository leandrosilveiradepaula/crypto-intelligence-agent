"""J2 trend pullback strategy: causal tests with explicit synthetic candles."""
import unittest
from decimal import Decimal as D

from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from crypto_intelligence_agent.synthetic_trend_pullback import (
    TrendPullbackConfig, research_synthetic_trend_pullbacks,
)


def candles(closes):
    result = []
    for i, price in enumerate(closes):
        p = D(str(price))
        result.append(ClosedCandle(
            exchange="bybit", market="linear_perpetual", symbol="BTCUSDT",
            interval="1h", open_time_ms=1_800_000_000_000 + i * 3_600_000,
            close_time_ms=1_800_000_000_000 + (i + 1) * 3_600_000 - 1,
            open=p, high=p + D("0.2"), low=p - D("0.2"),
            close=p, base_volume=D("10"), quote_volume=D("100"),
            quality="synthetic_fixture",
        ))
    return tuple(result)


def config():
    return TrendPullbackConfig(
        FeatureConfig(ema_period=2, atr_period=2,
                      extrema_period=2, quote_volume_period=2),
        min_ema_slope_atr=D("0.01"), min_volume_ratio=D("0.5"),
        max_trigger_extension_atr=D("10"),
    )


class TrendPullbackTests(unittest.TestCase):
    def test_long_resumption_and_prefix_causality(self):
        cs = candles([10, 11, 12, 13, 12, 14])
        # With EMA(2), prior 12 is below EMA after an uptrend.
        x = research_synthetic_trend_pullbacks(
            cs, config=config(), decision_at_ms=cs[-1].close_time_ms + 1000)
        self.assertEqual(len(x.candidates), 1)
        self.assertEqual(x.candidates[0].side, SyntheticSide.LONG)
        self.assertEqual(x.candidates[0].trigger_close, D("14"))
        self.assertFalse(x.orders_sent)
        self.assertFalse(x.approved_for_live_use)
        early = research_synthetic_trend_pullbacks(
            cs[:-1], config=config(), decision_at_ms=cs[-2].close_time_ms + 1000)
        self.assertEqual(early.candidates, ())
        with self.assertRaises(DataValidationError):
            research_synthetic_trend_pullbacks(
                cs, config=config(), decision_at_ms=cs[-2].close_time_ms + 1000)

    def test_short_resumption(self):
        cs = candles([14, 13, 12, 11, 12, 10])
        x = research_synthetic_trend_pullbacks(
            cs, config=config(), decision_at_ms=cs[-1].close_time_ms + 1000)
        self.assertEqual(len(x.candidates), 1)
        self.assertEqual(x.candidates[0].side, SyntheticSide.SHORT)

    def test_no_pullback_no_signal(self):
        cs = candles([10, 11, 12, 13, 14, 15])
        x = research_synthetic_trend_pullbacks(
            cs, config=config(), decision_at_ms=cs[-1].close_time_ms + 1000)
        self.assertEqual(x.candidates, ())

    def test_reject_bad_config(self):
        for val in (D("NaN"), D("0"), D("-1"), D("11")):
            with self.subTest(val=val), self.assertRaises(DataValidationError):
                TrendPullbackConfig(
                    config().features, val, D("1"), D("1"))

    def test_reject_non_fixture(self):
        cs = list(candles([10, 11, 12, 13, 12, 14]))
        from dataclasses import replace
        cs[-1] = replace(cs[-1], quality="provider")
        with self.assertRaises(DataValidationError):
            research_synthetic_trend_pullbacks(
                tuple(cs), config=config(),
                decision_at_ms=cs[-1].close_time_ms + 1000)


if __name__ == "__main__":
    unittest.main()
