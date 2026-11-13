"""D327 owner-only recovery: static checks ensure no extra rank bootstrap."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"deploy/vps/recover_j1_n50_ws_d327_once.sh"


class D327RecoveryTests(unittest.TestCase):
    def test_only_old_d326_pinned_checkout_accepts_upgrade(self):
        contents=SCRIPT.read_text("ascii")
        self.assertIn("OLD_SHA=e6e4c40e12dcad5973fcad04ad6acfd7250721e6",contents)
        self.assertIn('NEW_SHA="$1"',contents)
        self.assertIn("test_j1_n50_ws_open_trade_timestamp_d327.py",contents)
        self.assertIn("test_j1_n50_ws_confirm_boundary_d326.py",contents)
        self.assertIn('test "$($SYSTEMCTL show "$SERVICE" -p ActiveState --value)" = failed',contents)
        self.assertIn('test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active',contents)
        self.assertIn('test "$($SYSTEMCTL show "$WS" -p ActiveState --value)" = inactive',contents)
        self.assertIn('test "$($SYSTEMCTL show "$ROT" -p ActiveState --value)" = inactive',contents)
        self.assertNotIn("prepare_install_j1_n50_ws_rotating",contents)
        self.assertNotIn("rotate_j1_n50_ws_epoch_once",contents)
        self.assertNotIn("rm -rf",contents)

    def test_owner_test_before_cutover_and_rollback_signal_trap(self):
        contents=SCRIPT.read_text("ascii")
        self.assertLess(contents.index("D327_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
                        contents.index('$SYSTEMCTL disable --now "$N2"'))
        self.assertIn('if ! $SYSTEMCTL enable --now "$WS"; then rollback_exit; fi',contents)
        self.assertIn('if ! $SYSTEMCTL enable --now "$ROT"; then rollback_exit; fi',contents)
        self.assertIn("trap rollback_on_exit EXIT",contents)
        self.assertIn("D327_RECOVERY_N2_ROLLED_BACK",contents.replace(
            "D327_RECOVERY_ROLLED_BACK_TO_N2","D327_RECOVERY_N2_ROLLED_BACK"
        ))

    @unittest.skipUnless(os.name=="posix", "Bash required")
    def test_bash_syntax(self):
        done=subprocess.run(
            ["/usr/bin/bash","-n",str(SCRIPT)],
            capture_output=True,text=True,timeout=10,check=False,
        )
        self.assertEqual(done.returncode,0,done.stderr)


if __name__=="__main__":
    unittest.main()
