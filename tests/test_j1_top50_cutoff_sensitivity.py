"""D276: deterministic conditional replacements at the Top50 research cutoff."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_top50_cutoff_sensitivity import cutoff_sensitivity


class CutoffSensitivityTests(unittest.TestCase):
    def setUp(self):
        # Synthetic frozen rank: 50 members plus at least 10 rivals.
        self.symbols = tuple(f"C{i:03d}USDT" for i in range(60))
        self.symbols = (
            self.symbols[:16] + ("LITUSDT",) + self.symbols[17:21] +
            ("ARIAUSDT",) + self.symbols[22:25] + ("BIRBUSDT",) +
            self.symbols[26:38] + ("CLANKERUSDT",) +
            self.symbols[39:49] + ("XAUTUSDT",) + self.symbols[50:]
        )
        self.assertEqual(len(self.symbols), 60)

    def evaluate(self, **kwargs):
        args = dict(all_complete_ranked_symbols=self.symbols,
                    retrospectively_excluded_symbols=frozenset(),
                    incomplete_candle_contracts=3,
                    include_private_symbols=True)
        args.update(kwargs)
        return cutoff_sensitivity(**args)

    def test_scenarios_replacements_and_no_eligibility_promotion(self):
        out = self.evaluate()
        baseline, gold, all_ambiguous = out["scenarios"]
        self.assertEqual(out["complete_candle_contracts"], 60)
        self.assertEqual(out["incomplete_candle_contracts"], 3)
        self.assertEqual(baseline["replacements_in_top50_count"], 0)
        self.assertEqual(gold["replacements_in_top50_count"], 1)
        self.assertEqual(
            gold["replacement_symbols_only"],
            [{"research_position": 50, "symbol": "C050USDT"}],
        )
        self.assertEqual(all_ambiguous["replacements_in_top50_count"], 5)
        self.assertEqual(
            [r["symbol"] for r in all_ambiguous["replacement_symbols_only"]],
            ["C050USDT", "C051USDT", "C052USDT", "C053USDT", "C054USDT"],
        )
        self.assertEqual(out["baseline_research_frontier_count"], 50)
        self.assertTrue(out["incomplete_contracts_remain_possible_rivals"])
        self.assertTrue(out["retrospective_exclusions_are_not_historical_pit"])
        for flag in ("identity_pit_authenticated", "marketwide_top50_verified",
                     "trading_enabled", "orders_sent", "database_modified"):
            self.assertFalse(out[flag])
        self.assertEqual(out["network_requests"], 0)

    def test_digest_reproducible_and_default_private(self):
        first = self.evaluate(include_private_symbols=False)
        second = self.evaluate(include_private_symbols=False)
        self.assertEqual(first, second)
        encoded = json.dumps(first)
        for symbol in self.symbols:
            self.assertNotIn(symbol, encoded)
        for scenario in first["scenarios"]:
            self.assertNotIn("replacement_symbols_only", scenario)
            self.assertEqual(len(scenario["retrospective_top50_symbol_order_digest"]), 64)

    def test_existing_exclusion_keeps_scenarios_consistent(self):
        exclusion = frozenset({"C000USDT", "C015USDT"})
        r = self.evaluate(retrospectively_excluded_symbols=exclusion)
        self.assertEqual(r["retrospectively_excluded_complete_contracts"], 2)
        self.assertEqual(r["scenarios"][0]["ranked_complete_candidates_remaining"], 58)
        self.assertEqual(r["scenarios"][1]["replacements_in_top50_count"], 1)
        self.assertEqual(r["scenarios"][2]["replacements_in_top50_count"], 5)

    def test_incomplete_scope_fails_closed_and_stays_unverified(self):
        r = self.evaluate(incomplete_candle_contracts=0)
        self.assertFalse(r["incomplete_contracts_remain_possible_rivals"])
        self.assertFalse(r["marketwide_top50_verified"])
        for changes in (
            {"all_complete_ranked_symbols": self.symbols[:49]},
            {"all_complete_ranked_symbols": list(self.symbols)},
            {"all_complete_ranked_symbols": self.symbols[:50] + (self.symbols[0],)},
            {"all_complete_ranked_symbols": self.symbols[:50] + ("badUSDT",)},
            {"retrospectively_excluded_symbols": {"C000USDT"}},
            {"incomplete_candle_contracts": -1},
            {"incomplete_candle_contracts": True},
            {"include_private_symbols": 1},
            {"retrospectively_excluded_symbols": frozenset(self.symbols[:11])},
        ):
            with self.subTest(changes=str(changes)[:50]):
                with self.assertRaises(ValueError):
                    self.evaluate(**changes)

    def test_no_network_or_db(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP")), \
             patch("sqlite3.connect", side_effect=AssertionError("SQLite")):
            self.evaluate()


if __name__ == "__main__":
    unittest.main()
