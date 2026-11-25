"""D533 residual versus fixed fourth target, explicit seven-day research."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j3_exit_research_d531 import parse_exit_experiments
from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import (
    compare_exit_scenarios, empty_replay_totals, accumulate_replay, summarize_replay,
)
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay, partitions
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j3_observed_exit_scenarios_d517 import bar, END, HOUR, MARGIN, POLICY
from test_j3_long_replay_d529 import OWNER, PLAN, START, bars
from test_j3_combination_research_d520 import matrix,row

ROOT=Path(__file__).resolve().parents[1]
RAW=(ROOT/"docs/examples/d533_runner_experiments.json").read_bytes()


class D533Tests(unittest.TestCase):
    def test_four_targets_conserve_position_and_mirror(self):
        v=parse_exit_experiments(RAW,POLICY)
        self.assertEqual(len(v),6)
        for side,cs in (
            (ResearchDirection.LONG, (bar(0,high="105.1",low="99.8",close="104.8"),
                bar(1,opening="104.8",high="111",low="104",close="108"))),
            (ResearchDirection.SHORT, (bar(0,high="100.2",low="94.9",close="95.2"),
                bar(1,opening="95.2",high="96",low="89",close="92"))),
        ):
            def run(name):
                p,m,_=v[name]
                return compare_exit_scenarios(cs,direction=side,decision_end_ms=END,
                    now_ms=END+2*HOUR,margin=MARGIN,
                    policy=replace(p,stop_distance_bps=D(150)),management=m)
            for order in ("adverse_first","favorable_first"):
                cap=run("runner_25_tp4_10")[order]
                free=run("runner_25_wide")[order]
                self.assertEqual(cap.targets_reached,4)
                self.assertEqual(cap.target_fraction,D(1))
                self.assertEqual(cap.gross_reference_quote,D("2.4375"))
                self.assertEqual(cap.horizon_residual_fraction,D(0))
                self.assertEqual(free.targets_reached,3)
                self.assertEqual(free.horizon_residual_fraction,D(".25"))
                self.assertEqual(free.gross_reference_quote,D("2.1875"))

    def test_tp3_protection_is_next_bar_and_gap_aware(self):
        v=parse_exit_experiments(RAW,POLICY)
        p,m,_=v["runner_25_wide_protect_tp3"]
        p=replace(p,stop_distance_bps=D(150))
        first=bar(0,high="105.1",low="98.8",close="104")
        def run(cs):
            return compare_exit_scenarios(tuple(cs),direction=ResearchDirection.LONG,
                decision_end_ms=END,now_ms=END+12*HOUR,margin=MARGIN,
                policy=p,management=m)["adverse_first"]
        self.assertEqual(run([first]).horizon_residual_fraction,D(".25"))
        after=run([first,bar(1,opening="104",high="106",low="99",close="102")])
        self.assertEqual(after.targets_reached,3)
        self.assertEqual(after.stopped_fraction,D(".25"))
        self.assertEqual(after.stop_bar_index,1)
        self.assertEqual(after.gross_reference_quote,D("1.1875"))
        gap=run([first,bar(1,opening="97",high="99",low="96",close="98")])
        self.assertEqual(gap.gross_reference_quote,D(".8125"))

    def test_target_diagnostics_opt_in(self):
        p,m,_=parse_exit_experiments(RAW,POLICY)["runner_25_tp4_10"]
        cs=(bar(0,high="111",low="99.8",close="108"),)
        totals=empty_replay_totals(include_payoff=True,include_target_diagnostics=True)
        accumulate_replay(totals,cs,direction=ResearchDirection.LONG,decision_end_ms=END,
            now_ms=END+HOUR,margin=MARGIN,policy=p,management=m)
        a=summarize_replay(totals,margin=MARGIN)["adverse_first"]
        self.assertEqual([a[f"tp{i}_reached_count"] for i in range(1,5)],[1,1,1,1])
        self.assertEqual(a["tp5_reached_count"],0)
        self.assertEqual(a["after_tp3_stopped_count"],0)
        self.assertEqual(a["after_tp3_residual_at_horizon_count"],0)
        self.assertNotIn("tp1_reached_count",empty_replay_totals()["adverse_first"])

    def test_seven_day_path_requires_explicit_cap(self):
        cs=bars("ETHUSDT",START,START+168*HOUR,"5m")
        self.assertEqual(len(cs),2016)
        kw=dict(direction=ResearchDirection.LONG,decision_end_ms=START,
                now_ms=START+169*HOUR,margin=MARGIN,policy=POLICY)
        for cap in (12,72,4321):
            with self.assertRaises(DataValidationError):
                compare_exit_scenarios(cs,**kw,research_max_horizon_hours=cap)
        self.assertIn("adverse_first",compare_exit_scenarios(cs,**kw,research_max_horizon_hours=168))

    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_extended_grid_matches_longest_complete_paths(self,read):
        end=partitions(PLAN,30)["development"][1]
        def load(home,plan,symbol,interval,start,until,**kwargs):
            self.assertLessEqual(until,end)
            cs=bars(symbol,start,until,interval)
            if symbol!="BTCUSDT" and interval=="5m":
                cs=tuple(c for c in cs if c.open_time_ms!=end-2*HOUR)
            return cs
        read.side_effect=load
        args=dict(home=Path("."),plan=PLAN,owner_policy=OWNER,matrix_raw=matrix([row("sma_control")]),
                  days=30,horizons=(48,168),stops=(100,150),resolution="5m",
                  strategy_names=("sma_control",))
        with self.assertRaises(DataValidationError):
            run_long_replay(**args)
        out=run_long_replay(**args,research_max_horizon_hours=168,target_diagnostics=True)
        self.assertTrue(out["horizons_require_longest_complete_path"])
        self.assertEqual(out["decision_range_ms"][1],end-168*HOUR)
        coverage=out["covered_symbol_hours_by_horizon"]
        self.assertEqual(coverage[48],coverage[168])
        self.assertGreater(coverage[168],0)
        self.assertLess(coverage[168],out["eligible_symbol_hours"])
        self.assertTrue(out["target_diagnostics"])


if __name__=="__main__":
    unittest.main()
