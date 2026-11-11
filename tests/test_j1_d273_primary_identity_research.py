"""D273 first-party identity lead: evidence, chronology, and fail-closed tests."""
import dataclasses
import unittest

from crypto_intelligence_agent.bybit_primary_identity_research import (
    PRIMARY_LEADS, PrimaryIdentityLead, lead_digest, primary_research_details,
)

NOV6 = 1793971800000
NOV12 = 1794492000000


class PrimaryIdentityLeadTests(unittest.TestCase):
    def test_dgai_two_sources_not_historical_pit(self):
        x = primary_research_details("DGAIUSDT", market_window_end_ms=NOV6)
        self.assertEqual(x["venue_underlying_research"], "DGrid AI")
        self.assertEqual(x["primary_publisher_roots_count"], 2)
        self.assertTrue(x["primary_sources_published_before_market_window"])
        self.assertFalse(x["research_reviewed_before_market_window"])
        self.assertEqual(x["status"], "historical_pit_not_established")
        for flag in ("identity_approved", "identity_pit_authenticated",
                     "eligible_top50", "marketwide_top50_verified",
                     "provider_identity_authenticated", "trading_enabled",
                     "orders_sent", "database_modified"):
            self.assertFalse(x[flag], flag)
        self.assertEqual(x["network_requests"], 0)

    def test_future_window_still_never_authorizes_identity(self):
        x = primary_research_details("DGAIUSDT", market_window_end_ms=NOV12)
        self.assertEqual(x["status"], "documented_two_primary_sources_research_only")
        self.assertFalse(x["identity_approved"])
        self.assertFalse(x["eligible_top50"])

    def test_unknown_does_not_inherit_venue_identity(self):
        self.assertIsNone(primary_research_details(
            "UNKNOWNUSDT", market_window_end_ms=NOV6))

    def test_stable_digest(self):
        self.assertEqual(lead_digest(), lead_digest())
        self.assertEqual(len(lead_digest()), 64)
        self.assertEqual(set(PRIMARY_LEADS), {"DGAIUSDT", "CLANKERUSDT"})

    def test_different_sources_required_and_negative_veto(self):
        row = PRIMARY_LEADS["DGAIUSDT"]
        for changes in (
            {"venue_symbol": "BZUSDT"},
            {"venue_symbol": "DGAI/USDT"},
            {"venue_announcement_url": row.independent_announcement_url},
            {"independent_announcement_url": row.venue_announcement_url},
            {"independent_announcement_url": "https://user:pass@www.gate.com/pt-br/announcements/article/101292"},
            {"venue_announcement_url": "https://announcements.bybit.com/en/article/x?token=secret"},
            {"network_contract_id": "bsc:invalid"},
            {"research_reviewed_on": "2026-08-01"},
            {"independent_published_on": "2026-11-12"},
            {"venue_published_on": "2026-02-30"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    dataclasses.replace(row, **changes)

    def test_clanker_two_primary_origins_do_not_override_collision_policy(self):
        from crypto_intelligence_agent.bybit_identity_crosswalk_research import (
            research_category,
        )
        x = primary_research_details("CLANKERUSDT", market_window_end_ms=NOV6)
        self.assertEqual(x["venue_underlying_research"], "tokenbot (CLANKER)")
        self.assertEqual(x["candidate_canonical_asset_ref"], "coingecko:tokenbot-2")
        self.assertEqual(
            x["network_contract_research"],
            "base:0x1bc0c42215582d5a085795f4badbac3ff36d1bcb",
        )
        self.assertEqual(x["primary_publisher_roots_count"], 2)
        self.assertTrue(x["primary_sources_published_before_market_window"])
        self.assertFalse(x["research_reviewed_before_market_window"])
        self.assertEqual(x["status"], "historical_pit_not_established")
        self.assertEqual(
            research_category("CLANKERUSDT", False), "ticker_collision_unresolved"
        )
        for key in ("identity_approved", "identity_pit_authenticated",
                    "eligible_top50", "marketwide_top50_verified",
                    "trading_enabled", "orders_sent"):
            self.assertFalse(x[key])

    def test_clanker_untrusted_source_and_token_are_rejected(self):
        row = PRIMARY_LEADS["CLANKERUSDT"]
        for change in (
            {"venue_announcement_url": "https://not-bybit.com/en/learn/ai/tokenbot"},
            {"independent_announcement_url": "https://www.binance.com/en/support/announcement/detail/x?secret=1"},
            {"independent_announcement_url": "https://www.bybit.com/en/learn/ai/what-is-clanker-tokenbot"},
            {"network_contract_id": "base:0x000"},
            {"venue_symbol": "XAUUSDT"},
            {"venue_published_on": "2026-12-01"},
            {"research_reviewed_on": "2025-01-01"},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    dataclasses.replace(row, **change)

    def test_invalid_timestamp_rejected_without_side_effects(self):
        for t in (True, "1793971800000", -1, 0, 5.5, None):
            with self.subTest(timestamp=t):
                with self.assertRaises(ValueError):
                    primary_research_details("DGAIUSDT", market_window_end_ms=t)


if __name__ == "__main__":
    unittest.main()
