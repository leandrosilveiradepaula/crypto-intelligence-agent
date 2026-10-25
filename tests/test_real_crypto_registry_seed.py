"""J1/WU33 real two-asset identity snapshot: integrity, causality and scope.

All tests are offline. A real public source URL is not a licensed market feed,
a live contract guarantee, or a complete current/historical Top50 universe.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import unittest

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, CryptoRegistrySnapshot, SOURCE_POLICY,
    load_registry_json, registry_sha256,
)
from crypto_intelligence_agent.market_data import DataValidationError

MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent /
    "registries" / "crypto-btc-eth-20261025-v1.json"
)


def live_references():
    return load_registry_json(MANIFEST_PATH.read_bytes())


def contract(symbol, base, category=None, *, pair=None):
    return {
        "symbol": symbol, "base": base, "quote": "USD",
        "pair": pair or f"{base}:USD", "category": category,
        "type": "flexible_futures", "tradfi": False,
        "tradeable": True, "suspended": False, "isExpired": False,
        "tickSize": "1", "contractSize": "1",
    }


def ticker(symbol, value):
    return {
        "symbol": symbol, "tag": "perpetual",
        "suspended": False, "postOnly": False,
        "volumeQuote": value,
    }


class ActualRegistrySeedTests(unittest.TestCase):
    def test_real_sources_are_limited_to_btc_eth_and_immutable(self):
        snapshot = live_references()
        self.assertEqual(snapshot.verified_crypto_bases, frozenset({"BTC", "ETH"}))
        self.assertEqual(
            {a.base: a.canonical_id for a in snapshot.assets},
            {"BTC": "bitcoin-mainnet", "ETH": "ethereum-native-ether"},
        )
        self.assertEqual(snapshot.label, "btc-eth-20261025-technical-v1")
        self.assertEqual(snapshot.selector_version, "sha256-" + snapshot.sha256_digest)
        self.assertGreater(snapshot.observed_at_ms, 1_792_964_400_000)
        self.assertEqual(len(snapshot.assets), 2)
        for item in snapshot.assets:
            with self.subTest(base=item.base):
                self.assertEqual(item.reviewed_by, "assistant-technical-review")
                self.assertEqual(len(item.evidence), 2)
                self.assertEqual(len({e.publisher for e in item.evidence}), 2)
                self.assertEqual(len({e.publisher_root for e in item.evidence}), 2)
                self.assertTrue(all(e.url.startswith("https://") for e in item.evidence))
                self.assertTrue(all(e.observed_at_ms <= item.reviewed_at_ms <=
                                    snapshot.observed_at_ms for e in item.evidence))
        self.assertEqual(
            {e.publisher_root for item in snapshot.assets for e in item.evidence},
            {"bitcoin.org", "europa.eu", "ethereum.org", "coingecko.com"},
        )
        self.assertEqual(live_references(), snapshot)

    def test_content_hash_matches_exact_manifest_and_tampering_fails(self):
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["usage_policy"], SOURCE_POLICY)
        unsigned = {key: value for key, value in payload.items() if key != "sha256"}
        self.assertEqual(registry_sha256(unsigned), payload["sha256"])
        for field, replacement in (
            ("base", "AAPLX"), ("canonical_id", "fake-asset"),
            ("reviewed_by", "fictional-human-reviewer"),
        ):
            modified = deepcopy(payload)
            modified["assets"][0][field] = replacement
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                CryptoRegistrySnapshot.from_manifest(modified)
        modified = deepcopy(payload)
        modified["assets"][0]["evidence"][1]["url"] = "https://other.invalid/bitcoin"
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(modified)

    def test_registry_never_backdates_live_crypto_identity(self):
        snapshot = live_references()
        history = CryptoRegistryHistory([snapshot, snapshot])
        when = snapshot.observed_at_ms
        with self.assertRaisesRegex(DataValidationError, "no reviewed crypto registry"):
            history.as_of(when - 1, max_age_ms=86_400_000)
        self.assertEqual(history.as_of(when, max_age_ms=0), snapshot)
        with self.assertRaisesRegex(DataValidationError, "too old"):
            history.as_of(when + 86_400_001, max_age_ms=86_400_000)

    def test_live_registry_only_selects_two_bases_in_synthetic_market(self):
        snapshot = live_references()
        history = CryptoRegistryHistory([snapshot])
        t = snapshot.observed_at_ms + 5_000
        instruments = [
            contract("PF_XBTUSD", "BTC", pair="XBT:USD"),
            contract("PF_ETHUSD", "ETH"),
            contract("PF_AAPLXUSD", "AAPLX", category="xStocks"),
            contract("PF_NEWUSD", "NEW"),
        ]
        tickers = [
            ticker("PF_XBTUSD", Decimal("300.000000000012")),
            ticker("PF_ETHUSD", Decimal("250.1")),
            ticker("PF_AAPLXUSD", Decimal("999999999999999")),
            ticker("PF_NEWUSD", Decimal("70000000")),
        ]
        snap = history.select_at(
            instruments=instruments, tickers=tickers,
            market_observed_at_ms=t, decision_at_ms=t + 1_000,
            max_market_age_ms=2_000, max_registry_age_ms=10_000,
        )
        self.assertEqual([(x.symbol, x.rank) for x in snap.eligible],
                         [("PF_XBTUSD", 1), ("PF_ETHUSD", 2)])
        self.assertEqual(snap.eligible[0].quote_volume, Decimal("300.000000000012"))
        self.assertEqual(snap.excluded["PF_AAPLXUSD"], "non_crypto_category")
        self.assertEqual(snap.excluded["PF_NEWUSD"], "base_not_verified_crypto")
        self.assertIn(snapshot.sha256_digest, snap.selection_rule_version)
        self.assertFalse(any(x.symbol.endswith("AAPLXUSD") for x in snap.eligible))
        self.assertLessEqual(len(snap.eligible), 2)

    def test_forged_instrument_cannot_borrow_btc_identity(self):
        snapshot = live_references()
        history = CryptoRegistryHistory([snapshot])
        t = snapshot.observed_at_ms + 1_000
        selected = history.select_at(
            instruments=[contract("PF_AAPLXUSD", "BTC", pair="BTC:USD")],
            tickers=[ticker("PF_AAPLXUSD", "999999999999")],
            market_observed_at_ms=t, decision_at_ms=t,
            max_market_age_ms=0, max_registry_age_ms=10_000,
        )
        self.assertEqual(selected.eligible, ())
        self.assertEqual(selected.excluded["PF_AAPLXUSD"], "symbol_base_mismatch")

    def test_future_market_time_and_stale_snapshot_fail(self):
        history = CryptoRegistryHistory([live_references()])
        t = live_references().observed_at_ms
        with self.assertRaises(DataValidationError):
            history.select_at(
                instruments=[], tickers=[],
                market_observed_at_ms=t - 1, decision_at_ms=t + 1,
                max_market_age_ms=10_000, max_registry_age_ms=10_000,
            )
        with self.assertRaises(DataValidationError):
            history.select_at(
                instruments=[], tickers=[],
                market_observed_at_ms=t + 1, decision_at_ms=t,
                max_market_age_ms=10_000, max_registry_age_ms=10_000,
            )


if __name__ == "__main__":
    unittest.main()
