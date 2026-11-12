"""D297 fail-closed cutover regression: no live systemd or database."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import install_j1_n50_cutover_once as install

SHA = "4f39658ea7537143ad3f70c26d2ba1642cadf139"
SRC = Path("/tmp/cia-n50-test-code")
ROOT = Path("/tmp/cia-n50-test-data")
PYTHON = Path("/usr/bin/python3")


def valid_audit():
    return {
        "schema_version": "j1_rest_resume_readiness_v1",
        "status": "historical_checkpoint_gaps_require_review",
        "journal_integrity_verified": True,
        "reviewed_research_contracts": 2,
        "research_closed_24h_ranked_contracts": 2,
        "orders_sent": False, "live_trading_authorized": False,
        "historical_checkpoint_gaps_present": True,
        "historical_unpublished_hours": 21,
        "last_published_end_ms": 1_800_000_000_000,
        "published_hours": 39, "stored_candles": 166,
    }


class D297CutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.units = Path(self.temp.name)
        self.state = {
            install.N2_TIMER: ("loaded", "active", "enabled"),
            install.N2_SERVICE: ("loaded", "inactive", "static"),
            install.N50_TIMER: ("not-found", "inactive", ""),
            install.N50_SERVICE: ("not-found", "inactive", ""),
        }
        self.calls = []

    def status(self, unit):
        a, b, c = self.state[unit]
        return {"LoadState": a, "ActiveState": b, "UnitFileState": c}

    def call(self, argv, *, timeout=20):
        self.calls.append(tuple(argv))
        if argv[:2] == ["/usr/bin/systemctl", "disable"]:
            self.state[argv[-1]] = ("loaded", "inactive", "disabled")
        if argv[:2] == ["/usr/bin/systemctl", "enable"]:
            self.state[argv[-1]] = ("loaded", "active", "enabled")
        return ""

    def opts(self, **kwargs):
        opts = dict(source=SRC, root=ROOT, python=PYTHON, sha=SHA)
        opts.update(kwargs)
        return opts

    def mock_context(self):
        plan = {
            "source_sha": SHA, "n2_integrity": True,
            "n2_published_hours": 39, "n2_stored_candles": 166,
            "service_text": "[Unit]\nDescription=offline service\n",
            "timer_text": "[Timer]\nOnCalendar=*-*-* *:01:05 UTC\n",
        }
        from contextlib import ExitStack
        ctx = ExitStack()
        ctx.enter_context(patch.object(install, "preflight", return_value=plan))
        ctx.enter_context(patch.object(install, "UNIT_ROOT", self.units))
        ctx.enter_context(patch.object(install, "_call", side_effect=self.call))
        ctx.enter_context(patch.object(install, "_show", side_effect=self.status))
        ctx.enter_context(patch(
            "scripts.preflight_j1_n50_systemd_isolation.n50_systemd_n2_quiescence",
            return_value={"status": "n2_quiesced_preflight_only"},
        ))
        return ctx

    def test_plan_is_read_only_even_when_preflight_passed(self):
        with self.mock_context():
            x = install.execute(**self.opts())
        self.assertEqual(x["status"], "preflight_pass_no_changes")
        self.assertEqual(x["n2_stored_candles"], 166)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.units.iterdir()), [])
        self.assertFalse(x["n50_timer_enabled"])

    def test_authorized_release_switches_only_timers(self):
        with self.mock_context():
            x = install.execute(**self.opts(
                confirm_controlled_cutover=True,
                allow_systemd_modifications=True,
            ))
        self.assertEqual(x["status"], "n50_timer_enabled_waiting_first_hour", x)
        self.assertTrue(x["systemd_modified"])
        self.assertEqual(self.state[install.N2_TIMER][1:], ("inactive", "disabled"))
        self.assertEqual(self.state[install.N50_TIMER][1:], ("active", "enabled"))
        self.assertEqual(self.state[install.N2_SERVICE][1], "inactive")
        self.assertEqual((self.units / install.N50_SERVICE).stat().st_mode & 0o777, 0o644)
        self.assertFalse(x["continuous_collector_verified"])
        self.assertFalse(x["orders_sent"])

    def test_failed_n50_enable_restores_n2_and_removes_new_units(self):
        def fail_n50(argv, *, timeout=20):
            if argv[:2] == ["/usr/bin/systemctl", "enable"] and (
                    argv[-1] == install.N50_TIMER):
                raise RuntimeError("simulated_launch_failure")
            return self.call(argv, timeout=timeout)
        with self.mock_context(), patch.object(
                install, "_call", side_effect=fail_n50):
            x = install.execute(**self.opts(
                confirm_controlled_cutover=True,
                allow_systemd_modifications=True,
            ))
        self.assertEqual(x["status"], "rolled_back_to_n2", x)
        self.assertTrue(x["rollback_succeeded"])
        self.assertEqual(self.state[install.N2_TIMER][1:], ("active", "enabled"))
        self.assertFalse((self.units / install.N50_SERVICE).exists())
        self.assertFalse((self.units / install.N50_TIMER).exists())

    def test_failure_before_first_unit_still_restores_n2(self):
        with self.mock_context(), patch.object(
                install, "_unit_write", side_effect=OSError("cannot write")):
            x = install.execute(**self.opts(
                confirm_controlled_cutover=True,
                allow_systemd_modifications=True,
            ))
        self.assertEqual(x["status"], "rolled_back_to_n2", x)
        self.assertTrue(x["rollback_succeeded"])
        self.assertFalse((self.units / install.N50_TIMER).exists())

    def test_invalid_n2_audit_refuses_release(self):
        report = valid_audit()
        report["historical_unpublished_hours"] = 22
        with patch.object(install, "_call", return_value=json.dumps(report)), patch.object(
                install.time, "time_ns", return_value=1_800_000_120_000 * 1_000_000):
            with self.assertRaises(ValueError):
                install._audit_n2(source=SRC, python=PYTHON)
        report = valid_audit()
        with patch.object(install, "_call", return_value=json.dumps(report)), patch.object(
                install.time, "time_ns", return_value=1_800_000_120_000 * 1_000_000):
            self.assertEqual(install._audit_n2(source=SRC, python=PYTHON),
                             report)

    def test_root_preflight_rejects_nonroot_before_any_systemd(self):
        with patch.object(install.os, "geteuid", return_value=1000), patch.object(
                install, "_call", side_effect=AssertionError("must not call")):
            with self.assertRaises(PermissionError):
                install.preflight(source=SRC, root=ROOT, python=PYTHON, sha=SHA)


if __name__ == "__main__":
    unittest.main()
