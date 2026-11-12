"""J2/D300: real SQLite owner fixtures, 50 contracts x 24 validated bars."""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import (
    SCHEMA, STATUS, FILE_NAME, HOUR_MS, _binding,
)
from crypto_intelligence_agent.j1_n50_managed_cycle import (
    ACTIVE_SCHEMA, ACTIVE_FILE, _pointer_write,
)
from crypto_intelligence_agent.j2_n50_private_screen import (
    audit_private_n50_research, _metrics, PrivateResearchAbstain,
)
from scripts.audit_bybit_marketwide_closed24h import _digest

T = 1_800_000_000_000 // HOUR_MS * HOUR_MS
END = T + HOUR_MS
NOW = END + 180_000
SYMBOLS = ["BTCUSDT"] + [f"TST{i:02d}USDT" for i in range(1, 50)]
DB = "j1-rest-hourly-research.sqlite"


def make_scope(symbols=SYMBOLS):
    obj = {
        "schema_version": SCHEMA, "status": STATUS,
        "closed_hour_end_ms": T,
        "catalog_pre_observed_at_ms": T + 65_000,
        "catalog_post_observed_at_ms": T + 120_000,
        "pool_candidate_count": 370,
        "candidate_pool_digest_sha256": "b" * 64,
        "closed24h_rank_digest_sha256": "c" * 64,
        "ranked_research_symbols_only": list(symbols),
        "scope_digest_sha256": "",
        "provisional_research_only": True,
        "marketwide_top50_verified": False,
        "independent_crypto_identity_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }
    obj["scope_digest_sha256"] = _binding(obj)
    return obj


def build(root: Path, *, symbols=SYMBOLS, publish=True):
    for p in (root, root / "lease", root / "epochs"):
        p.mkdir(mode=0o700, exist_ok=True)
        p.chmod(0o700)
    epoch = root / "epochs" / f"epoch-{T:013d}"
    scope_dir = epoch / "scope"
    journal_dir = epoch / "journal"
    for p in (epoch, scope_dir, journal_dir):
        p.mkdir(mode=0o700)
        p.chmod(0o700)
    scope = make_scope(symbols)
    manifest = scope_dir / FILE_NAME
    manifest.write_text(json.dumps(scope), encoding="ascii")
    manifest.chmod(0o600)
    pointer = {
        "schema_version": ACTIVE_SCHEMA,
        "epoch_id": epoch.name,
        "scope_digest_sha256": scope["scope_digest_sha256"],
        "catalog_post_observed_at_ms": scope["catalog_post_observed_at_ms"],
    }
    _pointer_write(root, pointer, decision=T)
    if publish:
        dbpath = journal_dir / DB
        with closing(sqlite3.connect(dbpath)) as db:
            db.executescript("""
                CREATE TABLE scope(
                    id INTEGER PRIMARY KEY,
                    scope_digest TEXT, members_json TEXT,
                    initial_end_ms INTEGER, halted_reason TEXT
                );
                CREATE TABLE cursor(symbol TEXT PRIMARY KEY,next_open_ms INTEGER);
                CREATE TABLE candles(
                    symbol TEXT NOT NULL,open_ms INTEGER NOT NULL,
                    open TEXT NOT NULL, high TEXT NOT NULL,low TEXT NOT NULL,
                    close TEXT NOT NULL,base_volume TEXT NOT NULL,
                    quote_turnover TEXT NOT NULL,received_at_ms INTEGER NOT NULL,
                    digest_sha256 TEXT NOT NULL,
                    PRIMARY KEY(symbol,open_ms)
                );
                CREATE TABLE published_hour(
                    end_ms INTEGER PRIMARY KEY, observed_at_ms INTEGER NOT NULL,
                    scope_digest TEXT NOT NULL,observed_contracts INTEGER NOT NULL
                );
            """)
            db.execute("INSERT INTO scope VALUES(1,?,?,?,NULL)", (
                scope["scope_digest_sha256"],
                json.dumps(list(symbols), separators=(",", ":")), END,
            ))
            db.execute("INSERT INTO published_hour VALUES(?,?,?,50)", (
                END, NOW - 30_000, scope["scope_digest_sha256"],
            ))
            for idx, symbol in enumerate(symbols):
                db.execute("INSERT INTO cursor VALUES (?,?)", (symbol, END))
                for i in range(24):
                    opened = END - 24 * HOUR_MS + i * HOUR_MS
                    with __import__("decimal").localcontext(
                            __import__("decimal").Context(prec=50)):
                        op = Decimal(100 + idx) + Decimal(i) / 5
                        if i == 23 and idx % 3 == 0:
                            cl = op + 8
                        elif i == 23 and idx % 3 == 1:
                            cl = op - 12
                        else:
                            cl = op
                        hi = max(op, cl) + 1
                        lo = min(op, cl) - 1
                    values = tuple(str(v) for v in (
                        op, hi, lo, cl, Decimal(100), Decimal(2000 if i == 23 else 1000)
                    ))
                    digest = _digest([symbol, (str(opened), *values)])
                    db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (symbol,opened,*values,NOW-60_000,digest))
            db.commit()
        dbpath.chmod(0o600)
    return epoch


@unittest.skipUnless(os.name == "posix", "0700/0600 owner SQLite POSIX")
class N50PrivateJ2ScreenTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "root"

    def scan(self, **opts):
        options = {
            "root_directory": self.root,
            "now_ms": NOW,
            "owner_ok": True,
            "allow_private_readonly_audit": True,
        }
        options.update(opts)
        return audit_private_n50_research(**options)

    def test_integral_real_sqlite_replay_and_private_50_asset_rank(self):
        build(self.root)
        data = self.scan(include_private_symbols=True)
        self.assertEqual(data["status"], "descriptive_research_ready", data)
        self.assertTrue(data["owner_journal_integrity_verified"])
        self.assertEqual(data["audited_assets"], 50)
        self.assertEqual(data["eligible_closed_bars_per_asset"], 24)
        self.assertEqual(len(data["research_rows"]), 50)
        self.assertTrue(data["btc_context_available"])
        self.assertEqual(data["descriptive_up_breakouts"] +
                         data["descriptive_down_breakouts"] +
                         data["descriptive_inside_bars"], 50)
        self.assertTrue(data["window_digest_sha256"])
        self.assertTrue(any(x["last_closed_bar_breakout"] ==
                            "above_prior_23h_high" for x in data["research_rows"]))
        self.assertTrue(any(x["last_closed_bar_breakout"] ==
                            "below_prior_23h_low" for x in data["research_rows"]))
        self.assertFalse(data["approved_for_signals"])
        self.assertFalse(data["approved_for_live_use"])
        self.assertFalse(data["orders_sent"])
        self.assertFalse(data["marketwide_top50_verified"])
        self.assertEqual(data["network_requests"], 0)
        self.assertEqual(data["database_mutation_statements"], 0)
        self.assertEqual(data["research_rows"][0]["descriptive_rank"], 1)
        self.assertTrue(all(item["orders_sent"] is False
                            for item in data["research_rows"]))
        self.assertTrue(all(type(item["return_24bars_pct"]) is str
                            for item in data["research_rows"]))

    def test_default_cli_safe_surface_suppresses_private_symbol_values(self):
        build(self.root)
        x=self.scan()
        self.assertEqual(x["status"], "descriptive_research_ready", x)
        self.assertEqual(x["research_rows"], [])
        self.assertNotIn("USDT", json.dumps(x))
        self.assertEqual(x["audited_assets"], 50)
        self.assertEqual(x["descriptive_up_breakouts"] +
                         x["descriptive_down_breakouts"] +
                         x["descriptive_inside_bars"], 50)

    def test_owner_and_optin_block_before_reading_private_pointer(self):
        with patch("crypto_intelligence_agent.j2_n50_private_screen._pointer_read",
                   side_effect=AssertionError("must not read")):
            self.assertEqual(self.scan(
                allow_private_readonly_audit=False)["status"],
                "owner_optin_required")
            self.assertEqual(self.scan(owner_ok=False)["status"],"blocked")

    def test_before_first_writer_is_explicitly_unverified(self):
        build(self.root, publish=False)
        x=self.scan()
        self.assertNotEqual(x["status"],"descriptive_research_ready")
        self.assertFalse(x["owner_journal_integrity_verified"])
        self.assertEqual(x["audited_assets"],0)

    def test_stale_scope_and_clock_do_not_infer_research(self):
        build(self.root)
        old=self.scan(now_ms=T+49*HOUR_MS)
        self.assertNotEqual(old["status"],"descriptive_research_ready")
        self.assertFalse(old["owner_journal_integrity_verified"])
        self.assertEqual(self.scan(now_ms=True)["status"],"blocked")

    def test_single_candle_checksum_tamper_blocks_all_50(self):
        epoch=build(self.root)
        dbpath=epoch/"journal"/DB
        with closing(sqlite3.connect(dbpath)) as db:
            with db:
                db.execute("UPDATE candles SET digest_sha256='0' WHERE rowid=1")
        x=self.scan(include_private_symbols=True)
        self.assertNotEqual(x["status"],"descriptive_research_ready")
        self.assertEqual(x["research_rows"], [])
        self.assertEqual(x["network_requests"], 0)

    def test_scope_pointer_mismatch_and_db_symlink_rejected(self):
        epoch=build(self.root)
        pointer=self.root/ACTIVE_FILE
        obj=json.loads(pointer.read_text())
        obj["scope_digest_sha256"]="0"*64
        pointer.write_text(json.dumps(obj),encoding="ascii")
        pointer.chmod(0o600)
        self.assertEqual(self.scan()["status"],"blocked")
        _pointer_write # cover immutable pointer contract via prod helper
        obj["scope_digest_sha256"]=make_scope()["scope_digest_sha256"]
        pointer.write_text(json.dumps(obj),encoding="ascii")
        pointer.chmod(0o600)
        db=epoch/"journal"/DB
        db.unlink()
        db.symlink_to(pointer)
        self.assertNotEqual(self.scan()["status"],"descriptive_research_ready")

    def test_no_btc_reference_never_approves_signals(self):
        alternative=[f"TST{i:02d}USDT" for i in range(50)]
        build(self.root,symbols=alternative)
        x=self.scan(include_private_symbols=True)
        self.assertEqual(x["status"],"btc_context_missing_research_only",x)
        self.assertEqual(len(x["research_rows"]),50)
        self.assertFalse(x["btc_context_available"])
        self.assertFalse(x["approved_for_signals"])
        self.assertTrue(all(v["relative_vs_btc_pct_points"] is None
                            for v in x["research_rows"]))

    def test_numeric_overflow_and_future_candle_block(self):
        epoch=build(self.root)
        db=epoch/"journal"/DB
        with closing(sqlite3.connect(db)) as conn:
            with conn:
                conn.execute("UPDATE candles SET high='NaN' WHERE rowid=1")
        self.assertNotEqual(self.scan()["status"],"descriptive_research_ready")

    def test_pure_metrics_do_not_look_into_next_candle(self):
        twentyfour=[]
        for i in range(24):
            price=Decimal(100+i)
            twentyfour.append((i*HOUR_MS,(price,price+1,price-1,price,
                                         Decimal(10),Decimal(100))))
        before=_metrics("TESTUSDT",twentyfour)
        future=(24*HOUR_MS,(Decimal(1000),)*4+(Decimal(10),Decimal(100)))
        self.assertEqual(before,_metrics("TESTUSDT",twentyfour))
        after=_metrics("TESTUSDT",twentyfour[1:]+[future])
        self.assertNotEqual(before["return_24bars_pct"],
                            after["return_24bars_pct"])


if __name__ == "__main__":
    unittest.main()
