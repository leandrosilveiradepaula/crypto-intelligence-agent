"""Offline and reproducible WU10 crypto registry provenance/temporal tests.

Fixture sources are illustrative only. No actual real-world crypto identity is
asserted or independently licensed by these tests.
"""
from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, CryptoRegistrySnapshot, SOURCE_POLICY,
    load_registry_json, registry_sha256,
)
from crypto_intelligence_agent.market_data import DataValidationError


T0 = 1_800_000_000_000
HOUR = 3_600_000


def fixture_evidence(*, when: int = T0 - 30_000):
    return [
        {"publisher": "example-project", "asset_ref": "btc-mainnet",
         "url": "https://project.example.org/asset/btc", "observed_at_ms": when},
        {"publisher": "example-reference", "asset_ref": "bitcoin",
         "url": "https://catalog.test.net/coins/bitcoin", "observed_at_ms": when},
    ]


def fixture_asset(base: str = "BTC", *, when: int = T0 - 10_000):
    return {
        "base": base, "canonical_id": "bitcoin-mainnet" if base == "BTC" else "ethereum-mainnet",
        "reviewed_by": "internal-reviewer-fixture", "reviewed_at_ms": when,
        "evidence": fixture_evidence(when=when - 1000),
    }


def unsigned_manifest(*, observed: int = T0, label: str = "reviewed-fixture-v1",
                      bases=("BTC",)):
    return {
        "schema_version": 1, "observed_at_ms": observed,
        "label": label, "usage_policy": SOURCE_POLICY,
        "assets": [fixture_asset(base, when=observed - 10_000) for base in bases],
    }


def signed_fixture(unsigned=None):
    obj = deepcopy(unsigned if unsigned is not None else unsigned_manifest())
    obj["sha256"] = registry_sha256(obj)
    return obj


def contract(symbol, base, category=None):
    return {
        "symbol": symbol, "base": base, "quote": "USD", "pair": f"{base}:USD",
        "type": "flexible_futures", "tradfi": False, "category": category,
        "tradeable": True, "suspended": False,
        "tickSize": "1", "contractSize": "1",
    }


def ticker(symbol, volume):
    return {"symbol": symbol, "tag": "perpetual", "suspended": False,
            "postOnly": False, "volumeQuote": volume}


class RegistryUnitTests(unittest.TestCase):
    def test_valid_registry_is_content_addressed_and_has_independent_sources(self):
        payload = signed_fixture()
        snapshot = load_registry_json(json.dumps(payload))
        self.assertEqual(snapshot.observed_at_ms, T0)
        self.assertEqual(snapshot.sha256_digest, payload["sha256"])
        self.assertEqual(snapshot.selector_version, "sha256-" + payload["sha256"])
        self.assertEqual(len(snapshot.selector_version), 71)
        self.assertEqual(snapshot.verified_crypto_bases, frozenset({"BTC"}))
        asset = snapshot.assets[0]
        self.assertEqual(asset.base, "BTC")
        self.assertEqual(len(asset.evidence), 2)
        self.assertNotEqual(asset.evidence[0].publisher_root,
                            asset.evidence[1].publisher_root)

    def test_tampering_without_rehash_is_rejected(self):
        payload = signed_fixture()
        payload["assets"][0]["base"] = "AAPLX"
        with self.assertRaisesRegex(DataValidationError, "hash mismatch"):
            CryptoRegistrySnapshot.from_manifest(payload)

    def test_hash_does_not_replace_real_review_or_license(self):
        payload = unsigned_manifest()
        payload["assets"][0]["reviewed_by"] = ""
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
        payload = unsigned_manifest()
        payload["usage_policy"] = "redistribution_approved"
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))

    def test_future_review_and_future_evidence_fail(self):
        payload = unsigned_manifest()
        payload["assets"][0]["reviewed_at_ms"] = T0 + 1
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
        payload = unsigned_manifest()
        payload["assets"][0]["evidence"][0]["observed_at_ms"] = T0
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))

    def test_two_distinct_publishers_and_domains_required(self):
        payload = unsigned_manifest()
        payload["assets"][0]["evidence"] = payload["assets"][0]["evidence"][:1]
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
        payload = unsigned_manifest()
        payload["assets"][0]["evidence"][1]["url"] = "https://other.example.org/bitcoin"
        with self.assertRaisesRegex(DataValidationError, "independent"):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
        payload = unsigned_manifest()
        payload["assets"][0]["evidence"][1]["publisher"] = "example-project"
        with self.assertRaisesRegex(DataValidationError, "independent"):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))

    def test_bad_https_source_is_rejected_without_fetching_any_urls(self):
        malicious_urls = [
            "http://example.org/asset", "https://user:password@catalog.test.net/asset",
            "https://localhost/asset", "https://127.0.0.1/asset",
            "https://api.kraken.com/instruments", "https://catalog.test.net:444/asset",
            "https://catalog.test.net/asset?token=secret",
            "https://catalog.test.net/asset#section",
        ]
        for bad in malicious_urls:
            with self.subTest(url=bad):
                payload = unsigned_manifest()
                payload["assets"][0]["evidence"][1]["url"] = bad
                with self.assertRaises(DataValidationError):
                    CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))

    def test_conflicting_base_or_canonical_asset_identity_is_rejected(self):
        payload = unsigned_manifest(bases=("BTC", "ETH"))
        payload["assets"][1]["base"] = "BTC"
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
        payload = unsigned_manifest(bases=("BTC", "ETH"))
        payload["assets"][1]["canonical_id"] = "bitcoin-mainnet"
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))

    def test_unknown_schema_missing_fields_and_nonfinite_numbers_are_rejected(self):
        payload = unsigned_manifest()
        payload["schema_version"] = 2
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
        payload = unsigned_manifest()
        del payload["assets"]
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
        with self.assertRaises(DataValidationError):
            load_registry_json('{"observed_at_ms": NaN}')
        with self.assertRaises(DataValidationError):
            load_registry_json('{"label": "one", "label": "two"}')
        with self.assertRaises(DataValidationError):
            load_registry_json("garbage")

    def test_timestamps_must_not_be_bool_float_or_negative(self):
        for bad in (True, -1, 12.5, "1800000000000"):
            with self.subTest(observed=bad):
                payload = unsigned_manifest()
                payload["observed_at_ms"] = bad
                with self.assertRaises(DataValidationError):
                    CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))
                payload = unsigned_manifest()
                payload["assets"][0]["evidence"][0]["observed_at_ms"] = bad
                with self.assertRaises(DataValidationError):
                    CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))

    def test_json_limit_and_disallow_unknown_fields(self):
        with self.assertRaises(DataValidationError):
            load_registry_json(b"x" * 1_000_001)
        payload = unsigned_manifest()
        payload["assets"][0]["unreviewed"] = True
        with self.assertRaises(DataValidationError):
            CryptoRegistrySnapshot.from_manifest(signed_fixture(payload))

    def test_registry_immutable_replay_and_time_revisions(self):
        a = CryptoRegistrySnapshot.from_manifest(signed_fixture())
        history = CryptoRegistryHistory([a, a])
        self.assertIs(history.as_of(T0, max_age_ms=0), a)
        later = CryptoRegistrySnapshot.from_manifest(
            signed_fixture(unsigned_manifest(observed=T0 + HOUR,
                label="reviewed-fixture-v2", bases=("ETH",)))
        )
        history.append(later)
        self.assertEqual(history.as_of(T0 + HOUR, max_age_ms=0).verified_crypto_bases,
                         frozenset({"ETH"}))
        self.assertEqual(history.as_of(T0, max_age_ms=0).verified_crypto_bases,
                         frozenset({"BTC"}))
        with self.assertRaises(DataValidationError):
            history.append(a)
        with self.assertRaises(DataValidationError):
            history.append(CryptoRegistrySnapshot.from_manifest(
                signed_fixture(unsigned_manifest(
                    observed=T0 + HOUR, label="different-revision"))))
        with self.assertRaises(DataValidationError):
            history.append(CryptoRegistrySnapshot.from_manifest(
                signed_fixture(unsigned_manifest(
                    observed=T0 + 2 * HOUR, label="reviewed-fixture-v2"))))
        # A label from the FIRST snapshot must also not be recycled
        # after a different, later revision was appended.
        with self.assertRaises(DataValidationError):
            history.append(CryptoRegistrySnapshot.from_manifest(
                signed_fixture(unsigned_manifest(
                    observed=T0 + 2 * HOUR, label="reviewed-fixture-v1"))))

    def test_no_future_registry_backfill_or_stale_reference(self):
        future = CryptoRegistrySnapshot.from_manifest(signed_fixture(
            unsigned_manifest(observed=T0 + HOUR, label="future-review")))
        history = CryptoRegistryHistory([future])
        with self.assertRaisesRegex(DataValidationError, "no reviewed crypto registry"):
            history.as_of(T0, max_age_ms=24 * HOUR)
        with self.assertRaisesRegex(DataValidationError, "too old"):
            history.as_of(T0 + HOUR + 1, max_age_ms=0)

    def test_no_network_or_external_paid_service_required(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("no network permitted")):
            registry = CryptoRegistrySnapshot.from_manifest(signed_fixture())
            history = CryptoRegistryHistory([registry])
            self.assertEqual(history.as_of(T0 + 1, max_age_ms=1000), registry)


class RegistrySelectionTests(unittest.TestCase):
    def setUp(self):
        self.registry = CryptoRegistrySnapshot.from_manifest(signed_fixture())
        self.history = CryptoRegistryHistory([self.registry])
        self.instruments = [
            contract("PF_XBTUSD", "BTC"),
            contract("PF_ETHUSD", "ETH"),
            contract("PF_AAPLXUSD", "AAPLX", category="xStocks"),
        ]
        self.tickers = [
            ticker("PF_XBTUSD", "331016603.1374"),
            ticker("PF_ETHUSD", "900000000"),
            ticker("PF_AAPLXUSD", "9999999999"),
        ]

    def select(self, *, observed=T0 + 100, decision=T0 + 200,
               max_market_age=300000, max_registry_age=HOUR, history=None):
        return (self.history if history is None else history).select_at(
            instruments=self.instruments, tickers=self.tickers,
            market_observed_at_ms=observed, decision_at_ms=decision,
            max_market_age_ms=max_market_age, max_registry_age_ms=max_registry_age,
            max_symbols=50,
        )

    def test_only_approved_asset_selected_with_full_hash_version(self):
        result = self.select()
        self.assertEqual([m.symbol for m in result.eligible], ["PF_XBTUSD"])
        self.assertEqual(result.excluded["PF_ETHUSD"], "base_not_verified_crypto")
        self.assertEqual(result.excluded["PF_AAPLXUSD"], "non_crypto_category")
        self.assertEqual(result.observed_at_ms, T0 + 100)
        self.assertTrue(result.selection_rule_version.endswith(
            self.registry.sha256_digest))

    def test_later_crypto_approval_cannot_rewrite_prior_universe(self):
        later = CryptoRegistrySnapshot.from_manifest(signed_fixture(
            unsigned_manifest(observed=T0 + HOUR,
                label="reviewed-fixture-v2", bases=("ETH",))))
        history = CryptoRegistryHistory([self.registry, later])
        before = self.select(history=history)
        after = self.select(history=history, observed=T0 + HOUR + 100,
                            decision=T0 + HOUR + 200)
        self.assertEqual([m.symbol for m in before.eligible], ["PF_XBTUSD"])
        self.assertEqual([m.symbol for m in after.eligible], ["PF_ETHUSD"])
        self.assertNotEqual(before.selection_rule_version, after.selection_rule_version)

    def test_future_market_data_and_old_market_data_both_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "future market"):
            self.select(observed=T0 + 201, decision=T0 + 200)
        # Exactly at the configured freshness boundary is still valid.
        self.assertEqual(len(self.select(
            observed=T0 + 100, decision=T0 + 300100,
            max_market_age=300000,
        ).eligible), 1)
        # One millisecond beyond the boundary must fail closed.
        with self.assertRaisesRegex(DataValidationError, "stale"):
            self.select(observed=T0 + 100, decision=T0 + 300101,
                        max_market_age=300000)

    def test_stale_registry_fails_not_silently_reused(self):
        with self.assertRaisesRegex(DataValidationError, "too old"):
            self.select(observed=T0 + HOUR + 1, decision=T0 + HOUR + 2,
                        max_registry_age=HOUR)

    def test_earlier_decision_cannot_use_later_registry(self):
        future = CryptoRegistrySnapshot.from_manifest(signed_fixture(
            unsigned_manifest(observed=T0 + HOUR, label="future")))
        history = CryptoRegistryHistory([future])
        with self.assertRaisesRegex(DataValidationError, "no reviewed crypto registry"):
            self.select(history=history)

    def test_negative_and_bool_freshness_limits_rejected(self):
        for bad in (-1, True, 1.5):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    self.select(max_market_age=bad)
                with self.assertRaises(ValueError):
                    self.select(max_registry_age=bad)

    def test_registry_snapshot_is_not_conclusive_crypto_proof(self):
        # This is an offline synthetic fixture, not production crypto identity.
        self.assertEqual(self.registry.label, "reviewed-fixture-v1")
        self.assertEqual(self.registry.assets[0].reviewed_by,
                         "internal-reviewer-fixture")
        self.assertNotIn("api_key", json.dumps(signed_fixture()))


if __name__ == "__main__":
    unittest.main()
