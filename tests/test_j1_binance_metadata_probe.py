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



class CatalogOnlyUnverifiedModeTests(unittest.TestCase):
    """A stale identity registry must never be silently renewed by a GET."""

    def _census(self, *, raw=None, times=None, allow=True, owner=True, registry=None):
        calls = []
        clock = iter(times or [AT, AT + 10, AT + 30, AT + 50])
        messages = iter(raw or [json.dumps(payload()).encode()] * 2)

        def fetch(url, limit):
            calls.append((url, limit))
            return next(messages)

        report = capture_binance_metadata_once(
            catalog_only_unverified=True,
            registry=registry,
            allow_public_network=allow,
            confirm_region_and_personal_research=allow,
            owner_check=lambda: owner,
            fetch=fetch,
            utc_ms=lambda: next(clock),
        )
        return report, calls

    def test_no_registry_catalog_census_is_not_identity_or_marketwide(self):
        report, calls = self._census()
        self.assertEqual(report.status, "metadata_catalog_only_unverified")
        self.assertEqual(len(calls), 2)
        self.assertEqual(report.catalog_rows, 2)
        self.assertEqual(report.reviewed_crypto_perpetuals, 0)
        self.assertEqual(report.plausible_unreviewed, 2)
        self.assertFalse(report.identity_registry_applied)
        self.assertIsNotNone(report.catalog_digest_sha256)
        display = json.dumps(report.sanitized_report(), sort_keys=True)
        for protected in ("marketwide_top50_verified", "usdm_contract_verified",
                          "canonical_ohlcv_approved", "continuous_collector_authorized",
                          "crypto_identity_independently_authenticated", "network_source_authenticated"):
            self.assertFalse(report.sanitized_report()[protected])
        self.assertNotIn("BTCUSDT", display)
        self.assertNotIn("ETHUSDT", display)
        self.assertNotIn('"o"', display)

    def test_catalog_only_refuses_supplied_even_fresh_registry_before_network(self):
        registry = registry_for(("BTC",), observed=AT-1000)
        report, calls = self._census(registry=registry)
        self.assertEqual(report.status, "metadata_transport_or_validation_abstain")
        self.assertEqual(report.requested, 0)
        self.assertFalse(calls)

    def test_catalog_only_requires_both_optins_and_nonroot(self):
        for kwargs in ({"allow":False},{"owner":False}):
            with self.subTest(kwargs=kwargs):
                report,calls = self._census(**kwargs)
                self.assertNotEqual(report.status, "metadata_catalog_only_unverified")
                self.assertFalse(calls)

    def test_catalog_only_never_swallows_catalog_drift(self):
        b=payload([instrument("BTC"),instrument("NEW")])
        report,calls=self._census(raw=[json.dumps(payload()).encode(),json.dumps(b).encode()])
        self.assertEqual(len(calls),2)
        self.assertNotEqual(report.status,"metadata_catalog_only_unverified")
        self.assertIsNone(report.catalog_digest_sha256)

    def test_catalog_only_never_swallows_duplicate_json(self):
        report,calls=self._census(raw=[b'{"symbols":[],"symbols":[]}']*2)
        self.assertEqual(len(calls),1)
        self.assertEqual(report.status,"metadata_duplicate_keys_abstain")

    def test_catalog_only_rejects_nonboolean_mode_without_network(self):
        calls=[]
        result=capture_binance_metadata_once(
            catalog_only_unverified=1,
            registry=None, allow_public_network=True,
            confirm_region_and_personal_research=True,
            owner_check=lambda:True,
            fetch=lambda *_: calls.append(True), utc_ms=lambda:AT)
        self.assertEqual(result.status,"metadata_transport_or_validation_abstain")
        self.assertFalse(calls)

    def test_registry_still_cannot_be_stale_or_future_in_ordinary_mode(self):
        for observed in (AT-8*86400000,AT+1000):
            with self.subTest(observed=observed):
                report,calls=case(registry=registry_for(("BTC",),observed=observed))
                self.assertNotEqual(report.status,"metadata_catalog_pair_research_unverified")
                self.assertFalse(calls)

    def test_registry_expiring_between_gets_blocks_second_http(self):
        from crypto_intelligence_agent.j1_binance_top50_pit import MAX_REGISTRY_AGE_MS
        registry=registry_for(("BTC",),observed=AT-MAX_REGISTRY_AGE_MS+15)
        report,calls=case(registry=registry)
        self.assertNotEqual(report.status,"metadata_catalog_pair_research_unverified")
        self.assertEqual(len(calls),1)
        self.assertFalse(report.identity_registry_applied)

    def test_registry_expiring_during_first_get_abstains(self):
        from crypto_intelligence_agent.j1_binance_top50_pit import MAX_REGISTRY_AGE_MS
        registry=registry_for(("BTC",),observed=AT-MAX_REGISTRY_AGE_MS+5)
        report,calls=case(registry=registry)
        self.assertNotEqual(report.status,"metadata_catalog_pair_research_unverified")
        self.assertEqual(len(calls),1)

    def test_cli_catalog_mode_does_not_load_any_registry_or_open_network(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        from crypto_intelligence_agent.j1_binance_metadata_probe import MetadataProbeReport
        from scripts import probe_binance_exchange_info_once as cli
        out=StringIO()
        from types import SimpleNamespace
        # Windows has no os.geteuid; inject only a fake CLI OS, never mutate
        # the process-wide os module or require POSIX APIs on the CI host.
        fake_os = SimpleNamespace(name="posix", geteuid=lambda: 1000)
        with (patch.object(cli,"os",fake_os),
              patch.object(cli,"load_reviewed_registry",side_effect=AssertionError("registry read")),
              patch.object(cli,"capture_binance_metadata_once",return_value=MetadataProbeReport(
                    "metadata_catalog_only_unverified")) as capture,
              redirect_stdout(out)):
            rc=cli.main(["--catalog-only-unverified","--allow-public-network",
                         "--confirm-region-and-personal-research"])
        self.assertEqual(rc,0)
        kwargs=capture.call_args.kwargs
        self.assertIsNone(kwargs["registry"])
        self.assertTrue(kwargs["catalog_only_unverified"])
        self.assertFalse(json.loads(out.getvalue())["marketwide_top50_verified"])


class SanitizedFailureStageTests(unittest.TestCase):
    """OPS37: diagnostic enums add observability, not admissibility."""

    def _check(self, report, stage, category, *, calls=None):
        sanitized = report.sanitized_report()
        self.assertEqual((sanitized["failure_stage"],
                          sanitized["failure_category"]), (stage, category))
        self.assertFalse(sanitized["canonical_ohlcv_approved"])
        self.assertFalse(sanitized["usdm_contract_verified"])
        self.assertFalse(sanitized["marketwide_top50_verified"])
        self.assertEqual(sanitized["storage_writes"], 0)
        self.assertFalse(sanitized["orders_sent"])
        if calls is not None:
            self.assertEqual(report.requested, calls)

    def test_catalog_root_invalid_no_payload_or_symbol_leak(self):
        bad = payload()
        del bad["timezone"]
        report, calls = case(responses=[json.dumps(bad).encode()] * 2)
        self._check(report, "catalog", "catalog_root_schema", calls=1)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("BTCUSDT", json.dumps(report.sanitized_report()))

    def test_missing_required_row_field_classified_without_field_name(self):
        bad = payload()
        del bad["symbols"][0]["underlyingType"]
        report, calls = case(responses=[json.dumps(bad).encode()] * 2)
        self._check(report, "catalog", "catalog_row_missing_required", calls=1)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("underlyingType", json.dumps(report.sanitized_report()))

    def test_duplicate_or_invalid_row_classification_is_conservative(self):
        bad = payload([instrument("BTC"), instrument("BTC")])
        report, calls = case(responses=[json.dumps(bad).encode()] * 2)
        self._check(report, "catalog", "catalog_row_invalid_or_duplicate", calls=1)
        self.assertEqual(len(calls), 1)
        bad = payload([instrument("BTC"), instrument("ETH")])
        bad["symbols"][0]["onboardDate"] = "not-an-integer"
        report, _ = case(responses=[json.dumps(bad).encode()] * 2)
        self._check(report, "catalog", "catalog_row_invalid_or_duplicate", calls=1)

    def test_response_clock_and_json_duplicate_distinguished(self):
        report, calls = case(times=[AT, AT + 40_000])
        self._check(report, "response_clock", "receipt_clock", calls=1)
        self.assertEqual(len(calls), 1)
        report, calls = case(responses=[b'{"symbols":[],"symbols":[]}'] * 2)
        self._check(report, "json", "json_duplicate_key", calls=1)
        self.assertEqual(len(calls), 1)

    def test_catalog_pair_drift_distinguished(self):
        first = payload()
        second = payload([instrument("BTC"), instrument("NEW")])
        report, calls = case(responses=[
            json.dumps(first).encode(), json.dumps(second).encode()])
        self._check(report, "compare", "catalog_pair_drift_or_order", calls=2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(report.received, 2)

    def test_http_and_unknown_fetch_errors_never_echo_exception(self):
        from crypto_intelligence_agent.j1_binance_metadata_probe import (
            capture_binance_metadata_once,
        )
        registry = registry_for(("BTC",), observed=AT - 10000)
        for message, category in (
            ("binance_http_access_or_provider_denied_no_retry",
             "http_access_or_provider_denied"),
            ("secret_body_ABC_XYZ", "fetch_unclassified"),
        ):
            def fail(_url, _cap):
                raise ValueError(message)
            report = capture_binance_metadata_once(
                registry=registry,
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                owner_check=lambda: True,
                fetch=fail, utc_ms=lambda: AT,
            )
            self._check(report, "fetch", category, calls=1)
            self.assertNotIn("ABC_XYZ", json.dumps(report.sanitized_report()))
            self.assertNotIn("https://", json.dumps(report.sanitized_report()))

    def test_valid_catalog_never_has_failure_stage_or_category(self):
        report, calls = case()
        self.assertEqual(len(calls), 2)
        self._check(report, "none", "none", calls=2)
        self.assertEqual(report.status,
                         "metadata_catalog_pair_research_unverified")


if __name__ == "__main__":
    unittest.main()
