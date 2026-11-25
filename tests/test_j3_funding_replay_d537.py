"""D537 observed-event accounting on reduced exposure and missing data."""
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j3_funding_replay_d537 import ExposureChange,ObservedFundingHistory
from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import compare_exit_scenarios,empty_replay_totals,accumulate_replay,summarize_replay
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay,partitions
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j3_observed_exit_scenarios_d517 import bar,END,HOUR,MARGIN,POLICY
from test_j3_long_replay_d529 import OWNER,PLAN,bars

ROOT=Path(__file__).resolve().parents[1]
LONG=ResearchDirection.LONG
SHORT=ResearchDirection.SHORT


def history(start,end,rates,mark_times,complete=True):
    return ObservedFundingHistory(start=start,end=end,resolution="1h",
        funding={"query_coverage_complete":complete,"rows":tuple(rates)},
        mark={"query_coverage_complete":False,
              "rows":tuple((t,"100","100","100","100") for t in mark_times)})


class FundingReplayTests(unittest.TestCase):
    def test_sparse_trace_and_cost_sign(self):
        cs=(bar(0,high="101.2",low="99.7",close="100.5"),
            bar(1,opening="100.5",high="102.1",low="100",close="101"),
            bar(2,opening="101",high="101.5",low="100",close="101"))
        args=dict(direction=LONG,decision_end_ms=END,now_ms=END+3*HOUR,
                  margin=MARGIN,policy=POLICY)
        traced=compare_exit_scenarios(cs,**args,trace_exposure=True)["adverse_first"]
        self.assertEqual(traced,compare_exit_scenarios(cs,**args)["adverse_first"])
        self.assertEqual(traced.exposure_changes,(
            ExposureChange(0,D(1),D(".75"),D(".75")),ExposureChange(1,D(".75"),D(".375"),D(".375"))))
        rates=((END,".001"),(END+HOUR,".002"),(END+2*HOUR,"-.001"))
        source=history(END,END+3*HOUR,rates,(END,END+HOUR,END+2*HOUR))
        kw=dict(entry_at=END,end_at=END+3*HOUR,entry_price=D(100),notional=D(50),
                changes=traced.exposure_changes)
        a=source.cost_bounds(direction=LONG,**kw)
        b=source.cost_bounds(direction=SHORT,**kw)
        self.assertEqual((a.cost_low,a.cost_high),(D(".01875"),D(".10625")))
        self.assertEqual((b.cost_low,b.cost_high),(-a.cost_high,-a.cost_low))
        self.assertEqual(a.exposed_event_count,3)

    def test_missing_query_or_exposed_mark_unavailable_but_post_exit_ignored(self):
        kw=dict(direction=LONG,entry_at=END,end_at=END+3*HOUR,entry_price=D(100),
                notional=D(50),changes=(ExposureChange(0,D(1),D(0)),))
        rates=((END,".001"),(END+HOUR,".001"))
        self.assertIsNone(history(END,END+3*HOUR,rates,(END,),False).cost_bounds(**kw))
        self.assertIsNone(history(END,END+3*HOUR,rates,()).cost_bounds(**kw))
        got=history(END,END+3*HOUR,rates,(END,)).cost_bounds(**kw)
        self.assertEqual((got.cost_low,got.cost_high,got.exposed_event_count),(D(0),D(".05"),1))
        with self.assertRaises(DataValidationError):
            history(END,END+3*HOUR,rates,(END,)).cost_bounds(**{
                **kw,"changes":(ExposureChange(0,D(".5"),D(0)),)})

    def test_matched_subset_and_legacy_accounting(self):
        cs=(bar(0,high="101.2",low="99.7",close="100.5"),)
        args=dict(direction=LONG,decision_end_ms=END,now_ms=END+HOUR,
                  margin=MARGIN,policy=POLICY)
        legacy=empty_replay_totals()
        accumulate_replay(legacy,cs,**args)
        totals=empty_replay_totals(include_observed_funding=True)
        source=history(END,END+HOUR,((END,".001"),),(END,))
        accumulate_replay(totals,cs,**args,observed_funding=source)
        accumulate_replay(totals,cs,**args)
        a=summarize_replay(totals,margin=MARGIN)["adverse_first"]
        old=summarize_replay(legacy,margin=MARGIN)["adverse_first"]
        self.assertEqual(a["funding_matched_path_count"],1)
        self.assertEqual(a["funding_unavailable_path_count"],1)
        self.assertEqual(D(a["funding_matched_before_quote"]),D(old["conditional_before_funding_quote"]))
        self.assertEqual(D(a["funding_matched_net_low_quote"]),D(a["funding_matched_before_quote"])-D(".05"))
        self.assertEqual(D(a["conditional_before_funding_quote"]),2*D(a["funding_matched_before_quote"]))
        none=empty_replay_totals(include_observed_funding=True)
        accumulate_replay(none,cs,**args)
        self.assertIsNone(summarize_replay(none,margin=MARGIN)["adverse_first"]["funding_matched_net_low_quote"])

    @patch("crypto_intelligence_agent.j3_long_replay_d529.ObservedFundingHistory.load")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.entry_events")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_long_replay_integrates_and_never_reads_reserved_tail(self,read,events,load):
        end=partitions(PLAN,30)["development"][1]
        def trade(home,plan,symbol,interval,start,until,**kwargs):
            self.assertLessEqual(until,end)
            return bars(symbol,start,until,interval)
        read.side_effect=trade
        def candidate(cs,cfg):
            i=next(i for i in range(150,200) if cs[i].close>cs[i-23].open)
            return {cs[i].close_time_ms+1:"LONG"}
        events.side_effect=candidate
        def data(home,plan,symbol,start,until,resolution):
            self.assertLessEqual(until,end)
            ts=tuple(range(start,until,HOUR))
            return history(start,until,tuple((t,".0001") for t in ts),ts)
        load.side_effect=data
        args=dict(home=Path("."),plan=PLAN,owner_policy=OWNER,days=30,
            matrix_raw=(ROOT/"docs/examples/d530_entry_controls_matrix.json").read_bytes(),
            entry_experiments_raw=(ROOT/"docs/examples/d532_squeeze_optimization.json").read_bytes(),
            strategy_names=("sq_w04_v2",),horizons=(48,),stops=(150,),resolution="1h")
        result=run_long_replay(**args,observed_funding=True,maintenance_stress_bps=(50,100))
        self.assertTrue(result["observed_funding"])
        self.assertFalse(result["funding_settlement_verified"])
        a=result["scenarios"][0]["rows"][0]["adverse_first"]
        self.assertEqual(a["funding_matched_path_count"],1)
        self.assertGreater(a["funding_observed_event_count"],0)
        self.assertEqual(a["stress_50bps_evaluated_count"],1)
        self.assertEqual(a["stress_100bps_evaluated_count"],1)
        self.assertTrue(result["maintenance_stress_is_not_venue_liquidation"])
        self.assertFalse(result["liquidation_verified"])
        with self.assertRaises(DataValidationError):
            run_long_replay(**args,observed_funding=True,partition="validation")


if __name__=="__main__":
    unittest.main()
