"""Read-only, private last-observation health for the J1 owner WS pilot.

This module never probes a PID, opens SQLite, starts a collector or makes a
network request. A fresh last-observation is not evidence of a running daemon.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import time

MAX_HEALTH_BYTES = 4096
MAX_HEALTH_AGE_MS = 2 * 3_600_000
_HEALTH_SCHEMA = "j1-owner-ws-last-observation-v1"
_LAST_STATUSES = frozenset({
    "ws_pilot_sample_rank_ready_not_marketwide",
    "ws_pilot_warming_up_abstain",
    "ws_pilot_scope_refreshed_waiting_next_closed_hour",
    "ws_pilot_degraded_abstain",
    "ws_pilot_catalog_denied_no_retry",
    "ws_pilot_fail_closed_abstain",
})


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate health key")
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError("non-finite health value")


def _unverified(status: str) -> dict:
    return {
        "status": status,
        "worker_running_verified": False,
        "realtime_stream_verified": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def read_owner_ws_health(directory: str | Path, *, now_ms: int | None = None,
                         max_age_ms: int = MAX_HEALTH_AGE_MS) -> dict:
    """Return only a fixed-shape, sanitized observation from private JSON.

    Even a recent sample is labelled unverified. The service manager, not this
    stale-able JSON, owns real process-liveness detection.
    """
    if now_ms is None:
        now_ms = time.time_ns() // 1_000_000
    if (os.name != "posix" or type(now_ms) is not int or now_ms <= 0
            or type(max_age_ms) is not int
            or not 1_000 <= max_age_ms <= 86_400_000):
        return _unverified("health_untrusted_abstain")
    directory = Path(directory)
    path = directory / "ws-pilot-health.json"
    try:
        root = directory.lstat()
        if (not stat.S_ISDIR(root.st_mode) or directory.is_symlink()
                or stat.S_IMODE(root.st_mode) != 0o700
                or root.st_uid != os.getuid()):
            return _unverified("health_untrusted_abstain")
        try:
            before = path.lstat()
        except FileNotFoundError:
            return _unverified("health_missing_abstain")
        if (path.is_symlink() or not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid() or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600
                or not 1 <= before.st_size <= MAX_HEALTH_BYTES):
            return _unverified("health_untrusted_abstain")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            inside = os.fstat(stream.fileno())
            if (inside.st_dev, inside.st_ino) != (before.st_dev, before.st_ino):
                return _unverified("health_untrusted_abstain")
            raw = stream.read(MAX_HEALTH_BYTES + 1)
        if not 1 <= len(raw) <= MAX_HEALTH_BYTES:
            return _unverified("health_untrusted_abstain")
        doc = json.loads(raw.decode("ascii"), object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
        if (type(doc) is not dict or set(doc) != {
                "schema", "observed_at_utc_ms", "worker_running_verified", "report"}
                or doc["schema"] != _HEALTH_SCHEMA
                or doc["worker_running_verified"] is not False
                or type(doc["observed_at_utc_ms"]) is not int
                or type(doc["report"]) is not dict):
            return _unverified("health_untrusted_abstain")
        when = doc["observed_at_utc_ms"]
        if when <= 0 or when > now_ms:
            return _unverified("health_untrusted_abstain")
        report = doc["report"]
        if (report.get("status") not in _LAST_STATUSES
                or report.get("orders_sent") is not False
                or report.get("marketwide_top50_verified") is not False
                or report.get("source_authenticated") is not False
                or report.get("live_trading_authorized") is not False
                or report.get("realtime_stream_verified") is not False):
            return _unverified("health_untrusted_abstain")
        missing = report.get("missing_24h_assets")
        complete = report.get("complete_24h_assets")
        for count in (missing, complete):
            if count is not None and (type(count) is not int or not 0 <= count <= 500):
                return _unverified("health_untrusted_abstain")
        age = now_ms - when
        result = _unverified("health_recent_unverified" if age <= max_age_ms
                             else "health_stale_abstain")
        result.update({
            "last_observed_at_utc_ms": when,
            "age_ms": age,
            "last_sample_status": report["status"],
            "missing_24h_assets": missing,
            "complete_24h_assets": complete,
        })
        return result
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        return _unverified("health_untrusted_abstain")