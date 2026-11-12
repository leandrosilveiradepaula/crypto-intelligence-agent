"""D294 managed epoch lifecycle: real owner files, fake clock, no GET."""
from __future__ import annotations
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import (
    SCHEMA, STATUS, HOUR_MS, FILE_NAME, _binding,
)
from crypto_intelligence_agent.j1_n50_managed_cycle import (
    ACTIVE_FILE, ACTIVE_SCHEMA, MANAGER_LOCK, _pointer_write,
    managed_n50_tick_once,
)
from crypto_intelligence_agent.j1_n50_global_lease import _record_claim
from hashlib import sha256

T=1_800_000_000_000 // HOUR_MS * HOUR_MS
SYMS=[f"TST{i:02d}USDT" for i in range(50)]


def sealed(decision):
    x={
        "schema_version":SCHEMA,
        "status":STATUS,
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
        "live_trading_authorized":False,
        "orders_sent":False,
    }
    x["scope_digest_sha256"]=_binding(x)
    return x


@unittest.skipUnless(os.name=="posix","owner-only private POSIX epoch pointer")
class ManagedN50EpochTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"root"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        for p in (self.root/"lease",self.root/"epochs"):
            p.mkdir(mode=0o700)
            p.chmod(0o700)
        self.now=T+120_000

    def invoke(self,**kwargs):
        opts={
            "root_directory":self.root,
            "allow_public_network":True,
            "allow_private_storage":True,
            "allow_private_manifest_read":True,
            "allow_private_readonly_audit":True,
            "allow_private_manifest_write":True,
            "confirm_region_and_personal_research":True,
            "enable_managed_n50_tick":True,
            "owner_ok":True,
            "clock_ms":lambda:self.now,
        }
        opts.update(kwargs)
        return managed_n50_tick_once(**opts)

    def fake_delegate(self,**kwargs):
        action=kwargs["action"]
        if action=="capture_seal":
            decision=self.now//HOUR_MS*HOUR_MS
            path=kwargs["manifest_directory"]/FILE_NAME
            data=sealed(decision)
            path.write_text(json.dumps(data),encoding="ascii")
            path.chmod(0o600)
            return {
                "status":"capture_sealed",
                "requests_attempted":372,
                "claims_created":1,
            }
        return {
            "status":"research_hour_persisted",
            "requests_attempted":50,
            "new_closed_candles":50,
            "claims_created":1,
        }

    def test_initial_capture_then_next_hour_writer_without_rebootstrap(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate) as delegate:
            first=self.invoke()
            self.assertEqual(first["status"],"epoch_started",first)
            self.assertEqual(first["requests_attempted"],372)
            self.assertTrue(first["network_accessed"])
            self.assertTrue(first["pointer_updated"])
            self.assertEqual(first["operation"],"capture_seal")
            self.assertFalse(first["orders_sent"])
            pointer=json.loads((self.root/ACTIVE_FILE).read_text())
            self.assertEqual(pointer["epoch_id"],f"epoch-{T:013d}")
            self.assertEqual((self.root/ACTIVE_FILE).stat().st_mode & 0o777,0o600)
            self.now=T+HOUR_MS+120_000
            second=self.invoke()
            self.assertEqual(second["status"],"research_hour_persisted",second)
            self.assertEqual(second["new_closed_candles"],50)
            self.assertFalse(second["pointer_updated"])
            self.assertEqual(second["epoch_id"],pointer["epoch_id"])
            self.assertEqual(delegate.call_args.kwargs["action"],"hourly_writer")
            self.assertEqual(delegate.call_count,2)

    def test_failstop_reason_survives_managed_tick_without_orders(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
        self.now=T+HOUR_MS+120_000
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   return_value={
                       "status":"blocked",
                       "failure_category":"provider_access_or_permission_denied_no_retry",
                       "requests_attempted":7,"new_closed_candles":6,
                       "claims_created":1,
                   }):
            out=self.invoke()
        self.assertEqual(out["status"],"blocked")
        self.assertEqual(out["failure_category"],
                         "provider_access_or_permission_denied_no_retry")
        self.assertEqual((out["requests_attempted"],out["new_closed_candles"]),(7,6))
        self.assertFalse(out["orders_sent"])

    def test_one_off_verified_halt_forces_fresh_epoch_before_36h(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
        old=self.root/"epochs"/f"epoch-{T:013d}"
        old_scope=(old/"scope"/FILE_NAME).read_bytes()
        old_journal=old/"journal"/"immutable-halted-research.sqlite"
        old_journal.write_bytes(b"sealed-verified-journal")
        old_journal.chmod(0o600)
        self.now=T+8*HOUR_MS+120_000
        proof={
            "status":"halted_owner_review_verified",
            "saved_rows_integrity_verified":True,
            "halted_reason":"provider_denied_owner_review",
            "scope_digest_sha256":sealed(T)["scope_digest_sha256"],
            "historical_missing_publication_hours":0,
            "resume_authorized":False,
            "orders_sent":False,
            "network_requests":0,
            "database_mutation_statements":0,
        }
        with patch("crypto_intelligence_agent.j1_n50_halted_forensic.audit_halted_n50_epoch",
                   return_value=proof) as forensic, patch(
                   "crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate) as delegate:
            out=self.invoke(recover_halted_epoch_once=True)
        self.assertEqual(out["status"],"epoch_recovered_from_halt",out)
        self.assertEqual(out["requests_attempted"],372)
        self.assertTrue(out["halted_epoch_recovery_verified"])
        self.assertTrue(out["previous_epoch_preserved"])
        self.assertNotEqual(out["epoch_id"],old.name)
        self.assertEqual((old/"scope"/FILE_NAME).read_bytes(),old_scope)
        self.assertEqual(old_journal.read_bytes(),b"sealed-verified-journal")
        self.assertEqual(delegate.call_args.kwargs["action"],"capture_seal")
        self.assertEqual(forensic.call_args.kwargs["owner_ok"],True)
        self.now+=HOUR_MS
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate) as writer:
            next_hour=self.invoke()
        self.assertEqual(next_hour["status"],"research_hour_persisted")
        self.assertEqual(next_hour["epoch_id"],out["epoch_id"])
        self.assertEqual(writer.call_args.kwargs["action"],"hourly_writer")

    def test_halt_proof_denied_cannot_issue_any_capture_get_or_move_pointer(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
        self.now=T+8*HOUR_MS+120_000
        previous=(self.root/ACTIVE_FILE).read_bytes()
        denial_cases=[
            {"status":"blocked"},
            {"status":"halted_owner_review_verified","saved_rows_integrity_verified":True,
             "halted_reason":"provider_denied_owner_review",
             "scope_digest_sha256":"0"*64,"historical_missing_publication_hours":0,
             "resume_authorized":False,"orders_sent":False,"network_requests":0,
             "database_mutation_statements":0},
            {"status":"halted_owner_review_verified","saved_rows_integrity_verified":True,
             "halted_reason":"candle_or_storage_integrity",
             "scope_digest_sha256":sealed(T)["scope_digest_sha256"],
             "historical_missing_publication_hours":0,"resume_authorized":False,
             "orders_sent":False,"network_requests":0,"database_mutation_statements":0},
        ]
        for denied in denial_cases:
            with self.subTest(denied=denied.get("halted_reason")), patch(
                    "crypto_intelligence_agent.j1_n50_halted_forensic.audit_halted_n50_epoch",
                    return_value=denied), patch(
                    "crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                    side_effect=AssertionError("forensic denied, no GET")):
                out=self.invoke(recover_halted_epoch_once=True)
            self.assertEqual(out["status"],"blocked")
            self.assertEqual(out["reason"],"halted_recovery_forensic_gate_failed")
            self.assertEqual((self.root/ACTIVE_FILE).read_bytes(),previous)
            self.assertFalse(out["network_accessed"])

    def test_halt_capture_fails_without_overwriting_old_pointer(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
        before=(self.root/ACTIVE_FILE).read_bytes()
        self.now=T+8*HOUR_MS+120_000
        valid={
            "status":"halted_owner_review_verified",
            "saved_rows_integrity_verified":True,
            "halted_reason":"provider_denied_owner_review",
            "scope_digest_sha256":sealed(T)["scope_digest_sha256"],
            "historical_missing_publication_hours":0,
            "resume_authorized":False,"orders_sent":False,
            "network_requests":0,"database_mutation_statements":0,
        }
        with patch("crypto_intelligence_agent.j1_n50_halted_forensic.audit_halted_n50_epoch",
                   return_value=valid), patch(
                   "crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   return_value={"status":"blocked","requests_attempted":3}):
            result=self.invoke(recover_halted_epoch_once=True)
        self.assertEqual(result["status"],"blocked")
        self.assertEqual((self.root/ACTIVE_FILE).read_bytes(),before)
        self.assertFalse(result["pointer_updated"])
        self.assertEqual(result["requests_attempted"],3)  # preserve actual attempted GETs
        self.assertTrue(result["network_accessed"])
        self.assertFalse(result["pointer_updated"])

    def test_halt_explicit_optin_is_bool_and_does_not_override_default(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
        self.now=T+8*HOUR_MS+120_000
        with patch("crypto_intelligence_agent.j1_n50_halted_forensic.audit_halted_n50_epoch",
                   side_effect=AssertionError("must not audit for normal writer")), patch(
                   "crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate) as writer:
            normal=self.invoke()
            invalid=self.invoke(recover_halted_epoch_once=1)
        self.assertEqual(normal["status"],"research_hour_persisted")
        self.assertEqual(writer.call_args.kwargs["action"],"hourly_writer")
        self.assertEqual(invalid["status"],"blocked")

    def test_after_37h_rotates_and_preserves_old_epoch_and_immutable_scope(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
            old=self.root/"epochs"/f"epoch-{T:013d}"
            old_scope=(old/"scope"/FILE_NAME).read_bytes()
            self.now=T+37*HOUR_MS+120_000
            rotate=self.invoke()
        self.assertEqual(rotate["status"],"epoch_rotated",rotate)
        self.assertNotEqual(rotate["epoch_id"],old.name)
        self.assertEqual((old/"scope"/FILE_NAME).read_bytes(),old_scope)
        self.assertEqual(len(list((self.root/"epochs").iterdir())),2)
        self.assertTrue((self.root/"epochs"/rotate["epoch_id"]/"journal").is_dir())
        self.assertEqual(json.loads((self.root/ACTIVE_FILE).read_text())["epoch_id"],
                         rotate["epoch_id"])

    def test_expired_epoch_is_refreshed_not_reused_as_historical_pit(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
            self.now=T+51*HOUR_MS+120_000
            rotated=self.invoke()
        self.assertEqual(rotated["status"],"epoch_rotated")
        self.assertFalse(rotated["marketwide_top50_verified"])

    def test_capture_failure_keeps_prior_active_pointer(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
        before=(self.root/ACTIVE_FILE).read_bytes()
        self.now=T+37*HOUR_MS+120_000
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   return_value={"status":"blocked","requests_attempted":4}):
            failed=self.invoke()
        self.assertEqual(failed["status"],"blocked")
        self.assertEqual((self.root/ACTIVE_FILE).read_bytes(),before)
        self.assertFalse(failed["pointer_updated"])

    def test_crash_after_capture_before_pointer_can_adopt_exact_claim(self):
        epoch=self.root/"epochs"/f"epoch-{T:013d}"
        scope=epoch/"scope"
        journal=epoch/"journal"
        for p in (epoch,scope,journal):
            p.mkdir(mode=0o700)
            p.chmod(0o700)
        path=scope/FILE_NAME
        path.write_text(json.dumps(sealed(T)),encoding="ascii")
        path.chmod(0o600)
        action_target=sha256(json.dumps(
            ["capture_seal",str(scope),""],separators=(",",":"),
            ensure_ascii=True).encode("ascii")).hexdigest()
        _record_claim(self.root/"lease",decision=T,action="capture_seal",
                      target_digest=action_target)
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=AssertionError("no repeat GET")):
            adopted=self.invoke()
        self.assertEqual(adopted["status"],"epoch_started",adopted)
        self.assertEqual(adopted["requests_attempted"],0)
        self.assertEqual(adopted["pointer_updated"],True)

    def test_without_capture_claim_existing_manifest_cannot_be_adopted(self):
        epoch=self.root/"epochs"/f"epoch-{T:013d}"
        scope=epoch/"scope"
        journal=epoch/"journal"
        for p in (epoch,scope,journal):
            p.mkdir(mode=0o700)
            p.chmod(0o700)
        path=scope/FILE_NAME
        path.write_text(json.dumps(sealed(T)),encoding="ascii")
        path.chmod(0o600)
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=AssertionError("must not recapture")):
            self.assertEqual(self.invoke()["status"],"blocked")
        self.assertFalse((self.root/ACTIVE_FILE).exists())

    def test_corrupt_pointer_refuses_write_and_get(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=self.fake_delegate):
            self.assertEqual(self.invoke()["status"],"epoch_started")
        ptr=self.root/ACTIVE_FILE
        ptr.write_text('{"schema_version":"invalid"}',encoding="ascii")
        ptr.chmod(0o600)
        self.now=T+HOUR_MS+120_000
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=AssertionError("no GET")):
            self.assertEqual(self.invoke()["status"],"blocked")
        self.assertFalse(self.invoke(enable_managed_n50_tick=False)["network_accessed"])

    def test_owner_gate_missing_optin_and_wrong_time_do_not_call_get(self):
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=AssertionError("network")):
            self.assertEqual(self.invoke(allow_public_network=False)["status"],"optin_required")
            self.assertEqual(self.invoke(owner_ok=False)["status"],"blocked")
            self.now=T+20_000
            self.assertEqual(self.invoke()["status"],"deferred")
            self.assertFalse((self.root/MANAGER_LOCK).exists())

    def test_manager_lock_prevents_concurrent_pointer_transitions(self):
        nested=[]
        def side_effect(**kwargs):
            nested.append(self.invoke())
            return self.fake_delegate(**kwargs)
        with patch("crypto_intelligence_agent.j1_n50_managed_cycle.coordinated_n50_once",
                   side_effect=side_effect):
            out=self.invoke()
        self.assertEqual(out["status"],"epoch_started")
        self.assertEqual(nested[0]["reason"],"manager_lock_busy")

    def test_identical_staged_pointer_recovered_after_crash(self):
        decision=T
        ptr={
            "schema_version": ACTIVE_SCHEMA,
            "epoch_id":f"epoch-{decision:013d}",
            "scope_digest_sha256":sealed(decision)["scope_digest_sha256"],
            "catalog_post_observed_at_ms":decision+120_000,
        }
        raw=json.dumps(ptr,sort_keys=True,
                       separators=(",",":"),ensure_ascii=True).encode("ascii")+b"\n"
        stage=self.root/f".n50-pointer-{decision:013d}.tmp"
        stage.write_bytes(raw)
        stage.chmod(0o600)
        _pointer_write(self.root,ptr,decision=decision)
        self.assertFalse(stage.exists())
        self.assertEqual(json.loads((self.root/ACTIVE_FILE).read_text()),ptr)
        self.assertEqual((self.root/ACTIVE_FILE).stat().st_mode & 0o777,0o600)

    def test_tampered_staged_pointer_blocks_without_overwriting_active(self):
        decision=T
        ptr={
            "schema_version":ACTIVE_SCHEMA,
            "epoch_id":f"epoch-{decision:013d}",
            "scope_digest_sha256":sealed(decision)["scope_digest_sha256"],
            "catalog_post_observed_at_ms":decision+120_000,
        }
        stage=self.root/f".n50-pointer-{decision:013d}.tmp"
        stage.write_bytes(b"tampered")
        stage.chmod(0o600)
        with self.assertRaises(ValueError):
            _pointer_write(self.root,ptr,decision=decision)
        self.assertFalse((self.root/ACTIVE_FILE).exists())
        self.assertEqual(stage.read_bytes(),b"tampered")


if __name__=="__main__":
    unittest.main()
