"""Network is disabled in CI: injected fake single-request transport only."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from scripts.probe_bybit_public_trade_archive import (
    ARCHIVE_URL, probe_archive,
)
from test_bybit_public_trade_archive import payload

class FakeResponse:
    def __init__(self, data, status=200, url=ARCHIVE_URL):
        self.data, self.status, self.url = data, status, url
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def getcode(self):
        return self.status
    def geturl(self):
        return self.url
    def read(self, n):
        return self.data[:n]


class BybitArchiveProbeTests(unittest.TestCase):
    def test_default_and_single_optins_never_call_network(self):
        for a, b in ((False, False), (True, False), (False, True)):
            def forbidden(*args, **kwargs):
                raise AssertionError("network must be disabled")
            report = probe_archive(
                allow_public_network=a,
                allow_one_public_archive_probe=b, opened=forbidden,
            )
            self.assertEqual(report["requests_attempted"], 0)
            self.assertFalse(report["orders_sent"])

    def test_one_get_exact_destination_and_sanitized_success(self):
        fake = FakeResponse(payload())
        calls = []
        def opened(request, *, timeout):
            calls.append((request, timeout))
            return fake
        report = probe_archive(
            allow_public_network=True, allow_one_public_archive_probe=True,
            opened=opened,
        )
        # Fixture for a different date must not be promoted as successful.
        self.assertEqual(report["status"], "archive_unavailable_or_schema_rejected")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].full_url, ARCHIVE_URL)
        self.assertEqual(calls[0][0].get_method(), "GET")
        self.assertEqual(calls[0][1], 10)
        self.assertFalse(report["canonical_ohlcv_approved"])

    def test_wrong_url_403_or_invalid_bytes_fail_closed(self):
        for response in (
            FakeResponse(b"x", url="https://different.invalid"),
            FakeResponse(b"x", status=403),
            FakeResponse(b"x"),
        ):
            calls = []
            def opened(request, *, timeout):
                calls.append(request)
                return response
            report = probe_archive(
                allow_public_network=True, allow_one_public_archive_probe=True,
                opened=opened,
            )
            self.assertNotEqual(report["status"], "unverified_historical_trade_schema_observed")
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["requests_attempted"], 1)
            self.assertFalse(report["dataset_rights_authorized_for_production"])

if __name__ == "__main__":
    unittest.main()
