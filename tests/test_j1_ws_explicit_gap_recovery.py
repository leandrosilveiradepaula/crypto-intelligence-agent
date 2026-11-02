"""OPS12: transactional gap markers, no fabricated bars and eventual recovery."""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS, SQLiteOfflineClosedStreamJournal
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_j1_bybit_closed_stream_cache import DECISION, event, scope


class GapRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "separate-ws.sqlite"
        self.db = SQLiteOfflineClosedStreamJournal.create(self.path)
        self.scope = scope()
        self.first = DECISION - 24 * HOUR_MS

    def add(self, offset, *, allow=False):
        return self.db.append(
            event("BTCUSDT", self.first + offset * HOUR_MS, self.scope),
            allow_declared_gap=allow,
        )

    def audit(self, decision=DECISION):
        return self.db.audit(scope=self.scope, decision_at_ms=decision,
                             as_of_ms=decision + 4000)

    def gaps(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT key,value FROM meta WHERE key LIKE 'gap:%'").fetchall()

    def test_default_strict_and_single_gap_replay_idempotence(self):
        self.add(0)
        with self.assertRaises(DataGapError):
            self.add(2)
        self.assertEqual(self.gaps(), [])
        self.assertEqual(self.add(2, allow=True), "appended")
        self.assertEqual(len(self.gaps()), 1)
        self.assertEqual(self.add(2, allow=True), "idempotent")
        self.assertEqual(len(self.gaps()), 1)
        self.assertEqual(self.audit().persisted_rows, 2)
        self.assertIsNone(self.audit().rank_digest_sha256)
        with self.assertRaises(DataGapError):
            self.add(1, allow=True)

    def test_second_gap_requires_separate_marker(self):
        for offset in (0, 2, 4):
            self.add(offset, allow=True)
        self.assertEqual(len(self.gaps()), 2)
        self.assertEqual(self.audit().persisted_rows, 3)
        self.assertIsNone(self.audit().rank_digest_sha256)

    def test_complete_new_window_recovers_without_backfill(self):
        self.add(0)
        self.add(2, allow=True)
        for offset in range(3, 28):
            self.add(offset)
        # Other member absent: no marketwide/sample rank is ever inferred.
        audit = self.audit(decision=self.first + 28 * HOUR_MS)
        self.assertEqual(audit.complete_24h_symbols, 1)
        self.assertEqual(audit.missing_24h_symbols, 1)
        self.assertIsNone(audit.rank_digest_sha256)
        self.assertEqual(audit.persisted_rows, 27)
        self.assertEqual(len(self.gaps()), 1)

    def test_full_two_asset_window_recovers_local_rank_only(self):
        for symbol in ("BTCUSDT", "ETHUSDT"):
            self.assertEqual(self.db.append(event(symbol, self.first, self.scope)), "appended")
            self.assertEqual(self.db.append(
                event(symbol, self.first+2*HOUR_MS, self.scope),
                allow_declared_gap=True,
            ), "appended")
            for offset in range(3, 28):
                self.assertEqual(self.db.append(
                    event(symbol, self.first+offset*HOUR_MS, self.scope)), "appended")
        restored = self.audit(decision=self.first+28*HOUR_MS)
        self.assertEqual(restored.missing_24h_symbols, 0)
        self.assertEqual(restored.complete_24h_symbols, 2)
        self.assertIsNotNone(restored.rank_digest_sha256)
        self.assertEqual(restored.status, "offline_reviewed_24h_complete_not_top50")
        self.assertFalse(restored.sanitized_report()["marketwide_top50_verified"])
        self.assertEqual(len(self.gaps()), 2)

    def test_gap_budget_and_untrusted_boolean(self):
        self.add(0)
        with self.assertRaises(DataGapError):
            self.add(170, allow=True)
        with self.assertRaises(DataValidationError):
            self.db.append(event("BTCUSDT", self.first+2*HOUR_MS, self.scope),
                           allow_declared_gap=1)
        self.assertEqual(self.gaps(), [])

    def test_marker_missing_or_tampered_fails_audit(self):
        self.add(0)
        self.add(2, allow=True)
        key, value = self.gaps()[0]
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM meta WHERE key=?", (key,))
        with self.assertRaises(DataGapError):
            self.audit()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO meta VALUES (?, ?)", (key, value))
        self.assertEqual(self.audit().persisted_rows, 2)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE meta SET value=? WHERE key=?", ('{}', key))
        with self.assertRaises(DataGapError):
            self.audit()

    def test_orphan_marker_rejected(self):
        self.add(0)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO meta VALUES ('gap:BTCUSDT:999', '{}')")
        with self.assertRaises(DataGapError):
            self.audit()

    def test_reject_conflicting_replay_and_registry_drift(self):
        self.add(0)
        self.add(2, allow=True)
        with self.assertRaises(DataGapError):
            self.db.append(event("BTCUSDT", self.first+2*HOUR_MS,
                                 self.scope, turnover="5.5"), allow_declared_gap=True)
        self.assertEqual(len(self.gaps()), 1)
        self.assertEqual(self.audit().persisted_rows, 2)

    def test_no_rest_synthetic_or_trading_flags(self):
        self.add(0)
        self.add(2, allow=True)
        report = self.audit().sanitized_report()
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["source_authenticated"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(report["network_requests"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
