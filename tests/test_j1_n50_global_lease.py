"""D293 real POSIX owner lease, serialized actions and anti-tampering."""
from __future__ import annotations
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from crypto_intelligence_agent.j1_n50_global_lease import (
    coordinated_n50_once, LOCK_FILE, HOUR_MS,
)

T=1_800_000_000_000 // HOUR_MS * HOUR_MS

@unittest.skipUnless(os.name=="posix","flock/0600 owner-only POSIX")
class N50GlobalLeaseTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.lock=root/"lease"
        self.scope=root/"scope"
        self.output=root/"journal"
        for p in (self.lock,self.scope,self.output):
            p.mkdir(mode=0o700)
            p.chmod(0o700)

    def invoke(self,action,**kwargs):
        data=dict(
            action=action,lock_directory=self.lock,
            manifest_directory=self.scope,
            output_directory=self.output if action=="hourly_writer" else None,
            clock_ms=lambda:T+120_000,owner_ok=True,
            allow_public_network=True,
            allow_private_storage=True,
            allow_private_manifest_read=True,
            allow_private_readonly_audit=True,
            allow_private_manifest_write=True,
            confirm_region_and_personal_research=True,
            enable_coordinated_n50_once=True,
        )
        data.update(kwargs)
        return coordinated_n50_once(**data)

    def test_same_hour_capture_and_writer_are_mutually_exclusive(self):
        with patch("crypto_intelligence_agent.j1_n50_global_lease.capture_and_seal_current_rank_once",
                   return_value={"status":"sealed_current_auto_rank_research_scope_only",
                                 "requests_attempted":372}) as capture, \
                patch("crypto_intelligence_agent.j1_n50_global_lease.run_supervised_n50_once",
                      side_effect=AssertionError("should never run writer")):
            a=self.invoke("capture_seal")
            self.assertEqual(a["status"],"capture_sealed",a)
            self.assertEqual(a["claims_created"],1)
            self.assertEqual(a["requests_attempted"],372)
            self.assertEqual(self.invoke("hourly_writer")["status"],"blocked")
            self.assertEqual(capture.call_count,1)
            retry=self.invoke("capture_seal")
            self.assertEqual(retry["claims_created"],0)
            self.assertEqual(retry["status"],"capture_sealed")
            self.assertEqual(capture.call_count,2)
        files=list(self.lock.glob("claim-*.json"))
        self.assertEqual(len(files),1)
        self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
        self.assertEqual((self.lock/LOCK_FILE).stat().st_mode & 0o777,0o600)
        self.assertNotIn("USDT",json.dumps(a))
        self.assertFalse(a["orders_sent"])

    def test_writer_same_hour_locks_out_capture_even_if_writer_deferred(self):
        with patch("crypto_intelligence_agent.j1_n50_global_lease.run_supervised_n50_once",
                   return_value={"status":"deferred","requests_attempted":0}), \
                patch("crypto_intelligence_agent.j1_n50_global_lease.capture_and_seal_current_rank_once",
                      side_effect=AssertionError("must not capture")):
            w=self.invoke("hourly_writer")
            self.assertEqual(w["status"],"deferred",w)
            self.assertEqual(self.invoke("capture_seal")["status"],"blocked")
            self.assertEqual(self.invoke("hourly_writer",
                             output_directory=self.scope)["status"],"blocked")

    def test_nested_call_fails_on_live_flock_without_deadlock(self):
        observed=[]
        def nested(**kw):
            observed.append(self.invoke("hourly_writer"))
            return {"status":"sealed_current_auto_rank_research_scope_only"}
        with patch("crypto_intelligence_agent.j1_n50_global_lease.capture_and_seal_current_rank_once",
                   side_effect=nested):
            out=self.invoke("capture_seal")
        self.assertEqual(out["status"],"capture_sealed")
        self.assertEqual(observed[0]["reason"],"global_n50_lease_busy")

    def test_claim_tamper_and_symlink_block_before_get(self):
        with patch("crypto_intelligence_agent.j1_n50_global_lease.capture_and_seal_current_rank_once",
                   return_value={"status":"sealed_current_auto_rank_research_scope_only"}):
            self.assertEqual(self.invoke("capture_seal")["status"],"capture_sealed")
        claim=next(self.lock.glob("claim-*.json"))
        claim.write_text('{"schema_version":"tampered"}',encoding="ascii")
        claim.chmod(0o600)
        with patch("crypto_intelligence_agent.j1_n50_global_lease.capture_and_seal_current_rank_once",
                   side_effect=AssertionError("GET forbidden")):
            self.assertEqual(self.invoke("capture_seal")["status"],"blocked")
            claim.unlink()
            claim.symlink_to(self.lock/LOCK_FILE)
            self.assertEqual(self.invoke("capture_seal")["status"],"blocked")

    def test_missing_optin_wrong_owner_time_and_paths_are_inert(self):
        with patch("crypto_intelligence_agent.j1_n50_global_lease.capture_and_seal_current_rank_once",
                   side_effect=AssertionError("network")):
            self.assertEqual(self.invoke("capture_seal",allow_public_network=False)["status"],"optin_required")
            self.assertEqual(self.invoke("capture_seal",owner_ok=False)["status"],"blocked")
            self.assertEqual(self.invoke("capture_seal",clock_ms=lambda:T+20_000)["status"],"deferred")
            self.assertEqual(self.invoke("capture_seal",manifest_directory=self.lock)["status"],"blocked")
            self.assertEqual(self.invoke("capture_seal",lock_directory=Path("relative"))["status"],"blocked")
            self.assertEqual(self.invoke("unsupported")["status"],"blocked")

if __name__=="__main__":
    unittest.main()
