"""Offline WU2 tests for transactional historical replay and data quality."""
from __future__ import annotations

from decimal import Decimal
import tempfile
from pathlib import Path
import unittest

from crypto_intelligence_agent.backfill import HistoricalBackfill
from crypto_intelligence_agent.market_data import (
    ClosedCandle, ContractSpec, DataGapError, DataTimeoutError, DuplicateCandleError, MarketDataCheckpoint,
    UniverseMember, UniverseSnapshot,
)
from crypto_intelligence_agent.storage import SQLiteMarketDataStore


HOUR = 3_600_000


def candle(open_time_ms: int, close: str = "101.25") -> ClosedCandle:
    return ClosedCandle(
        exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h",
        open_time_ms=open_time_ms, close_time_ms=open_time_ms + HOUR - 1,
        open=Decimal("100.10"), high=Decimal("102.00"), low=Decimal("99.90"), close=Decimal(close),
        base_volume=Decimal("10.5"), quote_volume=Decimal("1060.0"), quality="source_closed",
    )


class PagedFixtureSource:
    def __init__(self, candles: list[ClosedCandle], *, fail_at_call: int | None = None) -> None:
        self.candles = candles
        self.fail_at_call = fail_at_call
        self.calls: list[tuple[int | None, int | None, int]] = []

    def closed_candles(self, symbol, interval, *, observed_at_ms, start_time_ms=None, end_time_ms=None, limit=500):
        self.calls.append((start_time_ms, end_time_ms, limit))
        if self.fail_at_call == len(self.calls):
            raise DataTimeoutError("offline simulated timeout")
        return tuple(candle for candle in self.candles if start_time_ms <= candle.open_time_ms <= end_time_ms)


class BackfillStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = SQLiteMarketDataStore(Path(self.directory.name) / "market.sqlite3")
        self.rows = [candle(index * HOUR) for index in range(5)]

    def tearDown(self) -> None:
        self.directory.cleanup()

    def backfill(self, source: PagedFixtureSource, *, end: int = 5 * HOUR):
        return HistoricalBackfill(source, self.store, page_size=2).run(
            exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h",
            start_open_ms=0, end_open_ms=end, observed_at_ms=30 * HOUR, source_name="fixture",
        )

    def test_two_pages_exact_window_decimal_replay_and_quality(self) -> None:
        result = self.backfill(PagedFixtureSource(self.rows))
        self.assertEqual(result.pages_committed, 3)
        persisted = self.store.candles(exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h", start_open_ms=0, end_open_ms=5 * HOUR)
        self.assertEqual(persisted, tuple(self.rows))
        self.assertIsInstance(persisted[0].open, Decimal)
        self.assertEqual(str(persisted[0].quote_volume), "1060.0")
        report = self.store.quality_report(exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h", start_open_ms=0, end_open_ms=5 * HOUR)
        self.assertTrue(report.complete)
        self.assertEqual(report.expected_candles, 5)
        self.assertEqual(report.latest_checkpoint.confirmed_end_ms, 5 * HOUR - 1)

    def test_second_backfill_is_idempotent_and_resumes_from_checkpoint(self) -> None:
        self.backfill(PagedFixtureSource(self.rows))
        repeated = self.backfill(PagedFixtureSource(self.rows))
        self.assertEqual((repeated.pages_committed, repeated.candles_committed), (0, 0))
        persisted = self.store.candles(exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h", start_open_ms=0, end_open_ms=5 * HOUR)
        self.assertEqual(len(persisted), 5)

    def test_api_interruption_keeps_only_prior_atomic_page_and_later_resumes(self) -> None:
        interrupted = PagedFixtureSource(self.rows, fail_at_call=2)
        with self.assertRaises(DataTimeoutError):
            self.backfill(interrupted)
        checkpoint = self.store.latest_checkpoint(data_type="closed_candle", exchange="binance", symbol="BTCUSDT", interval="1h")
        self.assertEqual(checkpoint.confirmed_end_ms, 2 * HOUR - 1)
        self.assertEqual(len(self.store.candles(exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h", start_open_ms=0, end_open_ms=5 * HOUR)), 2)
        resumed = self.backfill(PagedFixtureSource(self.rows))
        self.assertEqual(resumed.pages_committed, 2)
        self.assertEqual(resumed.candles_committed, 3)

    def test_gap_between_pages_does_not_advance_the_failing_page_checkpoint(self) -> None:
        missing = [row for row in self.rows if row.open_time_ms != 2 * HOUR]
        with self.assertRaises(DataGapError):
            self.backfill(PagedFixtureSource(missing))
        checkpoint = self.store.latest_checkpoint(data_type="closed_candle", exchange="binance", symbol="BTCUSDT", interval="1h")
        self.assertEqual(checkpoint.confirmed_end_ms, 2 * HOUR - 1)
        report = self.store.quality_report(exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h", start_open_ms=0, end_open_ms=5 * HOUR)
        self.assertEqual(report.missing_open_times_ms, (2 * HOUR, 3 * HOUR, 4 * HOUR))

    def test_conflicting_duplicate_rolls_back_page_and_checkpoint(self) -> None:
        self.backfill(PagedFixtureSource(self.rows[:2]), end=2 * HOUR)
        conflict = [candle(2 * HOUR, "101.26"), candle(3 * HOUR)]
        # Store a conflicting row directly through a later overlapping page attempt.
        source = PagedFixtureSource([self.rows[0], self.rows[1], candle(2 * HOUR), candle(2 * HOUR, "101.26"), candle(3 * HOUR)])
        with self.assertRaises(DataGapError):
            self.backfill(source, end=4 * HOUR)
        self.assertEqual(len(self.store.candles(exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h", start_open_ms=0, end_open_ms=4 * HOUR)), 2)

    def test_equal_duplicate_is_idempotent_but_conflicting_persisted_duplicate_is_rejected(self) -> None:
        checkpoint = MarketDataCheckpoint("closed_candle", "binance", "BTCUSDT", "1h", 0, HOUR - 1, "fixture", "j1-v1", "complete")
        self.store.commit_candle_page([self.rows[0]], checkpoint)
        self.store.commit_candle_page([self.rows[0]], checkpoint)
        conflicting = candle(0, "101.26")
        with self.assertRaises(DuplicateCandleError):
            self.store.commit_candle_page([conflicting], checkpoint)
        persisted = self.store.candles(exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h", start_open_ms=0, end_open_ms=HOUR)
        self.assertEqual(persisted, (self.rows[0],))

    def test_incomplete_window_is_not_persisted(self) -> None:
        with self.assertRaises(DataGapError):
            self.backfill(PagedFixtureSource(self.rows[:1]), end=2 * HOUR)
        self.assertIsNone(self.store.latest_checkpoint(data_type="closed_candle", exchange="binance", symbol="BTCUSDT", interval="1h"))

    def test_pagination_limit_and_window_alignment_fail_before_collection(self) -> None:
        source = PagedFixtureSource(self.rows)
        with self.assertRaises(ValueError):
            HistoricalBackfill(source, self.store, page_size=0)
        with self.assertRaises(ValueError):
            HistoricalBackfill(source, self.store, page_size=1_501)
        with self.assertRaises(ValueError):
            HistoricalBackfill(source, self.store, page_size=2).run(
                exchange="binance", market="linear_perpetual", symbol="BTCUSDT", interval="1h",
                start_open_ms=1, end_open_ms=HOUR, observed_at_ms=30 * HOUR, source_name="fixture",
            )
        self.assertEqual(source.calls, [])

    def test_snapshot_round_trip_is_decimal_preserving_and_conflict_safe(self) -> None:
        snapshot = UniverseSnapshot(
            observed_at_ms=30 * HOUR, selection_rule_version="j1-v1", source="fixture",
            eligible=(UniverseMember("BTCUSDT", 1, Decimal("123456.789")),), excluded={"OLDUSDT": "not_trading"},
        )
        self.store.save_universe_snapshot(snapshot)
        self.store.save_universe_snapshot(snapshot)
        self.assertEqual(self.store.universe_snapshot(observed_at_ms=30 * HOUR, selection_rule_version="j1-v1", source="fixture"), snapshot)
        conflicting = UniverseSnapshot(30 * HOUR, "j1-v1", (UniverseMember("BTCUSDT", 1, Decimal("1")),), {}, "fixture")
        with self.assertRaises(DuplicateCandleError):
            self.store.save_universe_snapshot(conflicting)

    def test_contract_metadata_round_trip_preserves_decimal_and_observation_timestamp(self) -> None:
        contract = ContractSpec("binance", "linear_perpetual", "BTCUSDT", "BTC", "USDT", "PERPETUAL", "TRADING", 0, Decimal("0.10"), Decimal("0.001"), Decimal("0.001"), Decimal("5"), 30 * HOUR, "fixture")
        self.store.save_contracts([contract])
        self.assertEqual(self.store.contracts(exchange="binance", market="linear_perpetual", observed_at_ms=30 * HOUR), (contract,))


if __name__ == "__main__":
    unittest.main()
