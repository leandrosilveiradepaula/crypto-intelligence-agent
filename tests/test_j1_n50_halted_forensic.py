"""D304: replay real 50-member latched M1 SQLite, without any recovery GET."""
from __future__ import annotations
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import (
    SCHEMA,STATUS,FILE_NAME,HOUR_MS,_binding,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import _DB_NAME
from crypto_intelligence_agent.j1_n50_halted_forensic import audit_halted_n50_epoch
from scripts.audit_bybit_marketwide_closed24h import _digest

T=1_800_000_000_000 // HOUR_MS * HOUR_MS
SYMS=[f"TST{i:02d}USDT" for i in range(50)]
DATA=("1","2","1","2","20","40")


@unittest.skipUnless(os.name=="posix","owner-only SQLite POSIX")
class HaltedN50ForensicTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)/"epoch"
        root.mkdir(mode=0o700)
        self.scope_dir=root/"scope"
        self.journal_dir=root/"journal"
        for d in (self.scope_dir,self.journal_dir):
            d.mkdir(mode=0o700)
            d.chmod(0o700)
        scope={
            "schema_version":SCHEMA,"status":STATUS,
            "closed_hour_end_ms":T-HOUR_MS,
            "catalog_pre_observed_at_ms":T-HOUR_MS+65_000,
            "catalog_post_observed_at_ms":T-HOUR_MS+120_000,
            "pool_candidate_count":370,
            "candidate_pool_digest_sha256":"b"*64,
            "closed24h_rank_digest_sha256":"c"*64,
            "ranked_research_symbols_only":SYMS,
            "scope_digest_sha256":"",
            "provisional_research_only":True,
            "marketwide_top50_verified":False,
            "independent_crypto_identity_verified":False,
            "live_trading_authorized":False,"orders_sent":False,
        }
        scope["scope_digest_sha256"]=_binding(scope)
        self.digest=scope["scope_digest_sha256"]
        manifest=self.scope_dir/FILE_NAME
        manifest.write_text(json.dumps(scope),encoding="ascii")
        manifest.chmod(0o600)
        self.db_path=self.journal_dir/_DB_NAME
        with closing(sqlite3.connect(self.db_path)) as db:
            db.executescript("""
            CREATE TABLE scope(id INTEGER PRIMARY KEY,scope_digest TEXT,members_json TEXT,initial_end_ms INTEGER,halted_reason TEXT);
            CREATE TABLE cursor(symbol TEXT PRIMARY KEY,next_open_ms INTEGER);
            CREATE TABLE candles(symbol TEXT,open_ms INTEGER,open TEXT,high TEXT,low TEXT,close TEXT,base_volume TEXT,quote_turnover TEXT,received_at_ms INTEGER,digest_sha256 TEXT,PRIMARY KEY(symbol,open_ms));
            CREATE TABLE published_hour(end_ms INTEGER PRIMARY KEY,observed_at_ms INTEGER,scope_digest TEXT,observed_contracts INTEGER);
            """)
            db.execute("INSERT INTO scope VALUES(1,?,?,?,?)",
                       (self.digest,json.dumps(SYMS),T,"provider_denied_owner_review"))
            for end in (T,T+HOUR_MS,T+2*HOUR_MS):
                db.execute("INSERT INTO published_hour VALUES(?,?,?,50)",
                           (end,end+120_000,self.digest))
            for i,sym in enumerate(SYMS):
                cursor=T+3*HOUR_MS if i<6 else T+2*HOUR_MS
                db.execute("INSERT INTO cursor VALUES(?,?)",(sym,cursor))
                for opened in range(T-24*HOUR_MS,cursor,HOUR_MS):
                    row=(str(opened),*DATA)
                    db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (sym,opened,*DATA,T+3*HOUR_MS+70_000,
                                _digest([sym,row])))
            db.commit()
        self.db_path.chmod(0o600)

    def audit(self,**kw):
        args={
            "scope_directory":self.scope_dir,
            "journal_directory":self.journal_dir,
            "allow_private_readonly_audit":True,
            "owner_ok":True,
            "now_ms":T+3*HOUR_MS+180_000,
        }
        args.update(kw)
        return audit_halted_n50_epoch(**args)

    def test_real_shape_three_published_six_partial_candles(self):
        report=self.audit()
        self.assertEqual(report["status"],"halted_owner_review_verified",report)
        self.assertEqual(report["halted_reason"],"provider_denied_owner_review")
        self.assertEqual(report["stored_candles"],1306)
        self.assertEqual(report["published_hours"],3)
        self.assertEqual(report["partial_contracts_at_next_hour"],6)
        self.assertEqual(report["historical_missing_publication_hours"],0)
        self.assertEqual(report["last_published_end_ms"],T+2*HOUR_MS)
        self.assertTrue(report["saved_rows_integrity_verified"])
        self.assertFalse(report["resume_authorized"])
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["continuous_collector_verified"])
        self.assertEqual(report["network_requests"],0)
        self.assertEqual(report["database_mutation_statements"],0)
        self.assertNotIn("TST00USDT",json.dumps(report))

    def test_expired_manifest_still_allows_no_network_forensic_replay(self):
        # Research scope expires for NEW decisions in 48h; immutable records
        # must remain forensically verifiable without authorizing a retry.
        result=self.audit(now_ms=T+60*HOUR_MS+180_000)
        self.assertEqual(result["status"],"halted_owner_review_verified",result)
        self.assertEqual(result["published_hours"],3)
        self.assertEqual(result["partial_contracts_at_next_hour"],6)
        self.assertFalse(result["resume_authorized"])
        self.assertEqual(result["network_requests"],0)

    def test_without_optin_no_private_access(self):
        with patch("crypto_intelligence_agent.j1_n50_halted_forensic._decode_private_file",
                   side_effect=AssertionError("should not read")):
            report=self.audit(allow_private_readonly_audit=False)
        self.assertEqual(report["status"],"optin_required")
        self.assertFalse(report["saved_rows_integrity_verified"])

    def test_saved_candle_digest_tamper_blocks(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE candles SET digest_sha256=? WHERE rowid=1",("0"*64,))
            db.commit()
        report=self.audit()
        self.assertEqual(report["status"],"blocked")
        self.assertFalse(report["resume_authorized"])

    def test_publication_receipt_tamper_blocks(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE published_hour SET observed_contracts=49")
            db.commit()
        self.assertEqual(self.audit()["status"],"blocked")

    def test_no_halt_never_reports_halted_verified(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE scope SET halted_reason=NULL")
            db.commit()
        self.assertEqual(self.audit()["status"],"not_halted")

    def test_scope_symlink_blocks_without_sqlite_read(self):
        self.db_path.unlink()
        self.db_path.symlink_to(self.scope_dir/FILE_NAME)
        self.assertEqual(self.audit()["status"],"blocked")

    def test_time_and_owner_gates(self):
        self.assertEqual(self.audit(owner_ok=False)["status"],"blocked")
        self.assertEqual(self.audit(now_ms=T-HOUR_MS)["status"],"blocked")


if __name__=="__main__":
    unittest.main()
