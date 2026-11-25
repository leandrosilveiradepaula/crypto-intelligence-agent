"""D534 long observation windows and explicit accounting of open positions."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import (
    compare_exit_scenarios, empty_replay_totals, accumulate_replay, summarize_replay,
)
from crypto_intelligence_agent.j3_exit_research_d531 import parse_exit_experiments
from crypto_intelligence_agent.j3_long_replay_d529 import partitions,run_long_replay
from crypto_intelligence_agent.j3_long_history_d528 import DAY
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j3_observed_exit_scenarios_d517 import bar, END,HOUR,MARGIN,POLICY
from test_j3_long_replay_d529 import OWNER,PLAN,START,bars
from test_j3_combination_research_d520 import matrix,row

RAW=(Path(__file__).resolve().parents[1]/"docs/examples/d533_runner_experiments.json").read_bytes()


class D534Tests(unittest.TestCase):
    def test_open_residual_is_not_realized_long_and_short(self):
        p,m,_=parse_exit_experiments(RAW,POLICY)["runner_25_wide"]
        p=replace(p,stop_distance_bps=D(150))
        for side,cs in (
            (ResearchDirection.LONG,(bar(0,high="105.1",low="99.8",close="104.8"),
                bar(1,opening="104.8",high="111",low="104",close="108"))),
            (ResearchDirection.SHORT,(bar(0,high="100.2",low="94.9",close="95.2"),
                bar(1,opening="95.2",high="96",low="89",close="92"))),
        ):
            args=dict(direction=side,decision_end_ms=END,now_ms=END+2*HOUR,
                      margin=MARGIN,policy=p,management=m)
            a=compare_exit_scenarios(cs,**args,separate_open_mark=True)["adverse_first"]
            old=compare_exit_scenarios(cs,**args)["adverse_first"]
            self.assertEqual(a.horizon_residual_fraction,D(".25"))
            self.assertEqual(a.open_mark.realized_gross_quote,D("1.1875"))
            self.assertEqual(a.open_mark.unrealized_gross_quote,D(1))
            self.assertEqual(a.conditional_before_funding_quote,old.conditional_before_funding_quote)
            self.assertEqual(a.open_mark.realized_after_incurred_cost_quote+a.open_mark.open_after_assumed_exit_cost_quote,
                             a.conditional_before_funding_quote)
            self.assertGreater(a.open_mark.hypothetical_residual_exit_cost_quote,0)
            totals=empty_replay_totals(include_payoff=True,include_open_mark=True)
            accumulate_replay(totals,cs,**args)
            x=summarize_replay(totals,margin=MARGIN)["adverse_first"]
            self.assertEqual(x["fully_exited_count"],0)
            self.assertEqual(x["open_positive_count"],1)
            self.assertEqual(D(x["open_fraction_sum"]),D(".25"))

    def test_closed_position_has_no_open_mark_cost_or_pnl(self):
        p,m,_=parse_exit_experiments(RAW,POLICY)["runner_25_tp4_10"]
        cs=(bar(0,high="111",low="99.8",close="108"),)
        args=dict(direction=ResearchDirection.LONG,decision_end_ms=END,now_ms=END+HOUR,
                  margin=MARGIN,policy=p,management=m)
        a=compare_exit_scenarios(cs,**args,separate_open_mark=True)["adverse_first"]
        self.assertEqual(a.horizon_residual_fraction,0)
        self.assertEqual(a.open_mark.unrealized_gross_quote,0)
        self.assertEqual(a.open_mark.hypothetical_residual_exit_cost_quote,0)
        self.assertEqual(a.open_mark.realized_after_incurred_cost_quote,a.conditional_before_funding_quote)

    def test_six_month_cap_is_explicit(self):
        cs=bars("ETHUSDT",START,START+180*DAY,"1h")
        args=dict(direction=ResearchDirection.LONG,decision_end_ms=START,
                  now_ms=START+181*DAY,margin=MARGIN,policy=POLICY)
        for cap in (72,168,4321):
            with self.assertRaises(DataValidationError):
                compare_exit_scenarios(cs,**args,research_max_horizon_hours=cap)
        self.assertIn("adverse_first",compare_exit_scenarios(cs,**args,research_max_horizon_hours=4320,
                                                              separate_open_mark=True))

    def test_preserve_original_reserved_tail_and_reject_short_window(self):
        original=partitions(PLAN,90)
        annual=partitions(PLAN,365,preserve_recent_90d=True)
        self.assertEqual(annual["validation"],original["validation"])
        self.assertEqual(annual["holdout"],original["holdout"])
        self.assertEqual(annual["development"][1],original["development"][1])
        self.assertEqual(annual["development"][0],PLAN.cutoff_ms-365*DAY)
        args=dict(home=Path("."),plan=PLAN,owner_policy=OWNER,
                  matrix_raw=matrix([row("sma_control")]),horizons=(720,),stops=(150,),
                  research_max_horizon_hours=720,separate_open_mark=True,preserve_recent_90d=True)
        with self.assertRaises(DataValidationError):
            run_long_replay(**args,days=90)
        with self.assertRaises(DataValidationError):
            run_long_replay(**args,days=365,partition="validation")


if __name__=="__main__":
    unittest.main()
