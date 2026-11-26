"""D542 tests: full vs partial paired evidence, sign, stress and D529 contract."""
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_financial_evidence_d542 import summarize_financial_replay
from crypto_intelligence_agent.j3_funding_replay_d537 import ObservedFundingHistory
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay
from crypto_intelligence_agent.market_data import DataValidationError
from test_j3_long_replay_d529 import OWNER,PLAN,bars,HOUR_MS

ROOT=Path(__file__).resolve().parents[1]
ORDERS=("adverse_first","favorable_first")


def metrics(before,low_cost,high_cost,matched=4):
    before=D(before)
    lo=D(low_cost)
    hi=D(high_cost)
    return {"conditional_before_funding_quote":str(before if matched==4 else before+D(1)),
            "funding_matched_path_count":matched,"funding_unavailable_path_count":4-matched,
            "funding_observed_event_count":matched,"funding_no_observed_events_path_count":0,
            "funding_matched_positive_low_count":1,"funding_matched_positive_high_count":2,
            "funding_matched_before_quote":str(before),
            "funding_observed_cost_low_quote":str(lo),"funding_observed_cost_high_quote":str(hi),
            "funding_matched_net_low_quote":str(before-hi),
            "funding_matched_net_high_quote":str(before-lo),
            "residual_at_horizon_count":1,
            **{f"stress_{b}bps_{k}":v for b,breach in ((50,1),(100,2))
               for k,v in (("evaluated_count",matched),("unavailable_count",4-matched),
                           ("possible_breach_count",breach),("no_observed_breach_count",matched-breach),
                           ("positive_before_funding_with_possible_breach_count",1),("checked_bars",matched*2))}}


def row(a,b):
    basic={"candidate_count":5,"complete_path_count":4,"missing_path_count":1,
           "adverse_first":a,"favorable_first":b}
    return {**basic,"name":"sq_w04_v15","directions":{"LONG":3,"SHORT":2,"covered_LONG":2,"covered_SHORT":2},
            "by_month":{"2026-05":deepcopy(basic)}}


def report():
    base={"schema_version":"d529-retrospective-cohort-replay-v1","status":"exploratory_replay_completed",
          "partition":"development","observed_funding":True,"funding_missing_queries_not_zero":True,
          "leverage_at_intent":50,"resolution":"1h","all_horizons_share_same_decision_grid":True,
          "partition_crossing_paths_excluded":True,"public_gets":0,"requested_days":365,"scenario_count":2,
          "horizons_hours":[48],"stop_grid_bps":[150],"maintenance_stress_bps":[50,100],
          "maintenance_stress_is_not_venue_liquidation":True,"maintenance_stress_rewrites_pnl":False,
          **{k:False for k in ("orders_sent","profile_modified","portfolio_simulated","winner_selected",
                               "out_of_sample_results_validated","funding_calendar_verified",
                               "funding_settlement_verified","liquidation_verified","historical_risk_tiers_verified")}}
    base["scenarios"]=[{"horizon_hours":48,"stop_bps":150,"exit_variant":v,
                        "common_covered_symbol_hours":100,"rows":[item]} for v,item in (
        ("runner_25_wide",row(metrics(12,1,2),metrics(14,2,3))),
        ("runner_25_tp4_10",row(metrics(8,0,1),metrics(9,0,1))))]
    return base


class FinancialEvidenceTests(unittest.TestCase):
    def test_compare_only_consistent_orders_and_months(self):
        out=summarize_financial_replay(report())
        self.assertEqual(out["fully_matched_scenario_count"],2)
        self.assertEqual(out["paired_comparison_count"],1)
        pair=out["paired_exit_comparisons"][0]
        self.assertEqual(pair["left_exit"],"runner_25_tp4_10")
        self.assertEqual(pair["left_minus_right_quote"],["-4","-2"])
        self.assertEqual(out["rows"][0]["monthly_entry_cohorts"]["positive_lower_bound_months"],1)
        self.assertFalse(out["bounds_cover_all_intrabar_paths"])

    def test_equal_partial_counts_do_not_prove_same_paths(self):
        d=report()
        for scenario in d["scenarios"]:
            scenario["rows"]=[row(metrics(6,0,1,3),metrics(7,0,1,3))]
        out=summarize_financial_replay(d)
        self.assertEqual(out["fully_matched_scenario_count"],0)
        self.assertIsNone(out["rows"][0]["full_match_conditional_net_range_quote"])
        self.assertEqual(out["paired_exit_comparisons"][0]["status"],"insufficient_paired_funding_evidence")
        self.assertIsNone(out["paired_exit_comparisons"][0]["left_minus_right_quote"])

    def test_reject_bad_accounting_or_different_trade_grid(self):
        d=report()
        d["scenarios"][0]["rows"][0]["adverse_first"]["funding_matched_net_low_quote"]="999"
        with self.assertRaises(DataValidationError):
            summarize_financial_replay(d)
        d=report()
        d["scenarios"][1]["common_covered_symbol_hours"]=101
        with self.assertRaises(DataValidationError):
            summarize_financial_replay(d)
        d=report()
        d["partition"]="holdout"
        with self.assertRaises(DataValidationError):
            summarize_financial_replay(d)

    def test_signed_funding_credit_and_unmatched_stress(self):
        d=report()
        d["scenarios"][0]["rows"]=[row(metrics(12,-2,-1),metrics(12,-2,-1))]
        out=summarize_financial_replay(d)
        item=next(x for x in out["rows"] if x["exit_variant"]=="runner_25_wide")
        self.assertEqual(item["full_match_conditional_net_range_quote"],["13","14"])
        self.assertEqual(item["orders"]["adverse_first"]["stress"]["100"]["possible_breaches"],2)

    @patch("crypto_intelligence_agent.j3_long_replay_d529.ObservedFundingHistory.load")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.entry_events")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_actual_d529_d537_d538_d540_json_contract(self,read,events,load):
        read.side_effect=lambda home,plan,symbol,interval,start,end,**kw:bars(symbol,start,end,interval)
        def candidate(cs,cfg):
            i=next(i for i in range(150,200) if cs[i].close>cs[i-23].open)
            return {cs[i].close_time_ms+1:"LONG"}
        events.side_effect=candidate
        def source(home,plan,symbol,start,end,resolution):
            ts=range(start,end,HOUR_MS)
            return ObservedFundingHistory(start=start,end=end,resolution=resolution,
                funding={"query_coverage_complete":True,"rows":tuple((t,".0001") for t in ts)},
                mark={"query_coverage_complete":True,"rows":tuple((t,"100","102","99","101") for t in ts)})
        load.side_effect=source
        d=run_long_replay(home=Path("."),plan=PLAN,owner_policy=OWNER,days=30,
            matrix_raw=(ROOT/"docs/examples/d530_entry_controls_matrix.json").read_bytes(),
            entry_experiments_raw=(ROOT/"docs/examples/d532_squeeze_optimization.json").read_bytes(),
            exit_experiments_raw=(ROOT/"docs/examples/d533_runner_experiments.json").read_bytes(),
            strategy_names=("sq_w04_v2",),horizons=(48,),stops=(150,),resolution="1h",
            observed_funding=True,maintenance_stress_bps=(50,100),
            separate_open_mark=True,exposure_diagnostics=True)
        out=summarize_financial_replay(json.loads(json.dumps(d,default=str)))
        self.assertEqual(out["scenario_count"],6)
        self.assertEqual(out["fully_matched_scenario_count"],6)
        self.assertEqual(out["paired_comparison_count"],15)
        self.assertIn("concentration_pre_funding",out["rows"][0])
        self.assertFalse(out["winner_selected"])


if __name__=="__main__":
    unittest.main()
