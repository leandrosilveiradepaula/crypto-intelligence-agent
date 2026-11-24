"""D517 conditional OHLC exit replay; no invented fill timestamps."""
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import (
    compare_exit_scenarios, empty_replay_totals, accumulate_replay, summarize_replay,
)
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import PaperEntryExitPolicy
from crypto_intelligence_agent.market_data import ClosedCandle, DataGapError, DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
from crypto_intelligence_agent.synthetic_partial_exits import ExitBasis, SyntheticExitTranche
from test_j3_archived_strategy_comparison_d512 import archive, compare, END, HOUR, known_hypothesis

D = Decimal
MARGIN = SyntheticMarginBasis(D(1), 50, D(50), "SYNTHETIC_USDT")
POLICY = PaperEntryExitPolicy(
    stop_distance_bps=D(50), target_distances_bps=(D(100), D(200)),
    tranches=(SyntheticExitTranche(ExitBasis.INITIAL_POSITION,D(25)),
              SyntheticExitTranche(ExitBasis.REMAINING_BALANCE,D(50))),
    runner_floor_percent=D(20), synthetic_lot_step_units=D("0.001"),
    entry_fee_bps=D(6), exit_fee_bps=D(6),
    entry_adverse_slippage_bps=D(3), exit_adverse_slippage_bps=D(3),
)


def bar(step, opening="100", high="103", low="99", close="100"):
    start = END + step*HOUR
    return ClosedCandle(
        exchange="bybit_v5_public", market="linear_perpetual", symbol="ALT00USDT",
        interval="1h", open_time_ms=start, close_time_ms=start+HOUR-1,
        open=D(opening), high=D(high), low=D(low), close=D(close),
        base_volume=D(10), quote_volume=D(1000),
        quality="bybit_public_rest_historical_closed_unverified",
    )


def run(bars, side=ResearchDirection.LONG, policy=POLICY):
    return compare_exit_scenarios(
        tuple(bars), direction=side, decision_end_ms=END,
        now_ms=END+12*HOUR, margin=MARGIN, policy=policy)


class ExitScenarioTests(unittest.TestCase):
    def test_long_and_short_same_bar_ambiguity_and_remaining_balance(self):
        for side, candle, expected in (
            (ResearchDirection.LONG, bar(0), D("0.315884375")),
            (ResearchDirection.SHORT, bar(0, high="101", low="97"), D("0.316615625")),
        ):
            with self.subTest(side=side):
                r = run([candle], side)
                a,b = r["adverse_first"],r["favorable_first"]
                self.assertEqual(a.stopped_fraction, 1)
                self.assertEqual(a.targets_reached, 0)
                self.assertEqual(a.gross_reference_quote,D("-0.25"))
                self.assertEqual(b.targets_reached,2)
                self.assertEqual(b.target_fraction,D(".625"))
                self.assertEqual(b.stopped_fraction,D(".375"))
                self.assertEqual(b.horizon_residual_fraction,0)
                self.assertEqual(b.conditional_before_funding_quote,expected)

    def test_stop_gap_uses_observed_open_and_risk_not_liquidation(self):
        r = run([bar(0, high="101.2", low="99.7", close="100.5"),
                 bar(1, opening="97", high="98", low="96", close="97.5")])
        self.assertEqual(r["adverse_first"], r["favorable_first"])
        a=r["adverse_first"]
        self.assertEqual(a.target_fraction,D(".25"))
        self.assertEqual(a.stopped_fraction,D(".75"))
        self.assertEqual(a.gross_reference_quote,D("-1"))
        self.assertEqual(a.conditional_before_funding_quote,D("-1.0891"))
        self.assertTrue(a.loss_at_least_requested_margin)

    def test_residual_mark_and_two_complete_tranches(self):
        r = run([bar(0, high="102",low="99.7",close="101")])
        a = r["adverse_first"]
        self.assertEqual(a,r["favorable_first"])
        self.assertEqual(a.target_fraction,D(".625"))
        self.assertEqual(a.horizon_residual_fraction,D(".375"))
        self.assertEqual(a.stopped_fraction,0)
        full=replace(POLICY,runner_floor_percent=D(0),tranches=(
            SyntheticExitTranche(ExitBasis.INITIAL_POSITION,D(50)),
            SyntheticExitTranche(ExitBasis.REMAINING_BALANCE,D(100)),
        ))
        r = run([bar(0)],policy=full)
        self.assertEqual(r["favorable_first"].target_fraction,1)
        self.assertEqual(r["favorable_first"].stopped_fraction,0)

    def test_invalid_or_missing_data_not_counted_as_zero_returns(self):
        for candles in ([bar(1)], [bar(0),bar(2)],
                        [replace(bar(0),quality="injected_offline")]):
            with self.subTest(candles=candles), self.assertRaises(DataGapError):
                run(candles)
        with self.assertRaises(DataValidationError):
            run([replace(bar(0),low=D(101))])
        totals=empty_replay_totals()
        accumulate_replay(totals,None,direction=ResearchDirection.LONG,
                          decision_end_ms=END,now_ms=END+HOUR,
                          margin=MARGIN,policy=POLICY)
        out=summarize_replay(totals,margin=MARGIN)
        self.assertEqual(out["missing_path_count"],1)
        self.assertIsNone(out["adverse_first"]["conditional_before_funding_quote"])

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_same_archived_candidates_and_future_coverage(self, evaluator):
        original=compare([archive(0),archive(1),archive(2)])
        result=compare([archive(0),archive(1),archive(2)],
                       replay_horizon_hours=2,replay_margin=MARGIN,exit_policy=POLICY)
        self.assertEqual(result["results"],original["results"])
        replay=result["exit_replay"]
        self.assertEqual(replay["target_tranches"][1]["basis"],"REMAINING_BALANCE")
        self.assertEqual(replay["horizon_hours"],2)
        self.assertEqual(replay["results"]["ema_cross"]["candidate_count"],2)
        self.assertEqual(replay["results"]["ema_cross"]["complete_path_count"],1)
        self.assertEqual(replay["results"]["ema_cross"]["missing_path_count"],1)
        self.assertFalse(replay["orders_sent"])
        self.assertFalse(replay["intrabar_path_verified"])
        self.assertFalse(replay["funding_settlement_verified"])
        self.assertFalse(replay["liquidation_verified"])
        changed=compare([archive(0),archive(1),archive(2,drop=True)],
                        replay_horizon_hours=2,replay_margin=MARGIN,exit_policy=POLICY)
        self.assertEqual(changed["exit_replay"]["results"]["ema_cross"]["complete_path_count"],0)


if __name__ == "__main__":
    unittest.main()
