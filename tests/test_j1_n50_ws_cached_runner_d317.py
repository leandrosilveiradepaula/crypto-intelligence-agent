"""J1/D317: cached owner N50 -> journal -> WS lease, synthetic sessions."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.j1_n50_ws_cached_runner import (
    run_cached_n50_ws_owner_window, WS_SQLITE_NAME,
)
from crypto_intelligence_agent.j1_n50_ws_private_cache import (
    cache_n50_ws_dynamic_admission_once,
)
from crypto_intelligence_agent.j1_auto_research_epoch import FILE_NAME
from test_j1_n50_managed_cycle import T, SYMS, sealed
from test_j1_n50_ws_dynamic_scope_d314 import OBS, page
from test_j1_n50_ws_hourly_attestation_d313 import DECISION, candle
from test_j1_n50_ws_owner_hour_d315 import FakeTime, FakeSession


@unittest.skipUnless(
    os.name == "posix" and os.geteuid() != 0,
    "private 0700/0600 POSIX owner runner",
)
class CachedOwnerN50WSRunnerTests(unittest.TestCase):
    def setUp(self):
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        base=Path(folder.name)
        self.manifest=base/"ranked-owner"
        self.ws=base/"ws-n50-owner"
        for d in (self.manifest,self.ws):
            d.mkdir(mode=0o700)
            d.chmod(0o700)
        self.ranked=sealed(T)
        p=self.manifest/FILE_NAME
        p.write_text(json.dumps(self.ranked,sort_keys=True),encoding="ascii")
        p.chmod(0o600)
        cache=cache_n50_ws_dynamic_admission_once(
            directory=self.ws,ranked_scope=self.ranked,
            instrument_pages=(page(tuple(SYMS)),),
            requested_cursors=(None,),
            page_received_at_ms=(OBS,),
            captured_at_ms=OBS,
            allow_private_scope_write=True,
        )
        self.assertTrue(cache.file_written)
        self.time=FakeTime()
        self.factory_count=0
        self.opts=dict(
            manifest_directory=self.manifest,
            ws_directory=self.ws,
            allow_private_manifest_read=True,
            allow_private_ws_scope_read=True,
            allow_private_ws_writer=True,
            allow_injected_public_ws=True,
            allow_create_ws_journal=True,
            clock=self.time.clock,wall_ms=self.time.wall_ms,
            sleeper=self.time.sleep,
            budget=WSRunBudget(max_sessions=1,max_frames=250,max_seconds=75),
        )

    def run_it(self,frames=(),**changes):
        send_pongs=changes.pop("send_pongs",False)
        class HealthyPongSession(FakeSession):
            def send(self,raw):
                super().send(raw)
                if json.loads(raw).get("op")=="ping":
                    # The venue replies with a bounded heartbeat ACK.
                    self.queue.append({"op":"ping","ret_msg":"pong"})
        session=(HealthyPongSession if send_pongs else FakeSession)(
            self.time,market=frames,
        )
        def factory():
            self.factory_count+=1
            return session
        args=dict(self.opts,session_factory=factory)
        args.update(changes)
        with patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("REST GET forbidden"),
        ), patch(
            "socket.create_connection",side_effect=AssertionError("WS network forbidden"),
        ):
            report=run_cached_n50_ws_owner_window(**args)
        return report,session

    def check_sanitized(self,out):
        text=json.dumps(out,sort_keys=True)
        for sym in SYMS:
            self.assertNotIn(sym,text)
        self.assertNotIn("turnover",text)
        self.assertEqual(out["http_gets"],0)
        self.assertFalse(out["rest_database_modified"])
        self.assertFalse(out["systemd_modified"])
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertFalse(out["source_authenticated"])

    def test_50_of_50_owner_cache_to_bounded_ws_journal(self):
        r,session=self.run_it([candle(s) for s in SYMS])
        self.assertEqual(r["status"],"ws_owner_hour_50_observed_local_only",r)
        self.assertEqual(r["confirmed_contracts"],50)
        self.assertEqual(r["closed_events_appended_to_ws_journal"],50)
        self.assertEqual(r["missing_contracts"],0)
        self.assertEqual(r["source_provenance"],"bybit_public_ws_confirmed")
        self.assertEqual(r["ranked_scope_sha256"],self.ranked["scope_digest_sha256"])
        self.assertTrue(r["private_ws_journal_created"])
        self.assertTrue(r["owner_lock_acquired"])
        self.assertEqual(len(r["hour_evidence_sha256"]),64)
        self.assertEqual(r["utc_closed_hour_end_ms"],DECISION)
        self.assertEqual((self.ws/WS_SQLITE_NAME).stat().st_mode&0o777,0o600)
        self.assertEqual(self.factory_count,1)
        self.assertTrue(session.closed)
        self.check_sanitized(r)

    def test_ten_second_preclose_start_is_bounded_before_receipt_expires(self):
        # A 150s default lease starting only 11s before close would otherwise
        # finish 139s after the boundary, outside D313 receipt safety.
        self.time.utc = DECISION - 11_000
        report,_=self.run_it(
            [candle(s) for s in SYMS],
            budget=WSRunBudget(max_sessions=1,max_frames=250,max_seconds=150),
            send_pongs=True,
        )
        self.assertEqual(report["status"],"ws_owner_hour_50_observed_local_only",report)
        self.assertEqual(report["confirmed_contracts"],50)
        self.assertIsNotNone(report["hour_evidence_sha256"])
        self.assertLessEqual(self.time.utc,DECISION+120_000)
        self.check_sanitized(report)

    def test_49_of_50_keeps_partial_rows_and_abstains(self):
        r,_=self.run_it([candle(s) for s in SYMS[:-1]])
        self.assertEqual(r["status"],"ws_owner_hour_incomplete_no_pit")
        self.assertEqual((r["confirmed_contracts"],r["missing_contracts"]),(49,1))
        self.assertIsNone(r["hour_evidence_sha256"])
        self.assertTrue(r["rest_gap_reconciliation_required"])
        self.assertEqual(r["closed_events_appended_to_ws_journal"],49)
        self.check_sanitized(r)

    def test_missing_optin_does_not_open_file_or_session(self):
        for key in (
            "allow_private_manifest_read", "allow_private_ws_scope_read",
            "allow_private_ws_writer", "allow_injected_public_ws",
        ):
            args={key:False}
            result,_=self.run_it([candle(SYMS[0])],**args)
            self.assertEqual(result["status"],"ws_owner_window_optin_required")
            self.assertFalse((self.ws/WS_SQLITE_NAME).exists())
        self.assertEqual(self.factory_count,0)

    def test_wrong_clock_refuses_before_new_journal(self):
        self.time.utc=DECISION-120_000
        r,_=self.run_it([candle(SYMS[0])])
        self.assertEqual(r["status"],"ws_owner_window_preflight_abstain")
        self.assertFalse((self.ws/WS_SQLITE_NAME).exists())
        self.assertEqual(self.factory_count,0)

    def test_manifest_changed_but_cache_old_never_opens_ws(self):
        old=(self.manifest/FILE_NAME)
        changed=dict(self.ranked,scope_digest_sha256="0"*64)
        old.write_text(json.dumps(changed,sort_keys=True))
        old.chmod(0o600)
        r,_=self.run_it([candle(SYMS[0])])
        self.assertEqual(r["status"],"ws_owner_window_integrity_abstain")
        self.assertEqual(self.factory_count,0)
        self.assertFalse((self.ws/WS_SQLITE_NAME).exists())

    def test_missing_or_tampered_cache_blocks_without_journal(self):
        f=self.ws/"ws-dynamic-n50-admission.json"
        blob=f.read_bytes()
        f.write_bytes(blob[:-1]+b"x")
        f.chmod(0o600)
        r,_=self.run_it([candle(SYMS[0])])
        self.assertEqual(r["status"],"ws_owner_window_scope_abstain")
        self.assertEqual(self.factory_count,0)
        self.assertFalse((self.ws/WS_SQLITE_NAME).exists())

    def test_existing_journal_requires_0600(self):
        p=self.ws/WS_SQLITE_NAME
        p.write_bytes(b"untrusted sqlite")
        p.chmod(0o644)
        r,_=self.run_it([candle(SYMS[0])])
        self.assertEqual(r["status"],"ws_owner_window_integrity_abstain")
        self.assertEqual(self.factory_count,0)

    def test_journal_missing_requires_independent_create_optin(self):
        r,_=self.run_it([candle(SYMS[0])],allow_create_ws_journal=False)
        self.assertEqual(r["status"],"ws_owner_window_journal_missing")
        self.assertEqual(self.factory_count,0)
        self.assertFalse((self.ws/WS_SQLITE_NAME).exists())
        self.check_sanitized(r)

    def test_symlinked_ancestor_cannot_redirect_ws_output(self):
        alias=self.ws.parent/"ws-alias"
        alias.symlink_to(self.ws,target_is_directory=True)
        report,_=self.run_it([candle(SYMS[0])],ws_directory=alias)
        self.assertEqual(report["status"],"ws_owner_window_preflight_abstain")
        self.assertEqual(self.factory_count,0)
        self.assertFalse((self.ws/WS_SQLITE_NAME).exists())

    def test_open_update_not_closed(self):
        frames=[candle(s) for s in SYMS[:-1]]
        frames.append(candle(SYMS[-1],confirm=False))
        r,_=self.run_it(frames)
        self.assertEqual(r["status"],"ws_owner_hour_incomplete_no_pit")
        self.assertEqual(r["confirmed_contracts"],49)

    def test_no_private_rest_halt_directory_ever_accepted(self):
        # Strictly deny the configured HALT root even when the caller has all
        # capability flags. No filesystem/network action occurs.
        r,_=self.run_it([candle(SYMS[0])],
            ws_directory=Path("/home/cia-probe/agent/j1-n50-managed-d296-private"))
        self.assertEqual(r["status"],"ws_owner_window_preflight_abstain")
        self.assertEqual(self.factory_count,0)


if __name__=="__main__":
    unittest.main()
