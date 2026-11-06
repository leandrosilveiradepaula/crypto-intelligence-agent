"""J1 local health: SQLite fixture and fail-closed adversarial tests, no network."""
from __future__ import annotations

from contextlib import closing, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from crypto_intelligence_agent.j1_local_health import HOUR_MS as H, audit_local_sqlite_health
from scripts.j1_local_health import main

DECISION = 5000 * H + 120000
END = 5000 * H
START = END - 24 * H


class LocalHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "market.sqlite"
        with closing(sqlite3.connect(self.db)) as c, c:
            c.executescript("""
            CREATE TABLE candles (
                exchange TEXT,market TEXT,symbol TEXT,interval TEXT,
                open_time_ms INTEGER,close_time_ms INTEGER,quality TEXT,
                PRIMARY KEY(exchange,market,symbol,interval,open_time_ms));
            CREATE TABLE checkpoints (
                data_type TEXT,exchange TEXT,symbol TEXT,interval TEXT,
                confirmed_start_ms INTEGER,confirmed_end_ms INTEGER,integrity TEXT);
            CREATE TABLE universe_snapshots (
                observed_at_ms INTEGER,selection_rule_version TEXT,source TEXT,
                eligible_json TEXT,excluded_json TEXT,
                PRIMARY KEY(observed_at_ms,selection_rule_version,source));
            CREATE TABLE collection_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT,mode TEXT,observed_end_ms INTEGER,status TEXT);
            """)
            self.add_snapshot(c)
            for symbol in ("BTCUSDT", "ETHUSDT"):
                c.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?)",
                    [("bybit","linear_perpetual",symbol,"1h",t,t+H-1,"source_closed")
                     for t in range(START,END,H)])
                c.execute("INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?)",
                    ("closed_candle","bybit",symbol,"1h",START,END-1,"complete"))
            c.execute("INSERT INTO collection_events(exchange,mode,observed_end_ms,status) VALUES (?,?,?,?)",
                      ("bybit","live",DECISION-20000,"success"))

    def tearDown(self):
        self.temp.cleanup()

    def add_snapshot(self,c,source="fixture",members=None,observed=DECISION-H):
        if members is None:
            members=[dict(symbol="BTCUSDT",rank=1,quote_volume="12.1"),
                     dict(symbol="ETHUSDT",rank=2,quote_volume="10")]
        c.execute("INSERT INTO universe_snapshots VALUES (?,?,?,?,?)",
                  (observed,"j1-v1",source,json.dumps(members),"{}"))

    def audit(self,**options):
        args=dict(db_path=self.db,decision_at_ms=DECISION,exchange="bybit")
        args.update(options)
        return audit_local_sqlite_health(**args)

    def test_complete_window_is_only_unverified_sample(self):
        r=self.audit()
        self.assertEqual(r["status"],"sample_window_complete_unverified")
        self.assertEqual((r["selected_members"],r["complete_24h_members"],r["observed_candles"]),(2,2,48))
        self.assertEqual(r["last_live_collection_age_ms"],20000)
        for k in ("sample_identity_authenticated","marketwide_top50_verified",
                  "canonical_ohlcv_approved","continuous_collector_verified",
                  "live_trading_authorized","orders_sent"):
            self.assertIs(r[k],False)
        self.assertNotIn("BTCUSDT",json.dumps(r))

    def test_no_new_db_and_no_writes(self):
        missing=self.db.parent/"missing.sqlite"
        self.assertEqual(self.audit(db_path=missing)["status"],"database_unavailable")
        self.assertFalse(missing.exists())
        before=self.db.read_bytes()
        self.audit()
        self.assertEqual(self.db.read_bytes(),before)

    def test_stale_or_ambiguous_pit(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            self.add_snapshot(c,source="second")
        self.assertEqual(self.audit()["status"],"snapshot_ambiguous")
        self.assertEqual(self.audit(snapshot_source="fixture")["complete_24h_members"],2)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("DELETE FROM universe_snapshots WHERE source='second'")
            c.execute("UPDATE universe_snapshots SET observed_at_ms=?",(DECISION-3*H,))
        self.assertEqual(self.audit()["status"],"snapshot_stale")

    def test_missing_and_bad_candle(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("DELETE FROM candles WHERE symbol='BTCUSDT' AND open_time_ms=?",(START+H,))
        r=self.audit()
        self.assertEqual(r["status"],"sample_window_incomplete")
        self.assertEqual(r["complete_24h_members"],1)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("UPDATE candles SET close_time_ms=? WHERE symbol='ETHUSDT' AND open_time_ms=?",
                      (START,START))
        self.assertEqual(self.audit()["status"],"candle_window_invalid")

    def test_checkpoint_boundaries_and_current_open_hour(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("UPDATE checkpoints SET confirmed_end_ms=? WHERE symbol='BTCUSDT'",(END-1-H,))
        self.assertEqual(self.audit()["complete_24h_members"],1)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("DELETE FROM candles WHERE symbol='ETHUSDT' AND open_time_ms=?",(END-H,))
            c.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?)",
                      ("bybit","linear_perpetual","ETHUSDT","1h",END,END+H-1,"source_closed"))
        self.assertEqual(self.audit()["complete_24h_members"],0)

    def test_snapshot_bad_rank_duplicates_nan_float_and_json_duplicate(self):
        bad=[
            "null",
            '[{"symbol":"BTCUSDT","rank":1,"rank":1,"quote_volume":"1"}]',
            json.dumps([dict(symbol="BTCUSDT",rank=2,quote_volume="1")]),
            json.dumps([dict(symbol="BTCUSDT",rank=1,quote_volume="NaN")]),
            json.dumps([dict(symbol="BTCUSDT",rank=1,quote_volume=1.25)]),
            json.dumps([dict(symbol="BTCUSDT",rank=1,quote_volume="1"),
                        dict(symbol="BTCUSDT",rank=2,quote_volume="2")])
        ]
        for raw in bad:
            with self.subTest(raw=raw):
                with closing(sqlite3.connect(self.db)) as c, c:
                    c.execute("UPDATE universe_snapshots SET eligible_json=?",(raw,))
                self.assertEqual(self.audit()["status"],"snapshot_invalid")

    def test_invalid_scope_rejected_and_market_isolation(self):
        self.assertEqual(self.audit(exchange="binance")["complete_24h_members"],0)
        for options in (dict(decision_at_ms=True),dict(exchange="../unsafe"),
                        dict(max_snapshot_age_ms=0)):
            with self.assertRaises(ValueError):
                self.audit(**options)

    def test_cli_nonroot_gate_and_sanitized_config_error(self):
        buf=StringIO()
        fake=SimpleNamespace(name="posix",geteuid=lambda:0)
        with patch("scripts.j1_local_health.os",fake), \
             patch("scripts.j1_local_health.audit_local_sqlite_health",side_effect=AssertionError), \
             redirect_stdout(buf):
            result=main(["--db",str(self.db),"--exchange","bybit"])
        self.assertEqual(result,2)
        self.assertEqual(json.loads(buf.getvalue())["status"],"nonroot_required")
        buf=StringIO()
        fake=SimpleNamespace(name="posix",geteuid=lambda:1000)
        with patch("scripts.j1_local_health.os",fake),redirect_stdout(buf):
            result=main(["--db",str(self.db),"--exchange","../unsafe",
                         "--decision-at-ms",str(DECISION)])
        self.assertEqual(result,2)
        self.assertEqual(json.loads(buf.getvalue())["status"],"config_invalid")


if __name__=="__main__":
    unittest.main()
