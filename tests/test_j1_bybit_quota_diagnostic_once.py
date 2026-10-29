"""J1 #324: one-GET rate quota probe cannot leak prices or retry.

Fake public REST bytes only, absolutely no external network, DB or orders.
"""
import os
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
)
from scripts.probe_bybit_rate_limit_once import (
    HOUR_MS as H, owner_observe_bybit_kline_quota_once,
)

T = 1793000000000 // H * H + 10_000


class SingleRequestBybitQuotaDiagnosticTests(unittest.TestCase):
    def test_owner_opt_in_required_even_for_one_public_get(self):
        fetch = BoundedBybitPublicClient(
            transport=lambda url, limit: self.fail("not called"))
        with self.assertRaisesRegex(J1BybitCaptureError, "opt_in"):
            owner_observe_bybit_kline_quota_once(
                client=fetch, clock_ms=lambda: T,
            )
        self.assertEqual(fetch.requests_attempted, 0)

    def test_utc_close_safety_checks_abort_before_any_get(self):
        fetch = BoundedBybitPublicClient(
            transport=lambda url, limit: self.fail("not called"))
        with patch("scripts.probe_bybit_rate_limit_once.os.name", "posix"):
            with self.assertRaisesRegex(
                J1BybitCaptureError, "closed_hour_safety",
            ):
                owner_observe_bybit_kline_quota_once(
                    allow_public_network=True,
                    confirm_region_and_personal_research=True,
                    client=fetch,
                    clock_ms=lambda: T // H * H + 1000,
                )
        self.assertEqual(fetch.requests_attempted, 0)

    @unittest.skipUnless(os.name == "posix", "owner-only POSIX gate")
    def test_exactly_one_closed_hour_btc_public_get_no_market_output(self):
        calls = []
        def transport(url, limit):
            calls.append(url)
            return (b'{"retCode":0,"retMsg":"OK","result":{'
                    b'"symbol":"BTCUSDT","list":[["0","SECRET_PRICE"]]},'
                    b'"time":1793000000000}')
        fetch = BoundedBybitPublicClient(transport=transport)
        with patch("socket.create_connection",
                   side_effect=AssertionError("no real network")):
            out = owner_observe_bybit_kline_quota_once(
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                client=fetch, clock_ms=lambda: T,
            )
        self.assertEqual(len(calls), 1)
        parsed = urlsplit(calls[0])
        self.assertEqual(parsed.path, "/v5/market/kline")
        q = parse_qs(parsed.query)
        self.assertEqual(q["symbol"], ["BTCUSDT"])
        self.assertEqual(q["interval"], ["60"])
        self.assertEqual(q["limit"], ["1"])
        self.assertEqual(out["network_gets_attempted"], 1)
        self.assertEqual(out["status"], "j1_one_public_kline_quota_observation_only")
        self.assertFalse(out["provider_quota_headers_present"])
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["data_stored"])
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertNotIn("SECRET_PRICE", str(out))
        self.assertNotIn("BTCUSDT", str(out))

    @unittest.skipUnless(os.name == "posix", "owner-only POSIX gate")
    def test_10006_from_one_get_is_fail_stop_no_retry(self):
        calls = []
        def transport(url, limit):
            calls.append(url)
            return b'{"retCode":10006,"retMsg":"TOKEN_DO_NOT_REPORT"}'
        fetch = BoundedBybitPublicClient(transport=transport)
        with patch("socket.create_connection",
                   side_effect=AssertionError("no real network")):
            with self.assertRaisesRegex(
                J1BybitCaptureError, "provider_rate_limit_no_retry",
            ) as err:
                owner_observe_bybit_kline_quota_once(
                    allow_public_network=True,
                    confirm_region_and_personal_research=True,
                    client=fetch, clock_ms=lambda: T,
                )
        self.assertEqual(len(calls), 1)
        self.assertEqual(fetch.requests_attempted, 1)
        self.assertEqual(fetch.last_provider_retcode, 10006)
        self.assertEqual(fetch.last_request_stage, "closed_kline_1h")
        self.assertFalse(fetch.sanitized_quota_fields()
                         ["provider_quota_headers_present"])
        self.assertNotIn("TOKEN_DO_NOT_REPORT", str(err.exception))


if __name__ == "__main__":
    unittest.main()
