"""J3/PRE7: causal OOS research integration; no actual fills or orders."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataValidationError, MARKET,
)
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticCostScenario
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_financial_scenarios import (
    ConditionalFinancialScenario, ScenarioResolution,
)
from crypto_intelligence_agent.synthetic_intrabar_barriers import (
    ObservationKind, ResearchDirection, SyntheticBarrier, SyntheticBarrierPlan,
)
from crypto_intelligence_agent.synthetic_label_purging import SyntheticLabelHorizonConfig
from crypto_intelligence_agent.synthetic_research_cycle import (
    SyntheticResearchCycleConfig, run_synthetic_research_cycle,
)
from crypto_intelligence_agent.synthetic_walk_forward import SyntheticWalkForwardConfig

D, H = Decimal, 3_600_000
LONG_ROWS = (
    ("100", "110", "90", "10"), ("101", "111", "91", "10"),
    ("101", "102", "100", "10"), ("101", "102", "100", "10"),
    ("101", "102", "100", "10"), ("105", "106", "101", "50"),
    ("111", "112", "104", "100"),
)
SHORT_ROWS = (
    ("100", "110", "90", "10"), ("99", "109", "89", "10"),
    ("99", "100", "98", "10"), ("99", "100", "98", "10"),
    ("99", "100", "98", "10"), ("95", "99", "94", "50"),
    ("90", "96", "89", "100"),
)


def candles(n=12, *, source=LONG_ROWS):
    rows = list(source)
    while len(rows) < n:
        close = rows[-1][0]
        rows.append((close, str(D(close) + 1), str(D(close) - 1), "10"))
    return tuple(
        ClosedCandle(
            "fixture_exchange", MARKET, "BTCUSDT", "1h",
            (10 + i) * H, (11 + i) * H - 1,
            D(close), D(high), D(low), D(close),
            D(1), D(volume), "synthetic_fixture",
        )
        for i, (close, high, low, volume) in enumerate(rows[:n])
    )


def config(safety=1000, *, test_bars=4, horizon=3):
    return SyntheticResearchCycleConfig(
        CompressionBreakoutConfig(
            FeatureConfig(2, 2, 2, 2), 2, 2, D("0.6"), D(2), 1,
        ),
        SyntheticWalkForwardConfig(4, 1, test_bars, test_bars),
        SyntheticLabelHorizonConfig(horizon),
        safety,
    )


def cycle(rows, *, safety=1000, plans=None, scenarios=None,
          test_bars=4, horizon=3):
    return run_synthetic_research_cycle(
        rows, config=config(safety, test_bars=test_bars, horizon=horizon),
        decision_at_ms=rows[-1].close_time_ms + safety,
        barrier_plans={} if plans is None else plans,
        financial_scenarios={} if scenarios is None else scenarios,
    )


def plan_for(event, *, side=ResearchDirection.LONG):
    if side is ResearchDirection.LONG:
        entry, stop, target = D(105), D(100), D(110)
    else:
        entry, stop, target = D(95), D(100), D(90)
    return SyntheticBarrierPlan(
        side, entry, stop, target, event.candidate_available_at_ms,
    )


def branch(event, rows, *, side=ResearchDirection.LONG,
           barrier=SyntheticBarrier.TARGET, exit_price=None,
           entry_timestamp=None, identity="fixture_financial_cycle"):
    entry = D(105) if side is ResearchDirection.LONG else D(95)
    if exit_price is None:
        exit_price = D(110) if side is ResearchDirection.LONG else D(90)
    if entry_timestamp is None:
        entry_timestamp = rows[event.first_eligible_candle_index].open_time_ms
    exit_at = rows[event.first_eligible_candle_index].open_time_ms + 1
    costs = SyntheticCostScenario(
        side, entry_timestamp, exit_at, entry * 2,
        exit_price * 2, D(0), D(0), D(0), D(0),
    )
    return ConditionalFinancialScenario(
        identity, "fixture_exchange", "BTCUSDT", "1h", side,
        barrier, entry, D(2), ScenarioResolution.EXPLICIT_EXIT,
        exit_price, None, "SYNTHETIC_QUOTE", costs,
    )


class SyntheticResearchCycleTests(unittest.TestCase):
    def test_close_safety_skips_next_open_and_replays_financial_branch(self):
        rows = candles()
        baseline = cycle(rows)
        event = baseline.events[0]
        self.assertEqual((event.fold_number, event.candidate_index), (1, 5))
        self.assertEqual(event.first_eligible_candle_index, 7)
        self.assertEqual(event.observation_end_exclusive_index, 9)
        self.assertEqual(event.abstention_reason, "missing_explicit_barrier_plan")
        plan = plan_for(event)
        result = cycle(rows, plans={5: plan},
                       scenarios={5: (branch(event, rows),)})
        self.assertEqual(result.events[0].barrier_observation.kind,
                         ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
        self.assertEqual(result.events[0].conditional_results[0]
                         .gross_price_movement_quote_units, D(10))
        self.assertEqual(result, cycle(rows, plans={5: plan},
                                       scenarios={5: (branch(event, rows),)}))
        self.assertEqual(result.signal_count, 1)
        self.assertEqual(result.j2_abstention_count, 0)
        self.assertEqual(result.pre7_refusal_count, 0)
        self.assertEqual(result.conditional_branch_count, 1)

    def test_zero_safety_can_use_immediate_next_bar(self):
        rows = candles()
        self.assertEqual(cycle(rows, safety=0).events[0].first_eligible_candle_index, 6)
        self.assertEqual(cycle(rows, safety=1000).events[0].first_eligible_candle_index, 7)

    def test_short_fixture_has_separate_directional_scenario(self):
        rows = candles(source=SHORT_ROWS)
        event = cycle(rows).events[0]
        self.assertEqual(event.candidate_index, 5)
        self.assertEqual(event.first_eligible_candle_index, 7)
        r = cycle(rows, plans={5: plan_for(event, side=ResearchDirection.SHORT)},
                  scenarios={5: (branch(event, rows, side=ResearchDirection.SHORT),)})
        self.assertEqual(r.events[0].conditional_results[0]
                         .gross_price_movement_quote_units, D(10))
        self.assertFalse(r.net_pnl_verified)

    def test_unordered_stop_and_target_require_explicit_distinct_branches(self):
        rows = candles()
        rows = rows[:7] + (
            replace(rows[7], open=D(105), close=D(105), high=D(112), low=D(98)),
        ) + rows[8:]
        event = cycle(rows).events[0]
        target = branch(event, rows)
        stop = branch(event, rows, barrier=SyntheticBarrier.STOP,
                      exit_price=D(100), identity="fixture_financial_stop")
        r = cycle(rows, plans={5: plan_for(event)}, scenarios={5: (target, stop)})
        self.assertEqual(r.conditional_branch_count, 2)
        results = r.events[0].conditional_results
        self.assertEqual(r.events[0].barrier_observation.kind,
                         ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        self.assertEqual({x.assumed_barrier for x in results},
                         {SyntheticBarrier.TARGET, SyntheticBarrier.STOP})
        self.assertEqual([x.conditional_net_quote_units for x in results],
                         [D(10), D(-10)])
        with self.assertRaisesRegex(DataValidationError, "cover"):
            cycle(rows, plans={5: plan_for(event)},
                  scenarios={5: (target,)})

    def test_short_two_bar_oos_excludes_next_fold_and_future_bars(self):
        rows = candles(n=12)
        result = cycle(rows, safety=1000, test_bars=2, horizon=1)
        event = result.events[0]
        self.assertEqual(event.candidate_index, 5)
        self.assertEqual(event.observation_end_exclusive_index, 7)
        self.assertIsNone(event.first_eligible_candle_index)
        self.assertEqual(event.abstention_reason,
                         "no_eligible_candle_within_oos_horizon")
        # Bars 7+ belong to subsequent folds and cannot rescue this event.
        changed = rows[:7] + (
            replace(rows[7], high=D(200), close=D(200), open=D(200)),
        ) + rows[8:]
        other = cycle(changed, safety=1000, test_bars=2, horizon=1)
        self.assertEqual(event, other.events[0])

    def test_no_future_bar_inside_oos_abstains_with_safety(self):
        rows = candles(n=7)
        report = cycle(rows, test_bars=2, horizon=1)
        self.assertEqual(report.events[0].abstention_reason,
                         "no_eligible_candle_within_oos_horizon")
        self.assertIsNone(report.events[0].barrier_observation)
        self.assertEqual(report.pre7_refusal_count, 1)
        for name in (
            "approved_for_live_use", "orders_sent", "financial_backtest_approved",
            "out_of_sample_results_validated", "net_pnl_verified",
        ):
            self.assertFalse(getattr(report, name))

    def test_no_reached_barrier_within_horizon_does_not_scan_later_candles(self):
        rows = candles()
        # Candidate i=5; under safety=1000, only bars 7 and 8 are
        # eligible. A later extreme at i=9 must not create an OOS branch.
        rows = (rows[:7] + tuple(
            replace(rows[i], open=D(105), close=D(105),
                    low=D(104), high=D(106)) for i in (7, 8)
        ) + (replace(rows[9], open=D(120), close=D(120),
                     low=D(119), high=D(121)),) + rows[10:])
        candidate = cycle(rows).events[0]
        r = cycle(rows, plans={5: plan_for(candidate)})
        self.assertEqual(r.events[0].abstention_reason,
                         "no_barrier_reached_within_oos_horizon")
        self.assertEqual(r.conditional_branch_count, 0)

    def test_missing_explicit_financial_premise_abstains(self):
        rows = candles()
        candidate = cycle(rows).events[0]
        r = cycle(rows, plans={5: plan_for(candidate)})
        self.assertEqual(r.events[0].abstention_reason,
                         "missing_explicit_financial_assumption")
        self.assertEqual(r.conditional_branch_count, 0)
        self.assertEqual(r.signal_count, 1)
        self.assertEqual(r.pre7_refusal_count, 1)

    def test_barrier_binding_and_financial_entry_time_must_be_causal(self):
        rows = candles()
        event = cycle(rows).events[0]
        mismatched = SyntheticBarrierPlan(
            ResearchDirection.LONG, D(106), D(100), D(110),
            event.candidate_available_at_ms,
        )
        with self.assertRaises(DataValidationError):
            cycle(rows, plans={5: mismatched})
        invalid_entry = branch(
            event, rows, entry_timestamp=event.candidate_available_at_ms,
        )
        with self.assertRaisesRegex(DataValidationError, "first eligible OOS open"):
            cycle(rows, plans={5: plan_for(event)},
                  scenarios={5: (invalid_entry,)})

    def test_non_candidate_or_ill_typed_assumptions_fail_closed(self):
        rows = candles()
        event = cycle(rows).events[0]
        valid = plan_for(event)
        for mapping in ({99: valid}, {True: valid}, {"5": valid}, {5: "fake"}):
            with self.subTest(mapping=mapping), self.assertRaises(DataValidationError):
                cycle(rows, plans=mapping)
        with self.assertRaises(DataValidationError):
            cycle(rows, scenarios={5: (branch(event, rows),)})
        with self.assertRaises(DataValidationError):
            cycle(rows, plans={5: valid}, scenarios={5: ()})
        with self.assertRaises(DataValidationError):
            cycle(rows, plans={5: valid}, scenarios={5: (None,)})
        with self.assertRaises(DataValidationError):
            cycle(rows, plans={5: valid}, scenarios={99: (branch(event, rows),)})

    def test_no_network_orders_and_replay_stability(self):
        rows = candles()
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                self.assertEqual(cycle(rows), cycle(rows))
        with self.assertRaises(DataValidationError):
            cycle(rows, safety=True)
        with self.assertRaises(DataValidationError):
            cycle(rows, safety=1.5)


if __name__ == "__main__":
    unittest.main()
