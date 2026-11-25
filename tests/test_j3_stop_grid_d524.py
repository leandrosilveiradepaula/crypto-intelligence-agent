"""D524: one causal evaluation, multiple exits, identical covered paths."""
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from crypto_intelligence_agent.j3_combination_research_d520 import run_matrix, parse_stop_grid
from crypto_intelligence_agent.j3_intrahour_replay_d518 import decode_intrahour
from crypto_intelligence_agent.j3_retrospective_warmup_d516 import WarmupSupplement
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.j3_local_research_job_d522 import ResearchJob
from test_j3_archived_strategy_comparison_d512 import END,HOUR,CFG,known_hypothesis
from test_j3_combination_research_d520 import slow_relative_archive,row,matrix
from test_j3_intrahour_replay_d518 import envelope
from test_j3_observed_exit_scenarios_d517 import POLICY


class StopGridTests(unittest.TestCase):
    def test_strict_bounded_grid(self):
        self.assertEqual(parse_stop_grid([50,75,100,125,150]),(50,75,100,125,150))
        self.assertEqual(parse_stop_grid(None),())
        self.assertEqual(parse_stop_grid([150],allow_single=True),(150,))
        for value in ([],[True],[0],[1001],["150"],[1.5],[50,50],[150,100]):
            with self.subTest(single=value),self.assertRaises(DataValidationError):
                parse_stop_grid(value,allow_single=True)
        with self.assertRaises(DataValidationError):
            parse_stop_grid([150],allow_single=1)
        for value in ([],[50],[50,50],[100,50],[True,100],[0,100],[50,1001],list(range(1,10))):
            with self.subTest(value=value),self.assertRaises(DataValidationError):
                parse_stop_grid(value)

    def test_grid_matches_single_runs_with_one_signal_evaluation(self):
        h0,h1=slow_relative_archive(0),slow_relative_archive(1)
        now=END+10*HOUR
        intra=decode_intrahour(envelope(h0,h1),now_ms=now)
        warm=WarmupSupplement(END+2*HOUR,24,"a"*64,())
        policy=SimpleNamespace(research=CFG,exits=POLICY,margin_quote=D(1),
                               leverage=SimpleNamespace(for_new_positions=50))
        target="crypto_intelligence_agent.j3_combination_research_d520."
        evaluator="crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research"
        args=dict(directory=Path("."),owner_policy=policy,matrix_raw=matrix([row()]),
                  as_of_ms=now,horizon_hours=1,min_complete=1)
        with patch(target+"read_comparison_archives",return_value=(h0,h1)) as archives, \
             patch(target+"read_latest_supplement",return_value=warm) as warming, \
             patch(target+"read_latest_intrahour",return_value=intra) as small, \
             patch(evaluator,side_effect=known_hypothesis) as signals:
            report=run_matrix(**args,research_stop_grid_bps=[50,100,150])
            for reader in (archives,warming,small):
                reader.assert_called_once_with(Path("."),now_ms=now)
            evaluated=signals.call_count
            self.assertGreater(evaluated,0)
            self.assertGreater(report["common_covered_symbol_hours"],0)
            self.assertEqual(report["scenario_count"],9)
            for v in report["stop_grid"]:
                signals.reset_mock()
                single=run_matrix(**args,research_stop_bps=v["stop_bps"])
                self.assertEqual(v["rows"],single["rows"])
                self.assertEqual(report["manifest"],single["manifest"])
                self.assertEqual(signals.call_count,evaluated)
            with self.assertRaises(DataValidationError):
                run_matrix(**args,research_stop_bps=50,research_stop_grid_bps=[50,100])
        self.assertEqual(policy.exits.stop_distance_bps,50)
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["liquidation_verified"])

    @patch("crypto_intelligence_agent.j3_local_research_job_d522.snapshot",return_value={"revision":"a"*64})
    @patch("crypto_intelligence_agent.j3_local_research_job_d522.threading.Thread")
    def test_worker_fixed_grid_arguments(self,thread,snapshot):
        job=ResearchJob(policy_file=Path("policy"),history_directory=Path("history"))
        with self.assertRaises(DataValidationError):
            job.start({"horizon_hours":4,"stop_bps":50,"stop_grid_bps":[50,100]})
        started=job.start({"horizon_hours":4,"preset":"swing","stop_grid_bps":[50,75,100,125,150]})
        self.assertEqual(started["scenario_count"],90)
        self.assertEqual(started["strategy_count"],18)
        cmd=thread.call_args.kwargs["args"][0]
        index=cmd.index("--research-stop-grid-bps")
        self.assertEqual(cmd[index+1:index+6],["50","75","100","125","150"])
        self.assertNotIn("--research-stop-bps",cmd)


if __name__=="__main__":
    unittest.main()
