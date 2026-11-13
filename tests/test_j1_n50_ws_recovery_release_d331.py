"""D331 in-place root diagnostic recovery: pinned code, N2 until preflight."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] /
          "deploy/vps/recover_j1_n50_ws_d331_once.sh")


class RecoveryD331Tests(unittest.TestCase):
    def test_uses_exact_installed_d329_pin_without_new_bootstrap(self):
        source = SCRIPT.read_text(encoding="ascii")
        self.assertIn(
            "OLD_SHA=a2fa30ad499e97f3cb836c5a7fd66eb9f43ae1b1", source
        )
        self.assertIn('NEW_SHA="$1"', source)
        self.assertIn("test_j1_n50_ws_halt_taxonomy_d331.py", source)
        for suite in (
            "test_j1_n50_ws_server_bounded_trade_clock_d329.py",
            "test_j1_n50_ws_temporal_quarantine_d328.py",
            "test_j1_n50_ws_open_trade_timestamp_d327.py",
            "test_j1_n50_ws_confirm_boundary_d326.py",
        ):
            self.assertIn(suite, source)
        self.assertNotIn("prepare_install_j1_n50_ws_rotating_d322_once.sh", source)
        self.assertNotIn("rotate_j1_n50_ws_epoch_once", source)
        self.assertNotIn("rm -rf", source)
        self.assertNotIn("sqlite3 ", source)
        self.assertNotIn("api.bybit.com", source)

    def test_n2_survives_until_tests_and_owner_pointer_checks(self):
        source = SCRIPT.read_text("ascii")
        self.assertLess(
            source.index("D331_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
            source.index('$SYSTEMCTL disable --now "$N2"'),
        )
        self.assertIn("load_active_n50_ws_epoch", source)
        self.assertIn("current_at_ms=time.time_ns()//1000000", source)
        self.assertIn("D331_RECOVERY_ROLLED_BACK_TO_N2", source)
        self.assertIn("trap rollback_on_exit EXIT", source)
        self.assertIn('if ! $SYSTEMCTL enable --now "$WS"; then rollback_exit; fi',
                      source)
        self.assertIn('if ! $SYSTEMCTL enable --now "$ROT"; then rollback_exit; fi',
                      source)
        self.assertIn("D331_RECOVERY_TIMERS_ENABLED_NO_ORDERS", source)

    @unittest.skipUnless(os.name == "posix", "bash syntax check POSIX")
    def test_syntax(self):
        p = subprocess.run(
            ["/usr/bin/bash", "-n", str(SCRIPT)],
            text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
