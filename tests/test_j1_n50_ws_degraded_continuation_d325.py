"""J1/D325: keep N50 WS collecting through <=3 explicit hourly gaps.

Offline fixtures only. Small incompleteness never becomes a 50/50 attestation;
severe failures still return nonzero and trigger systemd N2 failback.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.j1_n50_ws_dynamic_scope import admit_dynamic_n50_ws_scope
from crypto_intelligence_agent.j1_n50_ws_owner_hour import run_n50_ws_owner_hour_once
from crypto_intelligence_agent.j1_n50_ws_cached_runner import _report
from scripts.run_j1_n50_ws_owner_active_once import (
    _bounded_degraded_continuation, main as active_cli,
)
from test_j1_n50_managed_cycle import T, SYMS, sealed
from test_j1_n50_ws_dynamic_scope_d314 import OBS, page
from test_j1_n50_ws_hourly_attestation_d313 import DECISION, candle
from test_j1_n50_ws_owner_hour_d315 import FakeTime, FakeSession

CLI_FLAGS = [
    "--state-directory", "/home/cia-probe/agent/j1-n50-ws-epochs/active",
    "--allow-private-pointer-read",
    "--allow-private-manifest-read",
    "--allow-private-ws-scope-read",
    "--allow-private-ws-writer",
    "--allow-public-websocket",
    "--confirm-region-and-personal-research",
    "--allow-create-ws-journal",
]


def partial_report(missing=1):
    doc=_report("ws_owner_hour_incomplete_no_pit")
    doc.update(
        confirmed_contracts=50-missing, missing_contracts=missing,
        rest_gap_reconciliation_required=True,
        owner_lock_acquired=True, subscription_acks=1,
        ws_sessions_attempted=1, failure_category=None,
        declared_ws_gap_append_enabled=True,
    )
    return doc


class BoundedContinuationPolicyTests(unittest.TestCase):
    def test_only_one_to_three_clean_missing_members_can_continue(self):
        for missing in (1,2,3):
            with self.subTest(missing=missing):
                result=partial_report(missing)
                self.assertTrue(_bounded_degraded_continuation(result))
                self.assertFalse(result["continuous_collector_verified"])
                self.assertIsNone(result["hour_evidence_sha256"])
        for missing in (0,4,5,49,50):
            with self.subTest(missing=missing):
                self.assertFalse(_bounded_degraded_continuation(partial_report(missing)))

    def test_missing_ack_origin_or_declared_gap_optin_fail_closed(self):
        for key,value in (
            ("status","ws_owner_lease_degraded_abstain"),
            ("status","ws_owner_hour_50_observed_local_only"),
            ("declared_ws_gap_append_enabled",False),
            ("rest_gap_reconciliation_required",False),
            ("owner_lock_acquired",False),
            ("subscription_acks",0),
            ("ws_sessions_attempted",0),
            ("http_gets",1),
            ("orders_sent",True),
            ("source_provenance","bybit_public_ws_confirmed"),
            ("hour_evidence_sha256","a"*64),
            ("systemd_modified",True),
            ("failure_category","frame_budget_exhausted"),
            ("rest_database_modified",True),
            ("missing_contracts",True),
            ("confirmed_contracts",47.0),
        ):
            with self.subTest(field=key,value=value):
                report=partial_report()
                report[key]=value
                self.assertFalse(_bounded_degraded_continuation(report))
        self.assertFalse(_bounded_degraded_continuation(None))
        self.assertFalse(_bounded_degraded_continuation({"status":"partial"}))

    def test_active_systemd_cli_exit_zero_only_for_explicit_partial(self):
        active=SimpleNamespace(
            status="active_n50_ws_epoch_revalidated",
            manifest_directory=Path("/tmp/n50-man"),
            ws_directory=Path("/tmp/n50-ws"),
        )
        called=[]
        def fake_runner(**kwargs):
            called.append(kwargs)
            return result
        with patch(
            "scripts.run_j1_n50_ws_owner_active_once.load_active_n50_ws_epoch",
            return_value=active,
        ), patch(
            "scripts.run_j1_n50_ws_owner_active_once.run_cached_n50_ws_owner_window",
            side_effect=fake_runner,
        ), patch(
            "crypto_intelligence_agent.bybit_public_ws_once._real_session_factory",
            return_value=None,
        ) as socket_factory:
            # A 49/50 is not a completed hour but MUST preserve the WS timer.
            result=partial_report(missing=1)
            stdout=StringIO()
            with redirect_stdout(stdout):
                code=active_cli(CLI_FLAGS)
            self.assertEqual(code,0)
            self.assertTrue(json.loads(stdout.getvalue())[
                "ws_timer_continuation_with_gap_allowed"])
            self.assertEqual(called[-1]["allow_declared_ws_gap"],True)
            self.assertEqual(called[-1]["allow_private_ws_writer"],True)
            self.assertEqual(called[-1]["allow_create_ws_journal"],True)

            # Too many absent members => systemd OnFailure and N2.
            result=partial_report(missing=4)
            stdout=StringIO()
            with redirect_stdout(stdout):
                code=active_cli(CLI_FLAGS)
            self.assertEqual(code,65)
            self.assertFalse(json.loads(stdout.getvalue())[
                "ws_timer_continuation_with_gap_allowed"])

            result=partial_report(missing=1)
            result["declared_ws_gap_append_enabled"]=False
            with redirect_stdout(StringIO()):
                self.assertEqual(active_cli(CLI_FLAGS),65)
        self.assertEqual(len(called),3)
        self.assertEqual(socket_factory.call_count,0)


class HourSession(FakeSession):
    def __init__(self, time_, decision, messages):
        super().__init__(time_,market=messages)
        self.decision=decision

    def recv(self, timeout):
        if not self.queue:
            self.clock.advance(timeout)
            raise TimeoutError("fixture waiting")
        item=self.queue.pop(0)
        if isinstance(item,dict) and item.get("topic"):
            ready=self.decision+2000
            if self.clock.utc < ready:
                self.clock.advance((ready-self.clock.utc)/1000)
        self.clock.advance(.01)
        return json.dumps(item,separators=(",",":"))


def hourly_kline(symbol, index):
    row=candle(symbol)
    row["ts"]+=index*HOUR_MS
    row["data"][0]["start"]+=index*HOUR_MS
    row["data"][0]["end"]+=index*HOUR_MS
    row["data"][0]["timestamp"]+=index*HOUR_MS
    return row


@unittest.skipUnless(
    os.name=="posix" and os.geteuid()!=0,
    "owner-only WS journal uses Linux non-root POSIX DAC/flock",
)
class N50WSThreeHourGapTests(unittest.TestCase):
    def test_50_then_49_then_50_with_gap_marker_and_no_rest(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        folder=Path(temp.name)/"private-n50"
        folder.mkdir(mode=0o700)
        folder.chmod(0o700)
        journal=SQLiteOfflineClosedStreamJournal.create(
            folder/"ws-confirmed.sqlite")
        ranked=sealed(T)
        admission=admit_dynamic_n50_ws_scope(
            ranked_scope=ranked,instrument_pages=(page(tuple(SYMS)),),
            requested_cursors=(None,),page_received_at_ms=(OBS,),
            now_ms=OBS,
        )
        with patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("REST forbidden"),
        ), patch(
            "socket.create_connection",
            side_effect=AssertionError("real socket forbidden"),
        ):
            statuses=[]
            for hour,contracts in ((0,SYMS),(1,SYMS[:-1]),(2,SYMS)):
                decision=DECISION+hour*HOUR_MS
                clock=FakeTime()
                clock.utc=decision-30_000
                session=HourSession(clock,decision,
                                    [hourly_kline(s,hour) for s in contracts])
                report=run_n50_ws_owner_hour_once(
                    ranked_scope=ranked,admission=admission,journal=journal,
                    decision_at_ms=decision,started_at_ms=decision-30_000,
                    session_factory=lambda:session,
                    allow_private_ws_writer=True,allow_injected_public_ws=True,
                    allow_declared_ws_gap=True,
                    budget=WSRunBudget(max_sessions=1,max_frames=100,max_seconds=70),
                    clock=clock.clock,wall_ms=clock.wall_ms,
                    sleeper=clock.sleep,
                )
                statuses.append(report["status"])
                self.assertTrue(session.closed)
                self.assertEqual(report["confirmed_contracts"],len(contracts))
                self.assertFalse(report["orders_sent"])
                self.assertFalse(report["marketwide_top50_verified"])
                self.assertEqual(report["http_gets"],0)
        self.assertEqual(statuses,[
            "ws_owner_hour_50_observed_local_only",
            "ws_owner_hour_incomplete_no_pit",
            "ws_owner_hour_50_observed_local_only",
        ])
        final=journal.audit(
            scope=admission.ws_scope,
            decision_at_ms=DECISION+2*HOUR_MS,
            as_of_ms=DECISION+2*HOUR_MS+40_000,
            hour_evidence_symbols=tuple(sorted(SYMS)),
        )
        self.assertEqual(final.persisted_rows,149)
        self.assertEqual(final.hour_evidence_confirmed,50)
        self.assertEqual(final.declared_gap_markers,1)
        self.assertEqual(final.missing_24h_symbols,50)
        self.assertIsNone(final.rank_digest_sha256)
        self.assertNotIn(SYMS[-1],str(final.sanitized_report()))


if __name__=="__main__":
    unittest.main()
