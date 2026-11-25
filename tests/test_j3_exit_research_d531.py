"""D531 matched exit plans: fixed entry set, next-bar-only protection."""
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import unittest,json

from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import (
    ResearchStopManagement,compare_exit_scenarios,empty_replay_totals,
    accumulate_replay,summarize_replay,
)
from crypto_intelligence_agent.j3_exit_research_d531 import parse_exit_experiments
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay,partitions
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j3_observed_exit_scenarios_d517 import bar,END,HOUR,MARGIN,POLICY
from test_j3_long_replay_d529 import OWNER,PLAN,bars
from test_j3_combination_research_d520 import matrix,row

RAW=(Path(__file__).resolve().parents[1]/"docs/examples/d531_exit_experiments.json").read_bytes()


class D531Tests(unittest.TestCase):
    def run_path(self,cs,side=ResearchDirection.LONG,management=None):
        return compare_exit_scenarios(tuple(cs),direction=side,decision_end_ms=END,
                now_ms=END+12*HOUR,margin=MARGIN,policy=POLICY,management=management)

    def test_protection_next_bar_and_mirrored(self):
        m=ResearchStopManagement(protect_after_targets=1)
        for side,cs in (
            (ResearchDirection.LONG,[bar(0,high="101.5",low="99.7",close="100.4"),
               bar(1,opening="100.4",high="100.9",low="99.8",close="100.2")]),
            (ResearchDirection.SHORT,[bar(0,high="100.3",low="98.5",close="99.6"),
               bar(1,opening="99.6",high="100.2",low="99.1",close="99.8")])):
            with self.subTest(side=side):
                before=self.run_path(cs[:1],side,m)
                self.assertEqual(before["adverse_first"].stopped_fraction,0)
                a=self.run_path(cs,side,m)["adverse_first"]
                self.assertEqual(a.stop_bar_index,1)
                self.assertEqual(a.target_fraction,D(".25"))
                self.assertEqual(a.stopped_fraction,D(".75"))
                self.assertEqual(a.gross_reference_quote,D(".125"))
                self.assertEqual(self.run_path(cs,side)["adverse_first"].stopped_fraction,0)

    def test_trail_monotone_next_bar_and_observed_gap(self):
        m=ResearchStopManagement(1,2,D(100))
        cs=[bar(0,high="103",low="99.7",close="102.9"),
            bar(1,opening="102.8",high="104",low="102.5",close="103.6"),
            bar(2,opening="102.5",high="104",low="102",close="103")]
        a=self.run_path(cs,management=m)["adverse_first"]
        self.assertEqual(a.stop_bar_index,2)
        self.assertEqual(a.target_fraction,D(".625"))
        self.assertEqual(a.stopped_fraction,D(".375"))
        self.assertEqual(a.gross_reference_quote,D("1.09375"))
        # Adverse-first same-bar stop is not rescued by future favorable extreme.
        same=[bar(0)]
        self.assertEqual(self.run_path(same,management=m),self.run_path(same))

    def test_parser_and_payoff(self):
        v=parse_exit_experiments(RAW,POLICY)
        self.assertEqual(len(v),5)
        self.assertEqual(v["runner_25"][0].tranches,v["runner_25_trailing"][0].tranches)
        self.assertEqual(v["runner_25"][0].target_distances_bps,v["runner_25_trailing"][0].target_distances_bps)
        raw=json.loads(RAW)
        raw["profiles"][0]["tranches"][0]["percent"]="100"
        with self.assertRaises(DataValidationError):
            parse_exit_experiments(json.dumps(raw).encode(),POLICY)
        totals=empty_replay_totals(include_payoff=True)
        for cs in ([bar(0,high="103",low="99.7",close="102")],[bar(0)]):
            accumulate_replay(totals,tuple(cs),direction=ResearchDirection.LONG,
                decision_end_ms=END,now_ms=END+HOUR,margin=MARGIN,policy=POLICY)
        a=summarize_replay(totals,margin=MARGIN)["adverse_first"]
        self.assertEqual(a["positive_count"],1)
        self.assertEqual(a["negative_count"],1)
        self.assertEqual(D(a["positive_net_quote_sum"])-D(a["negative_net_quote_sum"]),
                         D(a["conditional_before_funding_quote"]))
        self.assertGreater(D(a["profit_factor"]),0)

    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_replay_entry_and_path_counts_match_every_exit(self,read):
        until=partitions(PLAN,30)["development"][1]
        def load(home,plan,symbol,interval,start,end,**kwargs):
            self.assertLessEqual(end,until)
            return bars(symbol,start,end,interval)
        read.side_effect=load
        raw=matrix([row("sma_control")])
        base=run_long_replay(home=Path("."),plan=PLAN,owner_policy=OWNER,
            matrix_raw=raw,days=30,horizons=(24,),stops=(100,150))
        out=run_long_replay(home=Path("."),plan=PLAN,owner_policy=OWNER,
            matrix_raw=raw,exit_experiments_raw=RAW,days=30,horizons=(24,),stops=(100,150))
        self.assertEqual(out["scenario_count"],base["scenario_count"]*5)
        self.assertIn("exit_experiments_sha256",out["manifest"])
        for sc in out["scenarios"]:
            original=next(s for s in base["scenarios"] if s["stop_bps"]==sc["stop_bps"])
            for a,b in zip(sc["rows"],original["rows"]):
                for key in ("name","candidate_count","complete_path_count","directions"):
                    self.assertEqual(a[key],b[key])
                if sc["exit_variant"]=="owner_baseline":
                    self.assertEqual(a["adverse_first"]["conditional_before_funding_quote"],
                                     b["adverse_first"]["conditional_before_funding_quote"])


if __name__=="__main__":
    unittest.main()
