"""D530 causal state and matched veto; no network or live configuration."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_entry_research_d530 import EntryExperiment,parse_experiments,entry_events
from crypto_intelligence_agent.j3_long_replay_d529 import make_policies,run_long_replay,partitions
from crypto_intelligence_agent.market_data import ClosedCandle,DataValidationError
from test_j3_long_replay_d529 import OWNER,PLAN,START,bars
from crypto_intelligence_agent.j3_long_history_d528 import HOUR_MS,EXCHANGE,MARKET,QUALITY

ROOT=Path(__file__).resolve().parents[1]
CONTROL=(ROOT/"docs/examples/d530_entry_controls_matrix.json").read_bytes()
EXTRA=(ROOT/"docs/examples/d530_entry_experiments.json").read_bytes()


class D530Tests(unittest.TestCase):
    def test_presets_and_matched_controls(self):
        p=parse_experiments(EXTRA)
        self.assertEqual(len(p),10)
        for a,b in zip(p[::2],p[1::2]):
            self.assertEqual(a[2:4],b[2:4])
            self.assertIsNone(a[4])
            self.assertIsNotNone(b[4])
        settings,labels,warmup=make_policies(OWNER,CONTROL,EXTRA)
        self.assertEqual(len(labels),19)
        self.assertEqual(set(settings),set(labels))
        with self.assertRaises(DataValidationError):
            replace(p[0][2],fast=100,slow=30)

    def test_pullback_requires_prior_correction_and_is_prefix_causal(self):
        cfg=EntryExperiment("pullback",3,8,False,5,3,20,D(2),5,30,D(".7"),5,D(1),0)
        prices=[D(100)+i for i in range(30)]+[D(127),D(126),D(132),D(133),D(134)]
        def make(values):
            return tuple(ClosedCandle(EXCHANGE,MARKET,"ETHUSDT","1h",
                START+i*HOUR_MS,START+(i+1)*HOUR_MS-1,p,p+D(".1"),p-D(".1"),p,
                D(1),D(1000),QUALITY) for i,p in enumerate(values))
        cs=make(prices)
        result=entry_events(cs,cfg)
        self.assertEqual(result,{cs[32].close_time_ms+1:"LONG"})
        for n in (24,30,31,32,33,34):
            self.assertEqual(entry_events(cs[:n],cfg),
                {t:s for t,s in result.items() if t<=cs[n-1].close_time_ms+1})
        self.assertEqual(entry_events(make([D(300)-x for x in prices]),cfg),
                         {cs[32].close_time_ms+1:"SHORT"})

    def test_squeeze_prefix_invariance(self):
        cfg=parse_experiments(EXTRA)[6][2]
        cs=bars("ETHUSDT",START,START+250*HOUR_MS)
        result=entry_events(cs,cfg)
        for n in (60,80,120,200):
            self.assertEqual(entry_events(cs[:n],cfg),
                {t:s for t,s in result.items() if t<=cs[n-1].close_time_ms+1})

    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_replay_integration(self,read):
        end=partitions(PLAN,30)["development"][1]
        def load(home,plan,symbol,interval,start,until,**kwargs):
            self.assertLessEqual(until,end)
            return bars(symbol,start,until,interval)
        read.side_effect=load
        report=run_long_replay(home=Path("."),plan=PLAN,owner_policy=OWNER,
            matrix_raw=CONTROL,entry_experiments_raw=EXTRA,days=30,
            horizons=(24,),stops=(100,150))
        self.assertEqual(report["scenario_count"],38)
        self.assertIn("entry_experiments_sha256",report["manifest"])
        for sc in report["scenarios"]:
            by={x["name"]:x for x in sc["rows"]}
            for name in ("pullback_sma_10_30","pullback_sma_20_50","pullback_ema_9_21",
                         "squeeze_bb_20_2","squeeze_bb_20_2_strict"):
                self.assertLessEqual(by[name+"_rsi"]["candidate_count"],by[name]["candidate_count"])


if __name__=="__main__":
    unittest.main()
