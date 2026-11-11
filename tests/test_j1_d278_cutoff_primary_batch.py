"""D278: multi-symbol primary research is not PIT identity certification."""
from __future__ import annotations

import dataclasses
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_cutoff_primary_batch_d278 import (
    PublicSource, RivalResearch, RIVALS, batch_research,
)


class D278CutoffPrimaryBatch(unittest.TestCase):
    def setUp(self):
        self.frontier = tuple(f"COIN{i:03d}USDT" for i in range(46)) + (
            "LITUSDT", "ARIAUSDT", "BIRBUSDT", "CLANKERUSDT",
        )
        self.replacements = (
            "LYNUSDT", "DOTUSDT", "ICNTUSDT", "ELSAUSDT", "AEROUSDT",
        ) + tuple(f"BACK{i:03d}USDT" for i in range(5))
        self.assertEqual(len(self.frontier), 50)

    def evaluate(self, *, show=False):
        return batch_research(
            raw_baseline_frontier=self.frontier,
            possible_replacements=self.replacements,
            include_private_symbols=show,
        )

    def test_all_nine_original_and_replacements_without_approval(self):
        r = self.evaluate(show=True)
        self.assertEqual(r["symbol_research_catalog_size"], 9)
        self.assertEqual(r["selected_in_observed_frontier_and_replacements"], 9)
        counts = r["selected_source_state_counts"]
        self.assertEqual(counts["cross_venue_perpetual_name_research"], 3)
        self.assertEqual(counts["existing_primary_collided_research"], 1)
        self.assertEqual(counts["spot_migration_not_perpetual"], 1)
        self.assertEqual(counts["external_underlying_no_venue_perpetual"], 1)
        self.assertEqual(counts["primary_evidence_missing"], 3)
        rows = r["private_symbol_research_rows_only"]
        self.assertEqual(
            {x["symbol"] for x in rows},
            {"LITUSDT", "ARIAUSDT", "BIRBUSDT", "CLANKERUSDT",
             "LYNUSDT", "DOTUSDT", "ICNTUSDT", "ELSAUSDT", "AEROUSDT"},
        )
        for row in rows:
            self.assertFalse(row["independently_authenticated_venue_mint"])
            self.assertFalse(row["identity_pit_authenticated"])
            self.assertFalse(row["eligible_top50"])
        for key in ("identity_pit_authenticated", "eligible_crypto_approved",
                    "marketwide_top50_verified", "trading_enabled",
                    "orders_sent", "database_modified"):
            self.assertFalse(r[key])
        self.assertEqual(r["network_requests"], 0)

    def test_default_contains_no_symbols_and_deterministic_digest(self):
        a, b = self.evaluate(), self.evaluate()
        self.assertEqual(a, b)
        self.assertNotIn("private_symbol_research_rows_only", a)
        self.assertEqual(len(a["research_catalog_digest"]), 64)
        payload = json.dumps(a)
        for symbol in RIVALS:
            self.assertNotIn(symbol, payload)

    def test_does_not_change_old_collision_status(self):
        result = self.evaluate(show=True)
        rows = {r["symbol"]: r for r in result["private_symbol_research_rows_only"]}
        for symbol in ("LITUSDT", "ARIAUSDT", "BIRBUSDT", "CLANKERUSDT"):
            self.assertEqual(rows[symbol]["historical_category_unchanged"],
                             "ticker_collision_unresolved")
        self.assertEqual(rows["AEROUSDT"]["source_class"],
                         "spot_migration_not_perpetual")
        self.assertEqual(rows["DOTUSDT"]["public_primary_urls"], [])
        self.assertEqual(rows["ELSAUSDT"]["proposed_underlying_unverified"],
                         "HeyElsa")

    def test_sources_have_fixed_distinct_origins(self):
        for sym in ("LYNUSDT", "LITUSDT", "ELSAUSDT"):
            records = RIVALS[sym].source_notes
            self.assertEqual(len(records), 2)
            self.assertIn("announcements.bybit.com", records[0].source_url)
            self.assertIn("www.binance.com", records[1].source_url)
        self.assertEqual(RIVALS["ICNTUSDT"].research_state,
                         "external_underlying_no_venue_perpetual")
        self.assertEqual(RIVALS["AEROUSDT"].research_state,
                         "spot_migration_not_perpetual")

    def test_malicious_urls_and_false_inferences_rejected(self):
        sample = RIVALS["ELSAUSDT"]
        venue, independent = sample.source_notes
        for change in (
            {"source_url": "http://announcements.bybit.com/en/article/x"},
            {"source_url": "https://fake-bybit.com/en/article/x"},
            {"source_url": "https://user:pass@announcements.bybit.com/en/article/x"},
            {"source_url": venue.source_url + "?token=secret"},
            {"role": "independent_perpetual_underlying"},
            {"published_on": "2030-02-01"},
            {"published_on": "2026-02-30"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                dataclasses.replace(venue, **change)
        for bad in (
            {"research_state": "primary_evidence_missing"},
            {"research_state": "spot_migration_not_perpetual"},
            {"source_notes": (venue, venue)},
            {"proposed_underlying": "<script>"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                dataclasses.replace(sample, **bad)
        with self.assertRaises(ValueError):
            dataclasses.replace(RIVALS["DOTUSDT"],
                                proposed_underlying="Polkadot")
        self.assertIsInstance(independent, PublicSource)

    def test_scope_duplicate_overlap_bad_types(self):
        for front, replacement in (
            (self.frontier[:49], self.replacements),
            (list(self.frontier), self.replacements),
            (self.frontier[:-1] + (self.frontier[0],), self.replacements),
            (self.frontier[:-1] + ("badUSDT",), self.replacements),
            (self.frontier, ("LYNUSDT", "LYNUSDT")),
            (self.frontier, (self.frontier[0],)),
        ):
            with self.subTest(front=repr(front)[:35]), self.assertRaises(ValueError):
                batch_research(raw_baseline_frontier=front,
                               possible_replacements=replacement)
        with self.assertRaises(ValueError):
            batch_research(raw_baseline_frontier=self.frontier,
                           possible_replacements=self.replacements,
                           include_private_symbols=1)

    def test_no_sqlite_or_network_access(self):
        with patch("sqlite3.connect", side_effect=AssertionError("SQLite")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("HTTP")):
            self.evaluate(show=True)


if __name__ == "__main__":
    unittest.main()
