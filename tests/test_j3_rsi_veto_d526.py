"""D526: veto is a strict subset of causal base signals, never a trigger."""
from pathlib import Path
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j3_combination_research_d520 import parse_matrix, summarize_matrix
from crypto_intelligence_agent.j3_intrahour_replay_d518 import decode_intrahour
from crypto_intelligence_agent.market_data import DataValidationError
from test_j3_archived_strategy_comparison_d512 import archive,compare,END,HOUR,known_hypothesis
from test_j3_combination_research_d520 import row,matrix
from test_j3_intrahour_replay_d518 import envelope
from test_j3_observed_exit_scenarios_d517 import MARGIN,POLICY


class RSIVetoTests(unittest.TestCase):
    def test_versioned_matrix_has_paired_controls_and_breakout_veto(self):
        p=Path(__file__).resolve().parents[1]/"docs/examples/d526_rsi_filter_research_matrix.json"
        _,profiles,labels=parse_matrix(p.read_bytes())
        by_name={x[0]:x for x in profiles}
        self.assertEqual(len(labels),20)
        self.assertEqual(by_name["sma_20_50"][1:3],by_name["sma_20_50_veto"][1:3])
        self.assertIsNone(by_name["breakout_veto"][1])
        self.assertEqual(by_name["breakout_veto"][3].period,14)

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_no_new_entries_and_reuse_base_evaluation(self,evaluator):
        h0,h1=archive(0),archive(1)
        intra=decode_intrahour(envelope(h0,h1),now_ms=END+10*HOUR)
        narrow={"period":14,"long_min":50,"long_max":70}
        wide={**narrow,"long_max":100}
        base=row("sma_control")
        rows=[base,dict(base,name="sma_veto",rsi_filter=narrow),
              dict(base,name="sma_wide",rsi_filter=wide),
              dict(base,name="breakout_veto",sma=[],trigger="breakout",rsi_filter=narrow),
              dict(base,name="breakout_wide",sma=[],trigger="breakout",rsi_filter=wide)]
        _,profiles,labels=parse_matrix(matrix(rows))
        out=compare([h0,h1],additional_profiles=profiles,replay_horizon_hours=1,
                    replay_margin=MARGIN,exit_policy=POLICY,intrahour_supplement=intra)
        self.assertEqual(evaluator.call_count,49*3)
        data={r["name"]:r for r in summarize_matrix(out,labels)["rows"]}
        for control, reject, accept in (("sma_control","sma_veto","sma_wide"),
                                         ("breakout","breakout_veto","breakout_wide")):
            self.assertGreater(data[control]["candidates"],0)
            self.assertEqual(data[reject]["candidates"],0)
            self.assertEqual(data[accept]["candidates"],data[control]["candidates"])
            self.assertEqual(data[accept]["complete"],data[control]["complete"])
            self.assertEqual(data[accept]["net_adverse"],data[control]["net_adverse"])
            self.assertEqual(data[reject]["rsi_veto"]["checked"],data[control]["candidates"])
            self.assertEqual(data[reject]["rsi_veto"]["rejected"],data[control]["candidates"])
            self.assertEqual(data[accept]["rsi_veto"]["rejected"],0)

    def test_invalid_mixed_trigger_and_veto(self):
        gate={"period":14,"long_min":50,"long_max":70}
        for invalid in (dict(row(),rsi=gate,rsi_filter=gate),
                        dict(row(),trigger="breakout",rsi_filter=gate),
                        dict(row(),sma=[],trigger="breakout"),
                        dict(row(),rsi_filter=dict(gate,period=True))):
            with self.subTest(invalid=invalid),self.assertRaises(DataValidationError):
                parse_matrix(matrix([invalid]))


if __name__=="__main__":
    unittest.main()
