"""J1 D265: BZ Brent commodity rejection and unverified symbol crosswalk."""
from __future__ import annotations

import json
import unittest

from crypto_intelligence_agent.bybit_tradfi_negative_evidence import (
    NEGATIVE_EVIDENCE, catalog_digest, classify_retrospective,
)
from crypto_intelligence_agent.bybit_identity_research_leads_d265 import (
    RESEARCH_LEADS, ResearchLead, lead_details, lead_digest,
)
from crypto_intelligence_agent.bybit_identity_crosswalk_research import (
    research_category, research_details, research_frontier,
)


class D265IdentityEvidenceTests(unittest.TestCase):
    def test_provider_documented_bz_oil_is_negative_not_crypto(self):
        self.assertEqual(len(NEGATIVE_EVIDENCE), 25)
        evidence = NEGATIVE_EVIDENCE["BZUSDT"]
        self.assertEqual(evidence.provider_category,
                         "commodity_brent_oil_bybit_documented")
        self.assertEqual(evidence.announcement_date, "2026-05-13")
        self.assertIn("announcements.bybit.com", evidence.announcement_url)
        self.assertEqual(len(catalog_digest()), 64)
        self.assertEqual(research_category("BZUSDT", False),
                         "bybit_tradfi_documented_retrospective")
        self.assertEqual(research_category("BZUSDT", True),
                         "bybit_tradfi_documented_retrospective")
        self.assertEqual(classify_retrospective("BZUSDT", False),
                         "bybit_tradfi_documented_retrospective")
        self.assertIsNone(research_details("BZUSDT"))

    def test_nine_new_symbols_research_only_not_authenticated(self):
        self.assertEqual(len(RESEARCH_LEADS), 9)
        self.assertEqual(len(lead_digest()), 64)
        expected = {
            "WLFIUSDT", "CAPUSDT", "CYBERUSDT", "CLANKERUSDT",
            "XPLUSDT", "FARTCOINUSDT", "DGAIUSDT", "PONSUSDT",
            "ASTERUSDT",
        }
        self.assertEqual(set(RESEARCH_LEADS), expected)
        for sym, lead in RESEARCH_LEADS.items():
            self.assertNotIn(sym, NEGATIVE_EVIDENCE)
            self.assertEqual(research_category(sym, False), lead.category)
            detail = research_details(sym)
            self.assertEqual(detail, lead_details(sym))
            self.assertIs(detail["identity_approval"], False)
            self.assertIs(detail["evidence_pit_authenticated"], False)
            self.assertIs(detail["provider_contract_id_authenticated"], False)
            self.assertNotIn("prices", json.dumps(detail))
            self.assertNotIn("orders_sent", json.dumps(detail))
        self.assertEqual(research_category("DGAIUSDT", False),
                         "identity_unresolved")
        self.assertEqual(research_details("DGAIUSDT")[
            "proposed_asset_refs_unverified"], [])

    def test_clanker_same_symbol_two_different_assets_must_stay_blocked(self):
        r = RESEARCH_LEADS["CLANKERUSDT"]
        self.assertEqual(r.category, "ticker_collision_unresolved")
        self.assertEqual(set(r.proposed_refs),
                         {"coingecko:tokenbot-2", "coingecko:clanker"})
        self.assertEqual(research_category("CLANKERUSDT", True),
                         "ticker_collision_unresolved")
        self.assertNotEqual(
            RESEARCH_LEADS["XPLUSDT"].proposed_refs[0],
            "coingecko:xpl"
        )

    def test_d265_brent_excluded_from_research_frontier_even_without_d263_flag(self):
        ranked = ("BTCUSDT", "BZUSDT", "ETHUSDT", "XPLUSDT", "DGAIUSDT")
        self.assertEqual(research_frontier(ranked), (
            "BTCUSDT", "ETHUSDT", "XPLUSDT", "DGAIUSDT"
        ))
        self.assertNotIn("BZUSDT", research_frontier(ranked))
        self.assertEqual(research_category("BTCUSDT", True),
                         "archived_crypto_reference_only")
        self.assertEqual(research_category("XPLUSDT", False),
                         "crypto_token_candidate_unverified")
        self.assertEqual(research_category("DGAIUSDT", False),
                         "identity_unresolved")

    def test_tampered_candidate_and_unsafe_url_are_refused(self):
        cases = [
            ("CLANKERUSDT", "ticker_collision_unresolved",
             ("coingecko:tokenbot-2",),
             ("https://www.coingecko.com/en/coins/tokenbot-2",),
             "ticker_collision_needs_chain_contract"),
            ("DGAIUSDT", "identity_unresolved",
             ("coingecko:fake",), (),
             "identity_no_credible_crosswalk"),
            ("XPLUSDT", "crypto_token_candidate_unverified",
             ("coingecko:plasma",),
             ("http://www.coingecko.com/en/coins/plasma",),
             "direct_token_hypothesis_needs_venue_proof"),
            ("XPLUSDT", "crypto_token_candidate_unverified",
             ("coingecko:plasma",),
             ("https://user:pass@www.coingecko.com/en/coins/plasma",),
             "direct_token_hypothesis_needs_venue_proof"),
        ]
        for args in cases:
            with self.subTest(symbol=args[0]):
                with self.assertRaises(ValueError):
                    ResearchLead(*args)


if __name__ == "__main__":
    unittest.main()
