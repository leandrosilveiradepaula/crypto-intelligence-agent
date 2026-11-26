"""D544 compact journal evidence, pair orientation and incomplete matches."""
import unittest

from crypto_intelligence_agent.j3_compact_financial_d544 import compact_financial_summary
from crypto_intelligence_agent.j3_financial_evidence_d542 import summarize_financial_replay
from crypto_intelligence_agent.market_data import DataValidationError
from test_j3_financial_evidence_d542 import report,row,metrics


class CompactFinancialTests(unittest.TestCase):
    def test_bounded_horizon_and_correct_free_minus_fixed(self):
        s=summarize_financial_replay(report())
        s["source_report_sha256"]="a"*64
        result=compact_financial_summary(s)
        self.assertEqual(len(result),4)
        self.assertEqual(result[1]["positive_lower_bound"],2)
        self.assertEqual(result[1]["negative_upper_bound"],0)
        self.assertEqual(result[2]["free_positive_difference"],1)
        self.assertEqual(result[2]["focus_pairs"][0]["free_minus_fixed_quote"],["2","4"])
        self.assertEqual(result[-1]["status"],"compact_summary_completed")
        self.assertFalse(result[-1]["winner_selected"])
        self.assertEqual(result[1]["descriptive_top_mean"][0]["exit_variant"],"runner_25_wide")

    def test_partial_matches_are_not_ranked_or_paired(self):
        d=report()
        for scenario in d["scenarios"]:
            scenario["rows"]=[row(metrics(6,0,1,3),metrics(7,0,1,3))]
        s=summarize_financial_replay(d)
        s["source_report_sha256"]="b"*64
        out=compact_financial_summary(s)
        self.assertEqual(out[1]["incomplete_or_empty_funding"],2)
        self.assertEqual(out[1]["descriptive_top_mean"],[])
        self.assertEqual(out[2]["full_match_pairs"],0)
        self.assertEqual(out[2]["focus_pairs"],[])
        del s["source_report_sha256"]
        with self.assertRaises(DataValidationError):
            compact_financial_summary(s)


if __name__=="__main__":
    unittest.main()
