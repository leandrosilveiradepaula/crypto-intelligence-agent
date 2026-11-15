"""D359: audit launcher is a one-shot isolated owner-only proof, not a release."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/vps/audit_j1_top50_rank_d359_once.sh"


class D359Top50AuditContract(unittest.TestCase):
    def test_isolated_owner_audit_contract(self):
        content = SCRIPT.read_text(encoding="utf-8")
        for required in (
            "set -euo pipefail", "umask 077", "SHA=", "j1-d359-top50-pit-",
            "runuser", "cia-probe", "2026-11-15T19:01:30Z",
            "git", "checkout --quiet --detach", "PYTHONDONTWRITEBYTECODE",
            "test_j1_auto_research_epoch.py",
            "test_j1_auto_current_closed24h_once.py",
            "test_j1_n50_ws_epoch_rotation_d321.py",
            "scripts.run_j1_current_ranked_epoch_once capture-seal",
            "rank_all_candidate_windows_complete24h",
            "rank_incomplete_24h_candidates",
            "D359_POOL_COMPLETENESS=PASS_RESEARCH_ONLY",
            "marketwide_top50_verified",
            "orders_sent",
        ):
            self.assertIn(required, content)
        # Fail closed if a future edit changes this into a service or DB
        # mutator. Live coordination is separately authorized.
        for forbidden in (
            "systemctl start", "systemctl restart", "systemctl stop",
            "systemctl disable", "systemctl enable",
            "UPDATE ", "DELETE FROM ", "DROP TABLE ",
            "INSERT INTO ", "CREATE TABLE ",
            "git reset --hard", "curl -X POST", "place_order(",
        ):
            self.assertNotIn(forbidden, content)
        self.assertNotIn("chmod 777", content)
        self.assertNotIn("sudo ", content)

    @unittest.skipUnless(shutil.which("bash"), "Bash not installed")
    def test_shell_syntax(self):
        result = subprocess.run(
            [shutil.which("bash"), "-n", str(SCRIPT)],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
