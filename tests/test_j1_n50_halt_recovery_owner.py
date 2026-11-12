"""D306 owner one-shot recovery: root/N2 isolation, immutable epoch, optins."""
from __future__ import annotations
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from crypto_intelligence_agent.j1_auto_research_epoch import (
    FILE_NAME,HOUR_MS,SCHEMA,STATUS,_binding,
)
from crypto_intelligence_agent.j1_n50_managed_cycle import (
    _pointer_write, ACTIVE_SCHEMA,
)
from scripts.recover_j1_n50_halted_epoch_once import recover_halted_epoch_once

T=1_800_000_000_000//HOUR_MS*HOUR_MS
SYMS=[f"TST{i:02d}USDT" for i in range(50)]


def sealed(decision):
    s={"schema_version":SCHEMA,"status":STATUS,
       "closed_hour_end_ms":decision,
       "catalog_pre_observed_at_ms":decision+65_000,
       "catalog_post_observed_at_ms":decision+120_000,
       "pool_candidate_count":370,
       "candidate_pool_digest_sha256":"b"*64,
       "closed24h_rank_digest_sha256":"c"*64,
       "ranked_research_symbols_only":list(SYMS),
       "scope_digest_sha256":"",
       "provisional_research_only":True,
       "marketwide_top50_verified":False,
       "independent_crypto_identity_verified":False,
       "live_trading_authorized":False,"orders_sent":False}
    s["scope_digest_sha256"]=_binding(s)
    return s


@unittest.skipUnless(os.name=="posix","POSIX owner private journal")
class N50HaltRecoveryCliTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/"root"
        self.root.mkdir(mode=0o700)
        for p in (self.root/"lease",self.root/"epochs"):
            p.mkdir(mode=0o700)
        old=self.root/"epochs"/f"epoch-{T:013d}"
        old.mkdir(mode=0o700)
        self.old=old
        for p in (old/"scope",old/"journal"):
            p.mkdir(mode=0o700)
            p.chmod(0o700)
        m=old/"scope"/FILE_NAME
        m.write_text(json.dumps(sealed(T)),encoding="ascii")
        m.chmod(0o600)
        self.db=old/"journal"/"j1-rest-hourly-research.sqlite"
        self.db.write_bytes(b"old verified immutable journal fixture")
        self.db.chmod(0o600)
        self.pointer={
            "schema_version":ACTIVE_SCHEMA,
            "epoch_id":old.name,
            "scope_digest_sha256":sealed(T)["scope_digest_sha256"],
            "catalog_post_observed_at_ms":T+120_000,
        }
        _pointer_write(self.root,self.pointer,decision=T)
        self.now=T+8*HOUR_MS+120_000

    def gate(self,*,require_n2_quiesced=False):
        return {"status":"n2_quiesced_preflight_only",
                "n2_timer_disabled":True,"n2_service_inactive":True,
                "orders_sent":False}

    def fake_managed(self,**kwargs):
        decision=self.now//HOUR_MS*HOUR_MS
        name=f"epoch-{decision:013d}"
        new=self.root/"epochs"/name
        new.mkdir(mode=0o700)
        for p in (new/"scope",new/"journal"):
            p.mkdir(mode=0o700)
            p.chmod(0o700)
        s=sealed(decision)
        f=new/"scope"/FILE_NAME
        f.write_text(json.dumps(s),encoding="ascii")
        f.chmod(0o600)
        newpointer={
            "schema_version":ACTIVE_SCHEMA,"epoch_id":name,
            "scope_digest_sha256":s["scope_digest_sha256"],
            "catalog_post_observed_at_ms":decision+120_000,
        }
        _pointer_write(self.root,newpointer,decision=decision)
        return {"status":"epoch_recovered_from_halt",
                "halted_epoch_recovery_verified":True,
                "previous_epoch_preserved":True,
                "orders_sent":False,
                "requests_attempted":372,
                "epoch_id":name}

    def invoke(self,**kw):
        args={"root_directory":self.root,"confirm_halt_reviewed":True,
              "allow_fresh_public_census":True,"owner_ok":True,
              "clock_ms":lambda:self.now,"isolation_reader":self.gate}
        args.update(kw)
        return recover_halted_epoch_once(**args)

    def test_recovery_keeps_old_db_and_seals_new_50_contract_scope(self):
        with patch("scripts.recover_j1_n50_halted_epoch_once.managed_n50_tick_once",
                   side_effect=self.fake_managed) as managed:
            out=self.invoke()
        self.assertEqual(out["status"],"new_epoch_sealed_old_halt_preserved",out)
        self.assertEqual(out["requests_attempted"],372)
        self.assertTrue(out["old_journal_sha256_unchanged"])
        self.assertTrue(out["old_scope_sha256_unchanged"])
        self.assertEqual(self.db.read_bytes(),b"old verified immutable journal fixture")
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["continuous_collector_verified"])
        self.assertTrue(managed.call_args.kwargs["recover_halted_epoch_once"])

    def test_missing_either_optin_reads_no_owner_or_network(self):
        with patch("scripts.recover_j1_n50_halted_epoch_once.managed_n50_tick_once",
                   side_effect=AssertionError("no GET")):
            for flags in ((False,True),(True,False),(False,False)):
                out=self.invoke(confirm_halt_reviewed=flags[0],
                                allow_fresh_public_census=flags[1])
                self.assertEqual(out["status"],"optin_required")
                self.assertEqual(out["requests_attempted"],0)

    def test_running_n2_or_reboot_enabled_blocks_before_get(self):
        def invalid_gate(**kwargs):
            x=self.gate(**kwargs)
            x["n2_timer_disabled"]=False
            return x
        with patch("scripts.recover_j1_n50_halted_epoch_once.managed_n50_tick_once",
                   side_effect=AssertionError("N2 still running")):
            out=self.invoke(isolation_reader=invalid_gate)
        self.assertEqual(out["status"],"blocked")
        self.assertEqual(out["reason"],"n2_not_quiesced")

    def test_capture_failure_keeps_old_pointer_and_data_untouched(self):
        pointer=(self.root/"n50-active-epoch.json").read_bytes()
        with patch("scripts.recover_j1_n50_halted_epoch_once.managed_n50_tick_once",
                   return_value={"status":"blocked","requests_attempted":7,
                                 "failure_category":"provider_rate_limit_no_retry"}):
            out=self.invoke()
        self.assertEqual(out["status"],"blocked",out)
        self.assertEqual(out["requests_attempted"],7)
        self.assertEqual(out["failure_category"],"provider_rate_limit_no_retry")
        self.assertEqual((self.root/"n50-active-epoch.json").read_bytes(),pointer)
        self.assertFalse(out["orders_sent"])

    def test_old_data_tamper_during_capture_is_not_certified(self):
        def mutation(**kwargs):
            self.db.write_bytes(b"tamper")
            self.db.chmod(0o600)
            return self.fake_managed(**kwargs)
        with patch("scripts.recover_j1_n50_halted_epoch_once.managed_n50_tick_once",
                   side_effect=mutation):
            out=self.invoke()
        self.assertEqual(out["status"],"blocked")
        self.assertFalse(out["old_epoch_preserved"])
        self.assertEqual(out["reason"],"old_epoch_modified")


if __name__=="__main__":
    unittest.main()
