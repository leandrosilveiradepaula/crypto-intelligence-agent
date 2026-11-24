"""Tests exercise actual observed D435 decisions, not merely form fields."""
from dataclasses import replace
from decimal import Decimal
import unittest

from crypto_intelligence_agent.j2_configurable_indicators_d513 import (
    MovingAverageSlot, PivotSuperTrend, IndicatorSelection,
    moving_average, pivot_trend, combination_directions, parse_indicator_selection,
)
from crypto_intelligence_agent.j2_observed_bybit_research import evaluate_observed_bybit_research
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_j2_ema_cross_d503 import CONFIG, case

D = Decimal
OFF = tuple(MovingAverageSlot(False, n) for n in (10, 30, 120))
PIVOT_OFF = PivotSuperTrend(False, 50, 120, D(3))


def sma_only(period=10):
    return IndicatorSelection(OFF, (MovingAverageSlot(True, period), *OFF[1:]), PIVOT_OFF)


class ConfigurableIndicatorsD513Tests(unittest.TestCase):
    def test_decimal_sma_and_ema_are_different_after_seed(self):
        prices = tuple(map(D, ("2", "4", "6", "10", "8")))
        sma = moving_average(prices, 3, exponential=False)
        ema = moving_average(prices, 3, exponential=True)
        self.assertEqual(sma[:3], (None, None, D(4)))
        self.assertEqual(ema[:3], sma[:3])
        self.assertEqual(ema[3], D(7))
        self.assertEqual(sma[4], D(8))
        self.assertEqual(ema[4], D("7.5"))

    def test_only_sma_operates_without_ema_or_pivot_warmup(self):
        selection = sma_only()
        self.assertEqual(selection.minimum_closed_bars(2), 24)
        config = replace(CONFIG, entry_mode="indicator_combo", indicators=selection,
                         compression_bars=200, baseline_bars=200)
        for price, expected in (("113", SyntheticSide.LONG), ("87", SyntheticSide.SHORT)):
            with self.subTest(price=price):
                series, now = case(price, bars=24)
                result = evaluate_observed_bybit_research(series, config=config, decision_at_ms=now)
                self.assertEqual(len(result.hypotheses), 1)
                h = result.hypotheses[0]
                self.assertEqual(h.side, expected)
                self.assertEqual(h.entry_rule, "indicator_combo")
                self.assertIsNone(h.ema_close)
                self.assertFalse(h.orders_sent)

    def test_all_disabled_and_insufficient_enabled_period_abstain(self):
        series, now = case("113", bars=24)
        for selection in (IndicatorSelection(OFF, OFF, PIVOT_OFF), sma_only(60)):
            with self.subTest(selection=selection):
                cfg = replace(CONFIG, entry_mode="indicator_combo", indicators=selection)
                result = evaluate_observed_bybit_research(series, config=cfg, decision_at_ms=now)
                self.assertEqual(result.hypotheses, ())

    def test_confirmed_pivot_no_repaint_and_direction_changes(self):
        source, _ = case("100", bars=24)
        cs = tuple(replace(c, open=D(p), close=D(p), high=D(p)+1, low=D(p)-1)
                   for c, p in zip(source.candles, (100, 105, 101, 99, 108, 90)))
        policy = PivotSuperTrend(True, 1, 1, D("0.1"))
        result = pivot_trend(cs, policy)
        self.assertEqual(result[:3], (None, None, 0))
        self.assertEqual(result[3:], (-1, 1, -1))
        for i in range(1, len(cs)+1):
            self.assertEqual(pivot_trend(cs[:i], policy), result[:i])
        selection = IndicatorSelection(OFF, OFF, policy)
        self.assertEqual(combination_directions(cs, selection), result)

    def test_pivot_only_reaches_the_existing_observed_evaluator(self):
        source, now = case("100", bars=24)
        tail = tuple(replace(c, open=D(p), close=D(p), high=D(p)+1, low=D(p)-1)
                     for c, p in zip(source.candles[-6:], (100, 105, 101, 99, 108, 90)))
        series = replace(source, candles=source.candles[:-6]+tail)
        selection = IndicatorSelection(OFF, OFF, PivotSuperTrend(True, 1, 1, D("0.1")))
        cfg = replace(CONFIG, entry_mode="indicator_combo", indicators=selection)
        out = evaluate_observed_bybit_research(series, config=cfg, decision_at_ms=now)
        self.assertEqual(len(out.hypotheses), 1)
        self.assertEqual(out.hypotheses[0].side, SyntheticSide.SHORT)
        self.assertIsNone(out.hypotheses[0].ema_close)

    def test_conflicting_families_do_not_emit_direction(self):
        source, _ = case("100", bars=24)
        cs = tuple(replace(c, open=D(p), close=D(p), high=D(p)+1, low=D(p)-1)
                   for c, p in zip(source.candles, (100, 110, 120, 130, 125, 124)))
        ema = (MovingAverageSlot(True, 4), *OFF[1:])
        sma = (MovingAverageSlot(True, 2), *OFF[1:])
        self.assertEqual(combination_directions(cs, IndicatorSelection(ema, OFF, PIVOT_OFF))[-1], 1)
        self.assertEqual(combination_directions(cs, IndicatorSelection(OFF, sma, PIVOT_OFF))[-1], -1)
        self.assertEqual(combination_directions(cs, IndicatorSelection(ema, sma, PIVOT_OFF))[-1], 0)

    def test_profile_roundtrip_and_bad_values(self):
        value = sma_only().as_json()
        self.assertEqual(parse_indicator_selection(value), sma_only())
        value["sma"][0]["enabled"] = "false"
        with self.assertRaises(DataValidationError):
            parse_indicator_selection(value)
        with self.assertRaises(DataValidationError):
            replace(CONFIG, entry_mode="indicator_combo", indicators=None)


if __name__ == "__main__":
    unittest.main()
