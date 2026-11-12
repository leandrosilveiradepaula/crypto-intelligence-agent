"""D320: root WS cutover is OFF by default, pinned and reversible, no VPS writes."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import unittest
from unittest.mock import patch

from scripts import release_j1_n50_ws_owner_once as rel

BASE=Path("/home/cia-probe/agent")
SRC=BASE/"j1-n50-ws-a-code-20261112"
MANIFEST=BASE/"j1-n50-ws-manifest-20261112"
WS=BASE/"j1-n50-ws-private-20261112"
SHA="a"*40
UNITS=(
    "unit-service-from-pinned-repo",
    "unit-timer-preclose",
    "unit-onfailure-to-N2",
)


def do_release(**params):
    args=dict(source=SRC,expected_sha=SHA,manifest=MANIFEST,ws_dir=WS)
    args.update(params)
    return rel.execute(**args)


class N50WSRootReleaseTests(unittest.TestCase):
    def test_default_does_not_change_systemd_with_clean_preflight(self):
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_run",side_effect=AssertionError("no commands")),\
             patch.object(rel,"_write_new_unit_once",
                          side_effect=AssertionError("no file writes")):
            for flags in (
                {}, {"allow_systemd_modifications":True},
                {"confirm_n50_ws_cutover":True},
            ):
                with self.subTest(flags=flags):
                    report=do_release(**flags)
                    self.assertEqual(report["status"],"preflight_pass_no_changes")
                    self.assertFalse(report["units_created"])
                    self.assertFalse(report["n2_quiesced"])
                    self.assertFalse(report["n50_ws_timer_enabled"])
                    self.assertFalse(report["orders_sent"])

    def test_preflight_denial_never_creates_units_or_disables_n2(self):
        with patch.object(rel,"preflight",side_effect=ValueError("invalid")),\
             patch.object(rel,"_write_new_unit_once",
                          side_effect=AssertionError("no writes")),\
             patch.object(rel,"_run",
                          side_effect=AssertionError("no systemctl")):
            r=do_release(confirm_n50_ws_cutover=True,
                         allow_systemd_modifications=True)
        self.assertEqual(r["status"],"preflight_blocked_N2_untouched")
        self.assertFalse(r["preflight_verified"])
        self.assertFalse(r["n2_quiesced"])
        self.assertFalse(r["n50_ws_timer_enabled"])

    def test_root_success_enables_ONLY_new_ws_after_isolating_n2(self):
        cmds=[]
        writes=[]
        def run(argv,**kw):
            cmds.append(tuple(argv))
            return ""
        def show(unit):
            if unit==rel.N2_TIMER:
                active=any(c[1:3]==("disable","--now") for c in cmds)
                return {
                    "LoadState":"loaded",
                    "ActiveState":"inactive" if active else "active",
                    "UnitFileState":"disabled" if active else "enabled",
                }
            if unit==rel.WS_TIMER:
                active=any(c[1:3]==("enable","--now") for c in cmds)
                return {
                    "LoadState":"loaded",
                    "ActiveState":"active" if active else "inactive",
                    "UnitFileState":"enabled" if active else "disabled",
                }
            return {"LoadState":"loaded","ActiveState":"inactive",
                    "UnitFileState":"static"}
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_run",side_effect=run),\
             patch.object(rel,"_show",side_effect=show),\
             patch.object(rel,"_old_units_and_collectors_ok",return_value=True),\
             patch.object(rel,"_write_new_unit_once",
                          side_effect=lambda name,data:writes.append((name,data))):
            r=do_release(confirm_n50_ws_cutover=True,
                         allow_systemd_modifications=True)
        self.assertEqual(r["status"],"n50_ws_timer_enabled_N2_fallback_preserved")
        self.assertTrue(r["units_created"])
        self.assertTrue(r["n2_quiesced"])
        self.assertTrue(r["n50_ws_timer_enabled"])
        self.assertFalse(r["orders_sent"])
        self.assertEqual(writes,list(zip(
            (rel.WS_SERVICE,rel.WS_TIMER,rel.WS_FALLBACK),UNITS,
        )))
        self.assertEqual(cmds,[
            ("/usr/bin/systemctl","daemon-reload"),
            ("/usr/bin/systemctl","disable","--now",rel.N2_TIMER),
            ("/usr/bin/systemctl","enable","--now",rel.WS_TIMER),
        ])
        self.assertNotIn(rel.OLD_N50_TIMER,repr(cmds))

    def test_failed_to_enable_ws_rolls_back_to_n2(self):
        cmds=[]
        def fail(argv,**kw):
            cmds.append(tuple(argv))
            if list(argv)==["/usr/bin/systemctl","enable","--now",rel.WS_TIMER]:
                raise RuntimeError("service blocked")
            return ""
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_run",side_effect=fail),\
             patch.object(rel,"_show",
                          return_value={"LoadState":"loaded","ActiveState":"inactive",
                                        "UnitFileState":"disabled"}),\
             patch.object(rel,"_old_units_and_collectors_ok",return_value=True),\
             patch.object(rel,"_write_new_unit_once"),\
             patch.object(rel,"_rollback",return_value=True) as rollback:
            r=do_release(confirm_n50_ws_cutover=True,
                         allow_systemd_modifications=True)
        self.assertEqual(r["status"],"rolled_back_to_N2")
        self.assertTrue(r["n2_restored_after_failure"])
        self.assertFalse(r["n50_ws_timer_enabled"])
        self.assertEqual(rollback.call_count,1)
        self.assertFalse(r["orders_sent"])

    def test_failure_while_disabling_n2_still_invokes_rollback(self):
        def maybe(argv,**kw):
            if list(argv)==["/usr/bin/systemctl","disable","--now",rel.N2_TIMER]:
                raise RuntimeError("partially disabled N2")
            return ""
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_run",side_effect=maybe),\
             patch.object(rel,"_show",return_value={
                "LoadState":"loaded","ActiveState":"inactive",
                "UnitFileState":"static",
             }),\
             patch.object(rel,"_old_units_and_collectors_ok",return_value=True),\
             patch.object(rel,"_write_new_unit_once"),\
             patch.object(rel,"_rollback",return_value=True) as rb:
            r=do_release(confirm_n50_ws_cutover=True,
                         allow_systemd_modifications=True)
        self.assertEqual(r["status"],"rolled_back_to_N2")
        rb.assert_called_once()

    def test_failure_while_staging_units_does_not_touch_n2(self):
        with patch.object(rel,"preflight",return_value=UNITS),\
             patch.object(rel,"_write_new_unit_once",
                          side_effect=OSError("read-only systemd")),\
             patch.object(rel,"_run",side_effect=AssertionError("no systemctl")),\
             patch.object(rel,"_rollback",
                          side_effect=AssertionError("no rollback required")):
            r=do_release(confirm_n50_ws_cutover=True,
                         allow_systemd_modifications=True)
        self.assertEqual(r["status"],"ws_unit_install_failed_N2_untouched")
        self.assertFalse(r["units_created"])
        self.assertFalse(r["n2_quiesced"])

    def test_path_and_commit_regex_are_exact(self):
        self.assertTrue(rel._SAFE_PATH.fullmatch(str(SRC)))
        self.assertTrue(rel._SAFE_PATH.fullmatch(str(WS)))
        for path in (
            "/tmp/unsafe",
            "/home/cia-probe/agent/../unsafe",
            "/home/cia-probe/agent/with spaces",
            "/home/cia-probe/agent/",
            "/home/cia-probe/agent/ok;rm",
        ):
            self.assertIsNone(rel._SAFE_PATH.fullmatch(path))
        self.assertTrue(rel._SHA.fullmatch(SHA))
        self.assertIsNone(rel._SHA.fullmatch(SHA+";"))

    @unittest.skipUnless(os.name == "posix", "Bash installer is POSIX-only")
    def test_staging_script_has_valid_bash_syntax(self):
        path=Path(__file__).resolve().parents[1]/"deploy/vps/prepare_install_j1_n50_ws_d320_once.sh"
        result=subprocess.run(
            ["/usr/bin/bash","-n",str(path)],
            capture_output=True,text=True,timeout=10,check=False,
        )
        self.assertEqual(result.returncode,0,result.stderr)

    def test_staging_script_never_modifies_existing_rest_n50_template(self):
        path=Path(__file__).resolve().parents[1]/"deploy/vps/prepare_install_j1_n50_ws_d320_once.sh"
        src=path.read_text("ascii")
        self.assertIn("set -euo pipefail",src)
        self.assertIn("PY=/home/cia-probe/agent/ws-venv/bin/python",src)
        self.assertIn("scripts.run_j1_current_ranked_epoch_once capture-seal",src)
        self.assertIn("scripts.cache_j1_n50_ws_metadata_owner_once",src)
        self.assertIn("scripts.release_j1_n50_ws_owner_once",src)
        self.assertIn("--confirm-n50-ws-cutover --allow-systemd-modifications",src)
        self.assertIn("STAGE_5_ROOT_CUTOVER_WITH_FAILBACK",src)
        self.assertNotIn("rm -rf",src)
        self.assertNotIn("cia-j1-n50-managed.timer --now",src)
        self.assertNotIn("scripts.run_j1_n50_managed_once",src)


if __name__=="__main__":
    unittest.main()
