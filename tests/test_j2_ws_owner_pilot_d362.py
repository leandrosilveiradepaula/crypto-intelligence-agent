"""D362 / #658: root pilot remains gated; test the public shell contract offline."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "vps" / "j2_ws_prospective_owner_pilot_d362_once.sh"
SHA = "a"*40


class OwnerPilotD362ContractTests(unittest.TestCase):
    def test_script_is_syntactically_valid(self):
        self.assertTrue(SCRIPT.is_file())
        if shutil.which("bash") is None:
            self.skipTest("bash is unavailable on this runner")
        done = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_narrow_modes_and_guards_are_present(self):
        data = SCRIPT.read_text(encoding="utf-8")
        for needle in (
            "--preflight-os", "--confirm-owner-capture", "--score-once",
            "test \"$(/usr/bin/id -u)\" -eq 0",
            "test \"$(/usr/bin/hostname)\" = \"$HOST\"",
            "NTPSynchronized", "UnitFileState", "ActiveState",
            "/usr/sbin/runuser", "cia-probe", "/usr/bin/git",
            "rev-parse HEAD", "status --porcelain", "test ! -L",
            "j2_ws_owner_preflight.py", "test_j2_ws_owner_preflight.py",
            "test_j2_ws_prospective_ledger.py", "test_j2_n50_ws_private_screen.py",
            "owner_cli preflight", "owner_cli capture", "owner_cli score",
            "safe_report", "PILOT_JSON", "D362_CAPTURE_ABSTAIN_NO_RETRY",
            "D362_SCORE_ABSTAIN_NO_RETRY", "object_pairs_hook=distinct",
            "D362_NET_REFERENCE_COSTED_BPS_SUM", "D362_GROSS_REFERENCE_BPS_SUM",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, data)

    def test_does_not_mutate_n50_or_enable_trading(self):
        data = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("systemctl enable", data)
        self.assertNotIn("systemctl restart", data)
        self.assertNotIn("systemctl start", data)
        self.assertNotIn("systemctl stop", data)
        self.assertNotIn("systemd-run", data)
        self.assertNotIn("sudo ", data)
        self.assertNotIn("run_j1_current_ranked_epoch_once", data)
        self.assertNotIn("order/create", data)
        self.assertNotIn("--allow-public-network", data)
        self.assertNotIn("curl ", data)
        self.assertNotIn(" rm -rf ", data)
        self.assertIn("approved_for_signals", data)
        self.assertIn("orders_sent", data)

    @unittest.skipUnless(os.name == "posix" and os.geteuid() != 0,
                         "non-root denial requires POSIX nonroot runner")
    def test_any_mode_refuses_before_network_or_code_staging(self):
        for args in (
            ["--preflight-os", SHA],
            ["--confirm-owner-capture", SHA],
            ["--score-once", SHA, "1", "100", "4", "6", "2", "3"],
        ):
            with self.subTest(mode=args[0]):
                p = subprocess.run(["bash", str(SCRIPT), *args],
                                   capture_output=True, text=True, timeout=5)
                self.assertEqual(p.returncode, 77)
                self.assertEqual(p.stdout.strip(), "D362_BLOCKED_ROOT_REQUIRED")
                self.assertNotIn("github.com", p.stdout + p.stderr)

    def test_invalid_sha_fails_before_host_or_code_access(self):
        if shutil.which("bash") is None:
            self.skipTest("bash unavailable")
        p = subprocess.run(["bash", str(SCRIPT), "--confirm-owner-capture", "not-a-sha"],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 77)
        self.assertEqual(p.stdout.strip(), "D362_BLOCKED_SHA40_REQUIRED")

    def test_unknown_mode_fails_without_side_effects(self):
        if shutil.which("bash") is None:
            self.skipTest("bash unavailable")
        p = subprocess.run(["bash", str(SCRIPT), "--deploy-all", SHA],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 77)
        self.assertEqual(p.stdout.strip(), "D362_BLOCKED_MODE")


if __name__ == "__main__":
    unittest.main()
