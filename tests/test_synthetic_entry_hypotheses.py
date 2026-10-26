"""J2/PRE2: independent reference fixtures and adversarial causal tests."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext, getcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError, MARKET,
)
from crypto_intelligence_agent.synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, STRATEGY_ID,
    research_synthetic_compression_breakouts,
)
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide


D = Decimal
HOUR = 3_600_000
START = 10 * HOUR


def candle(i: int, close: str, high: str, low: str,
           volume: str = "10") -> ClosedCandle:
    return ClosedCandle(
        exchange="fixture_exchange", market=MARKET, symbol="BTCUSDT",
        interval="1h", open_time_ms=START + i * HOUR,
        close_time_ms=START + (i + 1) * HOUR - 1,
        open=D(close), high=D(high), low=D(low), close=D(close),
        base_volume=D("1"), quote_volume=D(volume),
        quality="synthetic_fixture",
    )


def rows_long(extra: bool = False) -> tuple[ClosedCandle, ...]:
    # First two wide-range candles, then three narrow-range candles;
    # the breakout candle i=5 has volume 5 times the previous mean.
    specs = [
        ("100", "110", "90", "10"),
        ("101", "111", "91", "10"),
        ("101", "102", "100", "10"),
        ("101", "102", "100", "10"),
        ("101", "102", "100", "10"),
        ("105", "106", "101", "50"),
    ]
    if extra:
        specs.append(("111", "112", "104", "100"))
    return tuple(candle(i, *v) for i, v in enumerate(specs))


def rows_short() -> tuple[ClosedCandle, ...]:
    specs = [
        ("100", "110", "90", "10"),
        ("99", "109", "89", "10"),
        ("99", "100", "98", "10"),
        ("99", "100", "98", "10"),
        ("99", "100", "98", "10"),
        ("95", "99", "94", "50"),
    ]
    return tuple(candle(i, *v) for i, v in enumerate(specs))


def config(**override) -> CompressionBreakoutConfig:
    args = dict(
        features=FeatureConfig(2, 2, 2, 2),
        compression_bars=2, baseline_bars=2,
        max_atr_ratio=D("0.6"),
        min_quote_volume_ratio=D("2"),
        cooldown_bars=1,
    )
    args.update(override)
    return CompressionBreakoutConfig(**args)


def run(
    rows=None, *, cfg=None, decision=None, safety=1_000,
):
    samples = rows_long() if rows is None else rows
    t = samples[-1].close_time_ms + safety if decision is None else decision
    return research_synthetic_compression_breakouts(
        samples, config=config() if cfg is None else cfg,
        decision_at_ms=t, close_safety_ms=safety,
    )


class SyntheticEntryHypothesesTests(unittest.TestCase):
    def test_reference_long_uses_two_disjoint_PRIOR_atr_windows(self):
        out = run()
        self.assertEqual(out.strategy_id, STRATEGY_ID)
        self.assertEqual(out.evaluated_candle_count, 6)
        self.assertEqual(len(out.candidates), 1)
        x = out.candidates[0]
        self.assertEqual(x.side, SyntheticSide.LONG)
        self.assertEqual(x.close, D(105))
        self.assertEqual(x.prior_breakout_level, D(102))
        # Wilder ATR(2): i1=20, i2=11, i3=6.5, i4=4.25.
        # Earlier baseline = mean(20,11)=15.5;
        # later compression = mean(6.5,4.25)=5.375.
        self.assertEqual(x.atr_baseline_mean, D("15.5"))
        self.assertEqual(x.atr_recent_mean, D("5.375"))
        with localcontext() as ctx:
            ctx.prec = 50
            self.assertEqual(x.atr_compression_ratio, D("5.375") / D("15.5"))
        self.assertEqual(x.volume_to_prior_mean, D(5))
        self.assertEqual(x.closed_at_ms, rows_long()[-1].close_time_ms)
        self.assertEqual(x.earliest_research_at_ms, x.closed_at_ms + 1_000)

    def test_reference_short_and_no_trading_authority(self):
        result = run(rows_short())
        self.assertEqual(len(result.candidates), 1)
        x = result.candidates[0]
        self.assertEqual(x.side, SyntheticSide.SHORT)
        self.assertEqual(x.prior_breakout_level, D(98))
        self.assertEqual(x.close, D(95))
        self.assertEqual(x.volume_to_prior_mean, D(5))
        self.assertEqual(x.quality, "synthetic_fixture_hypothesis_only")
        self.assertFalse(x.approved_for_live_use)
        self.assertFalse(x.approved_for_signals)
        self.assertFalse(x.order_capable)
        self.assertFalse(x.orders_sent)
        self.assertFalse(result.approved_for_live_use)
        self.assertFalse(result.approved_for_signals)
        self.assertFalse(result.order_capable)
        self.assertFalse(result.orders_sent)
        self.assertFalse(hasattr(x, "probability"))
        self.assertFalse(hasattr(x, "expected_return"))
        self.assertFalse(hasattr(x, "submit_order"))
        with self.assertRaises(FrozenInstanceError):
            x.side = SyntheticSide.LONG

    def test_strict_breakout_not_equal_barrier(self):
        xs = rows_long()
        modified = xs[:-1] + (replace(xs[-1], close=D(102), open=D(102)),)
        self.assertEqual(run(modified).candidates, ())

    def test_volume_confirmation_and_atr_threshold_fail_closed(self):
        self.assertEqual(run(cfg=config(min_quote_volume_ratio=D(6))).candidates, ())
        self.assertEqual(run(cfg=config(max_atr_ratio=D("0.3"))).candidates, ())
        zero_vol = tuple(replace(x, quote_volume=D(0)) for x in rows_long())
        self.assertEqual(run(zero_vol).candidates, ())
        zero_atr = tuple(candle(i, "100", "100", "100", "10") for i in range(6))
        self.assertEqual(run(zero_atr).candidates, ())

    def test_missing_history_and_warmup_does_not_invent_candidates(self):
        xs = rows_long()
        for n in range(1, 6):
            with self.subTest(n=n):
                self.assertEqual(run(xs[:n]).candidates, ())
        self.assertEqual(
            run(xs, cfg=config(baseline_bars=4)).candidates, (),
        )
        self.assertEqual(
            run(xs, cfg=config(compression_bars=4)).candidates, (),
        )

    def test_cooldown_is_global_research_debounce_not_position_count(self):
        xs = rows_long(extra=True)
        instant = run(xs, cfg=config(cooldown_bars=0))
        self.assertEqual([s.closed_at_ms for s in instant.candidates],
                         [xs[5].close_time_ms, xs[6].close_time_ms])
        one = run(xs, cfg=config(cooldown_bars=1))
        self.assertEqual([s.closed_at_ms for s in one.candidates],
                         [xs[5].close_time_ms])

    def test_prefix_invariance_and_no_future_decision(self):
        xs = rows_long(extra=True)
        t = xs[-1].close_time_ms + 1_000
        before = run(xs[:6], decision=t)
        after = run(xs, decision=t)
        changed_future = xs[:6] + (replace(
            xs[-1], open=D(1000), high=D(1001),
            low=D(1000), close=D(1000),
        ),)
        alternative = run(changed_future, decision=t)
        self.assertEqual(before.candidates, after.candidates[:len(before.candidates)])
        self.assertEqual(before.candidates, alternative.candidates[:len(before.candidates)])
        with self.assertRaises(DataValidationError):
            run(xs, decision=xs[-1].close_time_ms + 999)

    def test_exact_close_safety_and_replay_determinism(self):
        xs = rows_long()
        time = xs[-1].close_time_ms + 2500
        self.assertEqual(run(xs, safety=2500, decision=time),
                         run(xs, safety=2500, decision=time))
        with self.assertRaises(DataValidationError):
            run(xs, safety=2500, decision=time-1)

    def test_reject_mixed_or_unverified_market_quality(self):
        xs = rows_long()
        for change in (
            dict(quality="verified_live"),
            dict(exchange="binance"),
            dict(symbol="ETHUSDT"),
            dict(interval="4h"),
            dict(market="spot"),
        ):
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                run(xs[:3] + (replace(xs[3], **change),) + xs[4:])
        with self.assertRaises(DataGapError):
            run(xs[:2] + xs[3:])
        with self.assertRaises(DataGapError):
            run(xs[:3] + (xs[2],) + xs[3:])

    def test_invalid_numeric_and_temporal_inputs_fail_closed(self):
        xs = rows_long()
        for changes in (
            dict(close=D("NaN")),
            dict(quote_volume=-1.0),
            dict(high=D("Infinity")),
            dict(close=True),
            dict(close_time_ms=xs[-1].close_time_ms + 1),
        ):
            with self.subTest(change=changes), self.assertRaises(DataValidationError):
                run(xs[:-1] + (replace(xs[-1], **changes),))
        with self.assertRaises(DataValidationError):
            run(xs, decision=True)
        with self.assertRaises(DataValidationError):
            run(xs, safety=-1)
        with self.assertRaises(DataValidationError):
            run(xs, cfg=None if False else "invalid config")

    def test_configuration_requires_exact_bounded_types(self):
        for change in (
            dict(features=None),
            dict(compression_bars=1),
            dict(compression_bars=501),
            dict(compression_bars=True),
            dict(compression_bars=2.0),
            dict(baseline_bars=0),
            dict(baseline_bars="2"),
            dict(cooldown_bars=-1),
            dict(cooldown_bars=501),
            dict(cooldown_bars=False),
            dict(max_atr_ratio=D(0)),
            dict(max_atr_ratio=D("1.01")),
            dict(max_atr_ratio=D("NaN")),
            dict(max_atr_ratio=0.5),
            dict(min_quote_volume_ratio=D("0.99")),
            dict(min_quote_volume_ratio=D("Infinity")),
            dict(min_quote_volume_ratio="2"),
        ):
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                config(**change)

    def test_no_network_or_order_calls_and_decimal_context_independence(self):
        xs = rows_long()
        expected = run(xs)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
                with localcontext() as ctx:
                    ctx.prec = 6
                    self.assertEqual(run(xs), expected)
        self.assertEqual(expected.quality, "synthetic_fixture_hypothesis_only")
        self.assertTrue(all("synthetic" in s.quality for s in expected.candidates))


if __name__ == "__main__":
    unittest.main()
