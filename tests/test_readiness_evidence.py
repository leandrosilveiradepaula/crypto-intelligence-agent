"""WU21 regression tests: local claims may be well-formed, NEVER authoritative."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.readiness_evidence import (
    MAX_EVIDENCE_BYTES, audit_evidence_json, canonical_claim_sha256,
)
from scripts.j1_readiness_report import main, readiness_snapshot


NOW = 1_793_000_000_000


def claim(**changes):
    base = {
        "capability": "bybit_quote_currency",
        "provider": "bybit_v5",
        "dataset": "candles",
        "purpose": "internal_research",
        "origin": "documented_schema",
        "quote_currency": "USDT",
        "source_url": "https://docs.example.org/reference/kline",
        "source_version": "v5",
        "reviewed_by": "offline-qa",
        "observed_at_ms": NOW - 10_000,
        "reviewed_at_ms": NOW - 5_000,
        "valid_until_ms": NOW + 100_000,
    }
    base.update(changes)
    base["claim_sha256"] = canonical_claim_sha256(base)
    return base


def payload(*claims):
    return json.dumps({"schema_version": 1, "claims": list(claims)}, sort_keys=True)


class ProvenanceTests(unittest.TestCase):
    def audited(self, *claims, **kw):
        return audit_evidence_json(payload(*claims), decision_at_ms=NOW, **kw)

    def test_documented_quote_still_not_live_proof(self):
        result = self.audited(claim())
        self.assertEqual(result["status"], "unverified_claims_for_manual_review")
        self.assertEqual(result["claim_count"], 1)
        self.assertEqual(result["claims"][0]["verification"],
                         "metadata_valid_only_not_authenticated")
        self.assertEqual(result["claims"][0]["issue"], 50)
        self.assertFalse(result["live_evidence_authenticated"])
        self.assertFalse(result["independent_source_verified"])
        self.assertFalse(result["external_rights_authorized"])
        report = readiness_snapshot(evidence_json=payload(claim()), decision_at_ms=NOW)
        self.assertEqual(report["provenance_review"], result)
        for gate in ("ready_for_live_top50", "ready_for_canonical_ohlcv",
                     "ready_for_public_market_data_release"):
            self.assertFalse(report[gate])

    def test_empty_evidence_never_approves_readiness(self):
        self.assertEqual(self.audited()["status"], "no_claims")
        self.assertEqual(self.audited()["claim_count"], 0)
        self.assertNotIn("provenance_review", readiness_snapshot())

    def test_digest_change_is_detected_and_rehash_is_not_authenticity(self):
        row = claim()
        row["source_version"] = "spoofed"
        with self.assertRaises(DataValidationError):
            self.audited(row)
        row["claim_sha256"] = canonical_claim_sha256({
            k: v for k, v in row.items() if k != "claim_sha256"
        })
        self.assertFalse(self.audited(row)["live_evidence_authenticated"])

    def test_scopes_are_strict_and_cannot_cross_providers(self):
        bad = [
            {"capability": "kraken_candle_volume_units"},
            {"provider": "kraken_futures"},
            {"dataset": "tickers", "quote_currency": "not_applicable"},
            {"purpose": "commercial"},
            {"quote_currency": "USD"},
            {"quote_currency": "unverified"},
            {"capability": "crypto_only_identity"},
        ]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                self.audited(claim(**change))
        self.assertEqual(self.audited(claim(quote_currency="USDC"))["claim_count"], 1)

    def test_kraken_candle_volume_still_unverified_even_if_observed(self):
        observed = claim(
            capability="kraken_candle_volume_units",
            provider="kraken_futures", quote_currency="unverified",
            origin="observed_summary",
        )
        self.assertFalse(self.audited(observed)["live_evidence_authenticated"])
        with self.assertRaises(DataValidationError):
            self.audited(claim(capability="kraken_candle_volume_units",
                              provider="kraken_futures", quote_currency="USD"))

    def test_kraken_futures_chart_docs_not_proof_of_volume_units(self):
        record = claim(
            capability="kraken_candle_volume_units", provider="kraken_futures",
            dataset="candles", purpose="internal_research",
            origin="documented_schema", quote_currency="unverified",
            source_url="https://docs.kraken.com/api/docs/futures-api/charts/candles",
        )
        row = self.audited(record)["claims"][0]
        self.assertEqual(row["source_applicability"],
                         "chart_volume_field_documented_unit_not_defined")
        self.assertFalse(self.audited(record)["live_evidence_authenticated"])
        checkpoint = readiness_snapshot(evidence_json=payload(record),
                                        decision_at_ms=NOW)
        self.assertFalse(checkpoint["ready_for_canonical_ohlcv"])
        self.assertFalse(checkpoint["ready_for_live_top50"])
        self.assertFalse(checkpoint["ready_for_public_market_data_release"])

    def test_kraken_chart_docs_only_support_offline_candle_shape(self):
        record = claim(
            capability="closed_candle_parser", provider="kraken_futures",
            dataset="candles", origin="documented_schema",
            quote_currency="unverified",
            source_url="https://docs.kraken.com/api/docs/futures-api/charts/candles/",
        )
        row = self.audited(record)["claims"][0]
        self.assertEqual(row["source_applicability"],
                         "candle_schema_only_not_live_conformance")
        self.assertFalse(self.audited(record)["independent_source_verified"])

    def test_perpetual_contract_listing_not_positive_crypto_only_registry(self):
        url = (
            "https://support.kraken.com/articles/"
            "4844359082772-linear-multi-collateral-derivatives-contract-specifications"
        )
        identity = claim(
            capability="crypto_only_identity", provider="kraken_futures",
            dataset="instruments", quote_currency="not_applicable",
            origin="documented_schema", source_url=url,
        )
        self.assertEqual(
            self.audited(identity)["claims"][0]["source_applicability"],
            "instrument_list_includes_non_crypto_no_positive_registry_proof",
        )
        self.assertFalse(self.audited(identity)["independent_source_verified"])
        # Current min lot / leverage class is not an attestation of
        # chart.trade.volume's base/quote economic unit.
        volume = claim(
            capability="kraken_candle_volume_units", provider="kraken_futures",
            dataset="candles", quote_currency="unverified",
            origin="documented_schema", source_url=url,
        )
        self.assertEqual(
            self.audited(volume)["claims"][0]["source_applicability"],
            "current_contract_lot_not_historical_candle_volume_unit",
        )

    def test_official_usage_notice_is_warning_not_license_permission(self):
        grant = claim(
            capability="provider_external_rights",
            provider="kraken_futures", dataset="candles",
            purpose="commercial", quote_currency="unverified",
            origin="documented_schema",
            source_url="https://docs-legacy.kraken.com/api/docs/guides/global-intro/",
        )
        row = self.audited(grant)["claims"][0]
        self.assertEqual(
            row["source_applicability"],
            "terms_notice_requires_permission_not_a_rights_grant",
        )
        report = readiness_snapshot(evidence_json=payload(grant), decision_at_ms=NOW)
        self.assertFalse(report["provenance_review"]["external_rights_authorized"])
        self.assertFalse(report["ready_for_public_market_data_release"])

    def test_kraken_spot_ohlcvt_cannot_attest_kraken_futures(self):
        for url in (
            "https://support.kraken.com/br/articles/"
            "360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data",
            "https://support.kraken.com/in/articles/"
            "360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data",
        ):
            for capability, dataset, currency in (
                ("kraken_candle_volume_units", "candles", "unverified"),
                ("crypto_only_identity", "instruments", "not_applicable"),
                ("provider_external_rights", "candles", "unverified"),
            ):
                purpose = ("commercial" if capability == "provider_external_rights"
                           else "internal_research")
                with self.subTest(url=url, capability=capability), self.assertRaisesRegex(
                    DataValidationError, "different product"
                ):
                    self.audited(claim(
                        capability=capability, provider="kraken_futures",
                        dataset=dataset, purpose=purpose,
                        quote_currency=currency, source_url=url,
                    ))

    def test_kraken_derivatives_us_cme_bitnomial_docs_are_different_product(self):
        for slug in ("market-data", "contract-specifications"):
            for lang in ("", "pt/", "br/"):
                url = f"https://support.kraken.com/{lang}articles/{slug}"
                with self.subTest(url=url), self.assertRaisesRegex(
                    DataValidationError, "different product"
                ):
                    self.audited(claim(
                        capability="kraken_candle_volume_units",
                        provider="kraken_futures", dataset="candles",
                        quote_currency="unverified", source_url=url,
                    ))
        # A different website listing contract sizes must NOT be imported
        # as the Kraken PF_ perpetual tick/lot/multiplier rule.

    def test_known_kraken_docs_do_not_certify_other_providers(self):
        for url in (
            "https://docs.kraken.com/api/docs/futures-api/charts/candles",
            "https://support.kraken.com/articles/contract-specifications",
            "https://docs-legacy.kraken.com/api/docs/guides/global-intro",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(
                DataValidationError, "another provider"
            ):
                self.audited(claim(source_url=url))

    def test_known_kraken_docs_cannot_claim_wrong_capability(self):
        for fields in (
            dict(capability="crypto_only_identity", dataset="instruments",
                 quote_currency="not_applicable",
                 source_url="https://docs.kraken.com/api/docs/futures-api/charts/candles"),
            dict(capability="provider_external_rights", purpose="public_api",
                 source_url="https://support.kraken.com/articles/4844359082772-linear-multi-collateral-derivatives-contract-specifications"),
            dict(capability="kraken_candle_volume_units",
                 source_url="https://docs-legacy.kraken.com/api/docs/guides/global-intro"),
        ):
            common = dict(provider="kraken_futures", quote_currency="unverified")
            common.update(fields)
            with self.subTest(fields=fields), self.assertRaises(DataValidationError):
                self.audited(claim(**common))

    def test_document_page_cannot_pretend_to_be_observed_market_summary(self):
        with self.assertRaisesRegex(DataValidationError, "not an observed market run"):
            self.audited(claim(
                capability="kraken_candle_volume_units",
                provider="kraken_futures", quote_currency="unverified",
                origin="observed_summary",
                source_url="https://docs.kraken.com/api/docs/futures-api/charts/candles",
            ))

    def test_encoded_kraken_paths_fail_closed_before_any_scope_assertion(self):
        for url in (
            "https://support.kraken.com/articles/%6darket-data",
            "https://docs.kraken.com/api/docs/futures-api/charts/%63andles",
            "https://docs-legacy.kraken.com/api/docs/guides/global%2dintro",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(
                DataValidationError, "encoded Kraken"
            ):
                self.audited(claim(
                    capability="kraken_candle_volume_units",
                    provider="kraken_futures", quote_currency="unverified",
                    source_url=url,
                ))

    def test_unknown_hostname_is_not_mistaken_for_official_kraken_source(self):
        for url in (
            "https://support.kraken.com.attacker.test/articles/market-data",
            "https://somewhere.example.org/kraken/futures",
        ):
            record = claim(
                capability="kraken_candle_volume_units", provider="kraken_futures",
                quote_currency="unverified", source_url=url,
            )
            output = self.audited(record)
            self.assertEqual(output["claims"][0]["source_applicability"],
                             "unknown_reference_requires_independent_review")
            self.assertFalse(output["independent_source_verified"])
            self.assertFalse(output["live_evidence_authenticated"])

    def test_source_applicability_is_computed_not_trusted_as_claim(self):
        row = claim(
            capability="kraken_candle_volume_units",
            provider="kraken_futures", quote_currency="unverified",
            source_url="https://docs.kraken.com/api/docs/futures-api/charts/candles",
        )
        row["source_applicability"] = "verified"
        with self.assertRaises(DataValidationError):
            self.audited(row)

    def test_source_scope_checks_need_no_network_or_source_download(self):
        from unittest.mock import patch
        record = claim(
            capability="crypto_only_identity", provider="kraken_futures",
            dataset="instruments", quote_currency="not_applicable",
            source_url="https://support.kraken.com/articles/"
                       "4844359082772-linear-multi-collateral-derivatives-contract-specifications",
        )
        with patch("urllib.request.urlopen", side_effect=AssertionError("No HTTP allowed")):
            output = self.audited(record)
        self.assertFalse(output["independent_source_verified"])
        self.assertFalse(output["external_rights_authorized"])

    def test_okx_schema_evidence_cannot_claim_live_permissions(self):
        candidate = claim(capability="okx_quote_currency", provider="okx_v5")
        observed = self.audited(candidate)
        self.assertEqual(observed["claims"][0]["issue"], 60)
        self.assertFalse(observed["live_evidence_authenticated"])
        self.assertFalse(observed["external_rights_authorized"])
        report = readiness_snapshot(evidence_json=payload(candidate), decision_at_ms=NOW)
        self.assertFalse(report["ready_for_live_top50"])
        self.assertFalse(report["ready_for_canonical_ohlcv"])
        for variant in ({"provider":"bybit_v5"}, {"quote_currency":"USD"},
                        {"quote_currency":"unverified"}, {"purpose":"public_display"}):
            with self.subTest(variant=variant), self.assertRaises(DataValidationError):
                self.audited(claim(**dict({"capability": "okx_quote_currency",
                                               "provider": "okx_v5"}, **variant)))

    def test_hyperliquid_native_claims_cannot_authorize_live_or_cryptocurrency(self):
        candidate = claim(capability="hyperliquid_native_candle_schema",
                          provider="hyperliquid_native", quote_currency="unverified")
        result = self.audited(candidate)
        self.assertEqual(result["claims"][0]["issue"], 69)
        self.assertFalse(result["live_evidence_authenticated"])
        self.assertFalse(result["external_rights_authorized"])
        report = readiness_snapshot(evidence_json=payload(candidate), decision_at_ms=NOW)
        self.assertFalse(report["ready_for_live_top50"])
        self.assertFalse(report["ready_for_canonical_ohlcv"])
        for changes in ({"provider": "bybit_v5"}, {"quote_currency": "USDC"},
                        {"purpose": "commercial"}, {"dataset": "instruments"}):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                self.audited(claim(**dict({"capability": "hyperliquid_native_candle_schema",
                                           "provider": "hyperliquid_native",
                                           "quote_currency": "unverified"}, **changes)))

    def test_claimed_public_rights_never_authorize_distribution(self):
        rights = claim(
            capability="provider_external_rights", provider="kraken_futures",
            quote_currency="unverified", purpose="public_api",
            origin="observed_summary",
        )
        result = self.audited(rights)
        self.assertFalse(result["external_rights_authorized"])
        self.assertFalse(readiness_snapshot(
            evidence_json=payload(rights), decision_at_ms=NOW
        )["ready_for_public_market_data_release"])

    def test_expired_future_stale_and_invalid_age(self):
        scenarios = [
            {"observed_at_ms": NOW + 1, "reviewed_at_ms": NOW + 2},
            {"reviewed_at_ms": NOW + 1},
            {"valid_until_ms": NOW},
            {"observed_at_ms": NOW - 50_000},
            {"reviewed_at_ms": NOW - 20_000},
        ]
        for scenario in scenarios:
            with self.subTest(scenario=scenario), self.assertRaises(DataValidationError):
                self.audited(claim(**scenario), max_age_ms=30_000)
        for age in (True, -1, 400 * 86_400_000, 1.5):
            with self.subTest(age=age), self.assertRaises(DataValidationError):
                self.audited(claim(), max_age_ms=age)

    def test_rejects_fake_verification_extra_fields(self):
        row = claim()
        row["verified_live"] = True
        with self.assertRaises(DataValidationError):
            self.audited(row)
        for mutation in ({"purpose": 1}, {"provider": None},
                         {"observed_at_ms": True}, {"origin": "verified_live"},
                         {"source_version": "bad version"}):
            with self.subTest(mutation=mutation), self.assertRaises(DataValidationError):
                self.audited(claim(**mutation))

    def test_rejects_untrusted_urls(self):
        urls = (
            "http://docs.example.org/refs", "https://me:pw@docs.example.org/refs",
            "https://docs.example.org/refs?token=secret", "https://localhost/refs",
            "https://127.0.0.1/refs", "https://docs.example.org:443/refs",
            "https://docs.example.org/refs#fragment", "https://docs.example.org\refs",
            "https://docs.example.org/refs with space",
        )
        for url in urls:
            with self.subTest(url=url), self.assertRaises(DataValidationError):
                self.audited(claim(source_url=url))

    def test_duplicate_scope_duplicate_json_and_limits(self):
        with self.assertRaises(DataValidationError):
            self.audited(claim(), claim())
        with self.assertRaises(DataValidationError):
            audit_evidence_json('{"schema_version":1,"schema_version":1,"claims":[]}',
                                decision_at_ms=NOW)
        with self.assertRaises(DataValidationError):
            audit_evidence_json('{"schema_version":1.0,"claims":[]}', decision_at_ms=NOW)
        with self.assertRaises(DataValidationError):
            audit_evidence_json('{"schema_version":NaN,"claims":[]}', decision_at_ms=NOW)
        with self.assertRaises(DataValidationError):
            audit_evidence_json(" " * (MAX_EVIDENCE_BYTES + 1), decision_at_ms=NOW)
        with self.assertRaises(DataValidationError):
            audit_evidence_json(payload(*[claim(quote_currency="USDT") for _ in range(21)]),
                                decision_at_ms=NOW)
        with self.assertRaises(DataValidationError):
            audit_evidence_json(payload(claim()), decision_at_ms=True)

    def test_order_independence_and_cli(self):
        other = claim(
            capability="crypto_only_identity", provider="kraken_futures",
            dataset="instruments", quote_currency="not_applicable",
        )
        a = self.audited(other, claim())
        b = self.audited(claim(), other)
        self.assertEqual(a, b)
        with tempfile.TemporaryDirectory() as path:
            filename = Path(path) / "claims.json"
            filename.write_text(payload(other, claim()), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                main(["--evidence-json", str(filename), "--decision-at-ms", str(NOW)])
            data = json.loads(out.getvalue())
            self.assertEqual(data["provenance_review"], a)
            self.assertFalse(data["ready_for_live_top50"])


if __name__ == "__main__":
    unittest.main()
