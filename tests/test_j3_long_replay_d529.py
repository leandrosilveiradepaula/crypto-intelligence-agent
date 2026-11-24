"""D529 regression: causal sequence, explicit horizon, partition isolation."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from crypto_intelligence_agent.j2_observed_bybit_research import evaluate_observed_bybit_research
from crypto_intelligence_agent.j3_long_history_d528 import HistoryPlan, DAY,HOUR_MS,EXCHANGE,MARKET,QUALITY
from crypto_intelligence_agent.j3_long_replay_d529 import partitions,run_long_replay,bars_digest,contiguous_runs
from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import compare_exit_scenarios
from crypto_intelligence_agent.market_data import ClosedCandle,DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j3_observed_exit_scenarios_d517 import MARGIN,POLICY
from test_j3_archived_strategy_comparison_d512 import CFG
from test_j3_combination_research_d520 import matrix,row

END=20_700*DAY
PLAN=HistoryPlan(END,END+HOUR_MS,"a"*64,(("BTCUSDT",END-40*DAY),
    ("ETHUSDT",END-40*DAY)),"injected_offline_protocol_replay")
START=END-30*DAY
OWNER=SimpleNamespace(research=CFG,exits=POLICY,margin_quote=D(1),
                      leverage=SimpleNamespace(for_new_positions=50))


def bars(symbol,start,end,interval="1h"):
    dt=HOUR_MS if interval=="1h" else 300000
    out=[]
    for t in range(start,end,dt):
        p=D(100) if symbol=="BTCUSDT" else D(100)+D((t-START)//HOUR_MS%50)/10
        out.append(ClosedCandle(EXCHANGE,MARKET,symbol,interval,t,t+dt-1,p,p+D(".5"),
            p-D(".5"),p,D(1),D(1000),QUALITY))
    return tuple(out)


class LongReplayTests(unittest.TestCase):
    def test_continuous_opt_in_has_no_future_signal_change(self):
        cs=bars("ETHUSDT",START,START+100*HOUR_MS)
        def go(part,all_events):
            s=BybitClosedResearchSeries(part,bars_digest(part),PLAN.digest,
                "research_only_retrospective_rest_sequence" if all_events else "research_only_public_closed_series")
            return evaluate_observed_bybit_research(s,config=CFG,
                decision_at_ms=part[-1].close_time_ms+1,
                allow_rest_historical_research=True,all_retrospective_hypotheses=all_events)
        prefix=go(cs[:75],True)
        full=go(cs,True)
        self.assertEqual([(h.closed_at_ms,h.side) for h in prefix.hypotheses],
            [(h.closed_at_ms,h.side) for h in full.hypotheses if h.closed_at_ms<cs[75].open_time_ms])
        self.assertLessEqual(len(go(cs,False).hypotheses),1)
        s=BybitClosedResearchSeries(cs,bars_digest(cs),PLAN.digest,
                                    "research_only_retrospective_rest_sequence")
        with self.assertRaises(DataValidationError):
            evaluate_observed_bybit_research(s,config=CFG,
                decision_at_ms=cs[-1].close_time_ms+1,allow_rest_historical_research=True)

    def test_72_hour_path_explicit_only(self):
        start=START+DAY
        cs=bars("ETHUSDT",start,start+72*HOUR_MS,"5m")
        args=dict(direction=ResearchDirection.LONG,decision_end_ms=start,
                  now_ms=start+73*HOUR_MS,margin=MARGIN,policy=POLICY)
        with self.assertRaises(DataValidationError):
            compare_exit_scenarios(cs,**args)
        self.assertIn("adverse_first",compare_exit_scenarios(cs,**args,research_max_horizon_hours=72))
        with self.assertRaises(DataValidationError):
            compare_exit_scenarios(cs+(replace(cs[-1],open_time_ms=cs[-1].open_time_ms+300000,
                        close_time_ms=cs[-1].close_time_ms+300000),),
                        **args,research_max_horizon_hours=72)

    def test_gaps_split_and_partitions_do_not_cross(self):
        a=bars("ETHUSDT",START,START+30*HOUR_MS)
        self.assertEqual([len(x) for x in contiguous_runs(a[:10]+a[11:])],[10,19])
        p=partitions(PLAN,90)
        self.assertEqual(p["development"][1]-p["development"][0],54*DAY)
        self.assertEqual(p["validation"][1],p["holdout"][0])
        self.assertEqual(p["holdout"][1],END)

    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_matrix_and_partition(self,read):
        limit=partitions(PLAN,30)["development"][1]
        def load(home,plan,symbol,interval,start,end,**kwargs):
            self.assertLessEqual(end,limit)
            return bars(symbol,start,end,interval)
        read.side_effect=load
        base=row("sma_fast")
        gated=dict(row("sma_filter"),rsi_filter={"period":14,"long_min":55,"long_max":75})
        report=run_long_replay(home=Path("."),plan=PLAN,owner_policy=OWNER,
            matrix_raw=matrix([base,gated]),days=30,horizons=(24,72),stops=(100,250))
        self.assertEqual(report["scenario_count"],16)
        self.assertEqual(report["decision_range_ms"][1],limit-72*HOUR_MS)
        self.assertGreater(report["eligible_symbol_hours"],0)
        self.assertEqual(report["covered_symbol_hours_by_horizon"][24],report["eligible_symbol_hours"])
        self.assertFalse(report["historical_marketwide_top50_verified"])
        for scenario in report["scenarios"]:
            rows={r["name"]:r for r in scenario["rows"]}
            self.assertLessEqual(rows["sma_filter"]["candidate_count"],rows["sma_fast"]["candidate_count"])
            self.assertEqual(sum(v["candidate_count"] for v in rows["sma_fast"]["by_month"].values()),
                             rows["sma_fast"]["candidate_count"])
        with self.assertRaises(DataValidationError):
            run_long_replay(home=Path("."),plan=PLAN,owner_policy=OWNER,matrix_raw=matrix([base]),
                            days=30,partition="holdout")


if __name__=="__main__":
    unittest.main()
