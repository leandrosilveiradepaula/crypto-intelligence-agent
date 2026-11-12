"""D318: exact preclose WS timer, no REST timer shift or implicit release."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from scripts import preflight_j1_n50_ws_systemd as gate
from scripts.render_j1_n50_ws_systemd import render_n50_ws_systemd

P = "/home/cia-probe/agent/ws-venv/bin/python"
R = "/home/cia-probe/agent/repo-ws-d318"
M = "/home/cia-probe/agent/d318-manifest-private"
W = "/home/cia-probe/agent/d318-ws-private"


def cp(unit, *, active="inactive", enabled=None, load="loaded"):
    return SimpleNamespace(
        returncode=0, stderr="",
        stdout=f"LoadState={load}\nActiveState={active}\n"
               f"UnitFileState={enabled or ('disabled' if unit.endswith('.timer') else 'static')}\n",
    )


def eligible_runner(calls, **changes):
    def call(argv, **kwargs):
        calls.append(tuple(argv))
        assert argv[:2] == ["/usr/bin/systemctl", "show"]
        assert kwargs["timeout"] == 3
        assert not kwargs["check"]
        unit=argv[2]
        if unit=="cia-j1-n50-managed.timer":
            return cp(unit, **changes.get("old_timer", {}))
        if unit=="cia-j1-n50-managed.service":
            return cp(unit, **changes.get("old_service", {"active":"failed"}))
        if unit=="cia-j1-rest-hourly.timer":
            return cp(unit, **changes.get("n2_timer", {}))
        if unit=="cia-j1-rest-hourly.service":
            return cp(unit, **changes.get("n2_service", {}))
        raise AssertionError(f"unexpected service {unit}")
    return call


class N50WSPrecloseTimerTests(TestCase):
    def test_preclose_ws_is_30s_before_utc_close_and_never_old_rest(self):
        service, timer, fallback=render_n50_ws_systemd(
            owner="cia-probe",repo=R,python=P,
            manifest=M,ws_directory=W,
        )
        self.assertEqual(timer.count("OnCalendar="),1)
        self.assertIn("OnCalendar=*-*-* *:59:30 UTC",timer)
        self.assertIn("AccuracySec=1s",timer)
        self.assertIn("RandomizedDelaySec=0",timer)
        self.assertIn("Persistent=false",timer)
        self.assertIn("Unit=cia-j1-n50-ws.service",timer)
        self.assertNotIn("cia-j1-n50-managed",timer)
        self.assertIn("scripts.run_j1_n50_ws_owner_cached_once",service)
        self.assertNotIn("scripts.run_j1_n50_managed_once",service)
        self.assertIn("ReadWritePaths="+W,service)
        self.assertIn("User=cia-probe",service)
        self.assertIn("OnFailure=cia-j1-n50-ws-fallback.service",service)
        self.assertIn("ExecStart=-/usr/bin/systemctl disable --now cia-j1-n50-ws.timer",fallback)
        self.assertIn("ExecStartPost=/usr/bin/systemctl enable --now cia-j1-rest-hourly.timer",fallback)
        self.assertNotIn("systemctl enable",service+timer)
        self.assertNotIn("@",service+timer+fallback)

        # The original REST timer must remain at HH:01:05 untouched.
        original=(Path(__file__).resolve().parents[1]/"deploy/systemd/cia-j1-n50-managed.timer.template").read_text("ascii")
        self.assertIn("OnCalendar=*-*-* *:01:05 UTC",original)
        self.assertNotIn("OnCalendar=*-*-* *:59:30 UTC",original)

    def test_invalid_root_paths_overlap_and_injections_fail_without_writes(self):
        safe={"owner":"cia-probe","repo":R,"python":P,"manifest":M,"ws_directory":W}
        for changed in (
            {"owner":"root"},
            {"owner":"cia-probe;touch"},
            {"repo":R+";bad"},
            {"ws_directory":M},
            {"ws_directory":M+"/nested"},
            {"ws_directory":"/home/cia-probe/agent/j1-n50-managed-d296-private"},
            {"ws_directory":"/home/cia-probe/agent/j1-n50-managed-d296-private/new"},
            {"ws_directory":"/tmp/temporary"},
            {"ws_directory":"relative"},
            {"ws_directory":W+"/../oops"},
            {"ws_directory":R+"/ws"},
            {"python":""},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                render_n50_ws_systemd(**(safe|changed))

    def test_no_optin_preflight_does_not_call_systemctl(self):
        with patch.object(gate.subprocess,"run",
                          side_effect=AssertionError("not opted in")):
            r=gate.n50_ws_systemd_isolation()
        self.assertEqual(r["status"],"optin_required")
        self.assertFalse(r["systemd_modified"])
        self.assertFalse(r["n50_ws_start_authorized"])
        self.assertEqual(r["network_requests"],0)
        self.assertFalse(r["orders_sent"])

    def test_both_rest_collectors_must_be_quiesced(self):
        seen=[]
        with patch.object(gate.os,"name","posix"),\
             patch.object(gate.os,"getuid",return_value=1000),\
             patch.object(gate.os,"geteuid",return_value=1000):
            r=gate.n50_ws_systemd_isolation(
                require_old_collectors_quiesced=True,
                command_runner=eligible_runner(seen),
            )
        self.assertEqual(r["status"],"old_collectors_quiesced_preflight_only")
        self.assertTrue(r["n2_quiesced"])
        self.assertTrue(r["old_rest_timer_disabled"])
        self.assertTrue(r["old_rest_service_stopped"])
        self.assertFalse(r["n50_ws_start_authorized"])
        self.assertFalse(r["systemd_modified"])
        self.assertEqual([x[2] for x in seen],[
            "cia-j1-rest-hourly.timer","cia-j1-rest-hourly.service",
            "cia-j1-n50-managed.timer","cia-j1-n50-managed.service",
        ])

    def test_live_n2_or_old_n50_timer_blocks_before_ws(self):
        for changed in (
            {"n2_timer":{"active":"active","enabled":"enabled"}},
            {"n2_service":{"active":"active"}},
            {"old_timer":{"active":"active","enabled":"enabled"}},
            {"old_timer":{"active":"inactive","enabled":"enabled"}},
            {"old_timer":{"load":"not-found"}},
            {"old_service":{"active":"active"}},
            {"old_service":{"active":"activating"}},
        ):
            with self.subTest(changed=changed),\
                 patch.object(gate.os,"name","posix"),\
                 patch.object(gate.os,"getuid",return_value=1000),\
                 patch.object(gate.os,"geteuid",return_value=1000):
                result=gate.n50_ws_systemd_isolation(
                    require_old_collectors_quiesced=True,
                    command_runner=eligible_runner([],**changed),
                )
            self.assertEqual(result["status"],"blocked")
            self.assertFalse(result["n50_ws_start_authorized"])
            self.assertFalse(result["systemd_modified"])

    def test_root_denied_and_service_errors_abstain(self):
        with patch.object(gate.os,"name","posix"),\
             patch.object(gate.os,"getuid",return_value=0),\
             patch.object(gate.os,"geteuid",return_value=0):
            out=gate.n50_ws_systemd_isolation(
                require_old_collectors_quiesced=True,
                command_runner=lambda *_a,**_k: (_ for _ in ()).throw(
                    AssertionError("root must never probe"),
                ),
            )
        self.assertEqual(out["status"],"blocked")
        with patch.object(gate.os,"name","posix"),\
             patch.object(gate.os,"getuid",return_value=1000),\
             patch.object(gate.os,"geteuid",return_value=1000):
            out=gate.n50_ws_systemd_isolation(
                require_old_collectors_quiesced=True,
                command_runner=lambda *_a,**_k: SimpleNamespace(
                    returncode=1,stdout="",stderr="denied"),
            )
        self.assertEqual(out["status"],"blocked")


if __name__=="__main__":
    main()
