"""J1/WU56 #274: single-snapshot, read-only Bybit research quality regressions.

Only synthetic fixture bytes; no market feed, credentials, approved rights,
canonical OHLCV, trading or production. WAL tests prove *local* consistency.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_research_storage import (
    SQLiteBybitResearchStore, _digest,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_bybit_research_storage import END, HOUR, START, sample


class BybitQualityReadOnlySnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "research.sqlite"
        self.store = SQLiteBybitResearchStore(self.db)

    def stage(self, offset=0):
        a, b, manifest = sample(offset=offset)
        return self.store.commit_raw_pair(
            instrument_raw=a, kline_raw=b, manifest=manifest,
        )

    def report(self, end=END):
        return self.store.quality_report(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=end,
        )

    def test_quality_and_replay_never_enter_writer_transaction(self):
        self.stage()
        before = self.db.read_bytes()
        with patch.object(
            self.store, "_transaction",
            side_effect=AssertionError("write transaction entered"),
        ):
            quality = self.report()
            replay = self.store.replay_page(
                symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END,
            )
        self.assertEqual(quality.persisted_candles, 3)
        self.assertTrue(quality.complete_for_offline_staging_only)
        self.assertEqual(len(replay.candles), 3)
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse(replay.rights_authorized)
        self.assertFalse(replay.canonical_ohlcv_approved)

    def test_wal_writer_can_commit_while_snapshot_stays_at_first_page(self):
        self.stage()
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("PRAGMA journal_mode=WAL").fetchone()[0],
                "wal",
            )
        original = SQLiteBybitResearchStore._read_rows
        committed = []
        failures = []
        seen = set()

        def intercept(connection, page_id):
            rows = original(connection, page_id)
            if page_id not in seen:
                seen.add(page_id)
                if len(seen) == 1:
                    def append_page():
                        try:
                            self.stage(offset=3)
                            committed.append(True)
                        except Exception as exc:
                            failures.append(type(exc).__name__)
                    worker = Thread(target=append_page, daemon=True)
                    worker.start()
                    worker.join(timeout=5)
                    if worker.is_alive():
                        raise AssertionError("reader blocked WAL research writer")
            return rows

        with patch.object(SQLiteBybitResearchStore, "_read_rows", side_effect=intercept):
            old = self.report(end=END + 3 * HOUR)
        self.assertEqual(failures, [])
        self.assertEqual(committed, [True])
        self.assertEqual(old.expected_candles, 6)
        self.assertEqual(old.persisted_candles, 3)
        self.assertEqual(old.missing_open_times_ms,
                         (END, END + HOUR, END + 2 * HOUR))
        new = self.report(end=END + 3 * HOUR)
        self.assertEqual(new.persisted_candles, 6)
        self.assertTrue(new.complete_for_offline_staging_only)

    def test_new_missing_and_unrecognized_database_never_created_or_accepted(self):
        self.stage()
        missing = self.db.parent / "missing.sqlite"
        self.store._path = str(missing)
        with self.assertRaises(DataValidationError):
            self.report()
        self.assertFalse(missing.exists())
        self.store._path = str(self.db)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("CREATE VIEW dangerous_view AS SELECT 1")
            conn.commit()
        with self.assertRaises(DataValidationError):
            self.report()
        with self.assertRaises(DataValidationError):
            self.store.replay_page(
                symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END,
            )

    def test_orphaned_candles_reject_entire_quality_report(self):
        self.stage()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(
                """INSERT INTO bybit_research_candles
                   (page_id,open_time_ms,close_time_ms,open,high,low,close,
                    documented_base_volume,documented_quote_turnover)
                   SELECT 999,open_time_ms,close_time_ms,open,high,low,close,
                          documented_base_volume,documented_quote_turnover
                   FROM bybit_research_candles LIMIT 1"""
            )
            conn.commit()
        with self.assertRaises(DataValidationError):
            self.report()

    def test_recomputed_digest_does_not_hide_corrupt_economic_value(self):
        self.stage()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "UPDATE bybit_research_candles SET close='NaN' WHERE open_time_ms=?",
                (START,),
            )
            rows = tuple(tuple(row) for row in conn.execute(
                """SELECT open_time_ms,close_time_ms,open,high,low,close,
                          documented_base_volume,documented_quote_turnover
                   FROM bybit_research_candles ORDER BY open_time_ms"""
            ).fetchall())
            conn.execute(
                "UPDATE bybit_research_pages SET content_sha256=?",
                (_digest(rows),),
            )
            conn.commit()
        with self.assertRaises(DataGapError):
            self.report()
        with self.assertRaises(DataGapError):
            self.store.replay_page(
                symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END,
            )

    def test_second_page_corruption_rejects_whole_quality_decision(self):
        self.stage()
        self.stage(offset=3)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "UPDATE bybit_research_candles SET close='NaN' WHERE open_time_ms=?",
                (END,),
            )
            conn.commit()
        with self.assertRaises(DataGapError):
            self.report(end=END + 3 * HOUR)
        # First complete page must remain independently replayable.
        self.assertEqual(
            len(self.store.replay_page(
                symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END,
            ).candles), 3,
        )


if __name__ == "__main__":
    unittest.main()
