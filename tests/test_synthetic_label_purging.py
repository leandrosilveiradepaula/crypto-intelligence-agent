"""J3/PRE4: deterministic future-horizon constraints, never financial labels."""
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import ClosedCandle, MARKET, DataValidationError
from crypto_intelligence_agent.synthetic_walk_forward import (
    SyntheticWalkForwardConfig, plan_synthetic_walk_forward,
)
from crypto_intelligence_agent.synthetic_label_purging import (
    SyntheticLabelHorizonConfig, purge_synthetic_label_horizons,
)

D = Decimal
H = 3_600_000


def candles(n=12):
    return tuple(ClosedCandle(
        exchange="synthetic_venue", market=MARKET, symbol="BTCUSDT",
        interval="1h", open_time_ms=(40+i)*H,
        close_time_ms=(41+i)*H-1, open=D(100+i),
        high=D(101+i), low=D(99+i), close=D(100+i),
        base_volume=D(1), quote_volume=D(100),
        quality="synthetic_fixture",
    ) for i in range(n))


def evaluate(n=12, horizon=1, *, safety=1000, gap=1):
    cs = candles(n)
    p = plan_synthetic_walk_forward(
        cs, config=SyntheticWalkForwardConfig(
            train_bars=4, gap_bars=gap, test_bars=2, stride_bars=2,
        ), decision_at_ms=cs[-1].close_time_ms+safety,
        close_safety_ms=safety,
    )
    return purge_synthetic_label_horizons(
        cs, plan=p, config=SyntheticLabelHorizonConfig(horizon)
    )


class PurgedLabelHorizonTests(unittest.TestCase):
    def test_three_fold_reference_horizon_one(self):
        result = evaluate()
        self.assertEqual([f.train_indices for f in result.folds],
                         [(0, 1, 2), (2, 3, 4), (4, 5, 6)])
        self.assertEqual([f.purged_train_indices for f in result.folds],
                         [(3,), (5,), (7,)])
        self.assertEqual([f.oos_indices for f in result.folds],
                         [(5,), (7,), (9,)])
        self.assertEqual([f.censored_oos_indices for f in result.folds],
                         [(6,), (8,), (10,)])
        self.assertFalse(result.financial_backtest_approved)
        self.assertFalse(result.out_of_sample_results_validated)
        self.assertFalse(result.approved_for_live_use)
        self.assertFalse(result.orders_sent)

    def test_long_horizon_censors_entire_short_test(self):
        with self.assertRaisesRegex(DataValidationError, "no eligible"):
            evaluate(horizon=2)

    def test_gap_zero_and_safety_zero_still_purges_future_labels(self):
        result = evaluate(safety=0, gap=0)
        self.assertEqual(result.folds[0].train_indices, (0, 1, 2))
        self.assertEqual(result.folds[0].purged_train_indices, (3,))
        self.assertEqual(result.folds[0].oos_indices, (4,))

    def test_invalid_horizon_types_and_bounds(self):
        for value in (0, -1, 10_001, True, 1.0, "1", None):
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                SyntheticLabelHorizonConfig(value)

    def test_reject_stale_forged_and_mismatched_plan(self):
        cs = candles()
        p = plan_synthetic_walk_forward(
            cs, config=SyntheticWalkForwardConfig(4, 1, 2, 2),
            decision_at_ms=cs[-1].close_time_ms+1000,
        )
        h = SyntheticLabelHorizonConfig(1)
        with self.assertRaises(DataValidationError):
            purge_synthetic_label_horizons(
                cs, plan=replace(p, observed_candle_count=13), config=h)
        with self.assertRaises(DataValidationError):
            purge_synthetic_label_horizons(
                cs, plan=replace(p, folds=p.folds[:-1]), config=h)
        with self.assertRaises(DataValidationError):
            purge_synthetic_label_horizons(
                cs, plan=p, config="one")
        with self.assertRaises(DataValidationError):
            purge_synthetic_label_horizons(
                cs[:-1], plan=p, config=h)
        changed = cs[:8] + (replace(cs[8], exchange="other"),) + cs[9:]
        with self.assertRaises(DataValidationError):
            purge_synthetic_label_horizons(changed, plan=p, config=h)

    def test_offline_determinism_and_no_execution(self):
        with patch("urllib.request.urlopen",
                   side_effect=AssertionError("unexpected network")):
            self.assertEqual(evaluate(), evaluate())


if __name__ == "__main__":
    unittest.main()
