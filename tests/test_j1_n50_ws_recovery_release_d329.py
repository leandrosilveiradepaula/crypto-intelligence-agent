"""D329 root-only recovery static gate."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"deploy/vps/recover_j1_n50_ws_d329_once.sh"

class RecoveryD329Test(unittest.TestCase):
    def test_exact_old_pin_and_all_local_regressions(self):
        s=SCRIPT.read_text("ascii")
        self.assertIn("OLD_SHA=2b9fc08c168be4a187cc819c7e0102d1ee94f6cd",s)
        self.assertIn('NEW_SHA="$1"',s)
        for name in ("test_j1_n50_ws_server_bounded_trade_clock_d329.py",
                     "test_j1_n50_ws_temporal_quarantine_d328.py",
                     "test_j1_n50_ws_open_trade_timestamp_d327.py",
                     "test_j1_n50_ws_confirm_boundary_d326.py"):
            self.assertIn(name,s)
        self.assertNotIn("prepare_install_j1_n50_ws_rotating",s)
        self.assertNotIn("rotate_j1_n50_ws_epoch_once",s)
        self.assertNotIn("rm -rf",s)

    def test_n2_rollback_and_no_cutover_before_tests(self):
        s=SCRIPT.read_text("ascii")
        self.assertLess(s.index("D329_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
                        s.index('$SYSTEMCTL disable --now "$N2"'))
        self.assertIn('if ! $SYSTEMCTL enable --now "$WS"; then rollback_exit; fi',s)
        self.assertIn('if ! $SYSTEMCTL enable --now "$ROT"; then rollback_exit; fi',s)
        self.assertIn("trap rollback_on_exit EXIT",s)
        self.assertIn("D329_RECOVERY_ROLLED_BACK_TO_N2",s)

    @unittest.skipUnless(os.name=="posix","bash required")
    def test_syntax(self):
        result=subprocess.run(["/usr/bin/bash","-n",str(SCRIPT)],
                              capture_output=True,text=True,timeout=10,check=False)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":
    unittest.main()
