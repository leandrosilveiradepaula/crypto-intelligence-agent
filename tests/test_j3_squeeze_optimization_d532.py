"""D532 focalized replay and causal Pivot veto regression."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from crypto_intelligence_agent.j2_configurable_indicators_d513 import PivotSuperTrend
from crypto_intelligence_agent.j3_entry_research_d530 import parse_experiments, entry_events, EntryExperiment
from crypto_intelligence_agent.j3_exit_research_d531 import parse_exit_experiments
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay, partitions
from crypto_intelligence_agent.j3_long_history_d528 import HOUR_MS, EXCHANGE, MARKET, QUALITY
from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError
from test_j3_long_replay_d529 import OWNER, PLAN, START, bars
from test_j3_combination_research_d520 import matrix, row

ROOT=Path(__file__).resolve().parents[1]
ENTRY=(ROOT/"docs/examples/d532_squeeze_optimization.json").read_bytes()
EXIT=(ROOT/"docs/examples/d532_exit_optimization.json").read_bytes()
OLD=(ROOT/"docs/examples/d530_entry_experiments.json").read_bytes()


class D532Tests(unittest.TestCase):
    def test_presets_preserve_anchors_and_compare_exits(self):
        profiles={x[0]:x[2:] for x in parse_experiments(ENTRY)}
        old={x[0]:x[2:] for x in parse_experiments(OLD)}
        self.assertEqual(len(profiles),24)
        for name in ("squeeze_bb_20_2","squeeze_bb_20_2_rsi",
                     "squeeze_bb_20_2_strict","squeeze_bb_20_2_strict_rsi"):
            self.assertEqual(profiles[name],old[name])
        self.assertEqual(replace(profiles["sq_pivot"][0],pivot_filter=None),
                         profiles["squeeze_bb_20_2_strict"][0])
        variants=parse_exit_experiments(EXIT,OWNER.exits)
        self.assertEqual(len(variants),4)
        self.assertEqual(variants["runner_25_wide"][0],variants["runner_25_wide_protected"][0])
        bad=json.loads(ENTRY)
        next(p for p in bad["profiles"] if p["name"]=="sq_pivot")["parameters"]["pivot_filter"]["atr_factor"]="0"
        with self.assertRaises(DataValidationError):
            parse_experiments(json.dumps(bad).encode())

    def test_pivot_is_pure_veto_and_does_not_rearm(self):
        cfg=EntryExperiment("pullback",3,8,False,5,3,20,D(2),5,30,D(".7"),5,D(1),0)
        prices=[D(100)+i for i in range(30)]+[D(127),D("127.5"),D(132),D(133),D(134)]
        cs=tuple(ClosedCandle(EXCHANGE,MARKET,"ETHUSDT","1h",
            START+i*HOUR_MS,START+(i+1)*HOUR_MS-1,p,p+D(".1"),p-D(".1"),p,
            D(1),D(1000),QUALITY) for i,p in enumerate(prices))
        base=entry_events(cs,cfg)
        self.assertTrue(base)
        gated=replace(cfg,pivot_filter=PivotSuperTrend(True,2,10,D(3)))
        with patch("crypto_intelligence_agent.j3_entry_research_d530.pivot_trend",return_value=(1,)*len(cs)):
            self.assertEqual(entry_events(cs,gated),base)
        with patch("crypto_intelligence_agent.j3_entry_research_d530.pivot_trend",return_value=(0,)*len(cs)):
            self.assertEqual(entry_events(cs,gated),{})
        # Actual Pivot calculation: filtered signals must remain a subset and prefix-causal.
        full=entry_events(cs,gated)
        self.assertTrue(set(full.items())<=set(base.items()))
        self.assertEqual(entry_events(cs[:33],gated),
                         {k:v for k,v in full.items() if k<=cs[32].close_time_ms+1})

    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_subset_keeps_warmup_and_replay_identical(self,read):
        end=partitions(PLAN,30)["development"][1]
        def load(home,plan,symbol,interval,start,until,**kwargs):
            self.assertLessEqual(until,end)
            return bars(symbol,start,until,interval)
        read.side_effect=load
        raw=matrix([row("sma_control")])
        args=dict(home=Path("."),plan=PLAN,owner_policy=OWNER,matrix_raw=raw,
                  days=30,horizons=(24,),stops=(100,150))
        base=run_long_replay(**args)
        subset=run_long_replay(**args,strategy_names=("sma_control",))
        self.assertEqual(subset["scenario_count"],2)
        for key in ("warmup_hours","covered_symbol_hours_by_horizon","decision_range_ms"):
            self.assertEqual(base[key],subset[key])
        self.assertEqual(subset["manifest"]["selected_strategy_names"],["sma_control"])
        for s,b in zip(subset["scenarios"],base["scenarios"]):
            self.assertEqual(s["rows"],[x for x in b["rows"] if x["name"]=="sma_control"])
        for invalid in ([],["sma_control","sma_control"],["absent"],"sma_control"):
            with self.assertRaises(DataValidationError):
                run_long_replay(**args,strategy_names=invalid)


if __name__=="__main__":
    unittest.main()
