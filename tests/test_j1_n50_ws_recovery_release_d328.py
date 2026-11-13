"""D328 root recovery: no rebootstrap, N2 rollback and exact old pin."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"deploy/vps/recover_j1_n50_ws_d328_once.sh"


class D328RecoveryContractTests(unittest.TestCase):
    def test_exact_old_sha_and_triple_offline_test_gate(self):
        txt=SCRIPT.read_text("ascii")
        self.assertIn("OLD_SHA=dcd0e0adac8156db841704a430da0f7311793756",txt)
        self.assertIn('NEW_SHA="$1"',txt)
        for name in ("test_j1_n50_ws_temporal_quarantine_d328.py",
                     "test_j1_n50_ws_open_trade_timestamp_d327.py",
                     "test_j1_n50_ws_confirm_boundary_d326.py"):
            self.assertIn(name,txt)
        self.assertIn('test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active',txt)
        self.assertIn('test "$($SYSTEMCTL show "$SERVICE" -p ActiveState --value)" = failed',txt)
        self.assertIn("D328_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS",txt)
        self.assertNotIn("prepare_install_j1_n50_ws_rotating",txt)
        self.assertNotIn("rotate_j1_n50_ws_epoch_once",txt)
        self.assertNotIn("rm -rf",txt)
        self.assertNotIn("curl ",txt)

    def test_cutover_after_code_and_rollback_guaranteed(self):
        txt=SCRIPT.read_text("ascii")
        self.assertLess(txt.index("D328_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
                        txt.index('$SYSTEMCTL disable --now "$N2"'))
        self.assertIn('if ! $SYSTEMCTL enable --now "$WS"; then rollback_exit; fi',txt)
        self.assertIn('if ! $SYSTEMCTL enable --now "$ROT"; then rollback_exit; fi',txt)
        self.assertIn('trap rollback_on_exit EXIT',txt)
        self.assertIn('D328_RECOVERY_ROLLED_BACK_TO_N2',txt)

    @unittest.skipUnless(os.name=="posix","bash required")
    def test_bash_syntax(self):
        result=subprocess.run(["/usr/bin/bash","-n",str(SCRIPT)],
                              capture_output=True,text=True,timeout=10,check=False)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=="__main__":
    unittest.main()
