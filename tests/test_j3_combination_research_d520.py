"""D520: a fixed editable matrix, same causal opportunities and covered paths."""
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_combination_research_d520 import (
    parse_matrix, run_matrix, summarize_matrix,
)
from crypto_intelligence_agent.j3_intrahour_replay_d518 import decode_intrahour
from crypto_intelligence_agent.j3_retrospective_warmup_d516 import WarmupSupplement
from crypto_intelligence_agent.market_data import DataValidationError
from test_j3_archived_strategy_comparison_d512 import (
    archive, compare, END, START, HOUR, CFG, known_hypothesis,
)
from test_j3_intrahour_replay_d518 import envelope
from test_j3_observed_exit_scenarios_d517 import MARGIN, POLICY

D=Decimal
MATRIX=Path(__file__).resolve().parents[1]/"docs/examples/d520_indicator_research_matrix.json"


def row(name="sma_fast",threshold="0"):
    return {"name":name,"label":name,"ema":[],"sma":[2,3],
            "pivot":None,"relative_strength_bps":threshold}


def matrix(rows):
    return json.dumps({"schema":"d520-indicator-research-matrix-v1",
        "ema_reference_periods":[2,3,4],"profiles":rows}).encode()


def slow_relative_archive(step):
    h=archive(step)
    rows=[]
    for symbol,bars in h.series:
        if symbol=="ALT00USDT":
            updated=[]
            for b in bars:
                p=D(100)+D((b.open_time_ms-START)//HOUR)/D(100)
                updated.append(replace(b,open=p,high=p+1,low=p-1,close=p))
            bars=tuple(updated)
        rows.append((symbol,bars))
    return replace(h,series=tuple(rows))


class CombinationResearchTests(unittest.TestCase):
    def test_versioned_matrix_contains_requested_confluence(self):
        ref,profiles,labels=parse_matrix(MATRIX.read_bytes())
        self.assertEqual(ref,(10,30,60))
        self.assertEqual(len(profiles),23)
        by_name={n:(s,t) for n,s,t in profiles}
        s,t=by_name["sma_20_50_pivot"]
        self.assertEqual([x.period for x in s.sma if x.enabled],[20,50])
        self.assertFalse(any(x.enabled for x in s.ema))
        self.assertTrue(s.pivot_supertrend.enabled)
        self.assertEqual(t,0)
        self.assertEqual(by_name["sma_20_50_pivot_fr50"][1],50)
        self.assertEqual(len(labels),25)
        bb,_=by_name["sma_20_50_pivot_bb"]
        self.assertTrue(bb.bollinger.enabled)
        self.assertEqual(bb.bollinger.period,20)
        self.assertEqual(bb.bollinger.deviations,D(2))
        self.assertTrue(bb.pivot_supertrend.enabled)

    def test_matrix_validation(self):
        cases=([row(),row("duplicate_same")],
               [row("breakout")],
               [dict(row(),sma=[50,20])],
               [dict(row(),sma=[])],
               [row(threshold="1001")],
               [dict(row(),relative_strength_bps=0.5)],
               [dict(row(),pivot={"pivot_period":2,"atr_period":10,"atr_factor":"0"})])
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(DataValidationError):
                parse_matrix(matrix(rows))

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_threshold_same_causal_slot_and_complete_path(self,evaluator):
        h0,h1=slow_relative_archive(0),slow_relative_archive(1)
        intrahour=decode_intrahour(envelope(h0,h1),now_ms=END+10*HOUR)
        _,profiles,labels=parse_matrix(matrix([row("sma_lo"),row("sma_hi","50")]))
        opts=dict(replay_horizon_hours=1,replay_margin=MARGIN,exit_policy=POLICY,
                  intrahour_supplement=intrahour)
        baseline=compare([h0,h1],**opts)
        evaluator.reset_mock()
        result=compare([h0,h1],additional_profiles=profiles,**opts)
        self.assertEqual(result["results"]["breakout"],baseline["results"]["breakout"])
        self.assertEqual(result["results"]["ema_cross"],baseline["results"]["ema_cross"])
        self.assertEqual(result["common_eligible_symbol_hours"],49)
        self.assertEqual(evaluator.call_count,49*3) # same indicators, two RS thresholds
        self.assertEqual(result["batch_entry_counts"]["sma_lo"]["LONG"],1)
        self.assertEqual(result["batch_entry_counts"]["sma_hi"]["LONG"],0)
        self.assertEqual(result["batch_entry_counts"]["sma_lo"]["covered_LONG"],1)
        ex=result["batch_entry_examples"]["sma_lo"][0]
        self.assertEqual(ex["symbol"],"ALT00USDT")
        self.assertEqual(ex["decision_end_ms"],END)
        self.assertEqual(ex["side"],"LONG")
        self.assertEqual(ex["next_open_reference_ex_post"],
                         format(dict(h1.series)["ALT00USDT"][-1].open,"f"))
        screen=summarize_matrix(result,labels,min_complete=2)
        self.assertEqual(screen["common_covered_symbol_hours"],1)
        self.assertFalse(screen["winner_selected"])
        self.assertEqual(len(screen["rows"]),4)
        self.assertTrue(all(not r["descriptive_sample_screen_met"] for r in screen["rows"]))
        self.assertIsNone(next(r for r in screen["rows"] if r["name"]=="sma_hi")["net_adverse"])

    def test_run_matrix_reads_once_and_does_not_change_policy(self):
        h0,h1=archive(0),archive(1)
        intrahour=decode_intrahour(envelope(h0,h1),now_ms=END+10*HOUR)
        warmup=WarmupSupplement(END+2*HOUR,24,"a"*64,())
        policy=SimpleNamespace(research=CFG,exits=POLICY,margin_quote=D(1),
                               leverage=SimpleNamespace(for_new_positions=50))
        before=policy.research
        target="crypto_intelligence_agent.j3_combination_research_d520."
        with patch(target+"read_comparison_archives",return_value=(h0,h1)) as archives, \
             patch(target+"read_latest_supplement",return_value=warmup) as warm, \
             patch(target+"read_latest_intrahour",return_value=intrahour) as small:
            result=run_matrix(directory=Path("."),owner_policy=policy,
                              matrix_raw=matrix([row()]),as_of_ms=END+10*HOUR,
                              horizon_hours=1,min_complete=1)
        for reader in (archives,warm,small):
            reader.assert_called_once_with(Path("."),now_ms=END+10*HOUR)
        self.assertIs(policy.research,before)
        self.assertEqual(result["status"],"exploratory_matrix_completed")
        self.assertEqual(result["public_gets"],0)
        self.assertFalse(result["profile_modified"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["out_of_sample_results_validated"])
        self.assertEqual(len(result["rows"]),3)
        self.assertEqual(len(result["manifest"]["archive_digests"]),2)


if __name__=="__main__":
    unittest.main()
