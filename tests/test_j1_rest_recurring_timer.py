"""J1 #429: bounded finite -> recurrent timer plan, zero activation/network/DB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from crypto_intelligence_agent.j1_rest_recurring_plan import (
    RECURRING_CALENDAR, inspect_finite_to_recurring_rest_timer,
)
from scripts.audit_j1_rest_recurring_timer import audit_installed_timer
from scripts.render_j1_rest_hourly_timer import render

UTC = timezone.utc
NOW = datetime(2026, 11, 11, 14, 47, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)
TARGET = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)
TARGET_MS = int(TARGET.timestamp() * 1000)
OUTPUT = "/home/cia-probe/agent/j1-rest-m3-20261109/canary"
REPO = "/home/cia-probe/agent/repo"
PYTHON = "/home/cia-probe/agent/ws-venv/bin/python"
FROZEN = "/home/cia-probe/agent/j1-global-closed24h-private/run"


def rendered():
    return render(
        owner="cia-probe", repo=REPO, python=PYTHON,
        frozen=FROZEN, output=OUTPUT, max_assets=2,
    )


def finite_timer(desired_timer, *, count=24, shift=0):
    first = datetime(2026, 11, 9, 19, 2, tzinfo=UTC)
    lines = [
        "OnCalendar=" + (first + timedelta(hours=i + shift)).strftime(
            "%Y-%m-%d %H:%M:%S UTC")
        for i in range(count)
    ]
    return desired_timer.replace(RECURRING_CALENDAR, "\n".join(lines))


def readiness(*, catchup=21, historical=1):
    return {
        "schema_version": "j1_rest_resume_readiness_v1",
        "status": (
            "catchup_exceeds_48h_blocked" if catchup > 48 else
            "catchup_with_unobserved_hours_requires_review" if catchup >= 2 else
            "historical_checkpoint_gaps_require_review" if historical else "no_gap"
        ),
        "journal_integrity_verified": True,
        "reviewed_research_contracts": 2,
        "last_published_end_ms": TARGET_MS - catchup * 3_600_000,
        "next_eligible_end_ms": TARGET_MS,
        "catchup_hours": catchup,
        "unobserved_closed_hours": max(0, catchup-1),
        "historical_unpublished_hours": historical,
        "historical_checkpoint_gaps_present": historical > 0,
        "catchup_within_worker_limit": catchup <= 48,
        "activation_authorized": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "orders_sent": False,
    }


def plan(*, timer=None, service=None, desired=None, expected_service=None,
         readiness_report=None, now_ms=NOW_MS):
    rendered_service, rendered_timer = rendered()
    return inspect_finite_to_recurring_rest_timer(
        installed_timer=(
            finite_timer(rendered_timer) if timer is None else timer),
        installed_service=rendered_service if service is None else service,
        rendered_timer=rendered_timer if desired is None else desired,
        rendered_service=(
            rendered_service if expected_service is None else expected_service),
        readiness=readiness() if readiness_report is None else readiness_report,
        now_ms=now_ms,
    )


class FiniteToRecurringRestTests(unittest.TestCase):
    def test_exact_24_finite_hours_verifies_template_but_never_authorizes(self):
        r = plan()
        self.assertEqual(r["status"],
                         "recurring_unit_verified_pending_operational_gate")
        self.assertEqual(r["finite_utc_hours_present"], 24)
        self.assertTrue(r["recurring_template_exact"])
        self.assertTrue(r["installed_service_unchanged"])
        self.assertTrue(r["old_timer_other_directives_unchanged"])
        self.assertTrue(r["private_journal_integrity_verified"])
        self.assertEqual(r["hours_to_reconcile_at_next_close"], 21)
        self.assertEqual(r["unobserved_closed_hours"], 20)
        self.assertEqual(r["historical_unpublished_hours"], 1)
        self.assertTrue(r["historical_gap_requires_owner_review"])
        self.assertTrue(r["unobserved_hours_require_owner_review"])
        self.assertTrue(r["recovery_capacity_within_48h"])
        for name in ("activation_authorized", "systemd_reloaded",
                     "timer_activated", "service_started", "orders_sent",
                     "database_modified", "marketwide_top50_verified"):
            self.assertFalse(r[name], name)
        self.assertEqual(r["network_requests"], 0)
        self.assertNotIn("COIN", json.dumps(r))

    def test_service_drift_and_extraneous_timer_option_block(self):
        service, desired = rendered()
        bad_service = service.replace("User=cia-probe", "User=root")
        self.assertEqual(plan(service=bad_service)["failure_category"],
                         "installed_service_drift")
        self.assertEqual(
            plan(timer=finite_timer(desired).replace(
                "Persistent=false", "Persistent=true"))["failure_category"],
            "timer_directive_drift")
        self.assertEqual(
            plan(timer=finite_timer(desired) +
                 "OnBootSec=2s\n")["failure_category"],
            "timer_directive_drift")

    def test_missing_repeat_wrong_clock_and_duplicate_finite_lines_block(self):
        _, desired = rendered()
        self.assertEqual(
            plan(timer=finite_timer(desired, count=23))["failure_category"],
            "expected_finite_timer_not_found")
        base = finite_timer(desired)
        altered = base.replace("OnCalendar=2026-11-09 21:02:00 UTC",
                               "OnCalendar=2026-11-09 20:02:00 UTC")
        self.assertEqual(plan(timer=altered)["failure_category"],
                         "finite_calendar_gap_or_duplicate")
        late = base.replace("OnCalendar=2026-11-09 22:02:00 UTC",
                            "OnCalendar=2026-11-09 22:03:00 UTC")
        self.assertEqual(plan(timer=late)["failure_category"],
                         "finite_utc_calendar_invalid")
        self.assertEqual(
            plan(timer=desired)["failure_category"],
            "expected_finite_timer_not_found")
        self.assertEqual(
            plan(timer=finite_timer(desired),
                 now_ms=int(datetime(2026, 11, 10, 17, tzinfo=UTC).timestamp()*1000)
                )["failure_category"],
            "finite_calendar_not_elapsed")

    def test_unsafe_new_template_rejected_even_when_old_finite(self):
        service, desired = rendered()
        self.assertEqual(
            plan(desired=desired.replace("Persistent=false", "Persistent=true"))
            ["failure_category"], "recurring_repository_template_invalid")
        self.assertEqual(
            plan(desired=desired.replace(RECURRING_CALENDAR,
                                         "OnCalendar=*-*-* *:03:00 UTC"))
            ["failure_category"], "recurring_repository_template_invalid")

    def test_private_integrity_gap_over_48_and_latch_fail_closed(self):
        bad = readiness(catchup=49)
        out = plan(readiness_report=bad)
        self.assertEqual(out["failure_category"], "catchup_exceeds_48h")
        self.assertFalse(out["activation_authorized"])
        altered = readiness()
        altered["journal_integrity_verified"] = False
        self.assertEqual(
            plan(readiness_report=altered)["failure_category"],
            "private_journal_readiness_invalid")
        altered = readiness()
        altered["status"] = "halted_owner_review"
        self.assertEqual(
            plan(readiness_report=altered)["failure_category"],
            "private_journal_readiness_invalid")

    def test_clock_consistency_and_pit_flag_rejected(self):
        modified = readiness()
        modified["next_eligible_end_ms"] += 3_600_000
        self.assertEqual(
            plan(readiness_report=modified)["failure_category"],
            "private_journal_clock_mismatch")
        modified = readiness()
        modified["unobserved_closed_hours"] = 19
        self.assertEqual(
            plan(readiness_report=modified)["failure_category"],
            "private_journal_clock_mismatch")
        modified = readiness()
        modified["marketwide_top50_verified"] = True
        self.assertEqual(
            plan(readiness_report=modified)["failure_category"],
            "private_journal_readiness_invalid")

    def test_no_optin_is_inert_and_does_not_read_or_start(self):
        with patch("pathlib.Path.read_text", side_effect=AssertionError("read")):
            with patch("subprocess.run", side_effect=AssertionError("systemctl")):
                out = audit_installed_timer(
                    owner="cia-probe", repo=REPO, python=PYTHON,
                    frozen=FROZEN, output=OUTPUT, max_assets=2,
                    now_ms=NOW_MS, allow_private_readonly_audit=False,
                    readiness_reader=lambda **kwargs: self.fail("DB"))
        self.assertEqual(out["status"], "optin_required")
        self.assertFalse(out["activation_authorized"])

    def test_cli_readonly_plan_with_approved_unit_paths(self):
        svc, timer = rendered()
        actual_timer = finite_timer(timer)
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            if path == Path("/etc/systemd/system/cia-j1-rest-hourly.timer"):
                return actual_timer
            if path == Path("/etc/systemd/system/cia-j1-rest-hourly.service"):
                return svc
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", new=read_text):
            with patch("subprocess.run", side_effect=AssertionError("systemctl")):
                result = audit_installed_timer(
                    owner="cia-probe", repo=REPO, python=PYTHON,
                    frozen=FROZEN, output=OUTPUT, max_assets=2,
                    now_ms=NOW_MS, allow_private_readonly_audit=True,
                    readiness_reader=lambda **kwargs: readiness(),
                )
        self.assertEqual(result["status"],
                         "recurring_unit_verified_pending_operational_gate")
        self.assertFalse(result["timer_activated"])


if __name__ == "__main__":
    unittest.main()
