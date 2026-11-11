"""J1/OPS1: fail-closed, read-only plan for replacing the finite REST timer.

The M1 repository already has the proper recurring systemd template. This
module does not install, start, enable, modify or read a systemd service. It
compares the existing installed unit text and private-journal readiness against
the repository-owned templates. Installation remains a separate operational
gate, NEVER authorized by this function.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Mapping

from .j1_rest_incremental_owner import HOUR_MS, MAX_CATCHUP_HOURS

RECURRING_CALENDAR = "OnCalendar=*-*-* *:02:00 UTC"
FINITE_HOURS = 24


def _report(status: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-rest-recurring-timer-preflight-v1",
        "status": status,
        "failure_category": reason,
        "finite_utc_hours_present": 0,
        "recurring_template_exact": False,
        "installed_service_unchanged": False,
        "old_timer_other_directives_unchanged": False,
        "private_journal_integrity_verified": False,
        "hours_to_reconcile_at_next_close": None,
        "unobserved_closed_hours": None,
        "historical_unpublished_hours": None,
        "recovery_capacity_within_48h": False,
        "historical_checkpoint_gap_retained": False,
        "human_production_activation_gate_required": True,
        "activation_authorized": False,
        "systemd_reloaded": False,
        "timer_activated": False,
        "service_started": False,
        "network_requests": 0,
        "database_modified": False,
        "orders_sent": False,
        "marketwide_top50_verified": False,
    }


def _normalized(text: str) -> str:
    if (type(text) is not str or not text.isascii()
            or "\x00" in text or len(text) > 20_000):
        raise ValueError("unit_text_invalid")
    return text.replace("\r\n", "\n").strip() + "\n"


def _calendar_lines(text: str) -> tuple[str, ...]:
    return tuple(row for row in text.splitlines()
                 if row.startswith("OnCalendar="))


def _without_calendar(text: str) -> str:
    return "\n".join(row for row in text.splitlines()
                     if not row.startswith("OnCalendar=")) + "\n"


def inspect_finite_to_recurring_rest_timer(
    *, installed_timer: str,
    installed_service: str,
    rendered_timer: str,
    rendered_service: str,
    readiness: Mapping[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    """Verify ONLY the finite -> standard recurring unit diff and journal.

    A correct plan is evidence that the *files* may be proposed for an
    operator-controlled release; it is NOT approval to enable a service.
    """
    out = _report("abstain", "invalid_preflight_inputs")
    if (type(now_ms) is not int or
            not 1_600_000_000_000 <= now_ms <= 4_102_444_800_000
            or not isinstance(readiness, Mapping)):
        return out
    try:
        old = _normalized(installed_timer)
        new = _normalized(rendered_timer)
        actual_service = _normalized(installed_service)
        proposed_service = _normalized(rendered_service)
        if (len(_calendar_lines(new)) != 1
                or _calendar_lines(new)[0] != RECURRING_CALENDAR
                or new.count("[Timer]") != 1 or new.count("[Service]") != 0
                or "Persistent=false\n" not in new
                or "AccuracySec=1s\n" not in new
                or "RandomizedDelaySec=0\n" not in new
                or "Unit=cia-j1-rest-hourly.service\n" not in new
                or "WantedBy=timers.target\n" not in new):
            return _report("abstain", "recurring_repository_template_invalid")
        out["recurring_template_exact"] = True
        if actual_service != proposed_service:
            return {**out, "failure_category": "installed_service_drift"}
        out["installed_service_unchanged"] = True
        if _without_calendar(old) != _without_calendar(new):
            return {**out, "failure_category": "timer_directive_drift"}
        out["old_timer_other_directives_unchanged"] = True
        calendar = _calendar_lines(old)
        if len(calendar) != FINITE_HOURS:
            return {**out, "failure_category": "expected_finite_timer_not_found"}
        parsed = []
        for line in calendar:
            if line == RECURRING_CALENDAR:
                return {**out, "failure_category": "timer_already_recurring"}
            value = line[len("OnCalendar="):]
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC")
            except ValueError:
                return {**out, "failure_category": "finite_utc_calendar_invalid"}
            if dt.minute != 2 or dt.second != 0:
                return {**out, "failure_category": "finite_utc_calendar_invalid"}
            parsed.append(dt.replace(tzinfo=timezone.utc))
        if any(b-a != timedelta(hours=1) for a,b in zip(parsed,parsed[1:])):
            return {**out, "failure_category": "finite_calendar_gap_or_duplicate"}
        if int(parsed[-1].timestamp()*1000) >= now_ms:
            return {**out, "failure_category": "finite_calendar_not_elapsed"}
        out["finite_utc_hours_present"] = len(calendar)
        out["old_finite_last_end_ms"] = int(parsed[-1].timestamp()*1000)
        out["recurring_template_digest_sha256"] = sha256(
            new.encode("ascii")).hexdigest()
        out["installed_service_digest_sha256"] = sha256(
            actual_service.encode("ascii")).hexdigest()
    except (ValueError, TypeError, OverflowError):
        return _report("abstain", "unit_text_invalid")

    def valid_int(key: str, *, minimum: int = 0, maximum: int = 100000) -> bool:
        x = readiness.get(key)
        return type(x) is int and minimum <= x <= maximum

    if (readiness.get("schema_version") != "j1_rest_resume_readiness_v1"
            or readiness.get("journal_integrity_verified") is not True
            or readiness.get("reviewed_research_contracts") != 2
            or readiness.get("activation_authorized") is not False
            or readiness.get("continuous_collector_verified") is not False
            or readiness.get("orders_sent") is not False
            or readiness.get("marketwide_top50_verified") is not False
            or readiness.get("network_requests") != 0
            or readiness.get("database_mutation_statements") != 0
            or not valid_int("catchup_hours", maximum=100000)
            or not valid_int("unobserved_closed_hours")
            or not valid_int("historical_unpublished_hours")
            or not valid_int("last_published_end_ms", minimum=1_600_000_000_000,
                             maximum=4_102_444_800_000)
            or readiness.get("historical_checkpoint_gaps_present") is not
                (readiness.get("historical_unpublished_hours") > 0)
            or readiness.get("catchup_within_worker_limit") is not
                (readiness.get("catchup_hours") <= MAX_CATCHUP_HOURS)
            or readiness.get("status") not in (
                "no_gap", "historical_checkpoint_gaps_require_review",
                "catchup_with_unobserved_hours_requires_review",
                "catchup_exceeds_48h_blocked",
            )):
        return {**out, "failure_category": "private_journal_readiness_invalid"}
    out["private_journal_integrity_verified"] = True
    out["hours_to_reconcile_at_next_close"] = readiness["catchup_hours"]
    out["unobserved_closed_hours"] = readiness["unobserved_closed_hours"]
    out["historical_unpublished_hours"] = readiness["historical_unpublished_hours"]
    out["historical_checkpoint_gap_retained"] = (
        readiness["historical_checkpoint_gaps_present"]
    )
    if readiness["catchup_hours"] > MAX_CATCHUP_HOURS:
        return {**out, "failure_category": "catchup_exceeds_48h"}
    if (readiness["catchup_hours"] >= 2
            and readiness["status"] !=
                "catchup_with_unobserved_hours_requires_review"):
        return {**out, "failure_category": "unobserved_hours_need_review"}
    if (readiness["catchup_hours"] < 2 and readiness["status"] not in
            ("no_gap", "historical_checkpoint_gaps_require_review")):
        return {**out, "failure_category": "readiness_clock_inconsistent"}
    out.update({
        "status": "recurring_unit_verified_pending_operational_gate",
        "failure_category": None,
        "recovery_capacity_within_48h": True,
        "historical_gap_requires_owner_review":
            readiness["historical_checkpoint_gaps_present"],
        "unobserved_hours_require_owner_review":
            readiness["unobserved_closed_hours"] > 0,
    })
    return out
