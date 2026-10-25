"""J1/WU33: reproducible load of a real, limited BTC/ETH identity seed.

The linked publishers were reviewed for asset identity, NOT market-data rights,
venue eligibility, a commercial product or a 50-asset universe.
No third-party API or network call is made by these tests.
"""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import json
import unittest

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, load_registry_json, registry_sha256,
)
from crypto_intelligence_agent.market_data import DataValidationError


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "research" / "registry" / "research-btc-eth-20261025-v1.json"
CAPTURE_MS = 1_792_964_744_730
EXPECTED_SHA = "c3b6cb2b0e477f991cceeb5fcc3b02be50e921348996b493bec0c96d514284c3"


def instrument(symbol: str, base: str, *, category=None) -> dict:
    return {
        "symbol": symbol, "base": base, "quote": "USD", "pair": f"{base}:USD",
        "type": "flexible_futures", "tradfi": False,
        "tradeable": True, "suspended": False, "category": category,
        "tickSize": "1", "contractSize": "1",
    }


def ticker(symbol: str, volume: str) -> dict:
    return {
        "symbol": symbol, "tag": "perpetual", "postOnly": False,
        "suspended": False, "volumeQuote": volume,
    }


class RealResearchSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SEED.read_bytes()
        cls.manifest = json.loads(cls.raw)
        cls.snapshot = load_registry_json(cls.raw)
        cls.history = CryptoRegistryHistory([cls.snapshot])

    def test_real_seed_integrity_two_researched_assets_and_external_publishers(self):
        s = self.snapshot
        self.assertEqual(s.sha256_digest, EXPECTED_SHA)
        self.assertEqual(s.selector_version, "sha256-" + EXPECTED_SHA)
        self.assertEqual(s.observed_at_ms, CAPTURE_MS)
        self.assertEqual(s.verified_crypto_bases, frozenset({"BTC", "ETH"}))
        self.assertEqual(
            {a.base: a.canonical_id for a in s.assets},
            {"BTC": "bitcoin-mainnet", "ETH": "ethereum-mainnet-native-ether"},
        )
        self.assertEqual(self.manifest["usage_policy"], "internal_research_only")
        self.assertEqual(self.manifest["label"], "research-btc-eth-20261025-v1")
        for asset in s.assets:
            with self.subTest(asset=asset.base):
                self.assertEqual(asset.reviewed_by, "chatgpt-technical-review")
                self.assertEqual(asset.reviewed_at_ms, CAPTURE_MS)
                self.assertEqual(len(asset.evidence), 2)
                self.assertEqual(len({e.publisher_root for e in asset.evidence}), 2)
                self.assertTrue(all(e.observed_at_ms == CAPTURE_MS for e in asset.evidence))
        self.assertEqual({e.publisher_root for e in s.assets[0].evidence},
                         {"bitcoin.org", "europa.eu"})
        self.assertEqual({e.publisher_root for e in s.assets[1].evidence},
                         {"ethereum.org", "coingecko.com"})
        self.assertEqual(
            registry_sha256({key: value for key, value in self.manifest.items()
                             if key != "sha256"}),
            EXPECTED_SHA,
        )

    def test_no_backdating_registry_to_prior_market_observation(self):
        with self.assertRaisesRegex(DataValidationError, "no reviewed crypto registry"):
            self.history.as_of(CAPTURE_MS - 1, max_age_ms=86_400_000)
        self.assertEqual(self.history.as_of(CAPTURE_MS, max_age_ms=0), self.snapshot)
        with self.assertRaisesRegex(DataValidationError, "too old"):
            self.history.as_of(CAPTURE_MS + 86_400_001, max_age_ms=86_400_000)

    def test_only_btc_eth_from_synthetic_metadata_even_when_tradfi_flag_false(self):
        market_at = CAPTURE_MS + 1_000
        universe = self.history.select_at(
            instruments=[
                instrument("PF_XBTUSD", "XBT"),
                instrument("PF_ETHUSD", "ETH"),
                instrument("PF_AAPLXUSD", "AAPLX", category="xStocks"),
                instrument("PF_NEWUSD", "NEW", category="DeFi"),
            ],
            tickers=[
                ticker("PF_XBTUSD", "320000000.1234"),
                ticker("PF_ETHUSD", "120000000.5678"),
                ticker("PF_AAPLXUSD", "999999999999"),
                ticker("PF_NEWUSD", "888888888888"),
            ],
            market_observed_at_ms=market_at,
            decision_at_ms=market_at + 1_000,
            max_market_age_ms=30_000,
            max_registry_age_ms=3_600_000,
            max_symbols=50,
        )
        self.assertEqual([row.symbol for row in universe.eligible],
                         ["PF_XBTUSD", "PF_ETHUSD"])
        self.assertEqual(universe.excluded["PF_AAPLXUSD"], "non_crypto_category")
        self.assertEqual(universe.excluded["PF_NEWUSD"], "base_not_verified_crypto")
        self.assertTrue(universe.selection_rule_version.endswith(EXPECTED_SHA))
        # Fixture values are not a Kraken GET; never report real Top50 from here.
        self.assertEqual(len(universe.eligible), 2)

    def test_mutation_without_new_hash_fails_even_in_real_seed(self):
        data = json.loads(self.raw)
        data["assets"][1]["canonical_id"] = "ethereum-network-wrong-asset"
        with self.assertRaisesRegex(DataValidationError, "hash mismatch"):
            load_registry_json(json.dumps(data))
        data = json.loads(self.raw)
        data["usage_policy"] = "public_redistribution"
        with self.assertRaises(DataValidationError):
            load_registry_json(json.dumps(data))

    def test_no_live_or_commercial_rights_asserted_by_seed(self):
        self.assertNotIn(b"api_key", self.raw)
        self.assertNotIn(b"volumeQuote", self.raw)
        self.assertNotIn(b"private_key", self.raw)
        self.assertNotIn(b"commercial_approved", self.raw)
        self.assertFalse(hasattr(self.snapshot, "commercial_rights_authorized"))
        self.assertFalse(hasattr(self.snapshot, "ready_for_live_top50"))


if __name__ == "__main__":
    unittest.main()
