"""D515 cutover source contract: no production operation in tests."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/vps/paper_research/owner_paper_cutover_d515_once.sh"

class PaperReleaseD515Tests(unittest.TestCase):
    def test_scope_gate_and_preserved_rollback(self):
        s = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("exact_reviewed_main_sha_required", s)
        self.assertIn("main_moved_or_unapproved_revision", s)
        self.assertIn("installed_sha_changed", s)
        self.assertIn("AUTORIZO CUTOVER PAPER", s)
        self.assertIn("preflight_paper_owner_d505", s)
        self.assertLess(s.index('read -r -p'), s.index('ROLLBACK_ARMED=1\nsystemctl stop "$MOTOR"'))
        self.assertIn("with _owner_lock(", s)
        self.assertIn('rm -f -- "$MOTOR_DROP" "$PANEL_DROP"', s)
        self.assertNotIn('rm -f -- "$MOTOR_OLD"', s)
        self.assertIn("D515_PANEL_ENDPOINTS=PASS", s)
        self.assertLess(s.rindex('systemctl start "$PANEL"'), s.rindex('systemctl start "$MOTOR"'))
        self.assertIn("D515_HISTORICAL_COMPARISON_SAMPLE_NOT_YET_VALIDATED=YES", s)
        for op in ("start", "stop", "restart", "disable", "enable"):
            self.assertNotIn(f'systemctl {op} "$J1"', s)

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "bash syntax on POSIX")
    def test_shell_syntax(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True,
                           text=True, timeout=5, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)

if __name__ == "__main__":
    unittest.main()
