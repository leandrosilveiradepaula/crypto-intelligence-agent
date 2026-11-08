"""D267: one-shot WS operational preflight is read-only and non-authorizing."""
from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_ws_operational_preflight import (
    UNIT, _SYSTEMCTL, _parse_systemd, observe_ws_operational_preflight,
)
from scripts.read_j1_ws_operational_preflight import main

NOW = 1794103607305
DIR = Path("/tmp/j1-private-owner")
BASE = {
    "Id": UNIT,
    "LoadState": "loaded",
    "ActiveState": "active",
    "SubState": "running",
    "MainPID": "31234",
    "User": "cia-probe",
    "UnitFileState": "enabled",
    "Result": "success",
}


def systemd(**kwargs):
    d = dict(BASE)
    d.update(kwargs)
    return "\n".join(f"{key}={value}" for key, value in d.items()) + "\n"


def readiness(status="ws_private_sample_complete_not_live", total=52, missing=0):
    return {
        "status": status,
        "reviewed_contracts": total,
        "complete_24h_contracts": total - missing,
        "missing_24h_contracts": missing,
        "worker_running_verified": False,
        "source_authenticated": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "network_requests": 0,
        "orders_sent": False,
    }


def health(status="health_recent_unverified"):
    return {
        "status": status,
        "worker_running_verified": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


class D267PortableTests(unittest.TestCase):
    def observe(self, *, raw=None, private=None, last=None, **kwargs):
        used = []
        def unit():
            used.append("systemctl")
            return systemd() if raw is None else raw
        def priv(path, *, now_ms):
            used.append("readiness")
            self.assertEqual(path, DIR)
            self.assertEqual(now_ms, NOW)
            return readiness() if private is None else private
        def h(path, *, now_ms):
            used.append("health")
            self.assertEqual(path, DIR)
            return health() if last is None else last
        result = observe_ws_operational_preflight(
            directory=DIR, now_ms=NOW, owner_ok=True,
            allow_private_readonly_preflight=True,
            systemctl_reader=unit, readiness_reader=priv,
            health_reader=h, **kwargs)
        self.assertEqual(used[:2], ["systemctl", "readiness"])
        if result["status"] == "read_only_operational_diagnostic":
            self.assertEqual(used, ["systemctl", "readiness", "health"])
        self.assertNotIn("31234", json.dumps(result))
        self.assertNotIn(str(DIR), json.dumps(result))
        self.assertNotIn("BTCUSDT", json.dumps(result))
        for k in (
            "worker_running_verified", "continuous_collector_verified",
            "source_authenticated", "marketwide_top50_verified",
            "live_trading_authorized", "orders_sent", "database_modified",
        ):
            self.assertFalse(result[k], k)
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["service_queries"], 1)
        return result

    def test_active_full_recent_remains_not_continuity_verified(self):
        result = self.observe()
        self.assertEqual(result["status"], "read_only_operational_diagnostic")
        self.assertEqual(result["operational_blocker"],
                         "evidence_insufficient_for_continuity")
        self.assertTrue(result["service_manager_observed_running"])
        self.assertEqual(result["ws_reviewed_contracts"], 52)
        self.assertEqual(result["ws_complete_24h_contracts"], 52)
        self.assertEqual(result["ws_missing_24h_contracts"], 0)

    def test_absent_unit_distinct_from_inactive(self):
        absent = self.observe(raw=systemd(
            LoadState="not-found", ActiveState="inactive", SubState="dead",
            MainPID="0", User="", UnitFileState="disabled"))
        self.assertEqual(absent["operational_blocker"], "service_uninstalled")
        stopped = self.observe(raw=systemd(
            ActiveState="inactive", SubState="dead", MainPID="0"))
        self.assertEqual(stopped["operational_blocker"], "service_inactive")
        self.assertFalse(stopped["service_manager_observed_running"])

    def test_incomplete_private_and_stale_health_priorities(self):
        result = self.observe(private=readiness(
            status="ws_private_sample_incomplete_abstain", missing=7))
        self.assertEqual(result["operational_blocker"], "ws_window_incomplete")
        self.assertEqual(result["ws_missing_24h_contracts"], 7)
        unknown = self.observe(private={
            "status": "ws_private_readiness_abstain", "orders_sent": False})
        self.assertEqual(unknown["operational_blocker"], "ws_private_unavailable")
        stale = self.observe(last=health("health_stale_abstain"))
        self.assertEqual(stale["operational_blocker"],
                         "ws_health_stale_or_missing")

    def test_parser_rejects_malicious_duplicate_pid_owner_and_status(self):
        bad = [
            systemd(User="root"),
            systemd(MainPID="0"),
            systemd(MainPID="-1"),
            systemd(MainPID="99999999999"),
            systemd(ActiveState="failed", SubState="failed"),
            systemd(LoadState="loaded", SubState="dangerous"),
            systemd(Id="cia-j1-other.service"),
            systemd() + "User=cia-probe\n",
            systemd() + "ExecStart=/bin/sh\n",
            systemd().replace("Result=success", "Result=success\nBADLINE"),
            systemd().replace("UnitFileState=enabled", "UnitFileState=enabled\rINJECT"),
        ]
        for data in bad:
            with self.subTest(data=data[:40]):
                with self.assertRaises(ValueError):
                    _parse_systemd(data)

    def test_invalid_reports_cannot_claim_running_or_complete(self):
        fake = readiness()
        fake["worker_running_verified"] = True
        self.assertEqual(self.observe(private=fake)["status"], "abstain")
        fake = readiness()
        fake["complete_24h_contracts"] = 53
        self.assertEqual(self.observe(private=fake)["status"], "abstain")
        fake = readiness(status="ws_private_sample_complete_not_live",missing=1)
        self.assertEqual(self.observe(private=fake)["status"], "abstain")
        fake_h = health()
        fake_h["orders_sent"] = True
        self.assertEqual(self.observe(last=fake_h)["status"], "abstain")

    def test_owner_default_off_no_reader_or_subprocess_invocation(self):
        def forbid(*args, **kwargs):
            self.fail("any I/O forbidden without explicit opt-in")
        with patch("subprocess.run", side_effect=forbid):
            kw = dict(directory=DIR, systemctl_reader=forbid,
                      readiness_reader=forbid, health_reader=forbid,
                      now_ms=NOW)
            for flags in (
                {}, {"allow_private_readonly_preflight": True, "owner_ok": False},
                {"allow_private_readonly_preflight": False, "owner_ok": True},
            ):
                x = observe_ws_operational_preflight(**kw, **flags)
                self.assertEqual(x["status"], "abstain")
                self.assertEqual(x["service_queries"], 0)
                self.assertFalse(x["worker_running_verified"])
            x = observe_ws_operational_preflight(
                directory=Path("relative"), now_ms=NOW, owner_ok=True,
                allow_private_readonly_preflight=True,
                systemctl_reader=forbid)
            self.assertEqual(x["status"], "abstain")

    def test_clock_and_timeout_fail_closed_no_private_claim(self):
        for clock in (True, "1794103607305", 0, -1):
            x = observe_ws_operational_preflight(
                directory=DIR, now_ms=clock, owner_ok=True,
                allow_private_readonly_preflight=True,
                systemctl_reader=lambda: self.fail("I/O before clock gate"))
            self.assertEqual(x["status"], "abstain")
        def timeout():
            raise subprocess.TimeoutExpired(["systemctl"], 3)
        x = observe_ws_operational_preflight(
            directory=DIR, now_ms=NOW, owner_ok=True,
            allow_private_readonly_preflight=True,
            systemctl_reader=timeout,
            readiness_reader=lambda *a, **kw: self.fail("not reached"))
        self.assertEqual(x["status"], "abstain")
        self.assertFalse(x["service_manager_observed_running"])
        self.assertEqual(x["operational_blocker"],
                         "systemd_or_private_observation_invalid")

    def test_cli_without_optin_never_calls_systemctl(self):
        output = StringIO()
        with patch("subprocess.run", side_effect=AssertionError("network")):
            with redirect_stdout(output):
                rc = main(["--directory", "/no-owner-research"])
        self.assertEqual(rc, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "abstain")
        self.assertEqual(report["service_queries"], 0)
        self.assertNotIn("no-owner", output.getvalue())

    def test_fixed_systemctl_command_allowlist(self):
        self.assertEqual(_SYSTEMCTL[0:3],
                         ("systemctl", "show", UNIT))
        self.assertEqual(len(_SYSTEMCTL), 5)
        self.assertNotIn("start", repr(_SYSTEMCTL))
        self.assertNotIn("restart", repr(_SYSTEMCTL))
        self.assertNotIn("enable", repr(_SYSTEMCTL))


if __name__ == "__main__":
    unittest.main()
