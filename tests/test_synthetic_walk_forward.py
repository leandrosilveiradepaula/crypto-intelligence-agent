"""J3/PRE3: split-index mathematics, causal availability, no OOS double count."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError, MARKET,
)
from crypto_intelligence_agent.synthetic_walk_forward import (
    MAX_FOLDS, SyntheticWalkForwardConfig, plan_synthetic_walk_forward,
)


D = Decimal
HOUR = 3_600_000
START = 40 * HOUR


def candle(i: int) -> ClosedCandle:
    price = D(100 + i)
    return ClosedCandle(
        exchange="synthetic_venue", market=MARKET, symbol="BTCUSDT",
        interval="1h",
        open_time_ms=START + i * HOUR,
        close_time_ms=START + (i + 1) * HOUR - 1,
        open=price, high=price + 1, low=price - 1, close=price,
        base_volume=D(1), quote_volume=D(100),
        quality="synthetic_fixture",
    )


def candles(n: int = 12) -> tuple[ClosedCandle, ...]:
    return tuple(candle(i) for i in range(n))


def cfg(**changes) -> SyntheticWalkForwardConfig:
    params = dict(train_bars=4, gap_bars=1, test_bars=2, stride_bars=2)
    params.update(changes)
    return SyntheticWalkForwardConfig(**params)


def run(cs=None, *, settings=None, decision=None, safety=1000):
    rows = candles() if cs is None else cs
    at = rows[-1].close_time_ms + safety if decision is None else decision
    return plan_synthetic_walk_forward(
        rows, config=cfg() if settings is None else settings,
        decision_at_ms=at, close_safety_ms=safety,
    )


class SyntheticWalkForwardTests(unittest.TestCase):
    def test_explicit_reference_rolling_folds_and_disjoint_test_blocks(self):
        plan = run()
        self.assertEqual(plan.observed_candle_count, 12)
        self.assertEqual(len(plan.folds), 3)
        self.assertEqual(
            [(f.train_start, f.train_end, f.gap_start, f.gap_end,
              f.test_start, f.test_end) for f in plan.folds],
            [(0, 4, 4, 5, 5, 7),
             (2, 6, 6, 7, 7, 9),
             (4, 8, 8, 9, 9, 11)],
        )
        self.assertEqual([f.number for f in plan.folds], [1, 2, 3])
        self.assertTrue(all(f.training_bars == 4 and f.testing_bars == 2
                            and f.embargo_bars == 1 for f in plan.folds))
        self.assertTrue(all(f.train_end <= f.gap_start <= f.gap_end == f.test_start
                            for f in plan.folds))
        self.assertTrue(all(a.test_end <= b.test_start
                            for a, b in zip(plan.folds, plan.folds[1:])))
        self.assertTrue(all(f.train_available_at_ms <= f.test_first_open_ms
                            for f in plan.folds))
        self.assertEqual(plan.folds[0].train_last_closed_ms,
                         candles()[3].close_time_ms)
        self.assertEqual(plan.folds[0].test_last_closed_ms,
                         candles()[6].close_time_ms)
        self.assertEqual(plan.folds[-1].test_end, 11)  # leftover candle is not OOS
        self.assertEqual(plan.quality, "synthetic_fixture")

    def test_no_profit_backtest_or_order_permissions(self):
        result = run()
        self.assertFalse(result.financial_backtest_approved)
        self.assertFalse(result.out_of_sample_results_validated)
        self.assertFalse(result.real_market_data_verified)
        self.assertFalse(result.approved_for_live_use)
        self.assertFalse(result.orders_sent)
        self.assertFalse(hasattr(result, "pnl"))
        self.assertFalse(hasattr(result.folds[0], "sharpe"))
        with self.assertRaises(FrozenInstanceError):
            result.folds[0].test_end = 999

    def test_training_availability_safety_requires_gap(self):
        with self.assertRaisesRegex(DataValidationError, "increase gap"):
            run(settings=cfg(gap_bars=0))
        zero_safety = run(settings=cfg(gap_bars=0), safety=0)
        self.assertTrue(all(f.train_available_at_ms < f.test_first_open_ms
                            for f in zero_safety.folds))
        rows = candles()
        latest = rows[-1].close_time_ms + 1000
        self.assertEqual(run(decision=latest).decision_at_ms, latest)
        with self.assertRaises(DataValidationError):
            run(decision=latest - 1)

    def test_test_stride_must_prevent_same_oos_candle_twice(self):
        with self.assertRaises(DataValidationError):
            cfg(test_bars=3, stride_bars=2)
        with self.assertRaises(DataValidationError):
            cfg(test_bars=2, stride_bars=1)
        plan = run(settings=cfg(stride_bars=3))
        self.assertEqual([(f.test_start, f.test_end) for f in plan.folds],
                         [(5, 7), (8, 10)])
        self.assertTrue(plan.folds[0].test_end <= plan.folds[1].test_start)

    def test_earlier_test_may_become_future_training_only_after_its_time(self):
        plan = run()
        # Fold 2 rolls over earlier fold 1 test index 5; its OOS begins at 7.
        self.assertEqual(plan.folds[0].test_start, 5)
        self.assertEqual(plan.folds[1].train_end, 6)
        self.assertGreater(plan.folds[1].test_first_open_ms,
                           plan.folds[0].test_last_closed_ms)
        self.assertLess(plan.folds[1].train_available_at_ms,
                        plan.folds[1].test_first_open_ms)

    def test_incomplete_final_fold_not_inferred_or_padded(self):
        with self.assertRaisesRegex(DataValidationError, "no complete"):
            run(candles(6))
        one = run(candles(7))
        self.assertEqual(len(one.folds), 1)
        self.assertEqual((one.folds[0].train_start, one.folds[0].test_end), (0, 7))
        with self.assertRaises(DataValidationError):
            run(candles(4))

    def test_prefix_invariance_when_future_candles_change(self):
        historical = candles(12)
        future = candles(14)
        at = future[-1].close_time_ms + 1000
        original = run(historical, decision=at)
        extended = run(future, decision=at)
        changed = future[:-1] + (replace(
            future[-1], open=D(1000), high=D(1001),
            low=D(999), close=D(1000),
        ),)
        mutated = run(changed, decision=at)
        self.assertEqual(original.folds, extended.folds[:len(original.folds)])
        self.assertEqual(original.folds, mutated.folds[:len(original.folds)])
        self.assertEqual(len(original.folds), 3)
        self.assertEqual(len(extended.folds), 4)

    def test_reject_hidden_future_candle_even_if_last_fold_ignores_it(self):
        xs = candles()
        before_last = xs[-1].close_time_ms
        with self.assertRaises(DataValidationError):
            run(xs, decision=before_last + 999)
        with self.assertRaises(DataValidationError):
            run(xs[:-1] + (replace(xs[-1], quality="verified_live"),))

    def test_reject_gap_duplicate_reversal_or_mixed_source(self):
        xs = candles()
        for sample in (
            xs[:3] + xs[4:],
            xs[:4] + (xs[3],) + xs[4:],
            tuple(reversed(xs)),
        ):
            with self.subTest(length=len(sample)), self.assertRaises(
                (DataGapError, DataValidationError)
            ):
                run(sample)
        for change in (
            dict(exchange="other_venue"),
            dict(symbol="ETHUSDT"),
            dict(market="spot"),
            dict(interval="4h"),
            dict(quality="kraken_raw"),
        ):
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                run(xs[:5] + (replace(xs[5], **change),) + xs[6:])

    def test_reject_unsafe_types_nondecimal_and_timestamps(self):
        xs = candles()
        for change in (
            dict(open=D("NaN")),
            dict(high=D("Infinity")),
            dict(close=42.0),
            dict(quote_volume=-1.0),
            dict(open_time_ms=xs[5].open_time_ms + 1),
            dict(close_time_ms=xs[5].close_time_ms - 1),
        ):
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                run(xs[:5] + (replace(xs[5], **change),) + xs[6:])
        for dt in (True, -1, "tomorrow", float(xs[-1].close_time_ms + 1000)):
            with self.subTest(dt=dt), self.assertRaises(DataValidationError):
                run(decision=dt)
        for safety in (True, -1, 86_400_001):
            with self.subTest(safety=safety), self.assertRaises(DataValidationError):
                run(safety=safety)

    def test_config_limits_and_no_implicit_defaults(self):
        for changes in (
            dict(train_bars=1),
            dict(train_bars=10_001),
            dict(train_bars=True),
            dict(train_bars=4.0),
            dict(gap_bars=-1),
            dict(gap_bars=10_001),
            dict(gap_bars="1"),
            dict(test_bars=0),
            dict(test_bars=True),
            dict(stride_bars=0),
            dict(stride_bars=False),
            dict(stride_bars=10_001),
        ):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                cfg(**changes)
        with self.assertRaises(DataValidationError):
            run(settings="invalid")
        with self.assertRaises(TypeError):
            SyntheticWalkForwardConfig()  # type: ignore[call-arg]

    def test_resource_bounds_fail_closed_not_truncate(self):
        xs = candles(600)
        # Small fixed folds exceed the MAX_FOLDS bound; refuse rather than
        # silently dropping valid walk-forward samples.
        with self.assertRaisesRegex(DataValidationError, "too many"):
            run(xs, settings=cfg(train_bars=2, gap_bars=0,
                                 test_bars=1, stride_bars=1), safety=0)
        self.assertGreater(len(xs), MAX_FOLDS)

    def test_pure_offline_and_idempotent(self):
        with patch("urllib.request.urlopen",
                   side_effect=AssertionError("network should not run")):
            with patch("socket.create_connection",
                       side_effect=AssertionError("network should not run")):
                self.assertEqual(run(), run())
        self.assertFalse(run().orders_sent)


if __name__ == "__main__":
    unittest.main()
