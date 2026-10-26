"""J3/PRE1: no fabricated intrabar sequence, fills, profit or liquidation."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError, MARKET,
)
from crypto_intelligence_agent.synthetic_feature_engine import (
    validate_synthetic_closed_candles, validate_synthetic_research_price,
)
from crypto_intelligence_agent.synthetic_intrabar_barriers import (
    ObservationKind, ResearchDirection, SyntheticBarrier,
    SyntheticBarrierPlan, SyntheticBarrierObservation,
    observe_synthetic_intrabar_barriers,
)

D = Decimal
HOUR = 3_600_000
START = 40 * HOUR


def candle(i=0, *, opening="100", high="104", low="96", close="100",
           quality="synthetic_fixture", exchange="synthetic_venue",
           symbol="BTCUSDT", start=START):
    return ClosedCandle(
        exchange=exchange, market=MARKET, symbol=symbol, interval="1h",
        open_time_ms=start + i * HOUR,
        close_time_ms=start + (i+1) * HOUR - 1,
        open=D(str(opening)), high=D(str(high)), low=D(str(low)), close=D(str(close)),
        base_volume=D("1"), quote_volume=D("100"), quality=quality,
    )


def plan(*, side=ResearchDirection.LONG, entry=D(100), stop=D(95), target=D(110),
         liquidation=None, created=START-1_000):
    return SyntheticBarrierPlan(
        side=side, hypothetical_entry_price=entry, stop_level=stop,
        target_level=target, hypothetical_liquidation_level=liquidation,
        plan_created_at_ms=created,
    )


def assess(rows=None, *, p=None, as_of=None, safety=1_000):
    candles = (candle(),) if rows is None else rows
    if as_of is None:
        as_of = candles[-1].close_time_ms + safety
    return observe_synthetic_intrabar_barriers(
        plan() if p is None else p, candles,
        as_of_ms=as_of, close_safety_ms=safety,
    )


class SyntheticIntrabarBarrierTests(unittest.TestCase):
    def test_no_level_reached_is_not_profitable_position(self):
        res = assess()
        self.assertEqual(res.kind, ObservationKind.NO_LEVEL_REACHED)
        self.assertEqual(res.levels_reached, ())
        self.assertIsNone(res.first_candidate_index)
        self.assertIsNone(res.first_candidate_open_time_ms)
        self.assertEqual(res.examined_closed_candles, 1)
        self.assertFalse(res.profitable_trade_verified)

    def test_long_stop_only_is_observation_not_real_fill(self):
        res = assess((candle(low="94", high="108"),))
        self.assertEqual(res.kind, ObservationKind.SINGLE_LEVEL_RANGE)
        self.assertEqual(res.levels_reached, (SyntheticBarrier.STOP,))
        self.assertEqual(res.first_candidate_index, 0)
        self.assertFalse(res.fill_price_verified)

    def test_long_target_only_is_not_a_backtested_win(self):
        res = assess((candle(high="111", low="96"),))
        self.assertEqual(res.levels_reached, (SyntheticBarrier.TARGET,))
        self.assertEqual(res.kind, ObservationKind.SINGLE_LEVEL_RANGE)
        self.assertFalse(res.profitable_trade_verified)
        self.assertFalse(res.financial_backtest_approved)

    def test_long_target_and_stop_same_candle_order_is_unknown(self):
        res = assess((candle(high="111", low="94", close="101"),))
        self.assertEqual(res.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        self.assertEqual(res.levels_reached,
                         (SyntheticBarrier.STOP, SyntheticBarrier.TARGET))
        self.assertFalse(res.intrabar_path_verified)

    def test_favorable_close_does_not_resolve_same_candle_order(self):
        favorable = assess((candle(high="120", low="90", close="118"),))
        adverse = assess((candle(high="120", low="90", close="92"),))
        self.assertEqual(favorable.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        self.assertEqual(adverse.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        self.assertEqual(favorable.levels_reached, adverse.levels_reached)

    def test_long_gap_through_stop_does_not_assume_stop_fill_price(self):
        res = assess((candle(opening="93", high="97", low="92", close="95"),))
        self.assertEqual(res.kind, ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
        self.assertEqual(res.levels_reached, (SyntheticBarrier.STOP,))
        self.assertFalse(res.fill_price_verified)

    def test_long_gap_through_target_does_not_assume_limit_fill(self):
        res = assess((candle(opening="112", high="114", low="107", close="110"),))
        self.assertEqual(res.kind, ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
        self.assertEqual(res.levels_reached, (SyntheticBarrier.TARGET,))
        self.assertFalse(res.profitable_trade_verified)

    def test_long_open_exactly_on_stop_or_target_is_open_observation(self):
        for row, level in (
            (candle(opening="95", high="100", low="94", close="97"),
             SyntheticBarrier.STOP),
            (candle(opening="110", high="112", low="109", close="110"),
             SyntheticBarrier.TARGET),
        ):
            with self.subTest(level=level):
                res = assess((row,))
                self.assertEqual(res.kind, ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
                self.assertEqual(res.levels_reached, (level,))

    def test_short_stop_only_mirrors_long_adverse_side(self):
        p = plan(side=ResearchDirection.SHORT, stop=D(105), target=D(90))
        res = assess((candle(high="106", low="96"),), p=p)
        self.assertEqual(res.levels_reached, (SyntheticBarrier.STOP,))
        self.assertEqual(res.kind, ObservationKind.SINGLE_LEVEL_RANGE)

    def test_short_target_only_mirrors_long_favorable_side(self):
        p = plan(side=ResearchDirection.SHORT, stop=D(105), target=D(90))
        res = assess((candle(high="104", low="89"),), p=p)
        self.assertEqual(res.levels_reached, (SyntheticBarrier.TARGET,))
        self.assertFalse(res.profitable_trade_verified)

    def test_short_stop_and_target_touched_same_candle_ambiguous(self):
        p = plan(side=ResearchDirection.SHORT, stop=D(105), target=D(90))
        res = assess((candle(high="106", low="89", close="92"),), p=p)
        self.assertEqual(res.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        self.assertEqual(res.levels_reached,
                         (SyntheticBarrier.STOP, SyntheticBarrier.TARGET))

    def test_short_gap_open_at_or_beyond_both_directions(self):
        p = plan(side=ResearchDirection.SHORT, stop=D(105), target=D(90))
        adverse = assess((candle(opening="106", high="108", low="99", close="103"),), p=p)
        favorable = assess((candle(opening="89", high="101", low="88", close="98"),), p=p)
        self.assertEqual(adverse.kind, ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
        self.assertEqual(adverse.levels_reached, (SyntheticBarrier.STOP,))
        self.assertEqual(favorable.levels_reached, (SyntheticBarrier.TARGET,))

    def test_hypothetical_liquidation_and_target_same_bar_not_a_win(self):
        p = plan(liquidation=D("97"))
        res = assess((candle(high="112", low="96", close="108"),), p=p)
        self.assertEqual(res.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        self.assertEqual(res.levels_reached,
                         (SyntheticBarrier.TARGET, SyntheticBarrier.HYPOTHETICAL_LIQUIDATION))
        self.assertFalse(res.liquidation_formula_verified)
        self.assertFalse(res.profitable_trade_verified)

    def test_hypothetical_liquidation_and_stop_same_bar_not_ordered(self):
        p = plan(liquidation=D("94"))
        res = assess((candle(high="104", low="93", close="99"),), p=p)
        self.assertEqual(res.levels_reached,
                         (SyntheticBarrier.STOP, SyntheticBarrier.HYPOTHETICAL_LIQUIDATION))
        self.assertEqual(res.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)

    def test_gap_opens_past_stop_and_liquidation_simultaneously(self):
        p = plan(liquidation=D("97"))
        res = assess((candle(opening="93", high="98", low="92", close="96"),), p=p)
        self.assertEqual(res.kind, ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
        self.assertEqual(res.levels_reached,
                         (SyntheticBarrier.STOP, SyntheticBarrier.HYPOTHETICAL_LIQUIDATION))
        self.assertFalse(res.intrabar_path_verified)

    def test_hypothetical_liquidation_only_not_real_margin_call(self):
        p = plan(liquidation=D("97"))
        res = assess((candle(low="96", high="108"),), p=p)
        self.assertEqual(res.levels_reached,
                         (SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,))
        self.assertFalse(res.liquidation_formula_verified)

    def test_short_hypothetical_liquidation_and_target_are_ambiguous(self):
        p = plan(side=ResearchDirection.SHORT, stop=D(105),
                 target=D(90), liquidation=D(103))
        res = assess((candle(high="104", low="89", close="91"),), p=p)
        self.assertEqual(res.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        self.assertEqual(res.levels_reached,
                         (SyntheticBarrier.TARGET, SyntheticBarrier.HYPOTHETICAL_LIQUIDATION))

    def test_first_candle_no_hit_later_target_is_first_observable(self):
        rows = (candle(0), candle(1, high="111", low="96"),
                candle(2, high="112", low="90"))
        res = assess(rows)
        self.assertEqual(res.kind, ObservationKind.SINGLE_LEVEL_RANGE)
        self.assertEqual(res.levels_reached, (SyntheticBarrier.TARGET,))
        self.assertEqual(res.first_candidate_index, 1)
        self.assertEqual(res.examined_closed_candles, 2)
        self.assertEqual(res.available_closed_candles, 3)
        self.assertEqual(res.first_candidate_open_time_ms, rows[1].open_time_ms)
        self.assertEqual(res.first_candidate_close_time_ms, rows[1].close_time_ms)

    def test_future_bar_is_rejected_even_if_earlier_bar_has_target(self):
        rows = (candle(0, high="111"), candle(1))
        with self.assertRaisesRegex(DataValidationError, "future or unclosed"):
            assess(rows, as_of=rows[0].close_time_ms + 1_000)

    def test_all_bars_without_hits_are_reported_not_synthetic_losses(self):
        rows = (candle(0), candle(1), candle(2))
        res = assess(rows)
        self.assertEqual(res.kind, ObservationKind.NO_LEVEL_REACHED)
        self.assertEqual(res.examined_closed_candles, 3)
        self.assertEqual(res.available_closed_candles, 3)

    def test_plan_created_after_first_bar_open_fails_even_if_candle_closed(self):
        with self.assertRaisesRegex(DataValidationError, "cannot start after"):
            assess(p=plan(created=START+1))
        res = assess(p=plan(created=START))
        self.assertEqual(res.plan_created_at_ms, START)

    def test_close_safety_boundary_is_enforced(self):
        row = candle()
        assess((row,), as_of=row.close_time_ms+1_000)
        with self.assertRaises(DataValidationError):
            assess((row,), as_of=row.close_time_ms+999)
        with self.assertRaises(DataValidationError):
            assess((row,), as_of=row.close_time_ms+1_000, safety=1_001)

    def test_gap_duplicate_and_reverse_candles_fail_closed(self):
        cs = (candle(0), candle(1), candle(2))
        for rows in ((cs[0], cs[2]), (cs[0], cs[0]), (cs[2], cs[1], cs[0])):
            with self.subTest(rows=rows), self.assertRaises(
                (DataGapError, DataValidationError)
            ):
                assess(rows)

    def test_mixed_provider_market_interval_or_quality_is_rejected(self):
        start = candle(0)
        for mutated in (
            replace(candle(1), exchange="other"),
            replace(candle(1), symbol="ETHUSDT"),
            replace(candle(1), interval="4h"),
            replace(candle(1), market="spot"),
            replace(candle(1), quality="observed_unverified"),
        ):
            with self.subTest(mutated=mutated), self.assertRaises(DataValidationError):
                assess((start, mutated))
        with self.assertRaises(DataValidationError):
            assess((replace(start, quality="staging_kraken"),))

    def test_invalid_price_and_extrema_cannot_pass_candle_validation(self):
        valid = candle()
        for field, bad in (
            ("high", D(99)), ("low", D(101)), ("open", D("NaN")),
            ("close", D(0)), ("high", float(110)), ("low", True),
        ):
            with self.subTest(field=field, bad=bad), self.assertRaises(DataValidationError):
                assess((replace(valid, **{field: bad}),))

    def test_invalid_side_and_invalid_levels_rejected(self):
        for s in ("LONG", "SHORT", None, True, 0):
            with self.subTest(s=s), self.assertRaises(DataValidationError):
                plan(side=s)
        for field, bad in (
            ("entry", D(0)), ("entry", D("-1")), ("stop", D("NaN")),
            ("stop", float(95)), ("target", True), ("target", D("Infinity")),
            ("stop", D("1e-25")), ("entry", D("1e36")), ("target", "110"),
        ):
            with self.subTest(field=field, value=bad), self.assertRaises(DataValidationError):
                plan(**{field: bad})
        for value in (0, True, None, "180000", 2.5):
            with self.subTest(created=value), self.assertRaises(DataValidationError):
                plan(created=value)

    def test_reject_wrong_bracket_order_for_long_and_short(self):
        for pair in ((D(100), D(110)), (D(90), D(100)),
                     (D(100), D(100)), (D(110), D(90))):
            with self.subTest(pair=pair), self.assertRaises(DataValidationError):
                plan(stop=pair[0], target=pair[1])
        p = plan(side=ResearchDirection.SHORT, stop=D(105), target=D(90))
        self.assertEqual(p.side, ResearchDirection.SHORT)
        with self.assertRaises(DataValidationError):
            plan(side=ResearchDirection.SHORT, stop=D(95), target=D(110))

    def test_hypothetical_liquidation_must_be_distinct_and_adverse(self):
        for level in (D(95), D(100), D(110), D("NaN"),
                      D("Infinity"), float(96), True):
            with self.subTest(level=level), self.assertRaises(DataValidationError):
                plan(liquidation=level)
        for level in (D(105), D(100), D(90)):
            with self.subTest(level=level), self.assertRaises(DataValidationError):
                plan(side=ResearchDirection.SHORT, stop=D(105),
                     target=D(90), liquidation=level)

    def test_wrong_input_types_and_invalid_decision_time_rejected(self):
        with self.assertRaises(DataValidationError):
            observe_synthetic_intrabar_barriers({"side": "LONG"}, (candle(),),
                                               as_of_ms=START+HOUR+1_000)
        with self.assertRaises(DataValidationError):
            observe_synthetic_intrabar_barriers(plan(), (), as_of_ms=START+HOUR+1_000)
        with self.assertRaises(DataValidationError):
            assess((candle(),), as_of=True)
        with self.assertRaises(DataValidationError):
            assess((candle(),), safety=-1)
        with self.assertRaises(DataValidationError):
            assess((candle(),), safety=True)

    def test_decimal_comparison_independent_of_caller_precision(self):
        c = candle(opening="100.000000000000001",
                   high="110.000000000000001", low="96.123456789",
                   close="102.000000000000001")
        p = plan(entry=D(100), stop=D(95), target=D("110.000000000000000"))
        with localcontext() as context:
            context.prec = 3
            a = assess((c,), p=p)
        with localcontext() as context:
            context.prec = 150
            b = assess((c,), p=p)
        self.assertEqual(a, b)
        self.assertEqual(a.levels_reached, (SyntheticBarrier.TARGET,))

    def test_output_does_not_expose_fill_prices_and_has_fixed_false_flags(self):
        res = assess((candle(high="111"),))
        self.assertIsInstance(res, SyntheticBarrierObservation)
        self.assertEqual(res.quality, "synthetic_intrabar_observation_only")
        for name in (
            "intrabar_path_verified", "fill_price_verified", "liquidation_formula_verified",
            "profitable_trade_verified", "financial_backtest_approved",
            "approved_for_live_use", "orders_sent",
        ):
            self.assertIs(getattr(res, name), False)
            with self.subTest(flag=name), self.assertRaises(TypeError):
                replace(res, **{name: True})
            with self.subTest(flag=name), self.assertRaises(FrozenInstanceError):
                setattr(res, name, True)
        with self.assertRaises(TypeError):
            replace(res, quality="live")
        with self.assertRaises(FrozenInstanceError):
            res.kind = ObservationKind.NO_LEVEL_REACHED
        for attr in ("profit", "pnl", "fill_price", "fee", "slippage",
                     "funding", "liquidation_price", "order_id", "signal"):
            self.assertFalse(hasattr(res, attr))

    def test_public_candle_validator_reuses_causal_j2_contract(self):
        c = candle()
        got = validate_synthetic_closed_candles(
            [c], decision_at_ms=c.close_time_ms+1000,
        )
        self.assertEqual(got, (c,))
        self.assertIs(type(got), tuple)
        validate_synthetic_research_price(D("10.5"), "test")
        with self.assertRaises(DataValidationError):
            validate_synthetic_research_price(10.5, "test")


    def test_cross_module_cost_receipt_cannot_certify_intrabar_fill_or_profit(self):
        """Cost arithmetic and ambiguous OHLC remain separate evidence."""
        from crypto_intelligence_agent.synthetic_cost_scenarios import (
            SyntheticCostScenario, evaluate_synthetic_costs,
        )
        observation = assess(
            rows=(candle(high="112", low="94"),),
            p=plan(stop=D("95"), target=D("110")),
        )
        self.assertEqual(observation.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        costs = evaluate_synthetic_costs(SyntheticCostScenario(
            direction=ResearchDirection.LONG,
            entry_at_ms=START,
            exit_at_ms=START+HOUR,
            entry_hypothetical_notional_quote_units=D("1000"),
            exit_hypothetical_notional_quote_units=D("1000"),
            entry_fee_bps=D("10"),
            exit_fee_bps=D("10"),
            entry_adverse_slippage_bps=D("5"),
            exit_adverse_slippage_bps=D("5"),
        ))
        self.assertEqual(costs.total_signed_cost_units, D("3"))
        self.assertFalse(costs.fill_price_verified)
        self.assertFalse(costs.net_pnl_verified)
        self.assertFalse(observation.intrabar_path_verified)
        self.assertFalse(observation.financial_backtest_approved)
        self.assertFalse(observation.profitable_trade_verified)

    def test_cross_module_liquidation_collision_does_not_resolve_with_costs(self):
        from crypto_intelligence_agent.synthetic_cost_scenarios import (
            SyntheticCostScenario, evaluate_synthetic_costs,
        )
        for side, row, p in (
            (ResearchDirection.LONG, candle(high="112", low="89"),
             plan(liquidation=D("90"))),
            (ResearchDirection.SHORT, candle(high="111", low="88"),
             plan(side=ResearchDirection.SHORT, stop=D("105"),
                  target=D("90"), liquidation=D("110"))),
        ):
            with self.subTest(side=side):
                obs = assess(rows=(row,), p=p)
                self.assertEqual(obs.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
                self.assertIn(SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,
                              obs.levels_reached)
                costs = evaluate_synthetic_costs(SyntheticCostScenario(
                    direction=side, entry_at_ms=START, exit_at_ms=START+HOUR,
                    entry_hypothetical_notional_quote_units=D("100"),
                    exit_hypothetical_notional_quote_units=D("100"),
                    entry_fee_bps=D("0"), exit_fee_bps=D("0"),
                    entry_adverse_slippage_bps=D("0"),
                    exit_adverse_slippage_bps=D("0"),
                ))
                self.assertEqual(costs.total_signed_cost_units, D(0))
                self.assertFalse(obs.liquidation_formula_verified)
                self.assertFalse(costs.financial_backtest_approved)
                self.assertFalse(costs.fill_price_verified)

    def test_no_network_storage_or_real_order_dependencies(self):
        text = (Path(__file__).resolve().parent.parent
                / "crypto_intelligence_agent/synthetic_intrabar_barriers.py").read_text()
        for forbidden in ("urllib.request", "requests.", "socket", "sqlite3",
                          "open(", "create_order(", "send_order(", "subprocess",
                          "futures.kraken.com", "api.hyperliquid.xyz"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
