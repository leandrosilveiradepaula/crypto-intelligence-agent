"""End-to-end offline J1/WU3 checks; no network, no trading credentials."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.cli import main
from crypto_intelligence_agent.market_data import (
    BinanceFuturesPublicAdapter, DataGapError, DataTimeoutError,
    DataValidationError, HttpResponse,
)
from crypto_intelligence_agent.offline_fixtures import OfflineFixtureTransport
from crypto_intelligence_agent.pipeline import ReadOnlyCollectionPipeline
from crypto_intelligence_agent.storage import SQLiteMarketDataStore

HOUR = 3_600_000
DEMO_CLOCK = 20_000_000


class GapTransport(OfflineFixtureTransport):
    def get(self, url, timeout_seconds):
        result = super().get(url, timeout_seconds)
        if "/fapi/v1/klines" in url:
            rows = json.loads(result.body)
            rows = [row for row in rows if row[0] != HOUR]
            return HttpResponse(200, json.dumps(rows))
        return result


class ThrottleTransport(OfflineFixtureTransport):
    def get(self, url, timeout_seconds):
        if "/fapi/v1/klines" in url:
            return HttpResponse(429, "{}")
        return super().get(url, timeout_seconds)


class TimeoutTransport(OfflineFixtureTransport):
    def get(self, url, timeout_seconds):
        if "/fapi/v1/klines" in url:
            raise DataTimeoutError("simulated offline timeout")
        return super().get(url, timeout_seconds)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "market.sqlite3"
        self.store = SQLiteMarketDataStore(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def create_pipeline(self, transport=None, *, clock=None):
        current = clock or (lambda: DEMO_CLOCK)
        t = transport or OfflineFixtureTransport()
        adapter = BinanceFuturesPublicAdapter(
            t, clock_ms=current, initial_backoff_seconds=0,
        )
        return ReadOnlyCollectionPipeline(
            adapter, self.store, clock_ms=current,
            mode="offline", source_name="synthetic_fixture",
        ), t

    def run_pipeline(self, pipeline, *, max_symbols=2, required_symbols=()):
        return pipeline.run(
            interval="1h", start_open_ms=0, end_open_ms=3 * HOUR,
            max_symbols=max_symbols, page_size=2,
            required_symbols=required_symbols,
        )

    def test_two_symbols_through_adapter_sqlite_backfill_and_quality(self):
        pipeline, transport = self.create_pipeline()
        response = self.run_pipeline(pipeline)
        self.assertTrue(response.synthetic)
        self.assertEqual(response.source, "synthetic_fixture")
        self.assertEqual(response.selected_symbols, ("ETHUSDT", "BTCUSDT"))
        self.assertEqual(len(response.results), 2)
        self.assertEqual([r.candles_committed for r in response.results], [3, 3])
        self.assertTrue(all(r.complete for r in response.results))
        self.assertTrue(transport.requests)
        for symbol in response.selected_symbols:
            candles = self.store.candles(
                exchange="binance", market="linear_perpetual", symbol=symbol,
                interval="1h", start_open_ms=0, end_open_ms=3 * HOUR,
            )
            self.assertEqual(len(candles), 3)
            self.assertTrue(all(c.quality == "synthetic_fixture" for c in candles))

    def test_audit_records_actual_sources_and_public_endpoint_paths(self):
        pipeline, transport = self.create_pipeline()
        result = self.run_pipeline(pipeline, required_symbols=("BTCUSDT",))
        events = self.store.collection_events()
        self.assertEqual(len(events), 3)
        self.assertEqual([event.status for event in events], ["success"] * 3)
        self.assertEqual([event.endpoint for event in events], list(result.endpoints))
        self.assertTrue(all(event.mode == "offline" for event in events))
        self.assertEqual(events[-1].candles_committed, 3)
        snapshot = self.store.universe_snapshot(
            observed_at_ms=DEMO_CLOCK,
            selection_rule_version="j1-wu3-v1", source="synthetic_fixture",
        )
        self.assertEqual(snapshot.eligible[0].symbol, "ETHUSDT")
        self.assertEqual(snapshot.source, "synthetic_fixture")
        contracts = self.store.contracts(
            exchange="binance", market="linear_perpetual",
            observed_at_ms=DEMO_CLOCK,
        )
        self.assertEqual(len(contracts), 2)
        self.assertTrue(all(c.source == "synthetic_fixture" for c in contracts))

    def test_second_run_uses_checkpoints_without_new_candle_pages(self):
        pipeline, _ = self.create_pipeline()
        self.run_pipeline(pipeline)
        repeated = self.run_pipeline(pipeline)
        self.assertEqual([r.pages_committed for r in repeated.results], [0, 0])
        self.assertEqual([r.persisted_candles for r in repeated.results], [3, 3])
        self.assertEqual(len(self.store.collection_events()), 8)

    def test_required_symbol_must_belong_to_ranked_universe(self):
        pipeline, _ = self.create_pipeline()
        with self.assertRaises(DataValidationError):
            self.run_pipeline(pipeline, max_symbols=1, required_symbols=("BTCUSDT",))
        self.assertEqual(
            self.store.candles(exchange="binance", market="linear_perpetual",
                symbol="BTCUSDT", interval="1h",
                start_open_ms=0, end_open_ms=3 * HOUR),
            (),
        )

    def test_missing_middle_candle_cannot_advance_checkpoint(self):
        pipeline, _ = self.create_pipeline(GapTransport())
        with self.assertRaises(DataGapError):
            self.run_pipeline(pipeline, required_symbols=("BTCUSDT",))
        self.assertIsNone(self.store.latest_checkpoint(
            data_type="closed_candle", exchange="binance",
            symbol="BTCUSDT", interval="1h",
        ))
        events = self.store.collection_events()
        self.assertEqual(events[-1].status, "failure")
        self.assertEqual(events[-1].detail, "DataGapError")

    def test_throttle_and_timeout_leave_failed_audit_and_no_checkpoint(self):
        for transport_class in (ThrottleTransport, TimeoutTransport):
            with self.subTest(transport=transport_class.__name__):
                path = Path(self.temp.name) / f"{transport_class.__name__}.sqlite3"
                store = SQLiteMarketDataStore(path)
                clock = lambda: DEMO_CLOCK
                adapter = BinanceFuturesPublicAdapter(
                    transport_class(), clock_ms=clock,
                    initial_backoff_seconds=0,
                )
                pipeline = ReadOnlyCollectionPipeline(
                    adapter, store, clock_ms=clock,
                    mode="offline", source_name="synthetic_fixture",
                )
                with self.assertRaises((DataTimeoutError, DataValidationError)) if transport_class is TimeoutTransport else self.assertRaises(Exception):
                    self.run_pipeline(pipeline, required_symbols=("BTCUSDT",))
                self.assertEqual(store.collection_events()[-1].status, "failure")
                self.assertIsNone(store.latest_checkpoint(
                    data_type="closed_candle", exchange="binance",
                    symbol="BTCUSDT", interval="1h",
                ))

    def test_future_window_or_invalid_limits_do_not_contact_exchange(self):
        pipeline, transport = self.create_pipeline()
        with self.assertRaises(DataValidationError):
            pipeline.run(interval="1h", start_open_ms=0, end_open_ms=8 * HOUR)
        self.assertEqual(transport.requests, [])
        with self.assertRaises(ValueError):
            pipeline.run(interval="1h", start_open_ms=0, end_open_ms=HOUR, max_symbols=51)
        self.assertEqual(transport.requests, [])

    def test_capture_observation_timestamps_follow_response_completion(self):
        class AdvancingClock:
            def __init__(self):
                self.value = DEMO_CLOCK

            def __call__(self):
                self.value += 1
                return self.value

        clock = AdvancingClock()
        pipeline, _ = self.create_pipeline(clock=clock)
        summary = self.run_pipeline(pipeline, required_symbols=("BTCUSDT",))
        self.assertGreater(summary.contracts_observed_at_ms, DEMO_CLOCK)
        self.assertGreater(summary.universe_observed_at_ms, summary.contracts_observed_at_ms)
        events = self.store.collection_events()
        self.assertTrue(all(e.observed_end_ms >= e.observed_start_ms for e in events))
        self.assertEqual(self.store.contracts(
            exchange="binance", market="linear_perpetual",
            observed_at_ms=summary.contracts_observed_at_ms,
        )[0].observed_at_ms, summary.contracts_observed_at_ms)

    def test_empty_universe_is_fatal_with_no_false_candles(self):
        pipeline, transport = self.create_pipeline(
            OfflineFixtureTransport(available_symbols=())
        )
        with self.assertRaises(DataValidationError):
            self.run_pipeline(pipeline)
        self.assertEqual(
            self.store.collection_events()[-1].status,
            "success",
        )
        self.assertFalse(any("klines" in url for url in transport.requests))


class CLITests(unittest.TestCase):
    def test_default_mode_never_opens_a_network_connection(self):
        out = io.StringIO()
        with patch("crypto_intelligence_agent.market_data.urlopen", side_effect=AssertionError("network forbidden")):
            with redirect_stdout(out):
                result = main([])
        self.assertEqual(result, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["audit_events"], 4)
        self.assertTrue(payload["data"]["synthetic"])
        self.assertEqual(payload["database"], "temporary_removed_after_run")

    def test_live_mode_requires_explicit_permission(self):
        with self.assertRaises(SystemExit) as error:
            with redirect_stderr(io.StringIO()):
                main(["--mode", "live"])
        self.assertEqual(error.exception.code, 2)

    def test_live_mode_never_accepts_fixture_directory(self):
        with self.assertRaises(SystemExit) as error:
            with redirect_stderr(io.StringIO()):
                main(["--mode", "live", "--allow-public-network", "--fixture-dir", "tests/fixtures"])
        self.assertEqual(error.exception.code, 2)

    def test_offline_cli_persists_expected_rows_when_path_is_given(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "market.sqlite"
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--database", str(db_path), "--symbols", "BTCUSDT"])
            self.assertEqual(code, 0)
            saved = SQLiteMarketDataStore(db_path)
            self.assertEqual(len(saved.candles(
                exchange="binance", market="linear_perpetual", symbol="BTCUSDT",
                interval="1h", start_open_ms=0, end_open_ms=3 * HOUR,
            )), 3)
            self.assertEqual(len(saved.collection_events()), 3)

    def test_cli_errors_explicitly_for_unranked_symbol_without_network(self):
        output = io.StringIO()
        with redirect_stderr(output):
            code = main(["--symbols", "DOGEUSDT"])
        self.assertEqual(code, 2)
        error = json.loads(output.getvalue())
        self.assertEqual(error["status"], "error")
        self.assertFalse(error["network_enabled"])


if __name__ == "__main__":
    unittest.main()
