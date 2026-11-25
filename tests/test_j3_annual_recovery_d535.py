"""D535: reproduce the actual annual single-stop invocation on offline paths."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay, partitions
from crypto_intelligence_agent.j3_long_history_d528 import DAY,HOUR_MS
from test_j3_long_replay_d529 import OWNER,PLAN,bars

ROOT=Path(__file__).resolve().parents[1]
NAMES=("squeeze_bb_20_2_strict","squeeze_bb_20_2_strict_rsi","sq_w04_v2",
       "sq_w04_v15","sq_sma_30_60","sq_sma_10_30","sq_ema_9_21","sq_pivot")


class AnnualReplayTests(unittest.TestCase):
    @patch("crypto_intelligence_agent.j3_long_replay_d529.entry_events")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_annual_single_stop_all_240_scenarios(self,read,events):
        plan=replace(PLAN,members=tuple((s,PLAN.cutoff_ms-400*DAY)
                                       for s,_ in PLAN.members))
        end=partitions(plan,365,preserve_recent_90d=True)["development"][1]
        def load(home,plan,symbol,interval,start,until,**kwargs):
            self.assertEqual(interval,"1h")
            self.assertLessEqual(until,end)
            return bars(symbol,start,until,interval)
        read.side_effect=load
        def candidate(cs,cfg):
            # Inject only the trigger, not BTC/FR, path selection, exit logic,
            # coverage or accounting. Choose a causal positive FR slot.
            i=next(i for i in range(500,550) if cs[i].close>cs[i-23].open)
            return {cs[i].close_time_ms+1:"LONG"}
        events.side_effect=candidate
        result=run_long_replay(home=Path("."),plan=plan,owner_policy=OWNER,
            matrix_raw=(ROOT/"docs/examples/d530_entry_controls_matrix.json").read_bytes(),
            entry_experiments_raw=(ROOT/"docs/examples/d532_squeeze_optimization.json").read_bytes(),
            exit_experiments_raw=(ROOT/"docs/examples/d533_runner_experiments.json").read_bytes(),
            strategy_names=NAMES,days=365,partition="development",resolution="1h",
            horizons=(48,168,720,1440,2160),stops=(150,),research_max_horizon_hours=2160,
            target_diagnostics=True,separate_open_mark=True,preserve_recent_90d=True)
        self.assertEqual(result["scenario_count"],240)
        self.assertEqual(result["stop_grid_bps"],[150])
        self.assertEqual(result["status"],"exploratory_replay_completed")
        self.assertEqual(len(set(result["covered_symbol_hours_by_horizon"].values())),1)
        self.assertEqual(result["decision_range_ms"][1],end-2160*HOUR_MS)
        self.assertEqual(result["partition_ranges_ms"]["validation"],partitions(plan,90)["validation"])
        for scenario in result["scenarios"]:
            self.assertEqual(scenario["stop_bps"],150)
            row=next(r for r in scenario["rows"] if r["name"]=="sq_w04_v2")
            self.assertEqual(row["complete_path_count"],1)
            self.assertIn("realized_after_incurred_cost_quote",row["adverse_first"])
            self.assertIn("tp4_reached_count",row["adverse_first"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["liquidation_verified"])


if __name__=="__main__":
    unittest.main()
