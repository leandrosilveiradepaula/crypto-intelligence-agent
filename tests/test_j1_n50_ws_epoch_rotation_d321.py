"""J1/D321: atomic 36h WS epoch rotation + conservative zero-GET guards."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import FILE_NAME as MANIFEST
from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.j1_n50_ws_private_cache import (
    cache_n50_ws_dynamic_admission_once,
)
from crypto_intelligence_agent import j1_n50_ws_epoch_rotation as epoch
from scripts import rotate_j1_n50_ws_epoch_once as rotate
from scripts.run_j1_n50_ws_owner_active_once import main as ws_cli
from test_j1_n50_managed_cycle import T,SYMS,sealed
from test_j1_n50_ws_dynamic_scope_d314 import OBS,page

HOUR=3_600_000
NEXT=T+36*HOUR
NEXT_OBS=OBS+36*HOUR


@unittest.skipUnless(
    os.name=="posix" and os.geteuid()!=0,
    "private POSIX nonroot owner epoch pointer",
)
class N50WSEpochRotationTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"owner-root"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.state=self.root/"owner-state"
        self.state.mkdir(mode=0o700)
        self.state.chmod(0o700)
        self.patch_root=patch.object(epoch,"_OWNER_ROOT",self.root)
        self.patch_rotate_root=patch.object(rotate,"_OWNER_ROOT",self.root)
        self.patch_root.start()
        self.patch_rotate_root.start()
        self.addCleanup(self.patch_root.stop)
        self.addCleanup(self.patch_rotate_root.stop)
        self.man1,self.ws1=self.candidate("first",T,OBS)
        self.old=self.activate(self.man1,self.ws1,OBS)
        self.assertEqual(self.old.status,"active_n50_ws_epoch_bootstrapped")
        self.assertTrue(self.old.rotation_performed)

    def candidate(self,name,decision,observed):
        manifest=self.root/(name+"-manifest")
        ws=self.root/(name+"-ws")
        for d in (manifest,ws):
            d.mkdir(mode=0o700)
            d.chmod(0o700)
        ranked=sealed(decision)
        mf=manifest/MANIFEST
        mf.write_text(json.dumps(ranked,sort_keys=True),encoding="ascii")
        mf.chmod(0o600)
        metadata=page(tuple(SYMS))
        metadata["time"]=decision+170_000
        result=cache_n50_ws_dynamic_admission_once(
            directory=ws,ranked_scope=ranked,
            instrument_pages=(metadata,),
            requested_cursors=(None,),
            page_received_at_ms=(observed,),
            captured_at_ms=observed,
            allow_private_scope_write=True,
        )
        self.assertTrue(result.file_written,result)
        return manifest,ws

    def activate(self,man,ws,t):
        return epoch.activate_n50_ws_epoch_once(
            state_directory=self.state,manifest_directory=man,
            ws_directory=ws,current_at_ms=t,
            allow_private_pointer_write=True,
        )

    def read(self,t):
        return epoch.load_active_n50_ws_epoch(
            state_directory=self.state,current_at_ms=t,
            allow_private_pointer_read=True,
        )

    def test_active_pointer_replays_exact_50_and_does_not_expose_symbols(self):
        out=self.read(OBS+1000)
        self.assertEqual(out.status,"active_n50_ws_epoch_revalidated",out)
        self.assertEqual(out.manifest_directory,self.man1)
        self.assertEqual(out.ws_directory,self.ws1)
        self.assertEqual(out.ranked_scope_sha256,sealed(T)["scope_digest_sha256"])
        self.assertEqual((self.state/epoch.FILE_NAME).stat().st_mode&0o777,0o600)
        view=json.dumps(out.sanitized_report())
        for s in SYMS:
            self.assertNotIn(s,view)
        self.assertFalse(out.sanitized_report()["orders_sent"])
        self.assertFalse(out.sanitized_report()["marketwide_top50_verified"])
        self.assertEqual(out.sanitized_report()["http_gets"],0)

    def test_35h_rejected_and_36h_atomic_switch_preserves_old_files(self):
        man2,ws2=self.candidate("second",NEXT,NEXT_OBS)
        old_bytes=(self.state/epoch.FILE_NAME).read_bytes()
        journal=SQLiteOfflineClosedStreamJournal.create(self.ws1/"ws-confirmed.sqlite")
        old_journal_bytes=journal.path.read_bytes()
        too_early=self.activate(man2,ws2,OBS+35*HOUR)
        self.assertEqual(too_early.status,"active_n50_ws_not_due_no_get")
        self.assertEqual((self.state/epoch.FILE_NAME).read_bytes(),old_bytes)
        switched=self.activate(man2,ws2,NEXT_OBS)
        self.assertEqual(switched.status,"active_n50_ws_epoch_rotated")
        self.assertTrue(switched.rotation_performed)
        active=self.read(NEXT_OBS)
        self.assertEqual(active.manifest_directory,man2)
        self.assertEqual(active.ws_directory,ws2)
        self.assertNotEqual((self.state/epoch.FILE_NAME).read_bytes(),old_bytes)
        self.assertEqual(journal.path.read_bytes(),old_journal_bytes)
        self.assertEqual(self.read(NEXT_OBS).status,"active_n50_ws_epoch_revalidated")

    def test_tampered_pointer_rejected_without_network(self):
        f=self.state/epoch.FILE_NAME
        raw=f.read_bytes()
        f.write_bytes(raw[:-1]+b"!")
        f.chmod(0o600)
        out=self.read(OBS+1000)
        self.assertEqual(out.status,"active_n50_ws_epoch_read_abstain")
        self.assertFalse(out.rotation_performed)

    def test_symlink_alias_rejected_and_original_kept(self):
        alias=self.root/"state-link"
        alias.symlink_to(self.state,target_is_directory=True)
        out=epoch.load_active_n50_ws_epoch(
            state_directory=alias,current_at_ms=OBS+1000,
            allow_private_pointer_read=True,
        )
        self.assertEqual(out.status,"active_n50_ws_epoch_read_abstain")
        self.assertEqual(self.read(OBS+1000).status,"active_n50_ws_epoch_revalidated")

    def test_existing_candidate_rejected_even_after_36h(self):
        out=self.activate(self.man1,self.ws1,NEXT_OBS)
        self.assertEqual(out.status,"active_n50_ws_epoch_write_abstain")
        self.assertEqual(self.read(OBS+1000).ws_directory,self.ws1)

    def test_new_metadata_mismatch_prevents_pointer_swap(self):
        man2,ws2=self.candidate("second",NEXT,NEXT_OBS)
        f=ws2/"ws-dynamic-n50-admission.json"
        raw=f.read_bytes()
        f.write_bytes(raw[:-1]+b"x")
        f.chmod(0o600)
        old=(self.state/epoch.FILE_NAME).read_bytes()
        out=self.activate(man2,ws2,NEXT_OBS)
        self.assertEqual(out.status,"active_n50_ws_epoch_write_abstain")
        self.assertEqual((self.state/epoch.FILE_NAME).read_bytes(),old)

    def test_rotation_not_due_makes_no_get_and_no_folders(self):
        opts=dict(
            state_directory=self.state,epoch_root=self.root,
            allow_private_rotation=True,allow_public_network=True,
            confirm_region_and_personal_research=True,
            allow_private_manifest_write=True,
            allow_private_ws_cache_write=True,
            clock_ms=lambda:OBS+35*HOUR,
        )
        # The owner runner should reject before any network or file staging.
        with patch.object(rotate,"capture_and_seal_current_rank_once",
                          side_effect=AssertionError("NO GET")),\
             patch.object(rotate,"cache_current_n50_ws_metadata_once",
                          side_effect=AssertionError("NO GET")):
            out=rotate.rotate_n50_ws_owner_epoch_once(**opts)
        self.assertEqual(out["status"],"n50_ws_rotation_not_due_no_get")
        self.assertEqual(out["rank_network_requests"],0)
        self.assertFalse(out["new_epoch_activated"])

    def test_rotation_once_per_epoch_when_rank_rate_limited(self):
        due=NEXT_OBS
        # No actual provider I/O, rank fails in a fixture; the next tick
        # must refuse to retry the same failed epoch.
        opts=dict(
            state_directory=self.state,epoch_root=self.root,
            allow_private_rotation=True,allow_public_network=True,
            confirm_region_and_personal_research=True,
            allow_private_manifest_write=True,
            allow_private_ws_cache_write=True,
            clock_ms=lambda:due,
        )
        with patch.object(rotate,"capture_and_seal_current_rank_once",
                          return_value={
                              "status":"abstain",
                              "requests_attempted":1,
                              "failure_category":"provider_rate_limit_no_retry",
                          }) as capture,\
             patch.object(rotate,"cache_current_n50_ws_metadata_once",
                          side_effect=AssertionError("NO META GET")):
            first=rotate.rotate_n50_ws_owner_epoch_once(**opts)
            second=rotate.rotate_n50_ws_owner_epoch_once(**opts)
        self.assertEqual(first["status"],"n50_ws_rotation_rank_abstain_no_retry")
        self.assertEqual(first["rank_network_requests"],1)
        self.assertEqual(second["status"],"n50_ws_rotation_already_attempted_no_get")
        self.assertEqual(capture.call_count,1)
        self.assertEqual(self.read(OBS+1000).ws_directory,self.ws1)

    def test_owner_ws_cli_uses_current_pointer_not_old_static_directories(self):
        from scripts import run_j1_n50_ws_owner_active_once as cli
        all_flags=[
            "--allow-private-pointer-read","--allow-private-manifest-read",
            "--allow-private-ws-scope-read","--allow-private-ws-writer",
            "--allow-public-websocket",
            "--confirm-region-and-personal-research",
            "--allow-create-ws-journal",
        ]
        paths=[]
        def record(**kwargs):
            paths.append((kwargs["manifest_directory"],
                          kwargs["ws_directory"]))
            return {"status":"ws_owner_hour_50_observed_local_only"}
        from crypto_intelligence_agent import bybit_public_ws_once
        with patch.object(cli.time,"time_ns",return_value=(OBS+1000)*1_000_000),\\
             patch.object(bybit_public_ws_once,"_real_session_factory",
                          return_value=None),\\
             patch.object(cli,"run_cached_n50_ws_owner_window",
                          side_effect=record),\\
             redirect_stdout(StringIO()):
            self.assertEqual(ws_cli(["--state-directory",str(self.state)]
                                     +all_flags),0)
        man2,ws2=self.candidate("second",NEXT,NEXT_OBS)
        self.assertEqual(self.activate(man2,ws2,NEXT_OBS).status,
                         "active_n50_ws_epoch_rotated")
        with patch.object(cli.time,"time_ns",return_value=NEXT_OBS*1_000_000),\\
             patch.object(bybit_public_ws_once,"_real_session_factory",
                          return_value=None),\\
             patch.object(cli,"run_cached_n50_ws_owner_window",
                          side_effect=record),\\
             redirect_stdout(StringIO()):
            self.assertEqual(ws_cli(["--state-directory",str(self.state)]
                                     +all_flags),0)
        self.assertEqual(paths,[(self.man1,self.ws1),(man2,ws2)])

    def test_owner_ws_cli_requires_flags_before_pointer_or_network(self):
        buf=StringIO()
        with patch("scripts.run_j1_n50_ws_owner_active_once.load_active_n50_ws_epoch",
                   side_effect=AssertionError("no load")),\
             patch("scripts.run_j1_n50_ws_owner_active_once.run_cached_n50_ws_owner_window",
                   side_effect=AssertionError("no WS")),\
             redirect_stdout(buf):
            code=ws_cli(["--state-directory",str(self.state)])
        self.assertEqual(code,77)
        self.assertEqual(json.loads(buf.getvalue())["status"],
                         "ws_owner_window_optin_required")


if __name__=="__main__":
    unittest.main()
