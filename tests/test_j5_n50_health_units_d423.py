"""D423: release candidate service templates must be safe and disabled.

No systemd enable/installation, privileged subprocess, exchange network or
writer manipulation is performed by this file. This catches regressions in
the desired eventual production unit before any operational release gate.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "deploy" / "vps" / "health-d423"
SERVICE = BASE / "cia-j2-n50-health.service"
TIMER = BASE / "cia-j2-n50-health.timer"
LOOPBACK = BASE / "cia-j5-health-loopback.service"


def unit(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    section: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section in out:
                raise AssertionError("duplicate systemd section")
            out[section] = {}
        elif section is None or "=" not in line:
            raise AssertionError("invalid unit syntax")
        else:
            k, v = line.split("=", 1)
            if k in out[section]:
                raise AssertionError("duplicate directive")
            out[section][k] = v
    return out


class HealthSchedulerD423Tests(unittest.TestCase):
    def test_readonly_health_worker_no_j1_paper_or_order_write_access(self):
        data = unit(SERVICE)
        self.assertEqual(set(data), {"Unit", "Service"})
        s = data["Service"]
        self.assertEqual(s["Type"], "oneshot")
        self.assertEqual(s["User"], "cia-probe")
        self.assertEqual(s["Group"], "cia-probe")
        self.assertEqual(s["Restart"], "no")
        self.assertEqual(s["SuccessExitStatus"], "2")  # degraded is expected
        self.assertEqual(s["UMask"], "0077")
        self.assertEqual(s["ProtectSystem"], "strict")
        self.assertEqual(s["ProtectHome"], "read-only")
        self.assertEqual(s["NoNewPrivileges"], "true")
        self.assertEqual(s["PrivateTmp"], "true")
        self.assertEqual(s["ReadWritePaths"],
                         "/home/cia-probe/agent/j5-n50-health-private")
        self.assertIn("--cycles 1 --seconds 60", s["ExecStart"])
        self.assertIn("--allow-local-health-write", s["ExecStart"])
        self.assertIn("--state-directory /home/cia-probe/agent/j1-n50-ws-epochs/active", s["ExecStart"])
        self.assertIn("observe_j2_public_n50_health_cycles_d421", s["ExecStart"])
        self.assertIn("j5-health-release", s["WorkingDirectory"])
        self.assertLessEqual(int(s["TimeoutStartSec"]), 150)
        self.assertLessEqual(int(s["MemoryMax"].removesuffix("M")), 512)
        self.assertLessEqual(int(s["CPUQuota"].removesuffix("%")), 30)
        self.assertNotIn("Install", data)
        for unsafe in ("ExecStartPost", "ExecStopPost", "sudo", "curl ",
                       "--allow-real-orders", "exchange-key", "python -c",
                       "run_j1_n50_ws", "real_trade", "POST /v5/order",
                       "ReadWritePaths=/home/cia-probe/agent/j1"):
            self.assertNotIn(unsafe, SERVICE.read_text(encoding="utf-8"))
        self.assertNotIn("order", s["ExecStart"].lower())

    def test_timer_starts_after_deactivation_and_retries_failures(self):
        data = unit(TIMER)
        self.assertEqual(set(data), {"Unit", "Timer", "Install"})
        t = data["Timer"]
        self.assertEqual(t["OnBootSec"], "2min")
        self.assertEqual(t["OnUnitInactiveSec"], "45s")
        self.assertEqual(t["OnCalendar"], "*-*-* *:0/5:30 UTC")
        self.assertEqual(t["Unit"], "cia-j2-n50-health.service")
        self.assertEqual(t["Persistent"], "false")
        self.assertEqual(data["Install"]["WantedBy"], "timers.target")
        self.assertNotIn("OnActiveSec", t)
        self.assertNotIn("OnUnitActiveSec", t)

    def test_dashboard_still_loopback_only_without_install_or_login_bypass(self):
        data = unit(LOOPBACK)
        self.assertEqual(set(data), {"Unit", "Service"})
        s = data["Service"]
        self.assertEqual(s["Type"], "simple")
        self.assertEqual(s["User"], "cia-probe")
        self.assertEqual(s["ReadOnlyPaths"],
                         "/home/cia-probe/agent/j5-n50-health-private")
        self.assertEqual(s["ProtectSystem"], "strict")
        self.assertEqual(s["ProtectHome"], "read-only")
        self.assertEqual(s["NoNewPrivileges"], "true")
        self.assertEqual(s["PrivateTmp"], "true")
        self.assertEqual(s["Restart"], "on-failure")
        self.assertEqual(s["RestrictAddressFamilies"], "AF_UNIX AF_INET")
        self.assertIn("-m scripts.serve_j5_local_readonly", s["ExecStart"])
        self.assertIn("--allow-loopback-readonly-http", s["ExecStart"])
        self.assertIn("--allow-private-health-loopback", s["ExecStart"])
        self.assertIn("--private-health-directory /home/cia-probe/agent/j5-n50-health-private", s["ExecStart"])
        self.assertNotIn("Install", data)
        original_server = (ROOT / "scripts" / "serve_j5_local_readonly.py").read_text(encoding="utf-8")
        self.assertIn('HOST = "127.0.0.1"', original_server)
        self.assertIn('PORT = 8765', original_server)
        self.assertIn('if not self._request_allowed():', original_server)
        self.assertIn('self.path == "/api/n50-public-health"', original_server)

    def test_templates_are_never_installed_by_git_checkout_or_python_import(self):
        for path in (SERVICE, TIMER, LOOPBACK):
            raw = path.read_text(encoding="utf-8")
            self.assertIn("RELEASE CANDIDATE ONLY", raw)
            self.assertNotIn("systemctl enable", raw)
            self.assertNotIn("0.0.0.0", raw)
            self.assertNotIn("8443", raw)
            self.assertNotIn("traefik", raw.lower())
            self.assertNotIn("WantedBy=multi-user.target", raw)
            self.assertNotIn("RootDirectory=/", raw)
            self.assertTrue(re.fullmatch(r"[\w-]+\.(service|timer)", path.name))
        self.assertFalse((BASE / "install.sh").exists())


if __name__ == "__main__":
    unittest.main()
