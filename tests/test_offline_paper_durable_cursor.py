"""J6/PRE2-B: offline crash-safe cursor and PAPER reservation regression."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.offline_paper_durable_cursor import (
    recover_durable_offline_paper, step_durable_offline_paper,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import SHORT_ROWS, candles, config

D = Decimal


class DurableCursorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "orders.sqlite"
        self.positions_path = Path(tmp.name) / "positions.sqlite"
        self.journal = SQLitePaperOrderJournal(self.db)
        self.positions = SQLitePaperPositionJournal(self.positions_path)
        self.rows = candles(n=10)

    def args(self, rows, **overrides):
        now = rows[-1].close_time_ms + 1_000
        kw = dict(
            strategy=config().strategy,
            venue=PaperVenue.BINANCE_USDM,
            requested_units=D(2),
            limits=limits(),
            observation=observation(now),
            journal=self.journal,
            position_journal_path=self.positions_path,
            decision_at_ms=now,
            max_candles=20,
        )
        kw.update(overrides)
        return kw

    def step(self, n, rows=None, **overrides):
        cs = (self.rows if rows is None else rows)[:n]
        return step_durable_offline_paper(cs, **self.args(cs, **overrides))

    def recover(self, n, rows=None, **overrides):
        cs = (self.rows if rows is None else rows)[:n]
        args = self.args(cs, **overrides)
        args.pop("observation")
        args.pop("position_journal_path")
        args.pop("decision_at_ms")
        return recover_durable_offline_paper(cs, **args)

    def counts(self):
        with closing(sqlite3.connect(self.db)) as conn:
            return (
                conn.execute("SELECT COUNT(*) FROM paper_order_intents").fetchone()[0],
                conn.execute("SELECT COUNT(*) FROM paper_order_meta").fetchone()[0],
            )

    def test_bootstrap_no_signal_then_pending_open_and_restart(self):
        a = self.step(5)
        self.assertFalse(a.opening.paper_intent_reserved)
        self.assertEqual(self.counts(), (0, 2))
        self.assertEqual(a.seal, self.recover(5))
        b = self.step(6)
        self.assertTrue(b.opening.paper_intent_reserved)
        self.assertEqual(b.sequence_number, 2)
        self.assertEqual(self.counts(), (1, 2))
        self.assertEqual(b.seal, self.recover(6))
        c = self.step(7)
        self.assertFalse(c.opening.paper_intent_reserved)
        self.assertEqual(c.sequence_number, 3)
        self.assertEqual(self.counts(), (1, 2))
        for value in (a, b, c):
            self.assertFalse(value.orders_sent)
            self.assertFalse(value.order_submission_enabled)
            self.assertFalse(value.approved_for_live_use)
            self.assertFalse(value.market_data_verified)
            self.assertFalse(value.cross_database_atomic_snapshot_available)

    def test_short_paper_signal_is_pending_only(self):
        short = candles(n=6, source=SHORT_ROWS)
        self.step(5, rows=short)
        item = self.step(6, rows=short)
        self.assertTrue(item.opening.paper_intent_reserved)
        self.assertEqual(item.opening.candidate.side.value, "SHORT")
        self.assertEqual(self.counts(), (1, 2))

    def test_replay_rollback_jump_and_tampered_prefix_refused(self):
        self.step(5)
        for n in (4, 5, 7):
            with self.subTest(n=n), self.assertRaises(DataValidationError):
                self.step(n)
        edited = list(self.rows)
        edited[0] = replace(edited[0], open=D("100.0"))
        with self.assertRaises(DataValidationError):
            self.step(6, rows=edited)
        with self.assertRaises(DataValidationError):
            self.recover(5, rows=edited)
        self.assertEqual(self.counts(), (0, 2))
        self.step(6)

    def test_context_venue_and_lot_mutation_refused(self):
        self.step(5)
        for kw in (
            {"requested_units": D("2.0")},
            {"venue": PaperVenue.BYBIT_V5},
            {"strategy": replace(config().strategy, min_quote_volume_ratio=D("9"))},
            {"limits": replace(limits(), max_market_age_ms=limits().max_market_age_ms+1)},
        ):
            with self.subTest(kw=kw), self.assertRaises(DataValidationError):
                self.step(6, **kw)
        self.assertEqual(self.counts(), (0, 2))

    def test_fault_before_cursor_or_after_cursor_rolls_back_open(self):
        self.step(5)
        for fault in ("after_reservation_before_cursor", "after_cursor_before_commit"):
            with self.subTest(fault=fault):
                with self.assertRaises(RuntimeError):
                    self.step(6, fault_at=fault)
                self.assertEqual(self.counts(), (0, 2))
                self.assertEqual(self.recover(5).candle_count, 5)
        self.step(6)
        self.assertEqual(self.counts(), (1, 2))

    def test_fault_on_bootstrap_rolls_back_cursor(self):
        with self.assertRaises(RuntimeError):
            self.step(5, fault_at="after_cursor_before_commit")
        self.assertEqual(self.counts(), (0, 1))
        self.step(5)
        self.assertEqual(self.counts(), (0, 2))

    def test_two_instances_cannot_reserve_duplicate_open(self):
        self.step(5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(self.step, 6) for _ in range(2)]
            outcomes = []
            for job in jobs:
                try:
                    outcomes.append(job.result())
                except DataValidationError:
                    pass
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].opening.paper_intent_reserved)
        self.assertEqual(self.counts(), (1, 2))

    def test_legacy_open_without_cursor_cannot_bootstrap(self):
        from test_paper_order_store import make_intent
        self.journal.reserve(make_intent())
        with self.assertRaises(DataValidationError):
            self.step(5)
        self.assertEqual(self.counts(), (1, 1))

    def test_cursor_tamper_and_unknown_meta_block_recovery(self):
        self.step(5)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "UPDATE paper_order_meta SET value='{}' "
                "WHERE key='offline_paper_forward_cursor_v1'"
            )
            conn.commit()
        with self.assertRaises(DataValidationError):
            self.recover(5)
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.db)

    def test_real_process_termination_before_commit_rolls_back_cursor_and_open(self):
        self.step(5)
        # Terminate an actual child process AFTER both SQLite writes but BEFORE
        # AUTO2's context manager commits. Neither operation may survive.
        code = """
import os, sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path.cwd() / "tests"))
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import candles, config
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
import crypto_intelligence_agent.offline_paper_durable_cursor as cursor
db, positions = Path(sys.argv[1]), Path(sys.argv[2])
journal = SQLitePaperOrderJournal(db)
rows = candles(n=6)
now = rows[-1].close_time_ms + 1000
original = cursor._write_cursor
def kill_after_write(conn, new_cursor):
    original(conn, new_cursor)
    os._exit(73)
cursor._write_cursor = kill_after_write
cursor.step_durable_offline_paper(
    rows, strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
    requested_units=Decimal(2), limits=limits(),
    observation=observation(now), journal=journal,
    position_journal_path=positions, decision_at_ms=now, max_candles=20,
)
"""
        completed = subprocess.run(
            [sys.executable, "-c", code, str(self.db), str(self.positions_path)],
            cwd=Path(__file__).resolve().parent.parent, capture_output=True,
            text=True, timeout=20, check=False,
        )
        self.assertEqual(completed.returncode, 73, completed.stderr)
        self.assertEqual(self.counts(), (0, 2))
        self.assertEqual(self.recover(5).candle_count, 5)
        self.assertTrue(self.step(6).opening.paper_intent_reserved)
        self.assertEqual(self.counts(), (1, 2))

    def test_crash_after_commit_keeps_one_open_and_recoverable_cursor(self):
        self.step(5)
        # The process exits without graceful teardown AFTER the AUTO2 context
        # manager committed. Replay must be refused, not duplicated.
        code = """
import os, sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path.cwd() / "tests"))
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import candles, config
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from crypto_intelligence_agent.offline_paper_durable_cursor import step_durable_offline_paper
rows = candles(n=6)
now = rows[-1].close_time_ms + 1000
step_durable_offline_paper(
    rows, strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
    requested_units=Decimal(2), limits=limits(), observation=observation(now),
    journal=SQLitePaperOrderJournal(Path(sys.argv[1])),
    position_journal_path=Path(sys.argv[2]), decision_at_ms=now,
    max_candles=20,
)
os._exit(74)
"""
        completed = subprocess.run(
            [sys.executable, "-c", code, str(self.db), str(self.positions_path)],
            cwd=Path(__file__).resolve().parent.parent, capture_output=True,
            text=True, timeout=20, check=False,
        )
        self.assertEqual(completed.returncode, 74, completed.stderr)
        self.assertEqual(self.counts(), (1, 2))
        self.assertEqual(self.recover(6).candle_count, 6)
        with self.assertRaises(DataValidationError):
            self.step(6)
        self.assertFalse(self.step(7).opening.paper_intent_reserved)
        self.assertEqual(self.counts(), (1, 2))

    def test_sqlite_busy_does_not_advance_cursor_or_open(self):
        self.step(5)
        with closing(sqlite3.connect(self.db, timeout=1)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.step(6)
            blocker.rollback()
        self.assertEqual(self.recover(5).candle_count, 5)
        self.assertEqual(self.counts(), (0, 2))
        self.assertTrue(self.step(6).opening.paper_intent_reserved)

    def test_open_inventory_tampering_fails_closed_after_restart(self):
        self.step(5)
        self.step(6)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("DELETE FROM paper_order_intents")
            conn.commit()
        with self.assertRaisesRegex(DataValidationError, "diverged"):
            self.recover(6)
        with self.assertRaisesRegex(DataValidationError, "diverged"):
            self.step(7)

    def test_unknown_metadata_key_blocks_after_restart(self):
        self.step(5)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO paper_order_meta(key,value) VALUES('unexpected','x')"
            )
            conn.commit()
        with self.assertRaises(DataValidationError):
            self.recover(5)
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.db)

    def test_sqlite_corruption_is_not_silent_recovery(self):
        self.step(5)
        # Delete the order file bytes only in a disposable test fixture.
        self.db.write_bytes(b"not-a-sqlite-journal")
        with self.assertRaises(sqlite3.DatabaseError):
            self.recover(5)
        with self.assertRaises(sqlite3.DatabaseError):
            self.step(6)

    def test_no_network_and_recovery_does_not_reserve(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                self.step(5)
                self.recover(5)
        self.assertEqual(self.counts(), (0, 2))


if __name__ == "__main__":
    unittest.main()
