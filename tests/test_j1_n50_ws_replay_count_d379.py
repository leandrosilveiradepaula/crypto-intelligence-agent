"""Offline-only count audit regression: no private owner files or network."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import json
import sqlite3
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS, SQLiteOfflineClosedStreamJournal
from scripts.audit_j1_n50_ws_replay_count_d379_once import count_only_hours, main
from test_j1_bybit_closed_stream_cache import DECISION, event, scope

class ReplayCountAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ws-confirmed.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.path)
        self.end = DECISION

    def test_empty_and_partial_are_counts_not_pit(self):
        initial = count_only_hours(self.path, end_ms=self.end)
        self.assertEqual([h["persisted_rows"] for h in initial["hours"]], [0, 0])
        self.assertEqual(initial["status"], "count_only_not_content_verified")
        s = scope()
        self.assertEqual(self.journal.append(event("BTCUSDT", self.end-HOUR_MS, s)), "appended")
        result = count_only_hours(self.path, end_ms=self.end)
        self.assertEqual([h["persisted_rows"] for h in result["hours"]], [0, 1])
        self.assertTrue(result["sqlite_integrity_ok"])
        self.assertFalse(result["database_modified"])
        self.assertFalse(result["orders_sent"])
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn("turnover", json.dumps(result))
        self.assertEqual(count_only_hours(self.path, end_ms=self.end), result)

    def test_real_financial_revision_still_fails_closed(self):
        s=scope()
        self.journal.append(event("BTCUSDT", self.end-HOUR_MS, s))
        from crypto_intelligence_agent.market_data import DataGapError
        with self.assertRaises(DataGapError):
            self.journal.append(event("BTCUSDT", self.end-HOUR_MS, s, turnover="99"))
        self.assertEqual(count_only_hours(self.path, end_ms=self.end)["hours"][1]["persisted_rows"],1)

    def test_bad_path_schema_or_hour_rejected_without_repair(self):
        with self.assertRaises(ValueError):
            count_only_hours(self.path, end_ms=self.end+1)
        with self.assertRaises(ValueError):
            count_only_hours(Path(self.temp.name)/"missing.sqlite", end_ms=self.end)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE VIEW unauthorized_view AS SELECT 1")
        with self.assertRaises(ValueError):
            count_only_hours(self.path, end_ms=self.end)

    def test_cli_rejects_without_owner_optin_and_never_reads(self):
        with mock.patch("scripts.audit_j1_n50_ws_replay_count_d379_once.load_active_n50_ws_epoch",
                        side_effect=AssertionError("no private access")):
            from io import StringIO
            from contextlib import redirect_stdout
            out=StringIO()
            with redirect_stdout(out):
                rc=main(["--closed-hour-end-ms",str(self.end)])
            self.assertEqual(rc,65)
            self.assertEqual(json.loads(out.getvalue())["status"],"owner_audit_unavailable")

if __name__=="__main__":
    unittest.main()
