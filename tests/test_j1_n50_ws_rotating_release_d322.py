"""D322: install WS + epoch rotation in one root-gated reversible cutover.

Entire suite is offline. Never invokes real systemctl, network or orders.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from unittest import TestCase, main, skipUnless
from unittest.mock import patch

from scripts import release_j1_n50_ws_rotating_once as rel
from scripts.render_j1_n50_ws_rotating_systemd import (
    _EXPECTED_EPOCH_ROOT, _EXPECTED_STATE,
)

ROOT=Path(_EXPECTED_EPOCH_ROOT)
STATE=Path(_EXPECTED_STATE)
SOURCE=Path("/home/cia-probe/agent/j1-n50-ws-code-d322")
SHA="b"*40
UNITS=("ws-owner-service", "ws-preclose-timer", "ws-to-n2-fallback",
       "rotation-timer", "rotation-owner-service")


def invoke(**opts):
    args=dict(
        source=SOURCE,expected_sha=SHA,
        epoch_root=ROOT,state_directory=STATE,
    )
    args.update(opts)
    return rel.execute(**args)


class RotatingWSRootReleaseTests(TestCase):
    def test_default_is_inert_even_with_verified_preflight(self):
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_write",side_effect=AssertionError("write")),\
             patch.object(rel,"_run",side_effect=AssertionError("command")):
            for flags in (
                {},
                {"allow_systemd_modifications":True},
                {"confirm_rotating_ws_cutover":True},
            ):
                r=invoke(**flags)
                self.assertEqual(r["status"],"preflight_pass_no_changes")
                self.assertTrue(r["private_active_epoch_verified"])
                self.assertFalse(r["units_created"])
                self.assertFalse(r["n2_quiesced"])
                self.assertFalse(r["orders_sent"])

    def test_root_or_private_preflight_denial_never_changes_n2(self):
        with patch.object(rel,"preflight",side_effect=ValueError("bad owner")),\
             patch.object(rel,"_write",side_effect=AssertionError("write")),\
             patch.object(rel,"_run",side_effect=AssertionError("command")):
            r=invoke(confirm_rotating_ws_cutover=True,
                     allow_systemd_modifications=True)
        self.assertEqual(r["status"],"preflight_blocked_N2_untouched")
        self.assertFalse(r["units_created"])
        self.assertFalse(r["n2_quiesced"])
        self.assertFalse(r["private_active_epoch_verified"])

    def test_five_new_units_are_installed_before_switching_n2(self):
        commands=[]
        files=[]
        def call(argv,**kwargs):
            commands.append(tuple(argv))
            return ""
        def show(unit):
            if unit==rel.N2_TIMER:
                stopped=("/usr/bin/systemctl","disable","--now",
                         rel.N2_TIMER) in commands
                return dict(LoadState="loaded",
                            ActiveState="inactive" if stopped else "active",
                            UnitFileState="disabled" if stopped else "enabled")
            if unit in (rel.WS_TIMER,rel.ROT_TIMER):
                running=("/usr/bin/systemctl","enable","--now",unit) in commands
                return dict(LoadState="loaded",
                            ActiveState="active" if running else "inactive",
                            UnitFileState="enabled" if running else "disabled")
            return dict(LoadState="loaded",ActiveState="inactive",
                        UnitFileState="static")
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_write",side_effect=lambda n,s:files.append((n,s))),\
             patch.object(rel,"_run",side_effect=call),\
             patch.object(rel,"_show",side_effect=show),\
             patch.object(rel,"_old_units_and_collectors_ok",return_value=True):
            r=invoke(confirm_rotating_ws_cutover=True,
                     allow_systemd_modifications=True)
        self.assertEqual(r["status"],"n50_ws_with_36h_rotation_enabled",r)
        self.assertEqual(files,list(zip(rel._UNIT_ORDER,UNITS)))
        self.assertEqual(commands,[
            ("/usr/bin/systemctl","daemon-reload"),
            ("/usr/bin/systemctl","disable","--now",rel.N2_TIMER),
            ("/usr/bin/systemctl","enable","--now",rel.WS_TIMER),
            ("/usr/bin/systemctl","enable","--now",rel.ROT_TIMER),
        ])
        self.assertTrue(r["n2_quiesced"])
        self.assertTrue(r["n50_ws_timer_enabled"])
        self.assertTrue(r["n50_ws_rotation_timer_enabled"])
        self.assertFalse(r["old_n50_rest_database_modified"])
        self.assertFalse(r["orders_sent"])

    def test_failure_while_installing_new_units_keeps_n2_active(self):
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_write",side_effect=OSError("read-only systemd")),\
             patch.object(rel,"_run",side_effect=AssertionError("no command")),\
             patch.object(rel,"_rollback",
                          side_effect=AssertionError("no cutover attempted")):
            r=invoke(confirm_rotating_ws_cutover=True,
                     allow_systemd_modifications=True)
        self.assertEqual(r["status"],"ws_rotating_unit_install_failed_N2_untouched")
        self.assertFalse(r["n2_quiesced"])
        self.assertFalse(r["n50_ws_timer_enabled"])

    def test_any_partial_isolation_triggers_dual_timer_rollback(self):
        for failed_unit in (rel.N2_TIMER,rel.WS_TIMER,rel.ROT_TIMER):
            with self.subTest(failed_unit=failed_unit):
                def call(argv,**kwargs):
                    if argv==["/usr/bin/systemctl",
                              "disable" if failed_unit==rel.N2_TIMER else "enable",
                              "--now",failed_unit]:
                        raise RuntimeError("simulated partial systemd mutation")
                    return ""
                with patch.object(rel,"preflight",return_value=UNITS),\
                     patch.object(rel,"_write"),\
                     patch.object(rel,"_run",side_effect=call),\
                     patch.object(rel,"_show",return_value={
                         "LoadState":"loaded","ActiveState":"inactive",
                         "UnitFileState":"static"}),\
                     patch.object(rel,"_old_units_and_collectors_ok",
                                  return_value=True),\
                     patch.object(rel,"_rollback",return_value=True) as rollback:
                    r=invoke(confirm_rotating_ws_cutover=True,
                             allow_systemd_modifications=True)
                self.assertEqual(r["status"],"rolled_back_to_N2")
                self.assertTrue(r["n2_restored_after_failure"])
                self.assertFalse(r["n50_ws_timer_enabled"])
                rollback.assert_called_once()

    def test_rollback_disables_both_new_timers_and_restores_n2(self):
        commands=[]
        def fake(argv,**kw):
            commands.append(tuple(argv))
            return ""
        with patch.object(rel,"_run",side_effect=fake),\
             patch.object(rel,"_show",side_effect=lambda u:{
                "LoadState":"loaded",
                "ActiveState":"active" if u==rel.N2_TIMER else "inactive",
                "UnitFileState":"enabled" if u==rel.N2_TIMER else "disabled",
             }):
            self.assertTrue(rel._rollback())
        self.assertEqual(commands,[
            ("/usr/bin/systemctl","disable","--now",rel.ROT_TIMER),
            ("/usr/bin/systemctl","disable","--now",rel.WS_TIMER),
            ("/usr/bin/systemctl","enable","--now",rel.N2_TIMER),
        ])

    @skipUnless(os.name=="posix", "root systemd renderer requires POSIX absolute paths")
    def test_root_renderer_keeps_ws_preclose_rotation_and_dual_fallback(self):
        man=ROOT/"j1-n50-ws-manifest-1800000000000"
        ws=ROOT/"j1-n50-ws-private-1800000000000"
        service,timer,fallback,rot_timer,rot_service=rel._render(
            source=SOURCE,state_directory=STATE,epoch_root=ROOT,
            manifest=man,ws=ws,
        )
        self.assertIn("scripts.run_j1_n50_ws_owner_active_once",service)
        self.assertNotIn("scripts.run_j1_n50_ws_owner_cached_once",service)
        self.assertIn("OnFailure=cia-j1-n50-ws-fallback.service",service)
        self.assertIn("OnCalendar=*-*-* *:59:30 UTC",timer)
        self.assertIn("OnCalendar=*-*-* *:01:15 UTC",rot_timer)
        self.assertIn("scripts.rotate_j1_n50_ws_epoch_once",rot_service)
        self.assertIn("cia-j1-n50-ws-rotate.timer",fallback)
        self.assertIn("cia-j1-n50-ws.timer",fallback)
        self.assertIn("ExecStartPost=/usr/bin/systemctl enable --now cia-j1-rest-hourly.timer",fallback)
        self.assertEqual(fallback.count("ExecStart=-"),2)
        self.assertNotIn("scripts.run_j1_n50_managed_once",
                         service+timer+fallback+rot_service+rot_timer)

    def test_entry_command_is_one_gate_and_does_not_call_D320(self):
        script=(Path(__file__).resolve().parents[1]/
            "deploy/vps/prepare_install_j1_n50_ws_rotating_d322_once.sh"
        ).read_text("ascii")
        self.assertIn("scripts.rotate_j1_n50_ws_epoch_once",script)
        self.assertIn("scripts.release_j1_n50_ws_rotating_once",script)
        self.assertIn("--confirm-rotating-ws-cutover --allow-systemd-modifications",
                      script)
        self.assertIn("if (( PHASE < 75 )); then",script)
        self.assertIn("elif (( PHASE <= 90 )); then",script)
        self.assertNotIn("scripts.release_j1_n50_ws_owner_once",script)
        self.assertNotIn("rm -rf",script)
        self.assertNotIn("cia-j1-n50-managed.service",script)
        self.assertNotIn("systemctl disable --now cia-j1-rest-hourly.timer",script)

    @skipUnless(os.name=="posix","Bash is POSIX Linux-only")
    def test_script_has_valid_bash_syntax(self):
        path=(Path(__file__).resolve().parents[1]/
            "deploy/vps/prepare_install_j1_n50_ws_rotating_d322_once.sh")
        got=subprocess.run(
            ["/usr/bin/bash","-n",str(path)],
            capture_output=True,text=True,timeout=10,check=False,
        )
        self.assertEqual(got.returncode,0,got.stderr)


if __name__=="__main__":
    main()
