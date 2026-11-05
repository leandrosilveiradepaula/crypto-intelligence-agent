"""OPS35 offline adversarial tests; no actual network calls, orders or writes."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from crypto_intelligence_agent.j1_binance_metadata_probe import (
    URL, MAX_BODY_BYTES, capture_binance_metadata_once, _parse_json,
)
from test_j1_binance_top50_pit import instrument, registry_for, DECISION

AT = DECISION + 100_000


def payload(rows=None):
    return {"timezone": "UTC", "serverTime": AT,
            "symbols": rows if rows is not None else [instrument("BTC"), instrument("ETH")],
            "assets": []}


def case(*, responses=None, allow=True, owner=True, times=None, registry=None):
    raw = responses or [json.dumps(payload()).encode()] * 2
    events = []
    iterator = iter(raw)
    time_iter = iter(times or [AT, AT+10, AT+30, AT+50])
    def fetch(url, limit):
        events.append((url,limit))
        return next(iterator)
    result = capture_binance_metadata_once(
        registry=registry if registry is not None else registry_for(("BTC","ETH"), observed=AT-10000),
        allow_public_network=allow,
        confirm_region_and_personal_research=allow,
        owner_check=lambda: owner,
        fetch=fetch,
        utc_ms=lambda: next(time_iter),
    )
    return result, events


class MetadataProbeOfflineTests(unittest.TestCase):
    def test_valid_two_captures_only_research_and_no_symbols(self):
        report, calls = case()
        self.assertEqual(report.status, "metadata_catalog_pair_research_unverified")
        self.assertEqual(report.requested, 2)
        self.assertEqual(report.received, 2)
        self.assertEqual(report.reviewed_crypto_perpetuals, 2)
        self.assertEqual(calls, [(URL,MAX_BODY_BYTES)]*2)
        serialized = json.dumps(report.sanitized_report())
        self.assertNotIn("BTCUSDT", serialized)
        self.assertNotIn("ETHUSDT", serialized)
        for k in ("usdm_contract_verified", "marketwide_top50_verified",
                  "canonical_ohlcv_approved", "continuous_collector_authorized",
                  "orders_sent"):
            self.assertFalse(report.sanitized_report()[k])

    def test_default_is_off_and_nonroot_rejected_before_fetch(self):
        report, calls = case(allow=False)
        self.assertEqual(report.status, "metadata_owner_optin_required")
        self.assertFalse(calls)
        report, calls = case(owner=False)
        self.assertEqual(report.status, "metadata_nonroot_required")
        self.assertFalse(calls)

    def test_two_request_max_with_no_retry(self):
        report, calls = case()
        self.assertEqual(len(calls), 2)
        self.assertEqual(report.requested, 2)

    def test_http_failure_does_not_retry(self):
        def fail(url, limit):
            raise ValueError("binance_http_access_or_provider_denied_no_retry")
        r=capture_binance_metadata_once(
            registry=registry_for(("BTC",),observed=AT-10000),
            allow_public_network=True, confirm_region_and_personal_research=True,
            owner_check=lambda:True, fetch=fail, utc_ms=lambda:AT)
        self.assertEqual(r.status,"metadata_http_abstain")
        self.assertEqual(r.requested,1)

    def test_unauthorized_transport_not_configured(self):
        r=capture_binance_metadata_once(
            registry=registry_for(("BTC",),observed=AT-10000),
            allow_public_network=True, confirm_region_and_personal_research=True,
            owner_check=lambda:True)
        self.assertEqual(r.status,"metadata_transport_not_configured")

    def test_oversize_empty_and_nonbytes_rejected(self):
        for item in (b"", b"x"*(MAX_BODY_BYTES+1), "{}"):
            with self.subTest(length=len(item)):
                r,calls=case(responses=[item,item])
                self.assertEqual(r.status,"metadata_size_abstain")
                self.assertEqual(len(calls),1)

    def test_duplicate_keys_and_nan_cannot_be_loaded(self):
        for item in (b'{"timezone":"UTC","timezone":"UTC"}',
                     b'{"bad":NaN}', b'not json', b'[]'):
            with self.subTest(item=item):
                r,calls=case(responses=[item,item])
                self.assertNotEqual(r.status,"metadata_catalog_pair_research_unverified")
                self.assertEqual(len(calls),1)

    def test_catalog_drift_fails_atomically(self):
        a=payload()
        b=payload([instrument("BTC"),instrument("ETH"),instrument("NEW")])
        r,calls=case(responses=[json.dumps(a).encode(), json.dumps(b).encode()])
        self.assertEqual(r.status,"metadata_transport_or_validation_abstain")
        self.assertEqual(r.received,2)
        self.assertIsNone(r.catalog_digest_sha256)

    def test_catalog_duplicate_symbols_rejected(self):
        p=payload([instrument("BTC"),instrument("BTC")])
        r,_=case(responses=[json.dumps(p).encode()]*2)
        self.assertEqual(r.status,"metadata_transport_or_validation_abstain")

    def test_future_clock_rejected(self):
        r,_=case(times=[AT,AT+40000])
        self.assertEqual(r.status,"metadata_transport_or_validation_abstain")

    def test_backward_clock_rejected(self):
        r,_=case(times=[AT,AT-1])
        self.assertEqual(r.status,"metadata_transport_or_validation_abstain")

    def test_unreviewed_and_excluded_count_only(self):
        excluded=instrument("STOCK")
        excluded["underlyingType"]="STOCK"
        p=payload([instrument("BTC"),instrument("ETH"),instrument("NEW"),excluded])
        r,_=case(responses=[json.dumps(p).encode()]*2)
        self.assertEqual(r.status,"metadata_catalog_pair_research_unverified")
        self.assertEqual(r.reviewed_crypto_perpetuals,2)
        self.assertEqual(r.plausible_unreviewed,1)
        self.assertEqual(r.excluded_non_perp_or_non_usdt,1)

    def test_stale_or_future_registry_abstains_without_approving(self):
        for observed in (AT-8*86400000,AT+1000):
            with self.subTest(observed=observed):
                r,_=case(registry=registry_for(("BTC",),observed=observed))
                self.assertNotEqual(r.status,"metadata_catalog_pair_research_unverified")
                self.assertFalse(r.sanitized_report()["usdm_contract_verified"])

    def test_catalog_server_time_ignored_for_pit(self):
        p=payload()
        p["serverTime"]=AT+9999999
        data=json.dumps(p).encode()
        r,_=case(responses=[data,data])
        self.assertEqual(r.status,"metadata_catalog_pair_research_unverified")

    def test_contract_type_invalid_not_counted(self):
        row=instrument("BTC");row["contractType"]="CURRENT_QUARTER"
        p=payload([row,instrument("ETH")])
        r,_=case(responses=[json.dumps(p).encode()]*2)
        self.assertEqual(r.reviewed_crypto_perpetuals,1)
        self.assertEqual(r.excluded_non_perp_or_non_usdt,1)

    def test_no_raw_provider_error_or_http_url_in_report(self):
        def fail(url, limit):
            raise ValueError("binance_http_secret_in_provider_body_ABC")
        report=capture_binance_metadata_once(
            registry=registry_for(("BTC",),observed=AT-10000),
            allow_public_network=True, confirm_region_and_personal_research=True,
            owner_check=lambda:True,fetch=fail,utc_ms=lambda:AT)
        self.assertNotIn("ABC",json.dumps(report.sanitized_report()))
        self.assertNotIn("https://",json.dumps(report.sanitized_report()))


if __name__ == "__main__":
    unittest.main()
