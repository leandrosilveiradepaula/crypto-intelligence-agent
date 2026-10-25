"""No-network tests for conservative provider-rights gate (synthetic grants)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.provider_usage_gate import (
    Dataset, RightsGrantEvidence, UsagePurpose, assess_provider_usage,
)


T = 1_800_000_000_000


def grant(*, provider="kraken_futures", dataset=Dataset.CANDLES,
          purpose=UsagePurpose.PUBLIC_DISPLAY, reviewed=T-500,
          expires=T+500, confirmed=True, url="https://example.org/license/synthetic"):
    return RightsGrantEvidence(
        provider=provider, dataset=dataset, permitted_purpose=purpose,
        reviewed_at_ms=reviewed, valid_until_ms=expires,
        evidence_url=url, evidence_version="fixture-rights-v1",
        reviewed_by="reviewer-fixture", grant_confirmed=confirmed,
    )


def assess(*, provider="kraken_futures", dataset=Dataset.CANDLES,
           purpose=UsagePurpose.PUBLIC_DISPLAY, grants=(), moment=T,
           release=False):
    return assess_provider_usage(
        provider=provider, dataset=dataset, purpose=purpose,
        decision_at_ms=moment, grants=grants,
        externally_reviewed_release_gate=release,
    )


class ProviderRightsGateTests(unittest.TestCase):
    def test_no_rights_means_public_display_blocked(self):
        a = assess()
        self.assertFalse(a.allowed)
        self.assertEqual(a.reason, "no_current_scope_specific_verified_rights_claim")
        self.assertFalse(a.evidence_is_authentic)
        self.assertFalse(a.publishes_data)
        self.assertFalse(a.releases_to_production)

    def test_private_api_and_commercial_are_blocked_without_rights(self):
        for purpose in (UsagePurpose.PRIVATE_DASHBOARD, UsagePurpose.PUBLIC_API,
                        UsagePurpose.COMMERCIAL):
            with self.subTest(purpose=purpose):
                self.assertFalse(assess(purpose=purpose).allowed)

    def test_unverified_claim_cannot_authorize_public_distribution(self):
        a = assess(grants=(grant(),), release=True)
        self.assertFalse(a.allowed)
        self.assertEqual(a.reason,
                         "license_claim_requires_external_verification_and_release_gate")
        self.assertEqual(a.review_version, "fixture-rights-v1")
        self.assertFalse(a.publishes_data)

    def test_internal_research_is_not_license_approval(self):
        a = assess(purpose=UsagePurpose.INTERNAL_RESEARCH)
        self.assertFalse(a.allowed)
        self.assertIn("terms_review", a.reason)

    def test_future_and_expired_claims_fail_closed(self):
        for row in (grant(reviewed=T+1, expires=T+100),
                    grant(reviewed=T-100, expires=T),
                    grant(confirmed=False)):
            with self.subTest(row=row):
                a = assess(grants=(row,))
                self.assertFalse(a.allowed)
                self.assertIsNone(a.review_version)

    def test_scope_venue_and_dataset_cannot_bleed_across(self):
        evidence = grant()
        for provider,dataset,purpose in (
            ("bybit_v5", Dataset.CANDLES, UsagePurpose.PUBLIC_DISPLAY),
            ("kraken_futures", Dataset.TICKERS, UsagePurpose.PUBLIC_DISPLAY),
            ("kraken_futures", Dataset.CANDLES, UsagePurpose.PUBLIC_API),
            ("binance_usdm", Dataset.FUNDING, UsagePurpose.COMMERCIAL),
            ("kraken_futures", Dataset.DERIVED_ALERTS, UsagePurpose.PUBLIC_DISPLAY),
        ):
            with self.subTest(provider=provider,dataset=dataset,purpose=purpose):
                a = assess(provider=provider, dataset=dataset, purpose=purpose,
                           grants=(evidence,))
                self.assertFalse(a.allowed)
                self.assertIsNone(a.review_version)

    def test_okx_v5_fixtures_never_grant_data_rights(self):
        okx_claim = grant(provider="okx_v5")
        for purpose in (UsagePurpose.INTERNAL_RESEARCH, UsagePurpose.PRIVATE_DASHBOARD,
                        UsagePurpose.PUBLIC_DISPLAY, UsagePurpose.PUBLIC_API,
                        UsagePurpose.COMMERCIAL):
            with self.subTest(purpose=purpose):
                decision = assess(provider="okx_v5", purpose=purpose,
                                  grants=(okx_claim,), release=True)
                self.assertFalse(decision.allowed)
                self.assertFalse(decision.publishes_data)
                self.assertFalse(decision.releases_to_production)

    def test_hyperliquid_native_access_is_not_permission_to_distribute(self):
        evidence = grant(provider="hyperliquid_native")
        for purpose in UsagePurpose:
            with self.subTest(purpose=purpose):
                result = assess(provider="hyperliquid_native", purpose=purpose,
                                grants=(evidence,), release=True)
                self.assertFalse(result.allowed)
                self.assertFalse(result.releases_to_production)
                self.assertFalse(result.publishes_data)

    def test_multiple_synthetic_claims_never_enable_release(self):
        rows = (grant(reviewed=T-100), grant(reviewed=T-20))
        a = assess(grants=rows, release=True)
        self.assertFalse(a.allowed)
        self.assertEqual(a.review_version, "fixture-rights-v1")

    def test_bad_provenance_urls_and_flags_rejected(self):
        for url in ("http://example.org/license", "https://localhost/a",
                    "https://user:secret@example.org/a",
                    "https://example.org/a?token=secret",
                    "https://example.org/a#fragment",
                    "https://example.org:8443/license"):
            with self.subTest(url=url):
                with self.assertRaises(DataValidationError):
                    grant(url=url)
        with self.assertRaises(DataValidationError):
            grant(confirmed=1)

    def test_missing_invalid_review_times_and_expiry_rejected(self):
        for reviewed,expires in ((T,T), (T+1,T), (True,T),
                                  ("100",T), (T,False)):
            with self.subTest(reviewed=reviewed,expires=expires):
                with self.assertRaises(DataValidationError):
                    grant(reviewed=reviewed, expires=expires)
        for moment in (True, 0, -1, "now"):
            with self.subTest(moment=moment):
                with self.assertRaises(DataValidationError):
                    assess(moment=moment)

    def test_inputs_must_be_explicit_and_bounded(self):
        for bad in ("public_display", None, True):
            with self.subTest(purpose=bad):
                with self.assertRaises(DataValidationError):
                    assess(purpose=bad)
        with self.assertRaises(DataValidationError):
            assess(dataset="candles")
        with self.assertRaises(DataValidationError):
            assess(provider="unknown")
        with self.assertRaises(DataValidationError):
            assess(grants=[grant()])
        with self.assertRaises(DataValidationError):
            assess(grants=(grant(),)*21)
        with self.assertRaises(DataValidationError):
            assess(release=1)

    def test_decisions_and_grants_are_immutable(self):
        a = assess(grants=(grant(),))
        with self.assertRaises(FrozenInstanceError):
            a.allowed = True
        g = grant()
        with self.assertRaises(FrozenInstanceError):
            g.grant_confirmed = True


if __name__ == "__main__":
    unittest.main()
