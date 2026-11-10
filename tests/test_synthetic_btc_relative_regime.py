"""J2/PRE3 deterministic reference, causal and adversarial offline checks."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError, MARKET,
)
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_btc_relative_regime import (
    BtcRelativeConfig, HypotheticalBtcRegime,
    research_synthetic_btc_relative_regime,
)

D = Decimal
HOUR = 3_600_000
START = 10 * HOUR


def candles(symbol: str, closes: list[int] | tuple[int, ...], *,
            first: int = 0, exchange: str = "synthetic_venue"):
    out = []
    for i, value in enumerate(closes):
        p = D(value)
        out.append(ClosedCandle(
            exchange=exchange, market=MARKET, symbol=symbol,
            interval="1h",
            open_time_ms=START+(i+first)*HOUR,
            close_time_ms=START+(i+first+1)*HOUR-1,
            open=p, high=p+D(1), low=p-D(1), close=p,
            base_volume=D(1), quote_volume=D(10),
            quality="synthetic_fixture",
        ))
    return tuple(out)


def config(**kwargs):
    d = dict(features=FeatureConfig(2, 2, 2, 2),
             momentum_bars=2,
             btc_trend_threshold=D("0.05"),
             btc_atr_stress_ratio=D("0.4"))
    d.update(kwargs)
    return BtcRelativeConfig(**d)


def research(btc=None, asset=None, *, cfg=None, decision=None, safety=1000):
    btc = candles("BTCUSDT", (100, 105, 110, 120)) if btc is None else btc
    asset = candles("ETHUSDT", (50, 50, 55, 66)) if asset is None else asset
    at = btc[-1].close_time_ms + safety if decision is None else decision
    return research_synthetic_btc_relative_regime(
        btc, asset, config=config() if cfg is None else cfg,
        decision_at_ms=at, close_safety_ms=safety,
    )


class SyntheticBtcContextTests(unittest.TestCase):
    def test_reference_momentum_and_relative_outperformance(self):
        r = research()
        self.assertEqual(r.regime, HypotheticalBtcRegime.UPTREND)
        # 120 / 105 -1 = 1/7, 66/50 -1 = 8/25;
        # relative = 8/25 - 1/7 = 31/175.
        with localcontext() as ctx:
            ctx.prec = 50
            self.assertEqual(r.btc_momentum, D(120)/D(105)-1)
            self.assertEqual(r.asset_momentum, D("0.32"))
            self.assertEqual(r.relative_strength, D("0.32")-(D(120)/D(105)-1))
        self.assertEqual(r.overlapping_candles, 4)
        self.assertEqual(r.earliest_research_at_ms, r.closed_at_ms+1000)
        self.assertFalse(r.approved_for_signals)
        self.assertFalse(r.order_capable)
        self.assertFalse(r.orders_sent)
        self.assertFalse(r.approved_for_live_use)
        self.assertFalse(hasattr(r, "probability"))
        with self.assertRaises(FrozenInstanceError):
            r.regime = HypotheticalBtcRegime.UPTREND

    def test_downtrend_and_sideways(self):
        down = research(
            btc=candles("BTCUSDT", (100, 100, 90, 80)),
            asset=candles("ETHUSDT", (50, 50, 52, 53)),
        )
        self.assertEqual(down.regime, HypotheticalBtcRegime.DOWNTREND)
        flat = research(
            btc=candles("BTCUSDT", (100, 100, 101, 102)),
            asset=candles("ETHUSDT", (50, 50, 52, 53)),
        )
        self.assertEqual(flat.regime, HypotheticalBtcRegime.SIDEWAYS)

    def test_stress_precedes_trend_and_exact_threshold(self):
        btc = candles("BTCUSDT", (100, 100, 100, 200))
        asset = candles("ETHUSDT", (50, 50, 50, 70))
        r = research(btc, asset, cfg=config(btc_atr_stress_ratio=D("0.1")))
        self.assertEqual(r.regime, HypotheticalBtcRegime.VOLATILITY_STRESS)
        self.assertGreaterEqual(r.btc_atr_to_close, D("0.1"))

    def test_asset_starts_later_without_reindexing(self):
        btc = candles("BTCUSDT", (100, 100, 100, 110, 120, 130))
        asset = candles("ETHUSDT", (50, 55, 60, 66), first=2)
        r = research(btc, asset)
        self.assertEqual(r.overlapping_candles, 4)
        self.assertEqual(r.closed_at_ms, btc[-1].close_time_ms)
        with localcontext() as ctx:
            ctx.prec = 50
            self.assertEqual(r.btc_momentum, D(130)/D(110)-1)
            self.assertEqual(r.asset_momentum, D(66)/D(55)-1)

    def test_warmup_no_momentum_no_fabrication(self):
        btc = candles("BTCUSDT", (100, 101))
        asset = candles("ETHUSDT", (50, 51))
        result = research(btc, asset)
        self.assertEqual(result.regime, HypotheticalBtcRegime.INSUFFICIENT_HISTORY)
        self.assertIsNone(result.btc_momentum)
        self.assertIsNone(result.asset_momentum)
        self.assertIsNone(result.relative_strength)

    def test_reject_stale_btc_and_nonmatching_utc_close(self):
        btc = candles("BTCUSDT", (100, 101, 102))
        asset = candles("ETHUSDT", (50, 51, 52, 53))
        # Both histories must already be closed at this decision time;
        # otherwise PRE1 correctly rejects future data before the sync gate.
        with self.assertRaisesRegex(DataValidationError, "last closed UTC candle"):
            research(btc, asset, decision=asset[-1].close_time_ms + 1000)

    def test_strict_history_and_mixed_markets(self):
        b = candles("BTCUSDT", (100, 101, 102, 103))
        a = candles("ETHUSDT", (50, 51, 52, 53))
        changes = [
            (b[:-1]+(replace(b[-1], quality="verified_live"),), a),
            (b, a[:-1]+(replace(a[-1], market="spot"),)),
            (b, a[:-1]+(replace(a[-1], exchange="other"),)),
            (b, a[:-1]+(replace(a[-1], symbol="BTCUSDT"),)),
            (b, a[:-1]+(replace(a[-1], close=D("NaN")),)),
            (b, a[:-1]+(replace(a[-1], close=D("Infinity")),)),
            (b, a[:-1]+(replace(a[-1], quote_volume=1.0),)),
        ]
        for btc, asset in changes:
            with self.subTest(asset=asset[-1]), self.assertRaises(DataValidationError):
                research(btc, asset)
        with self.assertRaises(DataGapError):
            research(b[:2]+b[3:], a)

    def test_reject_last_unclosed_candle_and_close_safety(self):
        b = candles("BTCUSDT", (100, 100, 110, 120))
        a = candles("ETHUSDT", (50, 50, 55, 66))
        with self.assertRaises(DataValidationError):
            research(b, a, decision=b[-1].close_time_ms+999)
        self.assertEqual(research(b, a, decision=b[-1].close_time_ms+1000).closed_at_ms,
                         b[-1].close_time_ms)

    def test_prefix_invariance_to_future_data(self):
        b = candles("BTCUSDT", (100, 101, 102, 103, 140))
        a = candles("ETHUSDT", (50, 51, 52, 53, 75))
        t = b[3].close_time_ms + 1000
        before = research(b[:4], a[:4], decision=t)
        changed_future_b = b[:4] + (replace(b[4], close=D(999),
                                            open=D(999), high=D(1000),
                                            low=D(998)),)
        with self.assertRaises(DataValidationError):
            research(changed_future_b, a, decision=t)
        self.assertEqual(before, research(b[:4], a[:4], decision=t))

    def test_config_invalid_and_wrong_benchmark(self):
        for kwargs in (
            {"features": None}, {"momentum_bars": 1},
            {"momentum_bars": True}, {"momentum_bars": 501},
            {"btc_trend_threshold": D("NaN")},
            {"btc_trend_threshold": D("1.1")},
            {"btc_trend_threshold": 0.2},
            {"btc_atr_stress_ratio": D(0)},
            {"btc_atr_stress_ratio": D("Infinity")},
            {"btc_atr_stress_ratio": "0.1"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(DataValidationError):
                config(**kwargs)
        a = candles("BTCUSDT", (100, 100, 101, 102))
        with self.assertRaises(DataValidationError):
            research(a, a)

    def test_context_independent_and_network_free(self):
        expected = research()
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                with localcontext() as ctx:
                    ctx.prec = 6
                    self.assertEqual(research(), expected)


if __name__ == "__main__":
    unittest.main()
