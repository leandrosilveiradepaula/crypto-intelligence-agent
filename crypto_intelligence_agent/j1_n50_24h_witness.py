"""J1/D309: read-only N50 24-closed-hour witness and silent-stall gate.

Composes the existing D299 owner-only, replayed SQLite/PIT auditor and
fixed systemd unit introspection. Never reads raw prices or symbols, never
collects data, changes units, sends orders or certifies a successful strategy.

A 24h observation is NOT the 36h epoch rotation, external crypto identity,
nor a proof that systemd remained healthy for every past second.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from .j1_auto_research_epoch import HOUR_MS
from scripts.audit_j1_n50_managed_epochs import (
    ROOT, audit_managed_n50_epochs,
)

# Each subprocess argument is a checked literal, not an input from a user.
_UNITS = {
    "n50_timer": "cia-j1-n50-managed.timer",
    "n50_service": "cia-j1-n50-managed.service",
    "n2_timer": "cia-j1-rest-hourly.timer",
    "n2_service": "cia-j1-rest-hourly.service",
}
_TIMER_FIELDS = ("Id", "LoadState", "ActiveState", "SubState", "UnitFileState")
_SERVICE_FIELDS = _TIMER_FIELDS + ("Result", "ExecMainStatus")
_EPOCH = re.compile(r"epoch-[0-9]{13}\Z")
_SUPPORTED = frozenset(("verified_epoch_history", "verified_with_missing_pit",
                        "stale_active_publication"))
_PENDING = frozenset(("awaiting_first_epoch", "awaiting_first_writer",
                     "in_progress_unverified", "partial_first_writer",
                     "capture_in_progress_unverified",
                     "rotation_in_progress_unverified"))
_ALLOWED_FIELD_VALUES = frozenset((
    "loaded", "not-found", "active", "inactive", "failed", "dead", "waiting",
    "running", "activating", "start", "enabled", "disabled", "static",
    "success", "exit-code", "timeout", "signal", "resources", "protocol",
))


def _result(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-closed24h-witness-v1",
        "status": status,
        "quality": "owner_closed_pit_observation_only",
        "active_epoch_id": None,
        "latest_published_end_ms": None,
        "published_last_24_closed_hours": 0,
        "expected_last_24_closed_hours": 24,
        "historical_missing_pit_hours": None,
        "observed_owner_integrity": False,
        "n50_timer_active_enabled": False,
        "n2_timer_inactive_disabled": False,
        "n50_last_service_exit_success": False,
        "closed_24h_pit_verified": False,
        "automatic_epoch_rotation_verified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "financial_backtest_approved": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _systemd_unit_snapshot(unit_name: str, fields: tuple[str, ...]) -> dict[str, str]:
    """Exactly one fixed unit, with bounded output, exact keyset, no shell."""
    if unit_name not in _UNITS.values() or fields not in (
        _TIMER_FIELDS, _SERVICE_FIELDS
    ):
        raise ValueError("unapproved_systemd_contract")
    if fields == _TIMER_FIELDS and not unit_name.endswith(".timer"):
        raise ValueError("wrong_unit_type")
    if fields == _SERVICE_FIELDS and not unit_name.endswith(".service"):
        raise ValueError("wrong_unit_type")
    argv = ["/usr/bin/systemctl", "show", unit_name]
    for field in fields:
        argv.extend(("-p", field))
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=8,
            shell=False, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("systemd_unavailable") from exc
    if completed.returncode != 0 or len(completed.stdout.encode("utf-8")) > 2048:
        raise ValueError("systemd_unavailable")
    result: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        name, sep, value = line.partition("=")
        if (
            sep != "=" or name not in fields or name in result
            or len(value) > 80 or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("systemd_untrusted_output")
        result[name] = value
    if set(result) != set(fields) or result["Id"] != unit_name:
        raise ValueError("systemd_untrusted_output")
    for name in fields:
        value = result[name]
        if name == "Id":
            continue
        if name == "ExecMainStatus":
            if not value.isdecimal() or len(value) > 3 or int(value) > 255:
                raise ValueError("systemd_untrusted_output")
        elif value not in _ALLOWED_FIELD_VALUES:
            raise ValueError("systemd_untrusted_output")
    return result


def _systemd_snapshot() -> dict[str, dict[str, str]]:
    return {
        key: _systemd_unit_snapshot(
            name, _TIMER_FIELDS if name.endswith(".timer") else _SERVICE_FIELDS
        ) for key, name in _UNITS.items()
    }


def _safe_health(health: object, now_ms: int) -> bool:
    if type(health) is not dict:
        return False
    required_false = (
        "continuous_collector_verified", "marketwide_top50_verified",
        "crypto_identity_independently_verified", "live_trading_authorized",
        "orders_sent", "systemd_modified",
    )
    if (
        health.get("schema_version") != "j1-n50-managed-owner-health-v1"
        or health.get("owner_integrity_verified") is not True
        or health.get("status") not in _SUPPORTED
        or any(health.get(key) is not False for key in required_false)
        or health.get("network_requests") != 0
        or health.get("database_mutation_statements") != 0
        or type(health.get("active_epoch_id")) is not str
        or _EPOCH.fullmatch(health["active_epoch_id"]) is None
    ):
        return False
    integers = (
        "epoch_count", "audited_journals", "stored_candles",
        "published_checkpoints", "unique_published_utc_hours",
        "missing_hours_between_publications",
        "latest_published_end_ms", "latest_published_age_hours",
        "published_last_24_closed_hours", "expected_last_24_closed_hours",
    )
    if any(type(health.get(key)) is not int for key in integers):
        return False
    if any(health[key] < 0 for key in integers):
        return False
    last = health["latest_published_end_ms"]
    count = health["published_last_24_closed_hours"]
    if (
        not 1_600_000_000_000 <= last <= now_ms
        or last % HOUR_MS
        or health["latest_published_age_hours"] != (now_ms - last) // HOUR_MS
        or health["expected_last_24_closed_hours"] != 24
        or not 0 <= count <= 24
        or not 1 <= health["epoch_count"] <= 96
        or not 1 <= health["audited_journals"] <= health["epoch_count"]
        or not 1 <= health["unique_published_utc_hours"]
        or health["unique_published_utc_hours"] != health["published_checkpoints"]
        or count > health["unique_published_utc_hours"]
        or health["stored_candles"] < 24 * 50
    ):
        return False
    return True


def _safe_units(units: object) -> bool:
    if type(units) is not dict or set(units) != set(_UNITS):
        return False
    for key, name in _UNITS.items():
        u = units[key]
        fields = _TIMER_FIELDS if name.endswith(".timer") else _SERVICE_FIELDS
        if type(u) is not dict or set(u) != set(fields) or u["Id"] != name:
            return False
        for field in fields:
            value = u[field]
            if type(value) is not str:
                return False
            if field == "Id":
                continue
            if field == "ExecMainStatus":
                if not value.isdecimal() or len(value) > 3 or int(value) > 255:
                    return False
            elif value not in _ALLOWED_FIELD_VALUES:
                return False
    return True


def evaluate_n50_24h_witness(
    health: object, units: object, *, now_ms: int,
) -> dict[str, Any]:
    """Pure gate: never turn 24 PITs into a full 24/7 or trading approval."""
    out = _result("evidence_rejected")
    if (
        type(now_ms) is not int
        or not 1_600_000_000_000 <= now_ms < 4_102_444_800_000
        or not _safe_units(units)
    ):
        return out
    timer = units["n50_timer"]
    service = units["n50_service"]
    fallback = units["n2_timer"]
    n2_service = units["n2_service"]
    timer_ok = all((
        timer["LoadState"] == "loaded", timer["ActiveState"] == "active",
        timer["SubState"] == "waiting", timer["UnitFileState"] == "enabled",
    ))
    fallback_ok = all((
        fallback["LoadState"] == "loaded", fallback["ActiveState"] == "inactive",
        fallback["UnitFileState"] == "disabled",
    ))
    service_ok = all((
        service["LoadState"] == "loaded", service["ActiveState"] == "inactive",
        service["SubState"] == "dead", service["Result"] == "success",
        service["ExecMainStatus"] == "0",
    ))
    n2_idle = all((
        n2_service["LoadState"] == "loaded",
        n2_service["ActiveState"] == "inactive",
        n2_service["UnitFileState"] in ("static", "disabled"),
    ))
    out.update(
        n50_timer_active_enabled=timer_ok,
        n2_timer_inactive_disabled=fallback_ok,
        n50_last_service_exit_success=service_ok,
    )
    if fallback["ActiveState"] == "active" and timer["ActiveState"] != "active":
        out["status"] = "failback_to_n2_observed"
        return out
    if not (timer_ok and fallback_ok and service_ok and n2_idle):
        out["status"] = "isolation_or_service_gate_not_ready"
        return out
    if type(health) is dict and health.get("status") in _PENDING:
        out["status"] = "awaiting_verified_writer"
        return out
    if not _safe_health(health, now_ms):
        out["status"] = "owner_journal_integrity_not_verified"
        return out
    last = health["latest_published_end_ms"]
    count = health["published_last_24_closed_hours"]
    out.update(
        active_epoch_id=health["active_epoch_id"],
        latest_published_end_ms=last,
        published_last_24_closed_hours=count,
        historical_missing_pit_hours=health["missing_hours_between_publications"],
        observed_owner_integrity=True,
    )
    last_eligible = now_ms // HOUR_MS * HOUR_MS
    if now_ms % HOUR_MS < 60_000:
        last_eligible -= HOUR_MS
    if last != last_eligible or health["status"] == "stale_active_publication":
        out["status"] = "missing_or_stale_current_closed_hour"
        return out
    if count < 24:
        out["status"] = "accumulating_24_closed_hours"
        return out
    # 24 distinct, audited PITs in the last 24 eligible closed hours;
    # the D299 full journal replay and unique UTC-hour gate support this.
    out["status"] = "closed_24h_pit_evidence_verified"
    out["closed_24h_pit_verified"] = True
    return out


def observe_n50_24h_witness(
    *, root_directory: Path = ROOT,
    allow_private_readonly_audit: bool = False,
    enable_closed24h_witness: bool = False,
    owner_ok: bool | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Owner-only one-shot: audit complete journal and fixed systemd units."""
    if (
        allow_private_readonly_audit is not True
        or enable_closed24h_witness is not True
    ):
        return _result("owner_optin_required")
    owner = (
        os.name == "posix" and os.getuid() == os.geteuid()
        and os.geteuid() != 0
        if owner_ok is None else owner_ok
    )
    if (
        owner is not True or type(owner_ok) not in (bool, type(None))
        or not isinstance(root_directory, Path)
        or not root_directory.is_absolute()
        or (now_ms is not None and type(now_ms) is not int)
    ):
        return _result("owner_environment_abstain")
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if type(now) is not int or not 1_600_000_000_000 <= now < 4_102_444_800_000:
        return _result("invalid_clock")
    health = audit_managed_n50_epochs(
        root_directory=root_directory, now_ms=now,
        allow_private_readonly_audit=True, owner_ok=owner,
    )
    if type(health) is not dict or health.get("status") == "blocked":
        return _result("owner_journal_integrity_not_verified")
    try:
        units = _systemd_snapshot()
    except (OSError, TypeError, ValueError, subprocess.SubprocessError):
        return _result("systemd_unverified")
    return evaluate_n50_24h_witness(health, units, now_ms=now)
