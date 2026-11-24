"""D512 fixtures: paired archive marks, no future inputs and no invented fills."""
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j2_rest_n50_history_d461 import RestN50History
from crypto_intelligence_agent.j3_archived_strategy_comparison_d512 import (
    compare_archived_strategies,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig

HOUR = 3_600_000
START = 1_800_000_000_000
END = START + 24 * HOUR
SYMBOLS = ("BTCUSDT",) + tuple("ALT%02dUSDT" % i for i in range(49))
CFG = CompressionBreakoutConfig(FeatureConfig(2, 2, 2, 2), 2, 2,
                                Decimal("1"), Decimal("1"))


def archive(step, *, drop=False, next_shift=0, revised=False):
    # Artificial data used ONLY as test fixtures for the archive reader seam.
    # Public mode is simulated here; no such artifact is written to a journal.
    symbols = SYMBOLS if not drop else ("NEWUSDT",) + tuple(
        s for s in SYMBOLS if s != "ALT00USDT")
    rows = []
    for symbol in symbols:
        bars = []
        for i in range(step, step + 24):
            price = Decimal(100 if symbol == "BTCUSDT" else 100 + i)
            if symbol == "ALT00USDT" and i == step + 23:
                price += Decimal(next_shift)
            if revised and symbol == "ALT00USDT" and i == step + 22:
                price += Decimal(5)
            bars.append(ClosedCandle(
                exchange="bybit_v5_public", market="linear_perpetual",
                symbol=symbol, interval="1h", open_time_ms=START + i * HOUR,
                close_time_ms=START + (i + 1) * HOUR - 1,
                open=price, high=price + Decimal(1), low=price - Decimal(1),
                close=price, base_volume=Decimal(10), quote_volume=Decimal(1000),
                quality="bybit_public_rest_historical_closed_unverified",
            ))
        rows.append((symbol, tuple(bars)))
    end = END + step * HOUR
    return RestN50History("a" * 64, end, end + 1000, "b" * 64,
                          "public_rest_observed_unverified", tuple(rows))


def compare(histories, periods=(2, 3, 4), config=CFG):
    return compare_archived_strategies(
        tuple(histories), config=config, ema_periods=periods,
        reference_notional=Decimal(50),
        entry_fee_bps=Decimal(6), exit_fee_bps=Decimal(6),
        entry_slippage_bps=Decimal(3), exit_slippage_bps=Decimal(3),
        stop_distance_bps=Decimal(50), target_distances_bps=(Decimal(100), Decimal(200)),
        now_ms=END + 10 * HOUR,
    )


def known_hypothesis(series, *, config, decision_at_ms, **kwargs):
    assert all(bar.close_time_ms < decision_at_ms for bar in series.candles)
    assert series.candles[-1].close_time_ms + 1 == decision_at_ms
    # Both strategies receive exactly the same causal prefix for each slot.
    has_signal = (series.candles[-1].symbol == "ALT00USDT"
                  or config.entry_mode == "breakout")
    return SimpleNamespace(hypotheses=(
        (SimpleNamespace(side=SimpleNamespace(value="LONG")),) if has_signal else ()
    ))


class ArchivedComparisonD512Tests(unittest.TestCase):
    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_d513_custom_profile_uses_same_causal_cohort(self, evaluator):
        from crypto_intelligence_agent.j2_configurable_indicators_d513 import (
            MovingAverageSlot, IndicatorSelection, PivotSuperTrend,
        )
        off = tuple(MovingAverageSlot(False, n) for n in (10, 30, 120))
        selection = IndicatorSelection(off, (MovingAverageSlot(True, 4), *off[1:]),
                                       PivotSuperTrend(False, 2, 10, Decimal(3)))
        cfg = replace(CFG, entry_mode="indicator_combo", indicators=selection)
        result = compare([archive(0), archive(1)], config=cfg)
        self.assertEqual(evaluator.call_count, 49 * 3)
        self.assertEqual(result["results"]["indicator_combo"]["candidates"], 1)
        self.assertEqual(result["custom_indicators"], selection.as_json())
        self.assertEqual(result["common_eligible_symbol_hours"], 49)

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_same_slots_costs_and_missing_future_membership(self, evaluator):
        result = compare([archive(0), archive(1, drop=True)])
        self.assertEqual(result["paired_decision_hours"], 1)
        self.assertEqual(result["common_eligible_symbol_hours"], 49)
        self.assertEqual(evaluator.call_count, 98)
        a, b = result["results"]["breakout"], result["results"]["ema_cross"]
        self.assertEqual((a["candidates"], a["scored_marks"], a["missing_future_marks"]), (49, 48, 1))
        self.assertEqual((b["candidates"], b["scored_marks"], b["missing_future_marks"]), (1, 0, 1))
        self.assertIsNone(b["conditional_mark_before_funding_quote"])
        self.assertEqual(Decimal(a["cost_assumed_quote"]), Decimal("0.09") * 48)
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["financial_backtest_approved"])
        self.assertFalse(result["out_of_sample_results_validated"])

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_future_value_changes_outcome_not_candidates(self, evaluator):
        first = compare([archive(0), archive(1)])
        changed = compare([archive(0), archive(1, next_shift=10)])
        for mode in ("breakout", "ema_cross"):
            self.assertEqual(first["results"][mode]["candidates"],
                             changed["results"][mode]["candidates"])
            self.assertNotEqual(first["results"][mode]["gross_mark_quote"],
                                changed["results"][mode]["gross_mark_quote"])
        revised = compare([archive(0), archive(1, revised=True)])
        self.assertEqual(revised["results"]["ema_cross"]["missing_future_marks"], 1)

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_stitches_only_older_overlapping_archives_for_longer_ema(self, evaluator):
        result = compare([archive(i) for i in range(4)], periods=(2, 3, 24))
        self.assertEqual(result["required_warmup_hours"], 26)
        self.assertEqual(result["maximum_contiguous_hours_observed"], 26)
        self.assertEqual(result["common_eligible_symbol_hours"], 49)
        self.assertEqual(result["excluded_warmup_or_conflict_symbol_hours"], 98)
        self.assertEqual(result["windows"][0]["eligible_symbols"], 0)
        self.assertEqual(result["windows"][-1]["eligible_symbols"], 49)
        self.assertEqual(evaluator.call_count, 98)

    def test_insufficient_and_injected_sources_do_not_become_results(self):
        result = compare([archive(0)])
        self.assertEqual(result["status"], "insufficient_paired_archives_or_warmup")
        self.assertEqual(result["common_eligible_symbol_hours"], 0)
        self.assertIsNone(result["results"]["breakout"]["gross_mark_quote"])
        with self.assertRaises(DataValidationError):
            compare([replace(archive(0), source_mode="injected_offline_protocol_replay")])
        with self.assertRaises(DataValidationError):
            compare([archive(0), archive(0)])
        with self.assertRaises(DataValidationError):
            compare([archive(0)], periods=(4, 3, 2))


if __name__ == "__main__":
    unittest.main()
