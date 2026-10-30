"""Offline security and request-shape regressions for J1 public GET transport."""
import unittest
from email.message import Message
from urllib.error import HTTPError
from unittest.mock import patch
from crypto_intelligence_agent import bybit_public_j1_transport as transport_module
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
    MIN_PUBLIC_GET_INTERVAL_SECONDS, instruments_url, kline_url,
    _network_get, _NetworkGetWithQuota, _read_bybit_quota_headers,
)

H = 3_600_000
T = 1793000000000 // H * H


class J1BybitTransportTests(unittest.TestCase):
    def test_exact_builder_and_successful_injected_transport(self):
        urls = []
        def fake(url, limit):
            urls.append(url)
            return b'{"retCode":0,"result":{},"time":1793000000000}'
        client = BoundedBybitPublicClient(transport=fake)
        for url in (
            instruments_url(),
            instruments_url(cursor="abc/+=="),
            instruments_url(symbol="BTCUSDT"),
            kline_url("BTCUSDT", T-24*H, T),
            kline_url("BTCUSDT", T-72*H, T),
            kline_url("BTCUSDT", T-720*H, T),
        ):
            self.assertEqual(client.get(url)[1]["retCode"], 0)
        self.assertEqual(client.requests_attempted, 6)
        self.assertEqual(len(urls), 6)
        self.assertEqual(
            parse_qs(urlsplit(urls[1]).query)["cursor"], ["abc/+=="])


    def test_catalog_1000_limit_preserves_query_guards(self):
        from crypto_intelligence_agent.bybit_public_j1_transport import instruments_url
        one = instruments_url()
        self.assertEqual(parse_qs(urlsplit(one).query)["limit"], ["1000"])
        self.assertEqual(parse_qs(urlsplit(instruments_url(cursor="safe")).query)["limit"], ["1000"])
        self.assertEqual(parse_qs(urlsplit(instruments_url(symbol="BTCUSDT")).query)["limit"], ["1"])
        c = BoundedBybitPublicClient(transport=lambda url, limit: b'{"retCode":0}')
        for bad in (one.replace("limit=1000", "limit=200"),
                    one.replace("limit=1000", "limit=1001"),
                    instruments_url(cursor="safe").replace("limit=1000", "limit=200")):
            with self.subTest(bad=bad), self.assertRaises(J1BybitCaptureError):
                c.get(bad)
        self.assertEqual(c.requests_attempted, 0)

    def test_malformed_origin_or_extra_arguments_rejected_without_io(self):
        client = BoundedBybitPublicClient(
            transport=lambda url, limit: self.fail("transport must not run"))
        good = instruments_url()
        for url in (
            "http://" + good[len("https://"):],
            good.replace("api.bybit.com", "api.bybit.com.evil"),
            good + "&api_key=foo",
            good + "#fragment",
            good.replace("limit=200", "limit=1000"),
            instruments_url(symbol="BTCUSDT") + "&cursor=foo",
            kline_url("BTCUSDT", T-H, T).replace("interval=60", "interval=1"),
            kline_url("BTCUSDT", T-H, T).replace("limit=1", "limit=72"),
        ):
            with self.subTest(url=url), self.assertRaises(J1BybitCaptureError):
                client.get(url)
        self.assertEqual(client.requests_attempted, 0)

    def test_actual_network_path_has_strict_two_second_spacing(self):
        # This is still an OFFLINE test: patch the network boundary itself.
        # The clock and sleep are both injected deterministically so CI is
        # fast and does not issue a single external request.
        starts = []
        sleeps = []
        simulated = [17.0]

        def clock():
            return simulated[0]

        def fake_sleep(seconds):
            self.assertGreater(seconds, 0)
            sleeps.append(seconds)
            simulated[0] += seconds

        def fake_network(url, limit):
            starts.append(clock())
            return b'{"retCode":0,"result":{},"time":1793000000000}'

        with (
            patch.object(transport_module.time, "monotonic", side_effect=clock),
            patch.object(transport_module.time, "sleep", side_effect=fake_sleep),
            patch.object(transport_module, "_network_get", side_effect=fake_network),
        ):
            client = BoundedBybitPublicClient()
            for uri in (
                instruments_url(),
                instruments_url(symbol="BTCUSDT"),
                kline_url("BTCUSDT", T-H, T),
            ):
                self.assertEqual(client.get(uri)[1]["retCode"], 0)
        self.assertEqual(client.requests_attempted, 3)
        self.assertEqual(len(starts), 3)
        self.assertEqual(len(sleeps), 2)
        for previous, current in zip(starts, starts[1:]):
            self.assertGreaterEqual(
                current - previous, MIN_PUBLIC_GET_INTERVAL_SECONDS)
        self.assertEqual(MIN_PUBLIC_GET_INTERVAL_SECONDS, 2.0)

    def test_real_transport_rate_limit_aborts_once_without_retry(self):
        calls = []
        waits = []
        simulated = [2.0]

        def fake_sleep(seconds):
            waits.append(seconds)
            simulated[0] += seconds

        def fake_get(url, limit):
            calls.append(url)
            if len(calls) == 2:
                return b'{"retCode":10006,"retMsg":"PRIVATE_PRICE_NEVER_PRINT"}'
            return b'{"retCode":0,"result":{}}'

        with (
            patch.object(transport_module.time, "monotonic",
                         side_effect=lambda: simulated[0]),
            patch.object(transport_module.time, "sleep",
                         side_effect=fake_sleep),
            patch.object(transport_module, "_network_get",
                         side_effect=fake_get),
        ):
            client = BoundedBybitPublicClient()
            client.get(instruments_url())
            with self.assertRaisesRegex(
                J1BybitCaptureError, "provider_rate_limit_no_retry",
            ) as caught:
                client.get(kline_url("BTCUSDT", T-24*H, T))
        self.assertEqual(len(calls), 2)
        self.assertEqual(client.requests_attempted, 2)
        self.assertEqual(client.last_provider_retcode, 10006)
        self.assertEqual(client.last_request_stage, "closed_kline_24h")
        self.assertNotIn("PRIVATE_PRICE", str(caught.exception))
        self.assertEqual(waits, [MIN_PUBLIC_GET_INTERVAL_SECONDS])

    def test_real_http_wire_collects_only_bounded_quota_metadata(self):
        uri = kline_url("BTCUSDT", T - 24 * H, T)
        body = b'{"retCode":0,"result":{},"time":1793000000000}'
        response_headers = Message()
        response_headers["Content-Type"] = "application/json"
        response_headers["X-Bapi-Limit"] = "10"
        response_headers["X-Bapi-Limit-Status"] = "2"
        response_headers["X-Bapi-Limit-Reset-Timestamp"] = "1793000001500"
        response_headers["X-Untrusted-Api-Key"] = "SECRET_DO_NOT_SHOW"

        class FakeResponse:
            headers = response_headers
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def getcode(self):
                return 200
            def geturl(self):
                return uri
            def read(self, n):
                return body

        class FakeOpener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return FakeResponse()

        opener = FakeOpener()
        with (patch.object(transport_module, "build_opener",
                           return_value=opener),
              patch.object(transport_module.time, "time",
                           return_value=1793000000.0)):
            wire = _network_get(uri, 131_072)
        self.assertEqual(wire.raw, body)
        self.assertEqual(wire.quota.sanitized_fields(), {
            "provider_quota_headers_present": True,
            "provider_endpoint_limit": 10,
            "provider_endpoint_remaining": 2,
            "provider_reset_header_delta_ms": 1500,
        })
        self.assertEqual(opener.request.get_method(), "GET")
        self.assertNotIn(
            "SECRET_DO_NOT_SHOW",
            repr(wire.quota.sanitized_fields()),
        )
        # The call-site public API still returns exactly bytes and decoded
        # JSON even when the underlying real HTTP client carries metadata.
        with patch.object(transport_module, "_network_get",
                          return_value=wire):
            client = BoundedBybitPublicClient()
            raw, data = client.get(uri)
        self.assertEqual(raw, body)
        self.assertEqual(data["retCode"], 0)
        self.assertEqual(client.sanitized_quota_fields(),
                         wire.quota.sanitized_fields())

    def test_rate_limit_10006_retains_safe_numeric_quota_not_retmsg(self):
        headers = Message()
        headers["X-Bapi-Limit"] = "10"
        headers["X-Bapi-Limit-Status"] = "0"
        headers["X-Bapi-Limit-Reset-Timestamp"] = "1793000000200"
        with patch.object(transport_module.time, "time",
                          return_value=1793000000.0):
            hint = _read_bybit_quota_headers(headers)
        wire = _NetworkGetWithQuota(
            raw=b'{"retCode":10006,"retMsg":"PRIVATE_SYMBOL_PRICE_TOKEN"}',
            quota=hint,
        )
        client = BoundedBybitPublicClient()
        with patch.object(transport_module, "_network_get",
                          return_value=wire):
            with self.assertRaisesRegex(
                J1BybitCaptureError, "provider_rate_limit_no_retry",
            ) as err:
                client.get(kline_url("BTCUSDT", T-24*H, T))
        self.assertEqual(client.last_provider_retcode, 10006)
        self.assertEqual(client.requests_attempted, 1)
        snapshot = client.sanitized_quota_fields()
        self.assertEqual(snapshot["provider_endpoint_remaining"], 0)
        self.assertEqual(snapshot["provider_reset_header_delta_ms"], 200)
        self.assertNotIn("PRIVATE_SYMBOL", str(err.exception))
        self.assertNotIn("PRIVATE_SYMBOL", str(snapshot))

    def test_missing_or_malformed_quota_is_unknown_never_fake_zero(self):
        self.assertEqual(
            _read_bybit_quota_headers(Message()).sanitized_fields(),
            {"provider_quota_headers_present": False},
        )
        forged = Message()
        forged["X-Bapi-Limit"] = "-9"
        forged["X-Bapi-Limit-Status"] = "1000000000000000"
        forged["X-Bapi-Limit-Reset-Timestamp"] = "not-a-time"
        forged["X-Sensitive"] = "PRIVATE_CREDENTIAL"
        self.assertEqual(
            _read_bybit_quota_headers(forged).sanitized_fields(),
            {"provider_quota_headers_present": True},
        )
        inconsistent = Message()
        inconsistent["X-Bapi-Limit"] = "3"
        inconsistent["X-Bapi-Limit-Status"] = "5"
        with patch.object(transport_module.time, "time",
                          return_value=1793000000.0):
            sane = _read_bybit_quota_headers(inconsistent).sanitized_fields()
        self.assertEqual(sane["provider_endpoint_limit"], 3)
        self.assertNotIn("provider_endpoint_remaining", sane)
        # Synthetic in-memory transports must not pretend to carry HTTP
        # headers, even if their JSON includes an untrusted retMsg.
        client = BoundedBybitPublicClient(
            transport=lambda url, limit: b'{"retCode":0,"result":{}}')
        client.get(instruments_url())
        self.assertEqual(
            client.sanitized_quota_fields(),
            {"provider_quota_headers_present": False},
        )

    def test_forbidden_http_status_remains_fail_closed(self):
        uri = instruments_url()
        class DenyOpener:
            def open(self, request, timeout):
                raise HTTPError(
                    uri, 403, "SENSITIVE_FAILURE_MESSAGE",
                    Message(), None,
                )
        with patch.object(transport_module, "build_opener",
                          return_value=DenyOpener()):
            with self.assertRaisesRegex(
                J1BybitCaptureError, "access_region_or_rate_limit_no_retry",
            ) as err:
                _network_get(uri, 131_072)
        self.assertNotIn("SENSITIVE_FAILURE_MESSAGE", str(err.exception))

    def test_bounded_get_fail_closed(self):
        client = BoundedBybitPublicClient(
            transport=lambda url, limit: b'{"retCode":10009}')
        with self.assertRaisesRegex(J1BybitCaptureError, "region"):
            client.get(instruments_url())
        self.assertEqual(client.requests_attempted, 1)
        bad = BoundedBybitPublicClient(
            transport=lambda url, limit: b'{"retCode":0,"retCode":0}')
        with self.assertRaises(J1BybitCaptureError):
            bad.get(instruments_url())
        with self.assertRaises(J1BybitCaptureError):
            kline_url("BTCUSDT", T, T + 2*H)


if __name__ == "__main__":
    unittest.main()
