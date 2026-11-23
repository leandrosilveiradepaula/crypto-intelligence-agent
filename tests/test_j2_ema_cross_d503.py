"""D503: configurable three-EMA crossing on causal public closed candles."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest

from crypto_intelligence_agent.j2_bybit_closed_research_bridge import (
    BybitClosedResearchSeries,
)
from crypto_intelligence_agent.j2_observed_bybit_research import (
    evaluate_observed_bybit_research,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

HOUR = 3_600_000
FIRST = 1_792_998_000_000
CONFIG = CompressionBreakoutConfig(
    features=FeatureConfig(2, 2, 2, 2),
    compression_bars=2, baseline_bars=2,
    max_atr_ratio=Decimal("1"),
    min_quote_volume_ratio=Decimal("0.7"),
    experimental_paper_relaxation=True,
    entry_mode="ema_cross", ema_cross_periods=(10, 30, 60),
)


def case(final_close: str, bars: int = 80):
    candles = []
    for i in range(bars):
        price = Decimal(final_close) if i == bars - 1 else Decimal("100")
        low = min(Decimal("100"), price) - 1
        high = max(Decimal("100"), price) + 1
        opened = FIRST + i * HOUR
        candles.append(ClosedCandle(
            exchange="bybit_v5_public", market="linear_perpetual",
            symbol="BTCUSDT", interval="1h",
            open_time_ms=opened, close_time_ms=opened + HOUR - 1,
            open=Decimal("100"), high=high, low=low, close=price,
            base_volume=Decimal("10"), quote_volume=Decimal("2"),
            quality="bybit_public_ws_confirmed_unverified",
        ))
    series = BybitClosedResearchSeries(
        tuple(candles), "a" * 64, "b" * 64,
        "research_only_public_closed_series",
    )
    return series, candles[-1].close_time_ms + 1


class ConfigurableEmaCrossTests(unittest.TestCase):
    def test_periods_10_30_60_long_and_short_only_on_latest_close(self):
        for price, side in (("113", SyntheticSide.LONG), ("87", SyntheticSide.SHORT)):
            with self.subTest(price=price):
                series, now = case(price)
                out = evaluate_observed_bybit_research(
                    series, config=CONFIG, decision_at_ms=now,
                )
                self.assertEqual(len(out.hypotheses), 1)
                self.assertEqual(out.hypotheses[0].side, side)
                self.assertEqual(out.hypotheses[0].entry_rule, "ema_cross")
                self.assertEqual(out.hypotheses[0].closed_at_ms, now - 1)
                self.assertFalse(out.hypotheses[0].approved_for_signals)
                self.assertFalse(out.hypotheses[0].orders_sent)

    def test_flat_or_insufficient_history_does_not_open(self):
        for price, bars in (("100", 80), ("113", 24), ("113", 61)):
            with self.subTest(price=price, bars=bars):
                series, now = case(price, bars)
                out = evaluate_observed_bybit_research(
                    series, config=CONFIG, decision_at_ms=now,
                )
                self.assertFalse(out.hypotheses)
                self.assertFalse(out.orders_sent)

    def test_invalid_ordered_periods_and_default_legacy_mode(self):
        for vals in ((10, 10, 60), (30, 10, 60), (10, 30, 121),
                     (True, 30, 60), [10, 30, 60]):
            with self.subTest(periods=vals), self.assertRaises(DataValidationError):
                replace(CONFIG, ema_cross_periods=vals)
        with self.assertRaises(DataValidationError):
            replace(CONFIG, entry_mode="ema_cross", ema_cross_periods=None)
        with self.assertRaises(DataValidationError):
            replace(CONFIG, entry_mode="unknown")
        legacy = CompressionBreakoutConfig(
            FeatureConfig(2, 2, 2, 2), 2, 2,
            Decimal("1"), Decimal("1"),
        )
        self.assertEqual(legacy.entry_mode, "breakout")
        self.assertIsNone(legacy.ema_cross_periods)


if __name__ == "__main__":
    unittest.main()
