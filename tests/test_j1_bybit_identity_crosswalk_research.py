"""D261: adversarial, offline research-only venue crosswalk contract tests."""
from __future__ import annotations

import unittest

from crypto_intelligence_agent.bybit_identity_crosswalk_research import (
    CANDIDATE_CROSSWALK, CandidateCrosswalk, candidate_crosswalk_digest,
    research_category, research_details, research_frontier, research_provenance,
)
from crypto_intelligence_agent.bybit_tradfi_negative_evidence import (
    NEGATIVE_EVIDENCE,
)


class D261CandidateCrosswalkTests(unittest.TestCase):
    def test_ten_known_hypotheses_are_never_approved(self):
        self.assertEqual(len(CANDIDATE_CROSSWALK), 10)
        self.assertEqual(len(candidate_crosswalk_digest()), 64)
        for symbol, item in CANDIDATE_CROSSWALK.items():
            self.assertNotIn(symbol, NEGATIVE_EVIDENCE)
            self.assertFalse(research_details(symbol)["identity_approval"])
            self.assertFalse(research_details(symbol)["evidence_pit_authenticated"])
            self.assertEqual(research_category(symbol, False), item.research_class)
        provenance = research_provenance()
        self.assertFalse(provenance["candidate_venue_crosswalk_verified"])
        self.assertFalse(provenance["candidate_identity_independent_review_verified"])
        self.assertFalse(provenance["candidate_research_pit_authenticated"])
        self.assertFalse(provenance["candidate_catalog_complete_for_market"])

    def test_symbol_aliases_are_explicit_not_automatically_stripped(self):
        self.assertEqual(
            research_details("1000PEPEUSDT")["relation_hypothesis_only"],
            "unit_1000_requires_venue_proof",
        )
        self.assertEqual(
            research_details("PUMPFUNUSDT")["relation_hypothesis_only"],
            "venue_alias_requires_proof",
        )
        self.assertIsNone(research_details("PEPEUSDT"))
        self.assertIsNone(research_details("PUMPUSDT"))
        self.assertEqual(research_category("XAUUSDT", False),
                         "bybit_tradfi_documented_retrospective")

    def test_ticker_collisions_are_unresolved_without_venue_proof(self):
        for symbol in ("LITUSDT", "ARIAUSDT", "BIRBUSDT"):
            item = CANDIDATE_CROSSWALK[symbol]
            self.assertEqual(item.research_class, "ticker_collision_unresolved")
            self.assertEqual(len(item.proposed_asset_refs), 2)
            self.assertEqual(research_category(symbol, False),
                             "ticker_collision_unresolved")
        self.assertEqual(research_category("XAUTUSDT", False),
                         "tokenized_gold_policy_gate")
        self.assertEqual(research_category("XAUTUSDT", True),
                         "tokenized_gold_policy_gate")
        self.assertNotEqual(research_category("XAUUSDT", False),
                            research_category("XAUTUSDT", False))

    def test_archived_reference_is_not_positive_crypto_verification(self):
        self.assertEqual(research_category("BTCUSDT", True),
                         "archived_crypto_reference_only")
        self.assertEqual(research_category("UNKNOWNUSDT", False),
                         "identity_unresolved")
        self.assertEqual(research_category("SOXLUSDT", True),
                         "bybit_tradfi_documented_retrospective")
        self.assertIsNone(research_details("SOXLUSDT"))

    def test_frontier_uses_full_order_not_first_50_after_arbitrary_heuristics(self):
        prefix = ("BTCUSDT", "SOXLUSDT", "XAUUSDT", "ETHUSDT",
                  "NVDAUSDT", "1000PEPEUSDT", "PUMPFUNUSDT")
        tail = tuple(f"TEST{i:03d}USDT" for i in range(60))
        ranked = prefix + tail
        frontier = research_frontier(ranked)
        self.assertEqual(len(frontier), 50)
        self.assertEqual(frontier[:4], ("BTCUSDT", "ETHUSDT",
                                        "1000PEPEUSDT", "PUMPFUNUSDT"))
        self.assertNotIn("SOXLUSDT", frontier)
        self.assertNotIn("XAUUSDT", frontier)
        self.assertNotIn("NVDAUSDT", frontier)
        self.assertIn("TEST045USDT", frontier)
        self.assertNotIn("TEST046USDT", frontier)
        self.assertEqual(len(research_frontier(ranked, limit=10)), 10)
        self.assertEqual(research_frontier(prefix), (
            "BTCUSDT", "ETHUSDT", "1000PEPEUSDT", "PUMPFUNUSDT"
        ))

    def test_one_character_base_matches_d256_scope_and_does_not_approve_it(self):
        # D256 accepts 5..32 total characters; D261 previously required
        # >= 2 base chars and crashed on this valid shape at rank 51+.
        self.assertEqual(research_frontier(("XUSDT",)), ("XUSDT",))
        self.assertEqual(research_frontier(("1USDT",)), ("1USDT",))
        self.assertEqual(research_category("XUSDT", False),
                         "identity_unresolved")
        self.assertIsNone(research_details("XUSDT"))
        self.assertEqual(len(research_frontier(
            tuple(f"A{i:03d}USDT" for i in range(60)) + ("XUSDT",)
        )), 50)
        self.assertEqual(research_frontier(("A"*28 + "USDT",)),
                         ("A"*28 + "USDT",))
        for symbol in ("USDT", "A"*29 + "USDT", "A-USDT",
                       "aUSDT", "XUSDC"):
            with self.assertRaises(ValueError):
                research_frontier((symbol,))
        self.assertFalse(research_provenance()[
            "candidate_venue_crosswalk_verified"
        ])

    def test_fail_closed_malformed_inputs_or_duplicated_candidates(self):
        for ranked in (
            (), ("BTCUSDT", "BTCUSDT"), ("BTCUSDT", "bad"),
            ["BTCUSDT"], ("SOXLUSDT", 1),
        ):
            with self.assertRaises(ValueError):
                research_frontier(ranked)
        for limit in (0, -1, 51, True, "50"):
            with self.assertRaises(ValueError):
                research_frontier(("BTCUSDT",), limit=limit)
        for symbol in ("btcUSDT", "INVALID/USDT", "BTCUSD", 4):
            with self.assertRaises(ValueError):
                research_category(symbol, False)
        with self.assertRaises(ValueError):
            research_category("BTCUSDT", 1)
        with self.assertRaises(ValueError):
            CandidateCrosswalk("LITUSDT", "crypto_token_candidate_unverified",
                               "direct_ticker_hypothesis",
                               ("coingecko:lighter", "coingecko:litentry"),
                               ("https://www.coingecko.com/en/coins/lighter",))
        with self.assertRaises(ValueError):
            CandidateCrosswalk("EVILUSDT", "crypto_token_candidate_unverified",
                               "direct_ticker_hypothesis", ("coingecko:evil",),
                               ("https://user:pass@example.com/evidence",))


if __name__ == "__main__":
    unittest.main()
