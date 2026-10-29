"""Offline security and request-shape regressions for J1 public GET transport."""
import unittest
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
    instruments_url, kline_url,
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
