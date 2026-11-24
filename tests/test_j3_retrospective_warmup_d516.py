"""D516: retrospective warmup stays separate from prospective observations."""
from dataclasses import replace
from hashlib import sha256
from decimal import Decimal
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j2_rest_n50_history_d461 import _canonical
from crypto_intelligence_agent.j3_retrospective_warmup_d516 import (
    SCHEMA, SOURCE, _anchors, decode_supplement, seed_by_anchor,
)
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from test_j3_archived_strategy_comparison_d512 import (
    archive, compare, END, START, HOUR, known_hypothesis,
)


def envelope(h, *, mismatch=False, hours=62):
    # Matching original 24 closed candles plus older bars, retrieved LATER.
    rows = []
    for i in range(23, 23-hours, -1):
        price = Decimal(100+i)
        if mismatch and i == 0:
            price += 1
        rows.append([str(START+i*HOUR), str(price), str(price+1),
                     str(price-1), str(price), "10", "1000"])
    retrieved = END+3*HOUR
    p = {"source": SOURCE, "created_at_ms": retrieved, "history_hours": hours,
         "series": {"ALT00USDT": {
             "anchor_digest": h.digest_sha256, "anchor_end_ms": h.window_end_ms,
             "anchor_captured_at_ms": h.captured_at_ms, "retrieved_at_ms": retrieved,
             "rows": rows,
         }}}
    return _canonical({"schema": SCHEMA, "payload": p,
                       "sha256": sha256(_canonical(p)).hexdigest()})


class RetrospectiveWarmupTests(unittest.TestCase):
    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_missing_38_prior_bars_are_recovered_without_creating_members(self, evaluator):
        h0, h1 = archive(0), archive(1)
        supplement = decode_supplement(envelope(h0), now_ms=END+10*HOUR)
        original = compare([h0,h1], periods=(10,30,60))
        self.assertEqual(original["common_eligible_symbol_hours"], 0)
        r = compare([h0,h1], periods=(10,30,60), warmup_supplement=supplement)
        self.assertEqual(r["common_eligible_symbol_hours"], 1)
        self.assertEqual(r["retrospective_warmup_symbol_hours"], 1)
        self.assertEqual(r["retrospective_warmup_rejected_series"], 0)
        self.assertEqual(r["results"]["ema_cross"]["candidates"], 1)
        self.assertEqual(evaluator.call_count, 2)
        self.assertEqual(h0.history_hours, 24)
        self.assertTrue(r["retrospective_warmup_requested"])
        self.assertFalse(r["out_of_sample_results_validated"])
        self.assertFalse(r["orders_sent"])

    @patch("crypto_intelligence_agent.j3_archived_strategy_comparison_d512.evaluate_observed_bybit_research",
           side_effect=known_hypothesis)
    def test_retrospective_seed_cannot_override_or_create_future_prices(self, evaluator):
        h0 = archive(0)
        s = decode_supplement(envelope(h0), now_ms=END+10*HOUR)
        before = compare([h0,archive(1)], periods=(10,30,60), warmup_supplement=s)
        after = compare([h0,archive(1,next_shift=10)], periods=(10,30,60),
                        warmup_supplement=s)
        self.assertEqual(before["results"]["ema_cross"]["candidates"],
                         after["results"]["ema_cross"]["candidates"])
        self.assertNotEqual(before["results"]["ema_cross"]["gross_mark_quote"],
                            after["results"]["ema_cross"]["gross_mark_quote"])
        missing = compare([h0,archive(1,drop=True)], periods=(10,30,60),
                          warmup_supplement=s)
        self.assertEqual(missing["results"]["ema_cross"]["missing_future_marks"], 1)
        self.assertIsNone(missing["results"]["ema_cross"]["gross_mark_quote"])

    def test_complete_overlap_and_original_anchor_are_required(self):
        h0 = archive(0)
        bad = decode_supplement(envelope(h0,mismatch=True), now_ms=END+10*HOUR)
        seeds, rejected = seed_by_anchor((h0,), bad, now_ms=END+10*HOUR)
        self.assertEqual((seeds,rejected), ({},1))
        good = decode_supplement(envelope(h0), now_ms=END+10*HOUR)
        self.assertEqual(seed_by_anchor((archive(1),), good, now_ms=END+10*HOUR),
                         ({},1))
        seeds, rejected = seed_by_anchor((h0,), good, now_ms=END+10*HOUR)
        self.assertEqual(rejected,0)
        self.assertEqual(len(seeds[END]),38)
        self.assertTrue(all(c.close_time_ms < START for c in seeds[END]))

    def test_integrity_future_retrieval_and_plan(self):
        h0,h1 = archive(0),archive(1)
        raw = envelope(h0)
        with self.assertRaises((DataValidationError,DataGapError)):
            decode_supplement(raw.replace(b'"10","1000"', b'"11","1000"', 1),
                              now_ms=END+10*HOUR)
        with self.assertRaises(DataValidationError):
            decode_supplement(raw, now_ms=END+2*HOUR)
        plan = _anchors((h0,h1), 62)
        self.assertEqual(len(plan),49)
        self.assertNotIn("BTCUSDT",plan)
        self.assertTrue(all(h.window_end_ms == END for h,_ in plan.values()))
        self.assertEqual(_anchors((h0,h1),24),{})


if __name__ == "__main__":
    unittest.main()
