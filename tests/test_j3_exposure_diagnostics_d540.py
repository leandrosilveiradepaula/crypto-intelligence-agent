"""D540 overlap/concentration and exact compatibility with D529 paths."""
from decimal import Decimal as D
from pathlib import Path
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_exposure_diagnostics_d540 import ExposureDiagnostics
from crypto_intelligence_agent.j3_funding_replay_d537 import ExposureChange
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j3_long_replay_d529 import OWNER,PLAN,bars

ROOT=Path(__file__).resolve().parents[1]
H=3_600_000
START=10*H
LONG=ResearchDirection.LONG
SHORT=ResearchDirection.SHORT


class ExposureDiagnosticsTests(unittest.TestCase):
    def test_overlap_partial_censoring_and_concentration(self):
        d=ExposureDiagnostics(H)
        d.record(symbol="ETHUSDT",direction=LONG,start=START,end=START+3*H,
            changes=(ExposureChange(0,D(1),D(".25")),),residual=D(".25"),net=D(10))
        d.record(symbol="ETHUSDT",direction=SHORT,start=START+H,end=START+2*H,
            changes=(ExposureChange(0,D(1),D(0)),),residual=D(0),net=D(-6))
        d.record(symbol="SOLUSDT",direction=LONG,start=START+H,end=START+3*H,
            changes=(),residual=D(1),net=D(2))
        a=d.summary(expected_count=3,expected_net="6")
        self.assertEqual(a["peak_concurrent_paths"],3)
        self.assertEqual(a["peak_concurrent_assets"],2)
        self.assertEqual(a["peak_duplicate_paths"],1)
        self.assertEqual(a["peak_assets_with_overlapping_paths"],1)
        self.assertEqual(D(a["peak_gross_initial_notional_equivalents"]),D("2.25"))
        self.assertEqual(D(a["path_hours"]),D(6))
        self.assertEqual(D(a["gross_initial_notional_equivalent_hours"]),D("4.5"))
        self.assertEqual(D(a["hours_with_same_asset_overlap"]),D(1))
        self.assertEqual(a["censored_open_paths"],2)
        self.assertEqual(D(a["top_1_positive_path_share_percent"]),D("83.33"))
        self.assertEqual(D(a["top_5_positive_path_share_percent"]),D(100))
        self.assertEqual(D(a["pre_funding_net_without_top_5_positive_paths_quote"]),D(-6))
        self.assertEqual(D(a["top_positive_asset_share_of_positive_asset_net_percent"]),D("66.67"))
        self.assertEqual(D(a["pre_funding_net_without_top_positive_asset_quote"]),D(2))

    def test_equal_boundary_does_not_invent_overlap(self):
        d=ExposureDiagnostics(H)
        for t in (START,START+H):
            d.record(symbol="ETHUSDT",direction=LONG,start=t,end=t+H,
                changes=(ExposureChange(0,D(1),D(0)),),residual=D(0),net=D(1))
        a=d.summary(expected_count=2,expected_net="2")
        self.assertEqual(a["peak_concurrent_paths"],1)
        self.assertEqual(a["peak_duplicate_paths"],0)
        self.assertEqual(a["censored_open_paths"],0)

    def test_empty_and_invalid_trace(self):
        a=ExposureDiagnostics(H).summary(expected_count=0,expected_net=None)
        self.assertEqual(a["peak_concurrent_paths"],0)
        self.assertIsNone(a["top_5_positive_path_share_percent"])
        d=ExposureDiagnostics(H)
        with self.assertRaises(DataValidationError):
            d.record(symbol="ETHUSDT",direction=LONG,start=START,end=START+H,
                changes=(ExposureChange(0,D(".5"),D(0)),),residual=D(0),net=D(1))
        with self.assertRaises(DataValidationError):
            d.record(symbol="ETHUSDT",direction=LONG,start=START,end=START+H,
                changes=(),residual=D(0),net=D(1))

    @patch("crypto_intelligence_agent.j3_long_replay_d529.entry_events")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_actual_replay_diagnostics_do_not_change_pnl(self,read,events):
        read.side_effect=lambda home,plan,symbol,interval,start,end,**kw:bars(symbol,start,end,interval)
        def candidate(cs,cfg):
            i=next(i for i in range(150,200) if cs[i].close>cs[i-23].open)
            return {cs[i].close_time_ms+1:"LONG"}
        events.side_effect=candidate
        args=dict(home=Path("."),plan=PLAN,owner_policy=OWNER,days=30,
            matrix_raw=(ROOT/"docs/examples/d530_entry_controls_matrix.json").read_bytes(),
            entry_experiments_raw=(ROOT/"docs/examples/d532_squeeze_optimization.json").read_bytes(),
            strategy_names=("sq_w04_v2",),horizons=(48,),stops=(150,),resolution="1h")
        legacy=run_long_replay(**args)
        report=run_long_replay(**args,exposure_diagnostics=True)
        self.assertEqual(report["exposure_diagnostic_traced_paths"],1)
        old=legacy["scenarios"][0]["rows"][0]
        current=report["scenarios"][0]["rows"][0]
        diag=current.pop("exposure_diagnostics")
        self.assertEqual(old,current)
        self.assertEqual(diag["adverse_first"]["path_count"],1)
        self.assertEqual(diag["favorable_first"]["peak_concurrent_assets"],1)
        self.assertFalse(report["portfolio_simulated"])
        with self.assertRaises(DataValidationError):
            run_long_replay(**args,partition="validation",exposure_diagnostics=True)


if __name__=="__main__":
    unittest.main()
