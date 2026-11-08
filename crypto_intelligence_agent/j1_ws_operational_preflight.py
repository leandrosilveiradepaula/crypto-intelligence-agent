"""J1/D267: one read-only owner WS operational preflight (not a live certificate).

Never starts/restarts/enables a service, writes SQLite, opens a market socket,
issues a REST GET, or labels a research feed authenticated. A systemd process
state and a local 24h journal do not prove uninterrupted real collection.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable

from .j1_ws_private_readiness import read_private_ws_readiness
from .j1_ws_service_health import read_owner_ws_health

UNIT = "cia-j1-ws-owner.service"
USER = "cia-probe"
PROPERTIES = ("Id", "LoadState", "ActiveState", "SubState",
              "MainPID", "User", "UnitFileState", "Result")
_SYSTEMCTL = ("systemctl", "show", UNIT, "--no-pager",
              "--property=" + ",".join(PROPERTIES))
MAX_OUTPUT = 2048
_ALLOWED_STATES = {
    "LoadState": {"loaded", "not-found", "masked", "error"},
    "ActiveState": {"active", "inactive", "failed", "activating", "deactivating", "reloading"},
    "SubState": {"running", "dead", "failed", "start", "stop", "auto-restart",
                 "exited", "waiting", "condition", "start-pre", "stop-sigterm"},
    "UnitFileState": {"enabled", "disabled", "static", "masked", "indirect", "generated",
                      "linked", "linked-runtime", "enabled-runtime", "disabled-runtime"},
    "Result": {"success", "exit-code", "signal", "timeout", "core-dump",
               "resources", "start-limit-hit", "protocol", "dependency", "condition"},
}
_TOKEN = re.compile(r"[a-z][a-z0-9-]{0,35}\Z")


def _base() -> dict[str, Any]:
    return {
        "schema_version": "j1-d267-ws-ops-preflight-v1",
        "status": "abstain",
        "operational_blocker": "preflight_not_authorized",
        "service_load_state": "unverified",
        "service_active_state": "unverified",
        "service_sub_state": "unverified",
        "service_unit_file_state": "unverified",
        "service_result": "unverified",
        "service_manager_observed_running": False,
        "ws_private_status": "unverified",
        "ws_reviewed_contracts": 0,
        "ws_complete_24h_contracts": 0,
        "ws_missing_24h_contracts": 0,
        "ws_health_status": "unverified",
        "service_queries": 0,
        "network_requests": 0,
        "database_modified": False,
        "worker_running_verified": False,
        "continuous_collector_verified": False,
        "source_authenticated": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def _parse_systemd(raw: str) -> dict[str, str]:
    if (type(raw) is not str or not 10 <= len(raw) <= MAX_OUTPUT
            or not raw.isascii() or "\x00" in raw):
        raise ValueError("systemd_response_invalid")
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or "=" not in line:
            raise ValueError("systemd_response_invalid")
        key, val = line.split("=", 1)
        if key not in PROPERTIES or key in fields or len(val) > 80:
            raise ValueError("systemd_response_invalid")
        fields[key] = val
    if set(fields) != set(PROPERTIES) or fields["Id"] != UNIT:
        raise ValueError("systemd_unit_mismatch")
    for key, options in _ALLOWED_STATES.items():
        # systemctl legitimately returns an empty UnitFileState for a unit
        # that has never been installed; do not misclassify it as malformed.
        if (key == "UnitFileState" and fields[key] == ""
                and fields["LoadState"] == "not-found"):
            continue
        if fields[key] not in options:
            raise ValueError("systemd_state_invalid")
    if fields["User"] not in ("", USER):
        raise ValueError("systemd_owner_mismatch")
    pid = fields["MainPID"]
    if not pid.isascii() or not pid.isdecimal() or len(pid) > 12:
        raise ValueError("systemd_pid_invalid")
    number = int(pid)
    if number > 4_194_304:
        raise ValueError("systemd_pid_invalid")
    is_running = fields["ActiveState"] == "active" and fields["SubState"] == "running"
    if (is_running and (number == 0 or fields["LoadState"] != "loaded"
                        or fields["User"] != USER)):
        raise ValueError("systemd_running_state_invalid")
    if fields["LoadState"] == "not-found":
        if fields["ActiveState"] != "inactive" or number:
            raise ValueError("systemd_absent_state_invalid")
    if (fields["ActiveState"] in ("failed", "inactive") and number):
        raise ValueError("systemd_inactive_pid_invalid")
    return fields


def _systemctl_once() -> str:
    proc = subprocess.run(
        _SYSTEMCTL, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="ascii",
        errors="strict", timeout=3, check=False, close_fds=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
    )
    if proc.returncode != 0:
        raise ValueError("systemd_query_failed")
    return proc.stdout


def _sanitized_readiness(report: Any) -> tuple[str, int, int, int]:
    if type(report) is not dict or report.get("orders_sent") is not False:
        raise ValueError("readiness_untrusted")
    status = report.get("status")
    if status == "ws_private_readiness_abstain":
        return ("unavailable", 0, 0, 0)
    if status not in ("ws_private_sample_complete_not_live",
                      "ws_private_sample_incomplete_abstain"):
        raise ValueError("readiness_untrusted")
    if (report.get("worker_running_verified") is not False
            or report.get("source_authenticated") is not False
            or report.get("marketwide_top50_verified") is not False
            or report.get("live_trading_authorized") is not False
            or report.get("network_requests") != 0):
        raise ValueError("readiness_untrusted")
    n, complete, missing = (report.get("reviewed_contracts"),
                            report.get("complete_24h_contracts"),
                            report.get("missing_24h_contracts"))
    if (any(type(x) is not int for x in (n, complete, missing))
            or not 1 <= n <= 52 or not 0 <= complete <= n
            or not 0 <= missing <= n or complete + missing != n):
        raise ValueError("readiness_counts_invalid")
    if status == "ws_private_sample_complete_not_live" and (missing or complete != n):
        raise ValueError("readiness_status_mismatch")
    if status == "ws_private_sample_incomplete_abstain" and missing == 0:
        raise ValueError("readiness_status_mismatch")
    return ("complete" if missing == 0 else "incomplete", n, complete, missing)


def _sanitized_health(report: Any) -> str:
    if (type(report) is not dict
            or report.get("worker_running_verified") is not False
            or report.get("live_trading_authorized") is not False
            or report.get("marketwide_top50_verified") is not False
            or report.get("orders_sent") is not False):
        raise ValueError("health_untrusted")
    status = report.get("status")
    if status == "health_recent_unverified":
        return "recent_unverified"
    if status == "health_stale_abstain":
        return "stale"
    if status in ("health_missing_abstain", "health_untrusted_abstain"):
        return "unavailable"
    raise ValueError("health_untrusted")


def observe_ws_operational_preflight(
    *, directory: Path, allow_private_readonly_preflight: bool = False,
    now_ms: int | None = None, owner_ok: bool | None = None,
    systemctl_reader: Callable[[], str] = _systemctl_once,
    readiness_reader: Callable[..., dict] = read_private_ws_readiness,
    health_reader: Callable[..., dict] = read_owner_ws_health,
) -> dict[str, Any]:
    result = _base()
    owner = (os.name == "posix" and hasattr(os, "getuid")
             and os.getuid() == os.geteuid() and os.geteuid() != 0) if owner_ok is None else owner_ok
    if (allow_private_readonly_preflight is not True or owner is not True
            or not isinstance(directory, Path) or not directory.is_absolute()
            or type(owner_ok) not in (bool, type(None))):
        return result
    if now_ms is None:
        now_ms = time.time_ns() // 1_000_000
    if type(now_ms) is not int or not 1_600_000_000_000 <= now_ms <= 4_102_444_800_000:
        result["operational_blocker"] = "clock_invalid"
        return result
    try:
        raw = systemctl_reader()
        result["service_queries"] = 1
        unit = _parse_systemd(raw)
        result.update({
            "service_load_state": unit["LoadState"],
            "service_active_state": unit["ActiveState"],
            "service_sub_state": unit["SubState"],
            "service_unit_file_state": unit["UnitFileState"],
            "service_result": unit["Result"],
        })
        service_running = (unit["ActiveState"] == "active"
                           and unit["SubState"] == "running")
        result["service_manager_observed_running"] = service_running
        ws_status, n, full, missing = _sanitized_readiness(
            readiness_reader(directory, now_ms=now_ms))
        result.update({
            "ws_private_status": ws_status,
            "ws_reviewed_contracts": n,
            "ws_complete_24h_contracts": full,
            "ws_missing_24h_contracts": missing,
        })
        health_status = _sanitized_health(
            health_reader(directory, now_ms=now_ms))
        result["ws_health_status"] = health_status
        if unit["LoadState"] == "not-found":
            blocker = "service_uninstalled"
        elif not service_running:
            blocker = "service_inactive"
        elif ws_status == "unavailable":
            blocker = "ws_private_unavailable"
        elif ws_status != "complete":
            blocker = "ws_window_incomplete"
        elif health_status != "recent_unverified":
            blocker = "ws_health_stale_or_missing"
        else:
            blocker = "evidence_insufficient_for_continuity"
        result["status"] = "read_only_operational_diagnostic"
        result["operational_blocker"] = blocker
    except (OSError, ValueError, TypeError, TimeoutError, subprocess.TimeoutExpired,
            UnicodeError):
        result["status"] = "abstain"
        result["operational_blocker"] = "systemd_or_private_observation_invalid"
        result["service_manager_observed_running"] = False
        result["ws_private_status"] = "unverified"
        result["ws_health_status"] = "unverified"
        result["ws_reviewed_contracts"] = 0
        result["ws_complete_24h_contracts"] = 0
        result["ws_missing_24h_contracts"] = 0
    return result
