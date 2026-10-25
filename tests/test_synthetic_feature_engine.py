"""Reference and adversarial tests for causal SYNTHETIC feature math."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, getcontext, localcontext
import unittest

from crypto_intelligence_agent.market_data import (
    MARKET, ClosedCandle, DataGapError, DataValidationError,
)
from crypto_intelligence_agent.synthetic_feature_engine import (
    MAX_CANDLES, FeatureConfig, compute_synthetic_features,
)


HOUR = 3_600_000
DAY = 86_400_000
START = 10 * HOUR


def candle(
    i, *, start=START, interval="1h", duration=HOUR,
    opening=None, high=None, low=None, close=None, volume=None,
):
    closing = Decimal(str(10 + i)) if close is None else Decimal(str(close))
    return ClosedCandle(
        exchange="synthetic_exchange", market=MARKET, symbol="BTCUSDT",
        interval=interval, open_time_ms=start + i * duration,
        close_time_ms=start + (i + 1) * duration - 1,
        open=closing if opening is None else Decimal(str(opening)),
        high=closing + 1 if high is None else Decimal(str(high)),
        low=closing - 1 if low is None else Decimal(str(low)),
        close=closing,
        base_volume=Decimal(str(i + 1)),
        quote_volume=Decimal(str(10 * (i + 1) if volume is None else volume)),
        quality="synthetic_fixture",
    )


def run(rows=None, *, config=None, decision=None, safety=1_000):
    rows = [candle(i) for i in range(5)] if rows is None else rows
    conf = FeatureConfig(ema_period=3, atr_period=2, extrema_period=2,
                         quote_volume_period=2) if config is None else config
    cutoff = rows[-1].close_time_ms + 1000 if decision is None else decision
    return compute_synthetic_features(
        rows, config=conf, decision_at_ms=cutoff, close_safety_ms=safety,
    )


class SyntheticFeatureMathTests(unittest.TestCase):
    def test_trailing_output_is_pure_research_not_signal_or_order(self):
        output = run()
        self.assertEqual(output.quality, "synthetic_fixture")
        self.assertFalse(output.approved_for_live_use)
        self.assertFalse(output.order_capable)
        self.assertTrue(all(not item.approved_for_signals for item in output.rows))
        self.assertEqual(len(output.rows), 5)
        self.assertFalse(hasattr(output.rows[0], "buy"))
        self.assertFalse(hasattr(output.rows[0], "probability"))

    def test_ema_seed_sma_then_recursive_reference(self):
        rows = [candle(0, close="10"), candle(1, close="12"),
                candle(2, close="14"), candle(3, close="16")]
        s = run(rows)
        self.assertIsNone(s.rows[0].ema_close)
        self.assertIsNone(s.rows[1].ema_close)
        self.assertEqual(s.rows[2].ema_close, Decimal("12"))
        # alpha=2/(3+1)=1/2, 12 + (16-12)/2 = 14
        self.assertEqual(s.rows[3].ema_close, Decimal("14"))

    def test_wilder_atr_and_true_range_reference(self):
        rows = [
            candle(0, close="10", opening="10", high="11", low="9"),
            candle(1, close="12", opening="11", high="14", low="10"),
            candle(2, close="13", opening="12", high="17", low="11"),
        ]
        result = run(rows)
        self.assertEqual([x.true_range for x in result.rows],
                         [Decimal(2), Decimal(4), Decimal(6)])
        self.assertIsNone(result.rows[0].atr_wilder)
        self.assertEqual(result.rows[1].atr_wilder, Decimal(3))
        self.assertEqual(result.rows[2].atr_wilder, Decimal("4.5"))

    def test_extrema_exclude_current_and_use_exact_preceding_window(self):
        rows = [candle(0), candle(1), candle(2, high="999", low="1")]
        out = run(rows)
        self.assertIsNone(out.rows[1].preceding_high)
        self.assertEqual(out.rows[2].preceding_high, Decimal(12))
        self.assertEqual(out.rows[2].preceding_low, Decimal(9))
        self.assertEqual(out.rows[2].close, Decimal(12))

    def test_quote_volume_ratio_uses_preceding_not_current_mean(self):
        rows = [candle(0, volume="10"), candle(1, volume="20"),
                candle(2, volume="60")]
        out = run(rows)
        self.assertIsNone(out.rows[1].quote_volume_to_prior_mean)
        self.assertEqual(out.rows[2].quote_volume_to_prior_mean, Decimal("4"))

    def test_zero_prior_volume_yields_none_and_zero_current_is_zero(self):
        data = [candle(0, volume=0), candle(1, volume=0),
                candle(2, volume=12), candle(3, volume=0)]
        out = run(data)
        self.assertIsNone(out.rows[2].quote_volume_to_prior_mean)
        self.assertEqual(out.rows[3].quote_volume_to_prior_mean, Decimal(0))

    def test_simple_return_reference_and_no_first_return(self):
        rows = [candle(0, close=10), candle(1, close=15)]
        out = run(rows)
        self.assertIsNone(out.rows[0].simple_return)
        self.assertEqual(out.rows[1].simple_return, Decimal("0.5"))

    def test_prefix_invariance_when_future_prices_change(self):
        original = [candle(i) for i in range(4)]
        mutated = original + [candle(4, close=1000)]
        cutoff = mutated[-1].close_time_ms + 1000
        x = run(original, decision=cutoff)
        y = run(mutated, decision=cutoff)
        self.assertEqual(x.rows, y.rows[:4])
        self.assertEqual(x.config, y.config)

    def test_data_future_is_rejected_even_if_last_row_would_be_ignored(self):
        rows = [candle(i) for i in range(4)]
        with self.assertRaisesRegex(DataValidationError, "future or unclosed"):
            run(rows, decision=rows[2].close_time_ms + 1000)

    def test_close_safety_exact_boundary_and_one_millisecond_less(self):
        rows = [candle(i) for i in range(3)]
        cutoff = rows[-1].close_time_ms + 1000
        self.assertEqual(len(run(rows, decision=cutoff).rows), 3)
        with self.assertRaises(DataValidationError):
            run(rows, decision=cutoff - 1)

    def test_weekly_utc_monday_anchor(self):
        monday = 4 * DAY
        series = [candle(i, start=monday, interval="1w", duration=7 * DAY)
                  for i in range(2)]
        output = run(series)
        self.assertEqual(output.interval, "1w")
        self.assertEqual(output.rows[1].open_time_ms, monday + 7 * DAY)
        wrong = [candle(0, start=0, interval="1w", duration=7 * DAY)]
        with self.assertRaises(DataValidationError):
            run(wrong)

    def test_gap_duplicate_reverse_and_shift_are_rejected(self):
        base = [candle(i) for i in range(4)]
        examples = (
            base[:2] + base[3:],
            base[:2] + [base[1]] + base[2:],
            list(reversed(base)),
            base[:2] + [replace(base[2], open_time_ms=base[2].open_time_ms+1)] + base[3:],
        )
        for seq in examples:
            with self.subTest(seq=[c.open_time_ms for c in seq]), \
                    self.assertRaises((DataGapError, DataValidationError)):
                run(seq)

    def test_cross_venue_symbol_interval_or_market_rejected(self):
        base = [candle(i) for i in range(3)]
        for field, value in (
            ("exchange", "other"),
            ("symbol", "ETHUSDT"),
            ("interval", "4h"),
            ("market", "spot"),
            ("quality", "live"),
        ):
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                run(base[:2] + [replace(base[2], **{field: value})])

    def test_only_synthetic_verified_candle_contract_is_accepted(self):
        baseline = [candle(0)]
        for quality in ("", "kraken_raw", "documented", "verified_live", "synthetic"):
            with self.subTest(quality=quality), self.assertRaises(DataValidationError):
                run([replace(baseline[0], quality=quality)])
        with self.assertRaises(DataValidationError):
            run([{"symbol": "BTCUSDT", "quality": "synthetic_fixture"}])

    def test_bad_timestamps_type_grid_and_duration_rejected(self):
        row = candle(0)
        for changes in (
            {"open_time_ms": True},
            {"open_time_ms": -1},
            {"open_time_ms": row.open_time_ms+1},
            {"close_time_ms": row.close_time_ms-1},
            {"close_time_ms": float(row.close_time_ms)},
        ):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                run([replace(row, **changes)])

    def test_malformed_extrema_zero_prices_negative_volume_rejected(self):
        row = candle(0)
        for changes in (
            {"open": Decimal(0)},
            {"close": Decimal("-1")},
            {"high": Decimal("9")},
            {"low": Decimal("11")},
            {"quote_volume": Decimal("-0.01")},
            {"base_volume": Decimal("-1")},
            {"high": Decimal("Infinity")},
            {"close": Decimal("NaN")},
            {"open": 10.0},
            {"quote_volume": False},
        ):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                run([replace(row, **changes)])

    def test_overprecision_or_extreme_exponents_rejected(self):
        row = candle(0)
        for x in (Decimal("1E+36"), Decimal("1E-25"),
                  Decimal("12345678901234567890123456789012345678901")):
            with self.subTest(x=x), self.assertRaises(DataValidationError):
                run([replace(row, high=x)])

    def test_period_configuration_requires_explicit_bounded_ints(self):
        for n in (0, 1, -1, 501, True, 2.0, "14", None):
            with self.subTest(n=n), self.assertRaises(DataValidationError):
                FeatureConfig(n, 2, 2, 2)
        with self.assertRaises(DataValidationError):
            compute_synthetic_features([candle(0)], config=None, decision_at_ms=START+HOUR)

    def test_cutoff_and_safety_types_must_be_valid(self):
        rows = [candle(i) for i in range(3)]
        for moment in (0, -1, True, float(rows[-1].close_time_ms), "tomorrow"):
            with self.subTest(decision=moment), self.assertRaises(DataValidationError):
                run(rows, decision=moment)
        for safety in (-1, True, 1.5, 86_400_001):
            with self.subTest(safety=safety), self.assertRaises(DataValidationError):
                run(rows, safety=safety)

    def test_numeric_output_independent_of_ambient_decimal_precision(self):
        rows = [candle(i) for i in range(7)]
        with localcontext() as ctx:
            ctx.prec = 7
            first = run(rows)
        with localcontext() as ctx:
            ctx.prec = 37
            second = run(rows)
        self.assertEqual(first, second)

    def test_immutable_output_cannot_promote_to_signal(self):
        out = run()
        with self.assertRaises(FrozenInstanceError):
            out.rows[0].ema_close = Decimal(0)
        with self.assertRaises(TypeError):
            replace(out, approved_for_live_use=True)
        with self.assertRaises(TypeError):
            replace(out.rows[0], approved_for_signals=True)
        self.assertFalse(out.order_capable)

    def test_bounded_input_and_missing_candles_rejected(self):
        with self.assertRaises(DataValidationError):
            run([])
        with self.assertRaises(DataValidationError):
            run([candle(0)] * (MAX_CANDLES + 1))
        with self.assertRaises(DataValidationError):
            run(tuple(candle(i) for i in range(1, 5))[::-1])
        with self.assertRaises(DataValidationError):
            run((c for c in [candle(0)]))


if __name__ == "__main__":
    unittest.main()
