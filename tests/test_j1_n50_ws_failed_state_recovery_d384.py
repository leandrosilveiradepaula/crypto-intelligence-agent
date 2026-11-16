"""D384: prevent a new false WS admission failure after D381 cutover.

Offline-only: never invokes systemctl against the host and never starts timers.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts.preflight_j1_n50_ws_systemd import n50_ws_systemd_isolation

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/vps/recover_j1_n50_ws_d384_failed_state_once.sh"


def fake_runner(rest_state: str):
    states = {
        "cia-j1-rest-hourly.timer": ("inactive", "disabled"),
        "cia-j1-rest-hourly.service": (rest_state, "static"),
        "cia-j1-n50-managed.timer": ("inactive", "disabled"),
        "cia-j1-n50-managed.service": ("inactive", "static"),
    }

    def run(argv, **_kw):
        unit = argv[2]
        active, file_state = states[unit]
        output = (
            f"LoadState=loaded\nActiveState={active}\n"
            f"UnitFileState={file_state}\n"
        )
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="")
    return run


class D384FailedRestPreflightTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "Linux owner preflight only")
    def test_failed_rest_is_blocked_but_inactive_rest_passes(self):
        # Compare state only, do not weaken the old fail-closed gate.
        with patch("scripts.preflight_j1_n50_ws_systemd.os.getuid", return_value=999), \
             patch("scripts.preflight_j1_n50_ws_systemd.os.geteuid", return_value=999):
            bad = n50_ws_systemd_isolation(
                require_old_collectors_quiesced=True,
                command_runner=fake_runner("failed"),
            )
            ok = n50_ws_systemd_isolation(
                require_old_collectors_quiesced=True,
                command_runner=fake_runner("inactive"),
            )
        self.assertEqual(bad["status"], "blocked")
        self.assertFalse(bad["n2_quiesced"])
        self.assertEqual(ok["status"], "old_collectors_quiesced_preflight_only")
        self.assertTrue(ok["n2_quiesced"])
        self.assertTrue(ok["old_rest_timer_disabled"])
        self.assertTrue(ok["old_rest_service_stopped"])
        self.assertFalse(ok["orders_sent"])
        self.assertFalse(ok["systemd_modified"])

    @unittest.skipUnless(os.name == "posix" and Path("/usr/bin/bash").exists(),
                         "bash syntax check requires POSIX")
    def test_root_recovery_shell_syntax_and_gates(self):
        r = subprocess.run(["/usr/bin/bash", "-n", str(SCRIPT)],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = SCRIPT.read_text(encoding="utf-8")
        for term in (
            "PIN=507e698bcf7ffbf55afd5b30bfa5a9f1e6ee900f",
            "HOST=srv1319424", "OWNER=cia-probe",
            "D384_PRECHECK_PIN_TIMER_AND_QUIESCENT_SERVICES_PASS",
            'reset-failed "$N2_SERVICE" "$OLD_SERVICE" "$WS_SERVICE"',
            "scripts.preflight_j1_n50_ws_systemd",
            "--require-old-collectors-quiesced",
            "D384_OWNER_READONLY_SYSTEMD_PREFLIGHT_PASS",
            "D384_WS_TIMERS_ENABLED_WITH_N2_PREFLIGHT_PASS_NO_ORDERS",
            "D384_N2_RESTORED_ON_ABORT",
            "D384_ROLLBACK_REQUIRES_OPERATOR",
        ):
            self.assertIn(term, s)
        self.assertLess(
            s.index('disable --now "$N2"'),
            s.index('reset-failed "$N2_SERVICE"'),
        )
        self.assertLess(
            s.index("D384_OWNER_READONLY_SYSTEMD_PREFLIGHT_PASS"),
            s.index('$SYSTEMCTL enable --now "$WS"'),
        )
        self.assertLess(s.index("trap cleanup EXIT"), s.index('MUTATED=1'))
        for prohibited in ("curl ", "api.bybit.com", "sqlite3 ", "rm -rf", "order.create"):
            self.assertNotIn(prohibited, s)

    @unittest.skipUnless(os.name == "posix" and Path("/usr/bin/bash").exists(),
                         "mock bash date requires POSIX")
    def test_hourly_window_boundaries(self):
        source = SCRIPT.read_text(encoding="utf-8")
        guard = source[source.index("safe_hourly_window() {"):
                       source.index("\nsafe_hourly_window\n")]
        guard = guard.replace("/usr/bin/date -u +%s", "fake_date")
        for phase, code in ((0, 1), (179, 1), (180, 0),
                            (2100, 0), (3479, 0), (3480, 1), (3599, 1)):
            with self.subTest(phase=phase):
                p = "set -euo pipefail\n" + guard + "\n" + (
                    f"fake_date() {{ echo {phase}; }}\n"
                ) + "safe_hourly_window\n"
                r = subprocess.run(["/usr/bin/bash", "-c", p],
                                   capture_output=True, text=True, timeout=5)
                self.assertEqual(r.returncode, code, r.stderr)


if __name__ == "__main__":
    unittest.main()
