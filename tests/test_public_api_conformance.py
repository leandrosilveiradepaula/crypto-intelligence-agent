"""Public USD-M conformance/error tests using offline transports only."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import (
    BinanceFuturesPublicAdapter, DataValidationError, ExchangeAccessError,
    HttpResponse, HttpResponseError, RateLimitError, UrllibTransport,
)
from crypto_intelligence_agent.offline_fixtures import OfflineFixtureTransport
from crypto_intelligence_agent.pipeline import ReadOnlyCollectionPipeline
from crypto_intelligence_agent.storage import SQLiteMarketDataStore

CLOCK_MS = 20_000_000
HOUR = 3_600_000


class ResponseQueue:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url, timeout_seconds):
        self.urls.append(url)
        if not self.responses:
            raise AssertionError("unexpected extra API call")
        return self.responses.pop(0)


def adapter_for(responses, *, max_retries=2, max_wait=10):
    transport = ResponseQueue(responses)
    sleeps: list[float] = []
    adapter = BinanceFuturesPublicAdapter(
        transport, clock_ms=lambda: CLOCK_MS, max_rate_limit_retries=max_retries,
        initial_backoff_seconds=0.25, max_retry_wait_seconds=max_wait,
        sleep_fn=sleeps.append,
    )
    return adapter, transport, sleeps


class ErrorConformanceTests(unittest.TestCase):
    def test_retry_after_respected_for_public_429_without_live_wait(self):
        adapter, transport, sleeps = adapter_for([
            HttpResponse(429, "{}", {"retry-after": "2"}),
            HttpResponse(200, '{"serverTime":20000000}'),
        ])
        self.assertEqual(adapter.server_time_ms(), CLOCK_MS)
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(len(transport.urls), 2)

    def test_exponential_retry_without_header_is_bounded(self):
        adapter, transport, sleeps = adapter_for([
            HttpResponse(429, "{}"), HttpResponse(429, "{}"),
            HttpResponse(429, "{}"),
        ])
        with self.assertRaises(RateLimitError):
            adapter.server_time_ms()
        self.assertEqual(sleeps, [0.25, 0.5])
        self.assertEqual(len(transport.urls), 3)

    def test_retry_after_above_limit_fails_closed_before_retry(self):
        adapter, transport, sleeps = adapter_for(
            [HttpResponse(429, "{}", {"retry-after": "120"})]
        )
        with self.assertRaises(RateLimitError):
            adapter.server_time_ms()
        self.assertEqual(sleeps, [])
        self.assertEqual(len(transport.urls), 1)

    def test_invalid_retry_after_is_rejected(self):
        for invalid in ("abc", "-1", "nan", "inf"):
            with self.subTest(invalid=invalid):
                adapter, transport, sleeps = adapter_for([
                    HttpResponse(429, "{}", {"retry-after": invalid}),
                ])
                with self.assertRaises(RateLimitError):
                    adapter.server_time_ms()
                self.assertEqual(len(transport.urls), 1)
                self.assertEqual(sleeps, [])

    def test_forbidden_and_ip_ban_do_not_trigger_retries(self):
        for status in (403, 418):
            with self.subTest(status=status):
                adapter, transport, sleeps = adapter_for([HttpResponse(status, "{}")])
                with self.assertRaises(ExchangeAccessError):
                    adapter.server_time_ms()
                self.assertEqual(len(transport.urls), 1)
                self.assertEqual(sleeps, [])

    def test_other_http_failures_and_redirect_do_not_parse_as_success(self):
        for status in (302, 404, 500, 503):
            with self.subTest(status=status):
                adapter, transport, sleeps = adapter_for([HttpResponse(status, "{}")])
                with self.assertRaises(HttpResponseError):
                    adapter.server_time_ms()
                self.assertEqual(len(transport.urls), 1)
                self.assertEqual(sleeps, [])

    def test_invalid_json_and_missing_server_time_fail(self):
        for body in ('{invalid', '{}', '[]', '{"serverTime":1.5}'):
            with self.subTest(body=body):
                adapter, _, _ = adapter_for([HttpResponse(200, body)])
                with self.assertRaises(DataValidationError):
                    adapter.server_time_ms()

    def test_response_header_capture_uses_allowlist_without_secrets(self):
        class FakeResponse:
            status = 200
            headers = {
                "Retry-After": "3",
                "X-MBX-USED-WEIGHT-1M": "19",
                "X-API-KEY": "DO_NOT_PERSIST",
                "Authorization": "DO_NOT_PERSIST",
            }

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"serverTime":20000000}'

        with patch("crypto_intelligence_agent.market_data.urlopen", return_value=FakeResponse()):
            response = UrllibTransport().get("https://fapi.binance.com/fapi/v1/time", 1)
        self.assertEqual(response.headers, {
            "retry-after": "3", "x-mbx-used-weight-1m": "19",
        })
        self.assertNotIn("DO_NOT_PERSIST", repr(response.headers))


class ForbiddenFixtureTransport(OfflineFixtureTransport):
    def get(self, url, timeout_seconds):
        if "/fapi/v1/time" in url:
            self.requests.append(url)
            return HttpResponse(403, '{"msg":"restricted"}')
        return super().get(url, timeout_seconds)


class AuditConformanceTests(unittest.TestCase):
    def test_blocked_public_endpoint_records_failure_and_stops_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMarketDataStore(Path(directory) / "market.sqlite")
            transport = ForbiddenFixtureTransport()
            adapter = BinanceFuturesPublicAdapter(
                transport, clock_ms=lambda: CLOCK_MS, initial_backoff_seconds=0,
            )
            pipeline = ReadOnlyCollectionPipeline(
                adapter, store, clock_ms=lambda: CLOCK_MS, mode="offline",
                source_name="synthetic_fixture",
            )
            with self.assertRaises(ExchangeAccessError):
                pipeline.run(interval="1h", start_open_ms=0, end_open_ms=3 * HOUR)
            self.assertEqual(len(transport.requests), 1)
            events = store.collection_events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].status, "failure")
            self.assertEqual(events[0].detail, "ExchangeAccessError")
            self.assertIsNone(store.latest_checkpoint(
                data_type="closed_candle", exchange="binance", symbol="BTCUSDT",
                interval="1h",
            ))


if __name__ == "__main__":
    unittest.main()
