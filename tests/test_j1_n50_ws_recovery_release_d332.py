"""D332 root recovery static gates, no real service or network."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] /
          "deploy/vps/recover_j1_n50_ws_d332_once.sh")


class D332RecoveryTests(unittest.TestCase):
    def test_exact_d331_pin_and_six_offline_regressions(self):
        script = SCRIPT.read_text("ascii")
        self.assertIn(
            "OLD_SHA=c1fbd4cd46bba108be14859b9a04bb4184c3e91f", script)
        self.assertIn('NEW_SHA="$1"', script)
        for suite in (
            "test_j1_n50_ws_single_letter_usdt_d332.py",
            "test_j1_n50_ws_halt_taxonomy_d331.py",
            "test_j1_n50_ws_server_bounded_trade_clock_d329.py",
            "test_j1_n50_ws_temporal_quarantine_d328.py",
            "test_j1_n50_ws_open_trade_timestamp_d327.py",
            "test_j1_n50_ws_confirm_boundary_d326.py",
        ):
            self.assertIn('test -f "$CODE/tests/'+suite+'"', script)
            self.assertIn("-p "+suite+" -q", script)
        self.assertNotIn("prepare_install_j1_n50_ws_rotating", script)
        self.assertNotIn("rotate_j1_n50_ws_epoch_once", script)
        self.assertNotIn("rm -rf", script)
        self.assertNotIn("api.bybit.com", script)

    def test_n2_not_quiesced_before_all_tests_and_pointer(self):
        script = SCRIPT.read_text("ascii")
        self.assertLess(
            script.index("D332_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
            script.index('$SYSTEMCTL disable --now "$N2"'),
        )
        self.assertIn("load_active_n50_ws_epoch", script)
        self.assertIn("current_at_ms=time.time_ns()//1000000", script)
        self.assertIn("D332_RECOVERY_ROLLED_BACK_TO_N2", script)
        self.assertIn("trap rollback_on_exit EXIT", script)
        self.assertIn('if ! $SYSTEMCTL enable --now "$WS"; then rollback_exit; fi', script)
        self.assertIn('if ! $SYSTEMCTL enable --now "$ROT"; then rollback_exit; fi', script)
        self.assertIn("D332_RECOVERY_TIMERS_ENABLED_NO_ORDERS", script)

    @unittest.skipUnless(os.name=="posix", "bash available only on POSIX CI")
    def test_bash_syntax(self):
        p=subprocess.run(
            ["/usr/bin/bash", "-n", str(SCRIPT)],
            timeout=10, capture_output=True, text=True, check=False,
        )
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
