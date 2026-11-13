"""D326 root recovery wrapper: offline static safeguards and bash syntax."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/vps/recover_j1_n50_ws_d326_once.sh"


class D326RootRecoveryContractTests(unittest.TestCase):
    def test_preflight_pins_old_code_and_fails_closed_without_rebootstrap(self):
        text = SCRIPT.read_text("ascii")
        self.assertIn("OLD_SHA=70dec97d0a3974ca15ead1dd3d3095532b9c6803", text)
        self.assertIn('NEW_SHA="$1"', text)
        self.assertIn('test "$($SYSTEMCTL show "$N2" -p ActiveState --value)" = active', text)
        self.assertIn('test "$($SYSTEMCTL show "$SERVICE" -p ActiveState --value)" = failed', text)
        self.assertIn('checkout --quiet --detach "$NEW_SHA"', text)
        self.assertIn('test -z "$($RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" status --porcelain)"', text)
        self.assertIn("test_j1_n50_ws_confirm_boundary_d326.py", text)
        self.assertNotIn("rotate_j1_n50_ws_epoch_once", text)
        self.assertNotIn("capture_and_seal_current_rank_once", text)
        self.assertNotIn("prepare_install_j1_n50_ws_rotating", text)
        self.assertNotIn("rm -rf", text)
        self.assertNotIn("curl ", text)
        self.assertNotIn("cia-j1-n50-managed.service", text)

    def test_n2_toggled_only_after_test_and_has_explicit_rollback(self):
        text = SCRIPT.read_text("ascii")
        self.assertLess(text.index("D326_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
                        text.index('$SYSTEMCTL disable --now "$N2"'))
        self.assertIn('if ! $SYSTEMCTL enable --now "$WS"; then rollback_exit; fi', text)
        self.assertIn('if ! $SYSTEMCTL enable --now "$ROT"; then rollback_exit; fi', text)
        self.assertIn('D326_RECOVERY_ROLLED_BACK_TO_N2', text)
        self.assertIn('D326_RECOVERY_N2_ROLLBACK_REQUIRES_OPERATOR', text)
        self.assertNotIn('delete', text)

    @unittest.skipUnless(os.name == "posix", "bash present only on Linux CI")
    def test_bash_syntax(self):
        result = subprocess.run(
            ["/usr/bin/bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
