"""D274: research annotations on an existing ranked private census."""
import json
import unittest

from crypto_intelligence_agent.j1_top50_research_priorities import (
    annotate_raw_rank_research,
)

NOV6 = 1793971800000


class RankResearchAnnotationsTests(unittest.TestCase):
    def test_annotates_known_ambiguous_and_primary_without_approval(self):
        ranked = (
            "BTCUSDT", "CLANKERUSDT", "DGAIUSDT",
            "BZUSDT", "LITUSDT", "FARTCOINUSDT", "UNKNOWNUSDT",
        )
        x = annotate_raw_rank_research(
            ranked, market_window_end_ms=NOV6, include_symbols=True
        )
        self.assertEqual(x["status"], "raw_rank_research_annotations_not_eligibility")
        cats = x["research_category_counts"]
        self.assertEqual(cats["primary_crosswalk_research_count"], 2)
        self.assertEqual(cats["primary_crosswalk_not_pit_count"], 2)
        self.assertEqual(cats["ticker_collision_unresolved"], 2)
        self.assertEqual(cats["bybit_tradfi_documented_retrospective"], 1)
        self.assertEqual(cats["crypto_token_candidate_unverified"], 1)
        self.assertEqual(cats["identity_unresolved"], 3)
        self.assertEqual(x["raw_ranked_contracts"], 7)
        self.assertEqual(
            [row["symbol"] for row in x["raw_rank_research_symbols_only"]],
            list(ranked),
        )
        for row in x["raw_rank_research_symbols_only"]:
            self.assertFalse(row["identity_approved"])
        self.assertFalse(x["crypto_identity_independently_verified"])
        self.assertFalse(x["identity_pit_authenticated"])
        self.assertFalse(x["marketwide_top50_verified"])
        self.assertFalse(x["trading_enabled"])
        self.assertFalse(x["orders_sent"])

    def test_privacy_default_and_no_side_effects(self):
        x = annotate_raw_rank_research(
            ("CLANKERUSDT", "DGAIUSDT"), market_window_end_ms=NOV6
        )
        self.assertNotIn("raw_rank_research_symbols_only", x)
        self.assertNotIn("CLANKERUSDT", json.dumps(x))
        self.assertNotIn("DGAIUSDT", json.dumps(x))
        self.assertEqual(x["network_requests"], 0)
        self.assertFalse(x["database_modified"])

    def test_rejects_duplicate_malformed_or_oversize(self):
        bad = [
            (), ["BTCUSDT"], ("BTCUSDT", "BTCUSDT"),
            ("BTCUSDT", "badUSDT"), ("XAU/USDT",),
            tuple(f"C{i:03d}USDT" for i in range(51)),
        ]
        for ranked in bad:
            with self.subTest(ranked=repr(ranked)[:35]):
                with self.assertRaises(ValueError):
                    annotate_raw_rank_research(ranked, market_window_end_ms=NOV6)
        for stamp in (True, "1793971800000", -1, 0, None):
            with self.assertRaises(ValueError):
                annotate_raw_rank_research(
                    ("BTCUSDT",), market_window_end_ms=stamp
                )

    def test_unknown_has_no_primary_source(self):
        x = annotate_raw_rank_research(
            ("ABC999USDT",), market_window_end_ms=NOV6,
            include_symbols=True,
        )
        self.assertNotIn("primary_crosswalk_research_count",
                         x["research_category_counts"])
        self.assertEqual(
            x["raw_rank_research_symbols_only"][0]["identity_research_category"],
            "identity_unresolved",
        )


if __name__ == "__main__":
    unittest.main()
