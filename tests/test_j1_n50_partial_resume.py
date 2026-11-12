"""D292: real SQLite proof of same-hour partial N50 recovery."""
from __future__ import annotations
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from crypto_intelligence_agent.j1_auto_research_epoch import SCHEMA, STATUS, HOUR_MS, _binding
from crypto_intelligence_agent.j1_rest_incremental_owner import _DB_NAME
from crypto_intelligence_agent.j1_rest_resume_readiness import audit_existing_rest_resume
from crypto_intelligence_agent.j1_n50_supervision import plan_n50_supervision
from scripts.audit_bybit_marketwide_closed24h import _digest

T = 1_800_000_000_000 // HOUR_MS * HOUR_MS
SYMS = tuple(f"TST{i:02d}USDT" for i in range(50))
DATA = ("1","2","1","2","20","40")

def scope():
    x = {"schema_version":SCHEMA,"status":STATUS,"closed_hour_end_ms":T,
         "catalog_pre_observed_at_ms":T+65_000,"catalog_post_observed_at_ms":T+120_000,
         "pool_candidate_count":370,"candidate_pool_digest_sha256":"b"*64,
         "closed24h_rank_digest_sha256":"c"*64,
         "ranked_research_symbols_only":list(SYMS),"scope_digest_sha256":"",
         "provisional_research_only":True,"marketwide_top50_verified":False,
         "independent_crypto_identity_verified":False,
         "live_trading_authorized":False,"orders_sent":False}
    x["scope_digest_sha256"]=_binding(x)
    return x

def make(path,*,published=0,completed=13):
    digest=scope()["scope_digest_sha256"]
    last=T if published==0 else T+HOUR_MS
    with closing(sqlite3.connect(path)) as db,db:
        db.executescript("""
        CREATE TABLE scope(id INTEGER PRIMARY KEY,scope_digest TEXT,members_json TEXT,initial_end_ms INTEGER,halted_reason TEXT);
        CREATE TABLE cursor(symbol TEXT PRIMARY KEY,next_open_ms INTEGER);
        CREATE TABLE candles(symbol TEXT,open_ms INTEGER,open TEXT,high TEXT,low TEXT,close TEXT,base_volume TEXT,quote_turnover TEXT,received_at_ms INTEGER,digest_sha256 TEXT,PRIMARY KEY(symbol,open_ms));
        CREATE TABLE published_hour(end_ms INTEGER PRIMARY KEY,observed_at_ms INTEGER,scope_digest TEXT,observed_contracts INTEGER);
        """)
        db.execute("INSERT INTO scope VALUES(1,?,?,?,NULL)",(digest,json.dumps(SYMS),T))
        if published:
            db.execute("INSERT INTO published_hour VALUES(?,?,?,50)",(T,T+120_000,digest))
        for i,sym in enumerate(SYMS):
            end=last if i<completed else (T-24*HOUR_MS if published==0 else T)
            db.execute("INSERT INTO cursor VALUES(?,?)",(sym,end))
            for opened in range(T-24*HOUR_MS,end,HOUR_MS):
                row=(str(opened),*DATA)
                db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (sym,opened,*DATA,last+60_000,_digest([sym,row])))
    path.chmod(0o600)

@unittest.skipUnless(os.name=="posix","owner-only private SQLite POSIX")
class PartialN50Tests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir=Path(temp.name)/"journal"
        self.dir.mkdir(mode=0o700)
        self.dir.chmod(0o700)
        self.path=self.dir/_DB_NAME
    def read(self,now,**overrides):
        params={"output_directory":self.dir,"now_ms":now,"owner_ok":True,
                "expected_members":50,"allow_private_readonly_audit":True}
        params.update(overrides)
        return audit_existing_rest_resume(**params)
    def test_partial_bootstrap_same_hour(self):
        make(self.path,completed=13)
        now=T+180_000
        r=self.read(now,allow_unpublished_partial_hour=True)
        self.assertEqual(r["status"],"unpublished_bootstrap_resume_ready",r)
        self.assertEqual((r["stored_candles"],r["published_hours"],r["partial_contracts_at_target"]),(312,0,13))
        self.assertEqual(plan_n50_supervision(now_ms=now,sealed_scope=scope(),audit=r).action,"run_existing_epoch_once")
        self.assertFalse(self.read(now)["journal_integrity_verified"])
        self.assertIsNone(r["last_published_end_ms"])
    def test_partial_incremental_same_hour_only(self):
        make(self.path,published=1,completed=17)
        now=T+HOUR_MS+180_000
        r=self.read(now,allow_unpublished_partial_hour=True)
        self.assertEqual(r["status"],"unpublished_partial_hour_resume_ready",r)
        self.assertEqual(r["stored_candles"],1217)
        self.assertEqual(r["published_hours"],1)
        self.assertEqual(plan_n50_supervision(now_ms=now,sealed_scope=scope(),audit=r).action,"run_existing_epoch_once")
        self.assertFalse(self.read(now)["journal_integrity_verified"])
        self.assertFalse(self.read(now+HOUR_MS,allow_unpublished_partial_hour=True)["journal_integrity_verified"])
    def test_tamper_blocks(self):
        make(self.path,completed=13)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE candles SET digest_sha256='bad' WHERE rowid=1")
        r=self.read(T+180_000,allow_unpublished_partial_hour=True)
        self.assertFalse(r["journal_integrity_verified"])
    def test_zero_progress_and_late_window_block(self):
        make(self.path,completed=0)
        self.assertFalse(self.read(T+180_000,allow_unpublished_partial_hour=True)["journal_integrity_verified"])
        self.assertFalse(self.read(T+16*60_000,allow_unpublished_partial_hour=True)["journal_integrity_verified"])
    def test_latched_provider_failure_blocks(self):
        make(self.path,completed=12)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE scope SET halted_reason='provider_denied_owner_review'")
        self.assertFalse(self.read(T+180_000,allow_unpublished_partial_hour=True)["journal_integrity_verified"])

if __name__=="__main__":
    unittest.main()
