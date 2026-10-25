"""Regression tests for WU2 checkpoint continuity and immutable source snapshots.

All cases are local and offline: failures must be explicit, never silently
turning partial market history into a falsely complete backtest input.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from crypto_intelligence_agent.backfill import HistoricalBackfill
from crypto_intelligence_agent.market_data import (
    ClosedCandle, ContractSpec, DataGapError, DuplicateCandleError,
    MarketDataCheckpoint,
)
from crypto_intelligence_agent.storage import SQLiteMarketDataStore

HOUR = 3_600_000


def candle(open_ms: int, *, market: str = "linear_perpetual") -> ClosedCandle:
    return ClosedCandle(
        exchange="binance", market=market, symbol="BTCUSDT", interval="1h",
        open_time_ms=open_ms, close_time_ms=open_ms + HOUR - 1,
        open=Decimal("100.10"), high=Decimal("103"), low=Decimal("99"),
        close=Decimal("101"), base_volume=Decimal("8.0"),
        quote_volume=Decimal("840.0"), quality="source_closed",
    )


def contract(*, tick: str = "0.10", symbol: str = "BTCUSDT") -> ContractSpec:
    return ContractSpec(
        "binance", "linear_perpetual", symbol, "BTC", "USDT", "PERPETUAL",
        "TRADING", 0, Decimal(tick), Decimal("0.001"), Decimal("0.001"),
        Decimal("5"), 10 * HOUR, "fixture",
    )


class WindowSource:
    def __init__(self, candles):
        self.data = candles
        self.calls = []

    def closed_candles(self, symbol, interval, *, observed_at_ms, start_time_ms=None, end_time_ms=None, limit=500):
        self.calls.append((start_time_ms, end_time_ms))
        return tuple(c for c in self.data if start_time_ms <= c.open_time_ms <= end_time_ms)


class PersistenceInvariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "db.sqlite"
        self.store = SQLiteMarketDataStore(self.path)
        self.rows = [candle(x * HOUR) for x in range(8)]

    def tearDown(self):
        self.tmp.cleanup()

    def run_backfill(self, source, *, start=0, end=8 * HOUR, src="fixture", version="j1-wu2-v1"):
        return HistoricalBackfill(source, self.store, page_size=2, contract_version=version).run(
            exchange="binance", market="linear_perpetual", symbol="BTCUSDT",
            interval="1h", start_open_ms=start, end_open_ms=end,
            observed_at_ms=10 * HOUR, source_name=src,
        )

    def test_backdated_window_never_silently_skips_uncollected_prefix(self):
        self.run_backfill(WindowSource(self.rows), start=2 * HOUR, end=4 * HOUR)
        request = WindowSource(self.rows)
        with self.assertRaises(DataGapError):
            self.run_backfill(request, start=0, end=4 * HOUR)
        self.assertEqual(request.calls, [])

    def test_disjoint_future_window_rejected_instead_of_false_contiguous_checkpoint(self):
        self.run_backfill(WindowSource(self.rows), end=2 * HOUR)
        request = WindowSource(self.rows)
        with self.assertRaises(DataGapError):
            self.run_backfill(request, start=4 * HOUR, end=6 * HOUR)
        self.assertEqual(request.calls, [])

    def test_missing_cached_prefix_cannot_be_skipped_by_high_checkpoint(self):
        self.run_backfill(WindowSource(self.rows), end=6 * HOUR)
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM candles WHERE open_time_ms=?", (2 * HOUR,))
        request = WindowSource(self.rows)
        with self.assertRaises(DataGapError):
            self.run_backfill(request, end=8 * HOUR)
        self.assertEqual(request.calls, [])
        checkpoint = self.store.latest_checkpoint(
            data_type="closed_candle", exchange="binance", symbol="BTCUSDT", interval="1h",
        )
        self.assertEqual(checkpoint.confirmed_end_ms, 6 * HOUR - 1)

    def test_existing_checkpoint_cannot_be_relabelled_as_other_source(self):
        self.run_backfill(WindowSource(self.rows), end=2 * HOUR)
        request = WindowSource(self.rows)
        with self.assertRaises(DataGapError):
            self.run_backfill(request, end=4 * HOUR, src="other-source")
        self.assertEqual(request.calls, [])

    def test_existing_checkpoint_cannot_be_relabelled_as_other_version(self):
        self.run_backfill(WindowSource(self.rows), end=2 * HOUR)
        request = WindowSource(self.rows)
        with self.assertRaises(DataGapError):
            self.run_backfill(request, end=4 * HOUR, version="other-contract")
        self.assertEqual(request.calls, [])

    def test_direct_write_with_gap_rolls_back_entire_page_and_checkpoint(self):
        rows = (self.rows[0], self.rows[2])
        cp = MarketDataCheckpoint("closed_candle", "binance", "BTCUSDT", "1h",
                                  0, 3 * HOUR - 1, "fixture", "j1-wu2-v1", "complete")
        with self.assertRaises(DataGapError):
            self.store.commit_candle_page(rows, cp)
        self.assertIsNone(self.store.latest_checkpoint(
            data_type="closed_candle", exchange="binance", symbol="BTCUSDT", interval="1h",
        ))
        self.assertEqual(self.store.candles(
            exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h",
            start_open_ms=0, end_open_ms=4 * HOUR,
        ), ())

    def test_direct_write_rejects_mismatched_identity_on_second_row(self):
        rows = (self.rows[0], replace(self.rows[1], market="other_market"))
        cp = MarketDataCheckpoint("closed_candle", "binance", "BTCUSDT", "1h",
                                  0, 2 * HOUR - 1, "fixture", "j1-wu2-v1", "complete")
        with self.assertRaises(DataGapError):
            self.store.commit_candle_page(rows, cp)

    def test_direct_write_rejects_invalid_ohlc_before_checkpoint(self):
        damaged = replace(self.rows[0], high=Decimal("90"))
        cp = MarketDataCheckpoint("closed_candle", "binance", "BTCUSDT", "1h",
                                  0, HOUR - 1, "fixture", "j1-wu2-v1", "complete")
        with self.assertRaises(DataGapError):
            self.store.commit_candle_page([damaged], cp)

    def test_contract_same_timestamp_conflict_fails_without_overwrite(self):
        original = contract()
        self.store.save_contracts([original])
        with self.assertRaises(DuplicateCandleError):
            self.store.save_contracts([contract(tick="0.50")])
        self.assertEqual(self.store.contracts(
            exchange="binance", market="linear_perpetual", observed_at_ms=10 * HOUR,
        ), (original,))

    def test_contract_batch_conflict_rolls_back_other_new_rows(self):
        original = contract()
        self.store.save_contracts([original])
        with self.assertRaises(DuplicateCandleError):
            self.store.save_contracts([contract(symbol="ETHUSDT"), contract(tick="0.50")])
        self.assertEqual(self.store.contracts(
            exchange="binance", market="linear_perpetual", observed_at_ms=10 * HOUR,
        ), (original,))

    def test_memory_path_is_not_silently_accepted_without_persistent_connection(self):
        with self.assertRaises(ValueError):
            SQLiteMarketDataStore(":memory:")

    def test_resume_at_page_boundary_preserves_checkpoint_start(self):
        self.run_backfill(WindowSource(self.rows), end=2 * HOUR)
        continued = self.run_backfill(WindowSource(self.rows), start=2 * HOUR, end=4 * HOUR)
        self.assertEqual(continued.checkpoint.confirmed_start_ms, 0)
        self.assertEqual(continued.checkpoint.confirmed_end_ms, 4 * HOUR - 1)
        replay = self.run_backfill(WindowSource(self.rows), start=0, end=4 * HOUR)
        self.assertEqual(replay.pages_committed, 0)

    def test_monday_weekly_candles_backfill_and_quality(self):
        week = 7 * 86_400_000
        monday = 4 * 86_400_000
        rows = [replace(candle(monday + index * week), interval="1w",
                        close_time_ms=monday + (index + 1) * week - 1)
                for index in range(2)]
        result = HistoricalBackfill(WindowSource(rows), self.store, page_size=1).run(
            exchange="binance", market="linear_perpetual", symbol="BTCUSDT",
            interval="1w", start_open_ms=monday, end_open_ms=monday + 2 * week,
            observed_at_ms=monday + 3 * week, source_name="fixture",
        )
        self.assertEqual(result.candles_committed, 2)
        report = self.store.quality_report(
            exchange="binance", market="linear_perpetual", symbol="BTCUSDT",
            interval="1w", start_open_ms=monday, end_open_ms=monday + 2 * week,
        )
        self.assertTrue(report.complete)


if __name__ == "__main__":
    unittest.main()
