"""J1 #245 synthetic multi-page read-only snapshot regression."""
from __future__ import annotations

from dataclasses import replace
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from crypto_intelligence_agent.bybit_research_series import inspect_existing_bybit_research_series
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_bybit_research_storage import sample, START, END, HOUR


class BybitResearchSeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "private.sqlite"
        self.store = SQLiteBybitResearchStore(self.db)
        self.a, self.b, self.manifest = sample()

    def series(self, end=END, cutoff=None):
        return inspect_existing_bybit_research_series(
            self.db, symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=end,
            as_of_ms=(cutoff if cutoff is not None else self.manifest.capture_finished_ms + 1000),
        )

    def test_multiple_pages_one_snapshot_read_only_and_replay(self):
        self.store.commit_raw_pair(instrument_raw=self.a, kline_raw=self.b,
                                   manifest=self.manifest)
        x = sample(offset=3)
        self.store.commit_raw_pair(instrument_raw=x[0], kline_raw=x[1], manifest=x[2])
        before = self.db.read_bytes()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            first = self.series(end=END + 3*HOUR)
            second = self.series(end=END + 3*HOUR)
        self.assertEqual(first, second)
        self.assertEqual(first.page_count, 2)
        self.assertEqual(len(first.candles), 6)
        self.assertEqual(len(first.header_digest_sha256), 64)
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse(first.rights_authorized)
        self.assertFalse(first.source_authenticated)
        self.assertFalse(first.canonical_ohlcv_approved)
        self.assertFalse(first.financial_backtest_approved)
        self.assertFalse(first.orders_sent)

    def test_missing_gap_and_tamper_fail_closed(self):
        with self.assertRaises(DataGapError):
            self.series()
        self.store.commit_raw_pair(instrument_raw=self.a, kline_raw=self.b,
                                   manifest=self.manifest)
        with self.assertRaises(DataGapError):
            self.series(end=END + 3*HOUR)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE bybit_research_candles SET close='999' WHERE open_time_ms=START")
        with self.assertRaises(DataGapError):
            self.series()

    def test_unsupported_schema_and_future_gate(self):
        self.store.commit_raw_pair(instrument_raw=self.a, kline_raw=self.b,
                                   manifest=self.manifest)
        with self.assertRaises(DataValidationError):
            self.series(cutoff=END)
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE VIEW untrusted AS SELECT 1")
        with self.assertRaises(DataValidationError):
            self.series()

    def test_nonexistent_path_does_not_create_file(self):
        other = self.db.parent / "missing.sqlite"
        with self.assertRaises(DataValidationError):
            inspect_existing_bybit_research_series(
                other, symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END, as_of_ms=END+HOUR,
            )
        self.assertFalse(other.exists())


if __name__ == "__main__":
    unittest.main()
