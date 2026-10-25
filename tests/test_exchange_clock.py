"""Offline conformance and skew regressions for Binance USD-M public server time.

No test accesses the network; synthetic clock only.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.market_data import (
    BinanceFuturesPublicAdapter, DataTimeoutError, DataValidationError,
    HttpResponse, HttpResponseError, RateLimitError,
)
from crypto_intelligence_agent.offline_fixtures import OfflineFixtureTransport
from crypto_intelligence_agent.pipeline import ReadOnlyCollectionPipeline
from crypto_intelligence_agent.storage import SQLiteMarketDataStore


CLOCK_MS = 20_000_000
HOUR = 3_600_000


class TimeResponseTransport(OfflineFixtureTransport):
    def __init__(self, response: HttpResponse | Exception):
        super().__init__()
        self.time_response = response

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        if "/fapi/v1/time" in url:
            self.requests.append(url)
            if isinstance(self.time_response, Exception):
                raise self.time_response
            return self.time_response
        return super().get(url, timeout_seconds)


def clock_adapter(transport):
    return BinanceFuturesPublicAdapter(
        transport, clock_ms=lambda: CLOCK_MS,
        initial_backoff_seconds=0,
    )


class ServerClockTests(unittest.TestCase):
    def test_public_clock_is_utc_ms_and_fixture_is_always_offline(self):
        transport = OfflineFixtureTransport()
        self.assertEqual(clock_adapter(transport).server_time_ms(), CLOCK_MS)
        self.assertEqual(len(transport.requests), 1)
        self.assertIn("/fapi/v1/time", transport.requests[0])

    def test_malformed_server_time_fails_before_domain_use(self):
        payloads = [[], None, {}, {"serverTime": None}, {"serverTime": -1},
                    {"serverTime": True}, {"serverTime": 5.25},
                    {"serverTime": "5.25"}, {"serverTime": "NaN"}]
        for payload in payloads:
            with self.subTest(payload=payload):
                transport = TimeResponseTransport(HttpResponse(200, json.dumps(payload)))
                with self.assertRaises(DataValidationError):
                    clock_adapter(transport).server_time_ms()

    def test_rate_limit_server_error_and_timeout_are_explicit(self):
        for response, expected in (
            (HttpResponse(429, "{}"), RateLimitError),
            (HttpResponse(503, "{}"), HttpResponseError),
            (DataTimeoutError("offline timeout"), DataTimeoutError),
        ):
            with self.subTest(error_type=expected):
                with self.assertRaises(expected):
                    clock_adapter(TimeResponseTransport(response)).server_time_ms()

    def test_clock_drift_blocks_snapshots_and_candle_writes_with_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMarketDataStore(Path(directory) / "data.sqlite")
            transport = TimeResponseTransport(
                HttpResponse(200, json.dumps({"serverTime": CLOCK_MS + 30_000}))
            )
            pipeline = ReadOnlyCollectionPipeline(
                clock_adapter(transport), store, clock_ms=lambda: CLOCK_MS,
                mode="offline", source_name="synthetic_fixture",
            )
            with self.assertRaises(DataValidationError):
                pipeline.run(interval="1h", start_open_ms=0, end_open_ms=3 * HOUR)
            self.assertEqual(len(transport.requests), 1)
            self.assertEqual(len(store.collection_events()), 1)
            event = store.collection_events()[0]
            self.assertEqual(event.status, "failure")
            self.assertEqual(event.endpoint, "GET /fapi/v1/time")
            self.assertEqual(store.contracts(
                exchange="binance", market="linear_perpetual", observed_at_ms=CLOCK_MS,
            ), ())
            self.assertIsNone(store.latest_checkpoint(
                data_type="closed_candle", exchange="binance",
                symbol="BTCUSDT", interval="1h",
            ))

    def test_latency_uncertainty_is_part_of_clock_gate(self):
        class StepClock:
            def __init__(self, start: int, step: int):
                self.value = start
                self.step = step

            def __call__(self):
                self.value += self.step
                return self.value

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMarketDataStore(Path(directory) / "data.sqlite")
            clock = StepClock(CLOCK_MS, 1_000)
            pipeline = ReadOnlyCollectionPipeline(
                BinanceFuturesPublicAdapter(OfflineFixtureTransport(), clock_ms=clock),
                store, clock_ms=clock, mode="offline", source_name="synthetic_fixture",
                max_clock_skew_ms=1_000,
            )
            with self.assertRaises(DataValidationError):
                pipeline.run(interval="1h", start_open_ms=0, end_open_ms=3 * HOUR)
            self.assertEqual(store.collection_events()[0].status, "failure")

    def test_backward_local_clock_still_creates_failure_audit(self):
        values = iter([CLOCK_MS, CLOCK_MS, CLOCK_MS - 1, CLOCK_MS - 2])

        def unstable_clock():
            return next(values, CLOCK_MS - 2)

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMarketDataStore(Path(directory) / "data.sqlite")
            pipeline = ReadOnlyCollectionPipeline(
                BinanceFuturesPublicAdapter(
                    OfflineFixtureTransport(), clock_ms=unstable_clock,
                ),
                store, clock_ms=unstable_clock, mode="offline",
                source_name="synthetic_fixture",
            )
            with self.assertRaises(DataValidationError):
                pipeline.run(interval="1h", start_open_ms=0, end_open_ms=3 * HOUR)
            audit = store.collection_events()
            self.assertEqual(len(audit), 1)
            self.assertEqual(audit[0].status, "failure")
            self.assertIn("local_clock_moved_backwards", audit[0].detail)
            self.assertEqual(audit[0].observed_start_ms, audit[0].observed_end_ms)

    def test_clock_sample_is_exposed_in_successful_report_and_event(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMarketDataStore(Path(directory) / "data.sqlite")
            transport = OfflineFixtureTransport()
            pipeline = ReadOnlyCollectionPipeline(
                clock_adapter(transport), store, clock_ms=lambda: CLOCK_MS,
                mode="offline", source_name="synthetic_fixture",
            )
            result = pipeline.run(
                interval="1h", start_open_ms=0, end_open_ms=3 * HOUR,
                max_symbols=1, page_size=2,
            )
            self.assertEqual(result.server_time_ms, CLOCK_MS)
            self.assertEqual(result.clock_offset_ms, 0)
            self.assertEqual(result.clock_round_trip_ms, 0)
            self.assertEqual(result.endpoints[0], "GET /fapi/v1/time")
            audit = store.collection_events()
            self.assertEqual(audit[0].status, "success")
            self.assertIn("offset_ms=0", audit[0].detail)
            self.assertEqual(len(audit), 4)


if __name__ == "__main__":
    unittest.main()
