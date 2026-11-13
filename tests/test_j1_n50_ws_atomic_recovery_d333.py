"""J1/D333: rollback transaction tested offline, with mock runuser and N2."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/vps/recover_j1_n50_ws_d333_once.sh"
OLD_SHA = "c1fbd4cd46bba108be14859b9a04bb4184c3e91f"


def source() -> str:
    return SCRIPT.read_text(encoding="ascii")


def cleanup_functions() -> str:
    s = source()
    return s[s.index("restore_old_code_pin() {"):
             s.index("\ntrap recovery_exit_cleanup EXIT")]


class D333AtomicRecoveryTests(unittest.TestCase):
    def test_exact_old_pin_and_owner_audit_precede_n2_cutover(self):
        s = source()
        self.assertIn(f"OLD_SHA={OLD_SHA}", s)
        self.assertIn('NEW_SHA="$1"', s)
        for suite in (
            "test_j1_n50_ws_symbol_grammar_d332.py",
            "test_j1_n50_ws_single_letter_usdt_d332.py",
            "test_j1_n50_ws_halt_taxonomy_d331.py",
            "test_j1_n50_ws_server_bounded_trade_clock_d329.py",
            "test_j1_n50_ws_temporal_quarantine_d328.py",
            "test_j1_n50_ws_open_trade_timestamp_d327.py",
            "test_j1_n50_ws_confirm_boundary_d326.py",
        ):
            self.assertIn(f"-p {suite} -q", s)
        self.assertLess(
            s.index("scripts.audit_j1_n50_ws_symbol_grammar_d332_once"),
            s.index("D333_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
        )
        self.assertLess(
            s.index("D333_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
            s.index('$SYSTEMCTL disable --now "$N2"'),
        )
        self.assertNotIn("prepare_install_j1_n50_ws_rotating_d322_once.sh", s)
        self.assertNotIn("rotate_j1_n50_ws_epoch_once", s)
        self.assertNotIn("rm -rf", s)
        self.assertNotIn("api.bybit.com", s)
        self.assertIn("failed|inactive) ;;", s)
        self.assertEqual(s.count("failed|inactive) ;;"), 2)
        self.assertIn("blocked: WS owner service not quiesced", s)
        self.assertIn('$SYSTEMCTL stop "$SERVICE"', s)
        self.assertIn("inactive|failed) ;;", s)
        self.assertLess(s.index('$SYSTEMCTL stop "$SERVICE"'),
                        s.index('$SYSTEMCTL enable --now "$N2"'))

    def test_compensation_installed_before_checkout_and_success_commit_last(self):
        s = source()
        self.assertLess(s.index("trap recovery_exit_cleanup EXIT"),
                        s.index('PIN_CHANGED=1\n$RUNUSER -u "$OWNER" -- "$GIT" -C "$CODE" checkout --quiet --detach "$NEW_SHA"'))
        self.assertIn('original_status="$?"', cleanup_functions())
        self.assertIn('trap - EXIT', cleanup_functions())
        self.assertIn("D333_RECOVERY_COMPENSATION_REQUIRES_OPERATOR", s)
        self.assertIn('if test "$PIN_CHANGED" = 1; then', s)
        self.assertIn('if test "$CUTOVER_STARTED" = 1; then', s)
        self.assertIn("CUTOVER_STARTED=0\nRECOVERY_FINALIZED=1", s)
        self.assertEqual(s.count("trap recovery_exit_cleanup EXIT"), 1)
        self.assertNotIn("trap rollback_on_exit EXIT", s)

    @unittest.skipUnless(os.name == "posix" and Path("/usr/bin/bash").exists(),
                         "mocked bash requires POSIX")
    def test_exit_trap_rollback_matrix_never_calls_real_admin(self):
        definitions = cleanup_functions()
        preamble = r"""
set -euo pipefail
OWNER=test
CODE=/synthetic/test
OLD_SHA=c1fbd4cd46bba108be14859b9a04bb4184c3e91f
NEW_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
RUNUSER=mock_runuser
GIT=mock_git
MOCK_PIN="$NEW_SHA"
mock_runuser() {
  case "$*" in
    *"checkout --quiet --detach $OLD_SHA")
      if test "$FAIL_PIN" = 1; then return 1; fi
      MOCK_PIN="$OLD_SHA"
      echo "TEST_CODE_RESTORED" >&2 ;;
    *"rev-parse HEAD") printf '%s\n' "$MOCK_PIN" ;;
    *"status --porcelain") printf '' ;;
    *) return 22 ;;
  esac
}
restore_n2() {
  echo "TEST_N2_RESTORE" >&2
  test "$FAIL_N2" != 1
}
"""
        cases = {
            "preflight_aborts": (1, 0, 0, 0, 0, 65, True, False),
            "cutover_aborts": (1, 1, 0, 0, 0, 65, True, True),
            "successful_release": (1, 0, 1, 0, 0, 0, False, False),
            "old_pin_restore_fails": (1, 0, 0, 1, 0, 75, False, False),
            "n2_restore_fails": (1, 1, 0, 0, 1, 75, True, True),
            "no_pin_touched": (0, 0, 0, 0, 0, 65, False, False),
        }
        for name, (pin, cutover, final, fail_pin, fail_n2, code,
                   expect_pin, expect_n2) in cases.items():
            with self.subTest(name=name):
                script = (preamble + definitions + "\n"
                          + f"PIN_CHANGED={pin}\nCUTOVER_STARTED={cutover}\n"
                          + f"RECOVERY_FINALIZED={final}\nFAIL_PIN={fail_pin}\n"
                          + f"FAIL_N2={fail_n2}\n"
                          + "trap recovery_exit_cleanup EXIT\n"
                          + f"exit {0 if final else 65}\n")
                res = subprocess.run(
                    ["/usr/bin/bash", "-c", script],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                self.assertEqual(res.returncode, code, res.stderr)
                self.assertEqual("TEST_CODE_RESTORED" in res.stderr, expect_pin)
                self.assertEqual("TEST_N2_RESTORE" in res.stderr, expect_n2)
                if fail_pin or fail_n2:
                    self.assertIn("D333_RECOVERY_COMPENSATION_REQUIRES_OPERATOR", res.stderr)
                self.assertNotIn("/home/cia-probe", res.stdout + res.stderr)

    @unittest.skipUnless(os.name == "posix" and Path("/usr/bin/bash").exists(),
                         "bash syntax check POSIX")
    def test_shell_syntax(self):
        out = subprocess.run(
            ["/usr/bin/bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main()
