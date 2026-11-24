"""Research-only sizing and bankroll context, not a simulated account."""
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_combination_research_d520 import (
    parse_research_sizing, full_position_stop_risk, run_matrix,
)
from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.j3_intrahour_replay_d518 import decode_intrahour
from crypto_intelligence_agent.j3_retrospective_warmup_d516 import WarmupSupplement
from crypto_intelligence_agent.j3_local_research_job_d522 import ResearchJob
from test_j3_archived_strategy_comparison_d512 import END,HOUR,CFG,known_hypothesis
from test_j3_combination_research_d520 import slow_relative_archive,row,matrix
from test_j3_intrahour_replay_d518 import envelope
from test_j3_observed_exit_scenarios_d517 import POLICY


class ResearchSizingTests(unittest.TestCase):
    def test_stop_risk_exact_and_no_liquidation_claim(self):
        m=SyntheticMarginBasis(D(2),50,D(100),"SYNTHETIC_USDT")
        a=full_position_stop_risk(200,m,D(200))
        self.assertEqual(D(a["gross_stop_loss_quote"]),D(2))
        self.assertTrue(a["gross_stop_reaches_initial_margin"])
        b=full_position_stop_risk(250,m,D(200))
        self.assertEqual(D(b["gross_stop_loss_quote"]),D("2.5"))
        self.assertEqual(D(b["gross_loss_margin_pct"]),125)
        self.assertEqual(D(b["gross_stop_loss_pct_of_reference_bankroll"]),D("1.25"))
        m2=SyntheticMarginBasis(D(2),20,D(40),"SYNTHETIC_USDT")
        c=full_position_stop_risk(250,m2,D(200))
        self.assertEqual(D(c["gross_loss_margin_pct"]),50)
        self.assertEqual(D(c["gross_stop_loss_quote"]),D(1))
        self.assertFalse(c["gross_stop_reaches_initial_margin"])

    def test_bounded_exact_overrides(self):
        self.assertEqual(parse_research_sizing(leverage=50,margin_quote="1",bankroll_quote="200"),(50,D(1),D(200)))
        for v in ({"leverage":True},{"leverage":201},{"margin_quote":1.0},
                  {"margin_quote":"0"},{"bankroll_quote":"NaN"},{"bankroll_quote":"1e2"},
                  {"margin_quote":"2","bankroll_quote":"1"}):
            with self.subTest(v=v),self.assertRaises(DataValidationError):
                parse_research_sizing(**v)

    def test_overrides_do_not_change_signals_or_saved_profile(self):
        h0,h1=slow_relative_archive(0),slow_relative_archive(1)
        now=END+10*HOUR
        intra=decode_intrahour(envelope(h0,h1),now_ms=now)
        warm=WarmupSupplement(END+2*HOUR,24,"a"*64,())
        policy=SimpleNamespace(research=CFG,exits=POLICY,margin_quote=D(1),
                               leverage=SimpleNamespace(for_new_positions=50))
        target="crypto_intelligence_agent.j3_combination_research_d520."
        evaluator="crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research"
        args=dict(directory=Path("."),owner_policy=policy,matrix_raw=matrix([row()]),
                  as_of_ms=now,horizon_hours=1,research_stop_grid_bps=[50,75,100,125,150,200,250],
                  research_bankroll_quote="200")
        with patch(target+"read_comparison_archives",return_value=(h0,h1)), \
             patch(target+"read_latest_supplement",return_value=warm), \
             patch(target+"read_latest_intrahour",return_value=intra), \
             patch(evaluator,side_effect=known_hypothesis):
            a=run_matrix(**args,research_margin_quote="1",research_leverage=50)
            b=run_matrix(**args,research_margin_quote="2",research_leverage=20)
        self.assertEqual(a["scenario_count"],21)
        self.assertEqual(a["manifest"],b["manifest"])
        self.assertEqual(a["common_covered_symbol_hours"],b["common_covered_symbol_hours"])
        for x,y in zip(a["stop_grid"],b["stop_grid"]):
            self.assertEqual(x["stop_bps"],y["stop_bps"])
            self.assertEqual({r["name"]:(r["candidates"],r["complete"],r["stop_count"]) for r in x["rows"]},
                             {r["name"]:(r["candidates"],r["complete"],r["stop_count"]) for r in y["rows"]})
        self.assertEqual(D(a["margin_pct_of_reference_bankroll"]),D("0.5"))
        self.assertEqual(D(b["margin_pct_of_reference_bankroll"]),1)
        self.assertTrue(a["stop_grid"][-1]["gross_stop_reaches_initial_margin"])
        self.assertFalse(b["stop_grid"][-1]["gross_stop_reaches_initial_margin"])
        self.assertFalse(b["portfolio_simulated"])
        self.assertFalse(b["liquidation_verified"])
        self.assertFalse(b["profile_modified"])
        self.assertFalse(b["orders_sent"])
        self.assertEqual(policy.margin_quote,1)
        self.assertEqual(policy.leverage.for_new_positions,50)

    @patch("crypto_intelligence_agent.j3_local_research_job_d522.snapshot",return_value={"revision":"a"*64})
    @patch("crypto_intelligence_agent.j3_local_research_job_d522.threading.Thread")
    def test_worker_accepts_expanded_grid_and_sizing(self,thread,snapshot):
        job=ResearchJob(policy_file=Path("policy"),history_directory=Path("history"))
        started=job.start({"horizon_hours":4,"preset":"rsi_filter",
            "stop_grid_bps":[50,75,100,125,150,200,250],
            "research_leverage":20,"research_margin_quote":"2","research_bankroll_quote":"200"})
        self.assertEqual(started["scenario_count"],140)
        cmd=thread.call_args.kwargs["args"][0]
        for key,value in (("--research-leverage","20"),("--research-margin-quote","2"),("--research-bankroll-quote","200")):
            self.assertEqual(cmd[cmd.index(key)+1],value)


if __name__=="__main__":
    unittest.main()
