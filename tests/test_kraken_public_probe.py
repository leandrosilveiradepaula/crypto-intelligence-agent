"""Kraken Futures independent provider feasibility: exclusively offline tests."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from urllib.error import HTTPError, URLError
import unittest
from unittest.mock import patch

from scripts.probe_public_kraken import (
    PUBLIC_URL, MAX_RESPONSE_BYTES, _NoRedirect, main, make_report,
)


class FakeResponse:
    def __init__(self, data: bytes, status: int = 200):
        self.data = data
        self.status = status

    def getcode(self):
        return self.status

    def read(self, count):
        return self.data[:count]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class KrakenProbeTests(unittest.TestCase):
    def test_default_cli_never_contacts_network(self):
        with patch("scripts.probe_public_kraken._default_open",
                   side_effect=AssertionError("network forbidden")):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    main([])
        self.assertEqual(caught.exception.code, 2)

    def test_success_is_sanitized_and_symbol_count_is_heuristic(self):
        payload = {
            "result": "success",
            "instruments": [
                {"symbol": "PF_XBTUSD", "apiSecret": "NOT_EXPORTED"},
                {"symbol": "PI_XBTUSD"},
                {"symbol": "FI_XBTUSD_201225"},
            ],
        }
        opener = FakeOpener(FakeResponse(json.dumps(payload).encode()))
        report = make_report(opener=opener)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["instrument_count"], 3)
        self.assertEqual(report["perpetual_prefix_candidates"], 2)
        self.assertEqual(report["sample_symbols"], ["PF_XBTUSD", "PI_XBTUSD"])
        self.assertEqual(report["instrument_classification"], "symbol_prefix_heuristic_only")
        self.assertFalse(report["auth_used"])
        self.assertFalse(report["orders_enabled"])
        self.assertFalse(report["raw_response_persisted"])
        self.assertNotIn("NOT_EXPORTED", json.dumps(report))
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, PUBLIC_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertLessEqual(timeout, 8)

    def test_taxonomy_mode_uses_one_get_and_never_promotes_prefix_to_crypto_label(self):
        payload = {
            "result": "success",
            "instruments": [
                {"symbol": "PF_XBTUSD", "category": "crypto", "tradfi": False,
                 "base": "BTC", "quote": "USD", "pair": "BTC:USD",
                 "tags": ["perpetual", "crypto"], "type": "flexible_futures",
                 "tradeable": True},
                {"symbol": "PF_ETHUSD", "category": "crypto", "tradfi": False,
                 "tags": ["perpetual"], "type": "flexible_futures"},
                {"symbol": "PF_AAPLXUSD", "category": "equity", "tradfi": True,
                 "base": "AAPLx", "quote": "USD", "tags": ["tokenized", "equity"],
                 "type": "flexible_futures", "secret": "DO-NOT-EXPORT"},
            ],
        }
        opener = FakeOpener(FakeResponse(json.dumps(payload).encode()))
        report = make_report(opener=opener, include_taxonomy=True)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(len(opener.calls), 1)
        taxonomy = report["taxonomy"]
        self.assertEqual(taxonomy["category_counts"], {"crypto": 2, "equity": 1})
        self.assertEqual(taxonomy["tradfi_boolean_counts"], {"true": 1, "false": 2, "unknown": 0})
        self.assertTrue(taxonomy["examples"]["PF_AAPLXUSD"]["found"])
        self.assertEqual(taxonomy["examples"]["PF_AAPLXUSD"]["selected"]["tradfi"], True)
        self.assertEqual(taxonomy["taxonomy_validation_status"],
                         "observed_values_only_no_crypto_only_filter_yet")
        self.assertNotIn("DO-NOT-EXPORT", json.dumps(report))

    def test_taxonomy_ignores_unsafe_category_and_tag_values(self):
        payload = {
            "result": "success",
            "instruments": [
                {"symbol": "PF_XBTUSD", "category": "unsafe\\nvalue",
                 "tradfi": "false", "tags": ["ok", "bad\\nINJECT"], "base": "BTC"},
            ],
        }
        opener = FakeOpener(FakeResponse(json.dumps(payload).encode()))
        result = make_report(opener=opener, include_taxonomy=True)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(result["taxonomy"]["category_counts"], {"missing_or_invalid": 1})
        self.assertEqual(result["taxonomy"]["tradfi_boolean_counts"]["unknown"], 1)
        self.assertNotIn("bad\\nINJECT", json.dumps(result["taxonomy"]))

    def test_http451_is_a_policy_gate_not_an_invitation_to_retry(self):
        error = HTTPError(PUBLIC_URL, 451, "restricted", None, None)
        opener = FakeOpener(error)
        report = make_report(opener=opener)
        self.assertEqual(report["status"], "policy_or_access_restriction")
        self.assertEqual(report["http_status"], 451)
        self.assertEqual(len(opener.calls), 1)

    def test_http403_and_418_are_not_retried(self):
        for status in (403, 418):
            with self.subTest(status=status):
                opener = FakeOpener(HTTPError(PUBLIC_URL, status, "policy", None, None))
                self.assertEqual(
                    make_report(opener=opener)["status"],
                    "policy_or_access_restriction",
                )
                self.assertEqual(len(opener.calls), 1)

    def test_network_errors_are_sanitized(self):
        report = make_report(opener=FakeOpener(URLError("SECRET-PATH")))
        self.assertEqual(report["status"], "network_or_dns_failure")
        self.assertNotIn("SECRET-PATH", json.dumps(report))

    def test_invalid_payloads_are_never_called_conformant(self):
        payloads = (
            b"{broken",
            b"[]",
            b'{"result":"error","instruments":[]}',
            b'{"result":"success","instruments":"wrong"}',
            b'{"result":"success","instruments":[]}',
            b'{"result":"success","instruments":[{"symbol":null}]}',
        )
        for body in payloads:
            with self.subTest(body=body[:40]):
                report = make_report(opener=FakeOpener(FakeResponse(body)))
                self.assertNotEqual(report["status"], "ok")
                self.assertNotIn("instruments", report)

    def test_large_payload_is_rejected_not_persisted(self):
        opener = FakeOpener(FakeResponse(b"x" * (MAX_RESPONSE_BYTES + 1)))
        report = make_report(opener=opener)
        self.assertEqual(report["status"], "response_too_large")
        self.assertFalse(report["raw_response_persisted"])

    def test_redirects_are_not_followed(self):
        redirect = _NoRedirect()
        self.assertIsNone(redirect.redirect_request(None, None, 302, "redirect", {}, "https://example.com"))


if __name__ == "__main__":
    unittest.main()
