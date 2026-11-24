"""D525 cutover source contract; never invoke production operations in CI."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/vps/paper_research/owner_paper_cutover_d525_once.sh"


class PaperReleaseD525Tests(unittest.TestCase):
    def test_fixed_product_scope_gate_and_rollback(self):
        s = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('PRODUCT_SHA="b8a395ad4076f3eefb9731d78116ec791c508a1c"', s)
        self.assertIn("exact_reviewed_product_sha_required", s)
        self.assertIn("unapproved_product_revision", s)
        self.assertIn("92-cia-d525-pinned.conf", s)
        self.assertIn('RUN_LOCK="/run/cia-paper-d519-cutover.lock"', s)
        self.assertIn('"$MOTOR_BASE $MOTOR_OLD"', s)
        self.assertIn("AUTORIZO CUTOVER PAPER", s)
        self.assertIn("preflight_paper_owner_d505", s)
        self.assertLess(s.index("owner_preflight\ncheck_zero_open"), s.index("read -r -p"))
        self.assertLess(s.index("read -r -p"), s.index('ROLLBACK_ARMED=1\nsystemctl stop "$MOTOR"'))
        self.assertIn("with _owner_lock(", s)
        self.assertIn('rm -f -- "$MOTOR_DROP" "$PANEL_DROP"', s)
        self.assertNotIn('rm -f -- "$MOTOR_OLD"', s)
        self.assertIn("D525_PANEL_ENDPOINTS=PASS", s)
        self.assertIn("D525_RESEARCH_ENDPOINT_GUARDS=PASS", s)
        self.assertIn('b"matrix-grid-enabled" in html', s)
        for marker in ("rsi_filter", "matrix-bankroll", "matrix-margin", "matrix-leverage"):
            self.assertIn(marker, s)
        self.assertIn("same_origin_json_required", s)
        self.assertIn("research_request_rejected", s)
        self.assertIn('data=b\'{"horizon_hours":0}\'', s)
        self.assertNotIn("run_j3_combination_research_d520", s)
        self.assertNotIn("run_j3_retrospective_warmup_d516", s)
        self.assertLess(s.index("D525_RESEARCH_ENDPOINT_GUARDS=PASS"), s.rindex('systemctl start "$MOTOR"'))
        for op in ("start", "stop", "restart", "disable", "enable"):
            self.assertNotIn(f'systemctl {op} "$J1"', s)

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "bash syntax on POSIX")
    def test_shell_syntax(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True,
                           text=True, timeout=5, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
