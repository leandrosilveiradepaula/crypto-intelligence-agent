"""J1/D336 root recovery safety: offline syntax, preflight, mock rollback."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/vps/recover_j1_n50_ws_d336_once.sh"
OLD_SHA = "76ba09735b46e19e1e0af718c420d6a60cdd0067"


def source() -> str:
    return SCRIPT.read_text(encoding="ascii")


def functions() -> str:
    s = source()
    return s[s.index("restore_old_code_pin() {"):
             s.index("\ntrap recovery_exit_cleanup EXIT")]


@unittest.skipUnless(os.name == "posix" and Path("/usr/bin/bash").is_file(),
                     "mocked bash recovery requires POSIX")
class D336RecoveryTests(unittest.TestCase):
    def test_syntax_and_pinned_preflight(self):
        result = subprocess.run(
            ["/usr/bin/bash", "-n", str(SCRIPT)],
            capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        s = source()
        self.assertIn("OLD_SHA=" + OLD_SHA, s)
        self.assertIn('NEW_SHA="$1"', s)
        self.assertIn("HOST=srv1319424", s)
        self.assertIn("OWNER=cia-probe", s)
        self.assertIn('test "$(/usr/bin/timedatectl show -p NTPSynchronized --value)" = yes', s)
        self.assertIn("max_safe_seconds = (remaining + 105_000) // 1000", s)
        self.assertIn("test_j1_n50_ws_cached_runner_d317.py", s)
        self.assertIn("test_j1_n50_ws_hourly_attestation_d313.py", s)
        self.assertIn("test_j1_n50_ws_owner_hour_d315.py", s)
        self.assertIn("test_j1_n50_ws_single_letter_usdt_d332.py", s)
        self.assertLess(s.index("trap recovery_exit_cleanup EXIT"),
                        s.index('PIN_CHANGED=1\n$RUNUSER -u "$OWNER" -- "$GIT"'))
        self.assertLess(s.index("D336_RECOVERY_STAGE_2_CODE_PINNED_AND_OFFLINE_TESTS_PASS"),
                        s.index('$SYSTEMCTL disable --now "$N2"'))
        self.assertIn('merge-base --is-ancestor "$NEW_SHA" FETCH_HEAD', s)
        self.assertIn('$SYSTEMCTL stop "$SERVICE"', s)
        self.assertLess(s.index('$SYSTEMCTL stop "$SERVICE"'),
                        s.index('$SYSTEMCTL enable --now "$N2"'))
        self.assertEqual(s.count("safe_hourly_window\n"), 2)
        for prohibited in (
            "rm -rf", "curl ", "api.bybit.com", "prepare_install_j1_n50_ws_rotating_d322_once.sh",
            "scripts.audit_j1_n50_ws_symbol_grammar_d332_once", "sqlite3 ",
        ):
            self.assertNotIn(prohibited, s)
        self.assertIn("RECOVERY_FINALIZED=1\nCUTOVER_STARTED=0", s)

    def test_hourly_cutover_guard_boundaries_are_fail_closed(self):
        s = source()
        guard = s[s.index("safe_hourly_window() {"):s.index("\nsafe_hourly_window\n")]
        # No real clock, systemd, or owner state ever accessed by this test.
        guard = guard.replace("/usr/bin/date -u +%s", "fake_date")
        for phase, expected in ((0, 1), (179, 1), (180, 0),
                                (2000, 0), (3479, 0), (3480, 1), (3599, 1)):
            with self.subTest(phase=phase):
                script = (
                    "set -euo pipefail\n" + guard + "\n" +
                    f"fake_date() {{ echo {phase}; }}\n" +
                    "safe_hourly_window\n")
                r = subprocess.run(["/usr/bin/bash", "-c", script],
                                   capture_output=True, text=True, timeout=5)
                self.assertEqual(r.returncode, expected, r.stderr)

    def test_compensation_matrix_mocked_no_root_or_git(self):
        preamble = """
set -euo pipefail
OWNER=fixture
CODE=/fixture/no-access
OLD_SHA=76ba09735b46e19e1e0af718c420d6a60cdd0067
NEW_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
RUNUSER=mock_runuser
GIT=mock_git
PIN="$NEW_SHA"
mock_runuser() {
  case "$*" in
    *"checkout --quiet --detach $OLD_SHA")
      test "$FAIL_PIN" = 0 || return 1
      PIN="$OLD_SHA"; echo "TEST_PIN_RESTORED" >&2 ;;
    *"rev-parse HEAD") echo "$PIN" ;;
    *"status --porcelain") printf '' ;;
    *) return 22 ;;
  esac
}
restore_n2() {
  echo "TEST_N2_RESTORE" >&2
  test "$FAIL_N2" = 0
}
"""
        matrix = {
            "preflight_abstain": (1, 0, 0, 0, 0, 65, True, False),
            "cutover_rollback": (1, 1, 0, 0, 0, 65, True, True),
            "committed_success": (1, 0, 1, 0, 0, 0, False, False),
            "pin_rollback_failed": (1, 0, 0, 1, 0, 75, False, False),
            "n2_rollback_failed": (1, 1, 0, 0, 1, 75, True, True),
            "pre_checkout_abort": (0, 0, 0, 0, 0, 65, False, False),
        }
        for name, (pin,cutover,final,fail_pin,fail_n2,expected,had_pin,had_n2) in matrix.items():
            with self.subTest(case=name):
                code = (preamble + functions() +
                        f"\nPIN_CHANGED={pin}\nCUTOVER_STARTED={cutover}\n" +
                        f"RECOVERY_FINALIZED={final}\nFAIL_PIN={fail_pin}\n" +
                        f"FAIL_N2={fail_n2}\ntrap recovery_exit_cleanup EXIT\n" +
                        f"exit {0 if final else 65}\n")
                result = subprocess.run(
                    ["/usr/bin/bash", "-c", code],
                    capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual("TEST_PIN_RESTORED" in result.stderr, had_pin)
                self.assertEqual("TEST_N2_RESTORE" in result.stderr, had_n2)
                self.assertNotIn("/home/cia-probe", result.stdout+result.stderr)
                if fail_pin or fail_n2:
                    self.assertIn("D336_RECOVERY_COMPENSATION_REQUIRES_OPERATOR",
                                  result.stderr)


if __name__ == "__main__":
    unittest.main()
