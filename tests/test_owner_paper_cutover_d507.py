"""D507: secure, opt-in, PAPER-only VPS cutover contract."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "deploy" / "vps"
          / "paper_research" / "owner_paper_cutover_d507_once.sh")


class PaperCutoverScriptD507Tests(unittest.TestCase):
    def test_source_guarded_and_j1_never_stopped(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/usr/bin/env bash\n"))
        self.assertIn('APPROVED_SHA="056845fdc46b8c2d1b08acd86be75e59dd368bac"', text)
        self.assertIn('EXPECTED_HOST="${CIA_D507_EXPECT_HOST:-}"', text)
        self.assertIn('explicit_host_pin_required', text)
        self.assertNotIn('srv1319424', text)
        self.assertIn('read -r -p', text)
        self.assertIn('AUTORIZO CUTOVER PAPER', text)
        self.assertIn('preflight_paper_owner_d505', text)
        self.assertIn('ROLLBACK_ARMED=1', text)
        self.assertIn('D507_ROLLBACK=START', text)
        self.assertIn('http://127.0.0.1:8766/api/paper-history', text)
        self.assertIn('check_zero_open', text)
        self.assertIn('test "$(systemctl is-active "$J1")" = "active"', text)
        self.assertNotIn('systemctl stop "$J1"', text)
        self.assertNotIn('systemctl restart "$J1"', text)
        self.assertNotIn('trade-api', text)
        self.assertNotIn('withdraw', text.lower())
        self.assertNotIn('order/create', text.lower())
        self.assertLess(text.index('D507_PREFLIGHT=PASS_NO_SERVICE_CHANGED'),
                        text.index('read -r -p'))
        self.assertLess(text.index('read -r -p'),
                        text.index('systemctl stop "$MOTOR"'))
        self.assertLess(text.index('ROLLBACK_ARMED=1'),
                        text.index('systemctl stop "$MOTOR"'))
        self.assertIn('PYTHONDONTWRITEBYTECODE=1', text)

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"),
                         "bash syntax only on Linux/POSIX")
    def test_bash_parses_without_executing(self):
        process = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, timeout=5, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
