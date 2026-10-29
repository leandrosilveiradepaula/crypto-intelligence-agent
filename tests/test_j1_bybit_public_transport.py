"""Offline security and request-shape regressions for J1 public GET transport."""
import unittest
from unittest.mock import patch
from crypto_intelligence_agent import bybit_public_j1_transport as transport_module
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
    MIN_PUBLIC_GET_INTERVAL_SECONDS, instruments_url, kline_url,
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
        ):
            self.assertEqual(client.get(url)[1]["retCode"], 0)
        self.assertEqual(client.requests_attempted, 5)
        self.assertEqual(len(urls), 5)
        self.assertEqual(
            parse_qs(urlsplit(urls[1]).query)["cursor"], ["abc/+=="])

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
