"""D456: read-only J5 projection of the ACTUAL D453 resident PAPER state.

The owner status is an advisory, time-limited heartbeat, not proof that public
quotes, protective stops or real exchange positions are being serviced.
No websocket, private exchange API, journal write, shell or external requests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from .j4_private_paper_ws_operator_d425 import _private_directory, _owner_file
from .market_data import DataValidationError

_FILE = "paper-operator-state-d453.json"
_KEYS = frozenset((
    "schema_version", "state", "updated_at_ms", "stale_after_ms",
    "cycles_attempted", "primary_leases_completed", "held_only_fallbacks",
    "last_cycle", "last_failure_class", "mode",
    "native_protective_orders", "position_monitoring_guaranteed",
    "real_orders_sent",
))
_STATES = frozenset((
    "starting", "observing_public_lease", "held_only_fallback",
    "lease_ended_not_protected", "degraded_no_held_coverage",
    "bounded_run_completed", "stopped",
))
_FAILURES = frozenset(("primary_abstained", "degraded_primary"))
_MAX_SIZE = 4096
_MAX_AGE_MS = 375_000  # D453 180s max lease + 15s, not arbitrary producer TTL


class ResidentPaperStatusUnavailable(Exception):
    """Fail closed without leaking private paths, symbols or owner details."""


def _unique(pairs):
    value = {}
    for name, item in pairs:
        if name in value:
            raise DataValidationError("D456 repeated private status key")
        value[name] = item
    return value


def read_resident_paper_status(*, directory: Path, now_ms: int) -> dict:
    if (type(now_ms) is not int or
            not 1_600_000_000_000 <= now_ms <= 4_102_444_800_000):
        raise ResidentPaperStatusUnavailable("resident_paper_status_unavailable")
    try:
        home = _private_directory(directory)
        fd = _owner_file(home, _FILE)
        try:
            before = os.fstat(fd)
            if not 2 <= before.st_size <= _MAX_SIZE:
                raise DataValidationError("D456 private resident status length invalid")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(_MAX_SIZE + 1)
            after = os.fstat(fd)
            if (len(raw) != before.st_size or
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or
                    (current := (home / _FILE).lstat()).st_ino != before.st_ino
                    or current.st_dev != before.st_dev or not stat.S_ISREG(current.st_mode)
                    or (home / _FILE).is_symlink()):
                raise DataValidationError("D456 resident status changed mid-read")
        finally:
            os.close(fd)
        value = json.loads(
            raw.decode("ascii"), object_pairs_hook=_unique,
            parse_float=lambda _: (_ for _ in ()).throw(
                DataValidationError("D456 floats forbidden")),
            parse_constant=lambda _: (_ for _ in ()).throw(
                DataValidationError("D456 nonfinite status forbidden")),
        )
        if type(value) is not dict or set(value) != _KEYS:
            raise DataValidationError("D456 exact resident source schema required")
        v = value
        if (v["schema_version"] != "d453-resident-paper-status-v1"
                or v["state"] not in _STATES
                or v["mode"] not in (
                    "offline_injected_test", "public_research_unverified",
                )
                or v["last_failure_class"] not in _FAILURES | {None}
                or any(v[k] is not False for k in (
                    "native_protective_orders", "position_monitoring_guaranteed",
                    "real_orders_sent",
                )) or any(type(v[k]) is not int or not 0 <= v[k] <= 1_000_000
                         for k in ("cycles_attempted",
                                   "primary_leases_completed",
                                   "held_only_fallbacks", "last_cycle"))
                or v["primary_leases_completed"] + v["held_only_fallbacks"] >
                   v["cycles_attempted"]
                or v["last_cycle"] != v["cycles_attempted"]
                or type(v["updated_at_ms"]) is not int
                or type(v["stale_after_ms"]) is not int
                or not 1_600_000_000_000 <= v["updated_at_ms"] <= 4_102_444_800_000
                or not 15_000 <= v["stale_after_ms"] - v["updated_at_ms"] <= _MAX_AGE_MS
                or not -5000 <= now_ms - v["updated_at_ms"]
                or now_ms > v["stale_after_ms"]):
            raise DataValidationError("D456 stale or unsafe resident PAPER status")
        if (v["state"] == "degraded_no_held_coverage"
                and v["last_failure_class"] not in _FAILURES):
            raise DataValidationError("D456 inconsistent degraded status")
        return {
            "schema_version": "j5-resident-paper-readonly-d456-v1",
            "status": v["state"],
            "sampled_at_ms": now_ms,
            "last_reported_at_ms": v["updated_at_ms"],
            "cycle_attempts": v["cycles_attempted"],
            "primary_leases_completed": v["primary_leases_completed"],
            "held_only_fallbacks": v["held_only_fallbacks"],
            "source_mode": v["mode"],
            "lease_now_guaranteed_active": False,
            "uninterrupted_market_coverage_verified": False,
            "native_stop_verified": False,
            "venue_position_verified": False,
            "real_orders_sent": False,
            "approved_for_live_use": False,
        }
    except (OSError, DataValidationError, ValueError, UnicodeError,
            TypeError, OverflowError, AttributeError):
        raise ResidentPaperStatusUnavailable(
            "resident_paper_status_unavailable"
        ) from None
