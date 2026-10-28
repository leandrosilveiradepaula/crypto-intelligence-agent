"""J1/WU57 #276: every historical-series page obeys the same strict replay gate.

All data is synthetic; these checks never authenticate a provider, grant
rights, create a canonical feed, or authorize trading.
"""
from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_research_series import (
    inspect_existing_bybit_research_series,
)
from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_bybit_research_storage import END, HOUR, START, sample


class BybitSeriesSharedValidationTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "research.sqlite"
        self.writer = SQLiteBybitResearchStore(self.db)
        self.page1 = sample()
        self.writer.commit_raw_pair(
            instrument_raw=self.page1[0], kline_raw=self.page1[1],
            manifest=self.page1[2],
        )

    def add_second_page(self):
        next_page = sample(offset=3)
        self.writer.commit_raw_pair(
            instrument_raw=next_page[0], kline_raw=next_page[1],
            manifest=next_page[2],
        )

    def read(self, end=END):
        return inspect_existing_bybit_research_series(
            self.db, symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=end,
            as_of_ms=self.page1[2].capture_finished_ms + 10 * HOUR,
        )

    def test_valid_two_page_series_reuses_readonly_validator_without_writer(self):
        self.add_second_page()
        before = self.db.read_bytes()
        with patch.object(
            SQLiteBybitResearchStore, "_transaction",
            side_effect=AssertionError("unexpected write transaction"),
        ):
            first = self.read(end=END + 3 * HOUR)
            second = self.read(end=END + 3 * HOUR)
        self.assertEqual(first, second)
        self.assertEqual(first.page_count, 2)
        self.assertEqual(len(first.candles), 6)
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse(first.rights_authorized)
        self.assertFalse(first.canonical_ohlcv_approved)
        self.assertFalse(first.financial_backtest_approved)
        self.assertFalse(first.orders_sent)

    def test_nonhex_instrument_payload_digest_cannot_be_accepted(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute(
                "UPDATE bybit_research_pages SET instrument_bytes_sha256=?",
                ("this-is-not-a-hash",),
            )
            con.commit()
        with self.assertRaises(DataGapError):
            self.read()
        with self.assertRaises(DataGapError):
            self.writer.quality_report(
                symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END,
            )

    def test_nonhex_second_page_hash_blocks_whole_series(self):
        self.add_second_page()
        with closing(sqlite3.connect(self.db)) as con:
            con.execute(
                "UPDATE bybit_research_pages SET kline_bytes_sha256=? "
                "WHERE start_open_ms=?",
                ("z" * 64, END),
            )
            con.commit()
        with self.assertRaises(DataGapError):
            self.read(end=END + 3 * HOUR)
        # The original first page remains usable as research-only evidence.
        self.assertEqual(len(self.read().candles), 3)

    def test_orphan_candle_outside_requested_page_fails_closed(self):
        with closing(sqlite3.connect(self.db)) as con:
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute(
                """INSERT INTO bybit_research_candles
                   (page_id,open_time_ms,close_time_ms,open,high,low,close,
                    documented_base_volume,documented_quote_turnover)
                   SELECT 999,open_time_ms,close_time_ms,open,high,low,close,
                          documented_base_volume,documented_quote_turnover
                   FROM bybit_research_candles LIMIT 1"""
            )
            con.commit()
        with self.assertRaises(DataValidationError):
            self.read()

    def test_single_wal_read_snapshot_survives_second_page_tamper_midread(self):
        self.add_second_page()
        with closing(sqlite3.connect(self.db)) as con:
            self.assertEqual(
                con.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal",
            )
        original = SQLiteBybitResearchStore._read_rows
        triggered = []
        errors = []

        def read_hook(con, page_id):
            rows = original(con, page_id)
            if not triggered:
                triggered.append(True)
                def mutate_second_page():
                    try:
                        with closing(sqlite3.connect(self.db)) as writer:
                            writer.execute(
                                "UPDATE bybit_research_candles "
                                "SET documented_quote_turnover='999' "
                                "WHERE open_time_ms=?",
                                (END,),
                            )
                            writer.commit()
                    except Exception as error:
                        errors.append(type(error).__name__)
                worker = Thread(target=mutate_second_page, daemon=True)
                worker.start()
                worker.join(timeout=5)
                if worker.is_alive():
                    raise AssertionError("WAL writer blocked inside read snapshot")
            return rows

        with patch.object(
            SQLiteBybitResearchStore, "_read_rows", side_effect=read_hook,
        ):
            old = self.read(end=END + 3 * HOUR)
        self.assertEqual(triggered, [True])
        self.assertEqual(errors, [])
        self.assertEqual(len(old.candles), 6)
        self.assertFalse(old.source_authenticated)
        with self.assertRaises(DataGapError):
            self.read(end=END + 3 * HOUR)


if __name__ == "__main__":
    unittest.main()
