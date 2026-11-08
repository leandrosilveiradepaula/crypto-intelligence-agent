"""D266: identity claim evidence remains nontradable under all conditions."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from crypto_intelligence_agent.bybit_identity_dossier_guard import (
    SCHEMA, dossier_digest, evaluate_dossier,
)

NOW = 1794103607305
PAST = 1793970000000
EARLY = 1793700000000


def record(symbol="BTCUSDT", observed=EARLY, reviewed=EARLY+1000,
           ref="coingecko:bitcoin", network="bitcoin:mainnet"):
    base = {
        "schema_version": SCHEMA,
        "venue_symbol": symbol,
        "canonical_asset_id": ref,
        "asset_class": "crypto_token",
        "venue_contract_id": "bybit:linear-btcusdt",
        "network_contract_id": network,
        "observed_at_ms": observed,
        "valid_from_ms": observed,
        "valid_to_ms": None,
        "reviewed_by": "research_operator",
        "reviewed_at_ms": reviewed,
        "evidence": [
            {"publisher": "coingecko", "asset_ref": "coingecko:bitcoin",
             "url": "https://www.coingecko.com/en/coins/bitcoin",
             "observed_at_ms": observed},
            {"publisher": "coinpaprika", "asset_ref": "coinpaprika:btc-bitcoin",
             "url": "https://coinpaprika.com/coin/btc-bitcoin/",
             "observed_at_ms": observed},
        ],
    }
    base["sha256"] = dossier_digest(base)
    return base


def seal(d):
    d.pop("sha256", None)
    d["sha256"] = dossier_digest(d)
    return d


class D266EvidenceGuardTests(unittest.TestCase):
    def test_even_two_sources_and_mint_do_not_authorize_trading(self):
        d = record()
        x = evaluate_dossier(d, decision_at_ms=PAST)
        self.assertEqual(x["status"], "research_only")
        self.assertEqual(x["reason"], "research_candidate_only")
        self.assertFalse(x["identity_approved"])
        self.assertFalse(x["eligible_top50"])
        self.assertFalse(x["marketwide_top50_verified"])
        self.assertFalse(x["orders_sent"])
        self.assertFalse(x["provider_contract_authenticated"])
        self.assertFalse(x["independent_source_authentication_verified"])
        self.assertFalse(x["identity_pit_authenticated"])
        self.assertEqual(x["dossier_sha256"], d["sha256"])
        self.assertNotIn("BTCUSDT", json.dumps(x))
        self.assertFalse(x["database_modified"])
        self.assertFalse(x["network_accessed"])

    def test_bybit_oil_veto_even_if_crypto_is_claimed(self):
        x = evaluate_dossier(record(symbol="BZUSDT"), decision_at_ms=PAST)
        self.assertEqual(x["reason"], "blocked_documented_noncrypto")
        self.assertFalse(x["eligible_top50"])
        self.assertEqual(evaluate_dossier(
            record(), decision_at_ms=PAST,
            current_provider_negative=True,
        )["reason"], "blocked_documented_noncrypto")

    def test_rwa_and_ticker_collisions_veto_stale_references(self):
        for symbol in ("XAUTUSDT", "LITUSDT", "CLANKERUSDT",
                       "ARIAUSDT", "BIRBUSDT"):
            with self.subTest(symbol=symbol):
                self.assertEqual(evaluate_dossier(
                    record(symbol=symbol), decision_at_ms=PAST
                )["reason"], "blocked_policy_or_ambiguity")

    def test_historical_pit_requires_observed_and_reviewed_before_decision(self):
        for modification in (
            {"observed_at_ms": PAST + 1000, "reviewed_at_ms": PAST + 2000,
             "valid_from_ms": PAST + 1000},
            {"reviewed_at_ms": PAST + 2000},
            {"valid_to_ms": EARLY + 50},
        ):
            d = record()
            d.update(modification)
            seal(d)
            self.assertEqual(evaluate_dossier(
                d, decision_at_ms=PAST
            )["reason"], "evidence_not_pit")
        d = record()
        d["evidence"][1]["observed_at_ms"] = PAST+1
        d["reviewed_at_ms"] = PAST+2
        seal(d)
        self.assertEqual(evaluate_dossier(
            d, decision_at_ms=PAST
        )["reason"], "evidence_not_pit")

    def test_duplicate_domains_are_not_two_independent_publishers(self):
        d = record()
        d["evidence"][1]["publisher"] = "another_provider"
        d["evidence"][1]["url"] = "https://api.coingecko.com/en/coins/bitcoin"
        seal(d)
        self.assertEqual(evaluate_dossier(
            d, decision_at_ms=PAST
        )["reason"], "dossier_source_not_independent")

    def test_single_source_is_insufficient_even_with_forged_review(self):
        d = record()
        d["evidence"].pop()
        seal(d)
        self.assertEqual(evaluate_dossier(
            d, decision_at_ms=PAST
        )["reason"], "insufficient_independent_evidence")

    def test_aliases_no_automatic_approval(self):
        for symbol in ("1000PEPEUSDT", "PUMPFUNUSDT", "XPLUSDT"):
            d = record(symbol=symbol)
            self.assertEqual(evaluate_dossier(
                d, decision_at_ms=PAST
            )["reason"], "research_candidate_only")
            d["network_contract_id"] = ""
            seal(d)
            self.assertEqual(evaluate_dossier(
                d, decision_at_ms=PAST
            )["reason"], "requires_manual_venue_review")

    def test_data_tampering_and_duplicate_json_keys_rejected(self):
        d = record()
        d["asset_class"] = "tradfi"
        self.assertEqual(evaluate_dossier(
            d, decision_at_ms=PAST
        )["reason"], "dossier_integrity_mismatch")
        d = record()
        d["evil"] = True
        self.assertEqual(evaluate_dossier(
            d, decision_at_ms=PAST
        )["reason"], "dossier_fields_invalid")
        raw = json.dumps(record())[:-1] + ',"sha256":"not_sha"}'
        self.assertEqual(evaluate_dossier(
            raw, decision_at_ms=PAST
        )["reason"], "dossier_parse_invalid")

    def test_malicious_urls_and_nonfinite_numbers_fail_closed(self):
        for url in ("http://example.com/asset",
                    "https://user:pass@example.com/asset",
                    "https://localhost/asset",
                    "https://a.example.com/asset?token=secret"):
            d = record()
            d["evidence"][0]["url"] = url
            seal(d)
            self.assertEqual(evaluate_dossier(
                d, decision_at_ms=PAST
            )["reason"], "dossier_evidence_url_invalid")
        raw = json.dumps(record()).replace('"reviewed_at_ms": 1793700001000',
                                              '"reviewed_at_ms": NaN')
        self.assertEqual(evaluate_dossier(raw, decision_at_ms=PAST)[
            "status"], "abstain")

    def test_foreign_asset_class_and_unknown_never_tradable(self):
        for cls in ("tradfi", "tokenized_commodity", "unknown"):
            d = record()
            d["asset_class"] = cls
            seal(d)
            x = evaluate_dossier(d, decision_at_ms=PAST)
            self.assertEqual(x["reason"], "blocked_policy_or_ambiguity")
            self.assertFalse(x["identity_approved"])

    def test_invalid_params_never_approve(self):
        for raw, asof in ((record(), True), (record(), -1),
                          (record(), "1793970000000"), ([], PAST)):
            x = evaluate_dossier(raw, decision_at_ms=asof)
            self.assertEqual(x["status"], "abstain")
            self.assertFalse(x["marketwide_top50_verified"])


if __name__ == "__main__":
    unittest.main()
