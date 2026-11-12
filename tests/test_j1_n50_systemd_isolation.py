"""D295: offline N50 systemd preflight and inert service renderer."""
from __future__ import annotations
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.preflight_j1_n50_systemd_isolation import (
    n50_systemd_n2_quiescence,
)
from scripts.render_j1_n50_managed_systemd import (
    render_n50_managed_systemd,
)

P = "/home/cia-probe/agent/ws-venv/bin/python"
R = "/home/cia-probe/agent/repo"
D = "/home/cia-probe/agent/n50-managed"


def exit_result(state="inactive",code=0,stderr=""):
    return SimpleNamespace(returncode=code,stdout=state+"\n",stderr=stderr)


class N50ServiceIsolationTests(unittest.TestCase):
    def test_no_optin_does_not_read_or_modify_systemd(self):
        with patch("subprocess.run",side_effect=AssertionError("systemctl forbidden")):
            out=n50_systemd_n2_quiescence()
        self.assertEqual(out["status"],"optin_required")
        self.assertFalse(out["n50_start_authorized"])
        self.assertFalse(out["n2_systemd_modified"])
        self.assertEqual(out["network_requests"],0)
        self.assertFalse(out["orders_sent"])

    def test_both_legacy_units_must_be_inactive(self):
        observed=[]
        def safe(argv,**kw):
            observed.append((argv,kw))
            return exit_result()
        out=n50_systemd_n2_quiescence(
            require_n2_quiesced=True,command_runner=safe)
        self.assertEqual(out["status"],"n2_quiesced_preflight_only",out)
        self.assertTrue(out["n2_timer_inactive"])
        self.assertTrue(out["n2_service_inactive"])
        self.assertEqual(len(observed),2)
        self.assertEqual(observed[0][0],[
            "/usr/bin/systemctl","show","cia-j1-rest-hourly.timer",
            "--property=ActiveState","--value","--no-pager"])
        self.assertEqual(observed[1][0][2],"cia-j1-rest-hourly.service")
        self.assertTrue(all(x[1]["timeout"]==3 for x in observed))
        self.assertTrue(all(x[1]["check"] is False for x in observed))
        self.assertFalse(out["n50_start_authorized"])

    def test_active_failed_or_unknown_units_fail_closed(self):
        for states in (
            ("active","inactive"),("inactive","active"),
            ("failed","inactive"),("inactive","activating"),
            ("unknown","inactive"),("inactive","inactive"),
        ):
            for error in (None, "nonzero", "stderr"):
                if states == ("inactive","inactive") and error is None:
                    continue
                got=[]
                def bad(_argv,**_kw):
                    i=len(got)
                    got.append(i)
                    st=states[i]
                    return exit_result(
                        st,code=3 if error=="nonzero" else 0,
                        stderr="error" if error=="stderr" else "",
                    )
                with self.subTest(states=states,error=error):
                    out=n50_systemd_n2_quiescence(
                        require_n2_quiesced=True,command_runner=bad)
                    self.assertEqual(out["status"],"blocked",out)
                    self.assertFalse(out["n50_start_authorized"])

    def test_process_timeout_and_missing_systemctl_fail_closed(self):
        for ex in (
            OSError("missing"),
            subprocess.TimeoutExpired(cmd="systemctl",timeout=3),
        ):
            def fail(_argv,**_kw):
                raise ex
            r=n50_systemd_n2_quiescence(
                require_n2_quiesced=True,command_runner=fail)
            self.assertEqual(r["status"],"blocked")

    def test_renderer_keeps_timer_off_and_exec_guard(self):
        service,timer=render_n50_managed_systemd(
            owner="cia-probe",repo=R,python=P,root=D)
        self.assertIn("User=cia-probe",service)
        self.assertIn("WorkingDirectory="+R,service)
        self.assertIn("ReadWritePaths="+D,service)
        self.assertIn("UMask=0077",service)
        self.assertIn("scripts.preflight_j1_n50_systemd_isolation",service)
        self.assertIn("scripts.run_j1_n50_managed_once",service)
        self.assertIn("--enable-managed-n50-tick",service)
        self.assertIn("OnCalendar=*-*-* *:01:05 UTC",timer)
        self.assertIn("Persistent=false",timer)
        self.assertIn("Restart=no",service)
        self.assertNotIn("systemctl enable",service+timer)
        self.assertNotIn("@",service+timer)

    def test_renderer_rejects_root_injection_and_path_overlap(self):
        bad=[
            dict(owner="root"),
            dict(owner="cia-probe;whoami"),
            dict(repo="/home/cia-probe/agent/repo;rm"),
            dict(root=R+"/nested"),
            dict(root=R),
            dict(root="relative"),
            dict(root="/tmp/../private"),
            dict(python="/bad path/python"),
            dict(owner=""),
        ]
        for override in bad:
            with self.subTest(override=override):
                args=dict(owner="cia-probe",repo=R,python=P,root=D)
                args.update(override)
                with self.assertRaises(ValueError):
                    render_n50_managed_systemd(**args)


if __name__=="__main__":
    unittest.main()
