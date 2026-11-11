"""J1/D275: 50-member retrospective research queue, never Top50 approval."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_top50_frontier_worklist import (
    frontier_review_worklist,
)

NOV6 = 1793971800000


def sample():
    # Synthetic 50-member D264 worklist, with known collision and primary leads.
    return ("BTCUSDT", "CLANKERUSDT", "DGAIUSDT", "LITUSDT",
            "FARTCOINUSDT", "XAUTUSDT") + tuple(
                f"COIN{i:03d}USDT" for i in range(44)
            )


class FrontierWorklistTests(unittest.TestCase):
    def run_worklist(self, frontier=None, archived=None, show=False):
        return frontier_review_worklist(
            sample() if frontier is None else frontier,
            frozen_market_window_end_ms=NOV6,
            archived_crypto_bases=(
                frozenset({"BTC", "CLANKER", "COIN000"})
                if archived is None else archived
            ),
            include_private_symbols=show,
        )

    def test_full_batch_counts_and_no_approval(self):
        out = self.run_worklist(show=True)
        self.assertEqual(out["research_frontier_count"], 50)
        self.assertEqual(out["identity_review_pending_count"], 50)
        self.assertEqual(out["identity_approved_count"], 0)
        self.assertEqual(out["two_primary_sources_research_leads_count"], 2)
        self.assertEqual(out["two_primary_sources_not_reviewed_pit_count"], 2)
        rows = out["private_research_worklist_only"]
        self.assertEqual(len(rows), 50)
        self.assertEqual([r["symbol"] for r in rows], list(sample()))
        self.assertEqual(rows[0]["category_unverified"],
                         "archived_crypto_reference_only")
        self.assertEqual(rows[1]["category_unverified"],
                         "ticker_collision_unresolved")
        self.assertEqual(rows[2]["category_unverified"],
                         "crypto_token_candidate_unverified")
        self.assertEqual(rows[3]["category_unverified"],
                         "ticker_collision_unresolved")
        self.assertEqual(rows[5]["category_unverified"],
                         "tokenized_gold_policy_gate")
        self.assertEqual(rows[6]["category_unverified"],
                         "archived_crypto_reference_only")
        self.assertTrue(rows[1]["has_two_primary_source_research_lead"])
        self.assertTrue(rows[2]["has_two_primary_source_research_lead"])
        self.assertFalse(rows[3]["has_two_primary_source_research_lead"])
        self.assertEqual(sum(out["category_counts"].values()), 50)
        self.assertEqual(sum(out["review_action_counts"].values()), 50)
        for flag in ("snapshot_source_authenticated",
                     "identity_pit_authenticated", "marketwide_top50_verified",
                     "trading_enabled", "orders_sent", "database_modified"):
            self.assertFalse(out[flag])
        self.assertEqual(out["network_requests"], 0)
        self.assertTrue(all(r["identity_approved"] is False for r in rows))
        self.assertTrue(all(r["eligible_top50"] is False for r in rows))

    def test_no_private_symbols_in_default(self):
        out = self.run_worklist()
        self.assertNotIn("private_research_worklist_only", out)
        encoded = json.dumps(out)
        for symbol in sample():
            self.assertNotIn(symbol, encoded)
        self.assertEqual(len(out["research_queue_sha256"]), 64)

    def test_immutable_queue_digest_and_order_dependency(self):
        a = self.run_worklist()
        b = self.run_worklist()
        self.assertEqual(a["research_queue_sha256"], b["research_queue_sha256"])
        reordered = tuple(reversed(sample()))
        c = self.run_worklist(frontier=reordered)
        self.assertNotEqual(a["research_queue_sha256"],
                            c["research_queue_sha256"])

    def test_negative_in_frontier_must_fail_closed(self):
        for bad in ("BZUSDT", "SOXLUSDT"):
            frontier = (bad,) + sample()[1:]
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.run_worklist(frontier=frontier)

    def test_unknown_and_bad_arguments_fail_closed(self):
        for bad in ((), ("BTCUSDT",), list(sample()),
                    sample()[:-1] + ("BTCUSDT",),
                    sample()[:-1] + ("badUSDT",)):
            with self.subTest(kind=str(type(bad)), size=len(bad)):
                with self.assertRaises(ValueError):
                    self.run_worklist(frontier=bad)
        for bad in ({"BTC"}, frozenset({"bad-coin"}), frozenset({"BTC"}) |
                    frozenset({str(i) for i in range(2001)})):
            with self.assertRaises(ValueError):
                self.run_worklist(archived=bad)
        with self.assertRaises(ValueError):
            frontier_review_worklist(sample(),
                                     frozen_market_window_end_ms=True,
                                     archived_crypto_bases=frozenset())
        with self.assertRaises(ValueError):
            frontier_review_worklist(sample(),
                                     frozen_market_window_end_ms=NOV6,
                                     archived_crypto_bases=frozenset(),
                                     include_private_symbols=1)

    def test_never_reads_network_or_sqlite(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP")), \
             patch("sqlite3.connect", side_effect=AssertionError("SQL")):
            self.run_worklist(show=True)


if __name__ == "__main__":
    unittest.main()
