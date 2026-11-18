"""D427: count-only terminal PAPER lease observation for the LOOPBACK panel.

The producer reuses D425/D410, NEVER reads a private PAPER position to build
its report and NEVER claims that a finite lease protects a position now.
Only owner 0700/0600 local files; no public REST/WS, account, order or FILL.
This is a status artifact, not a supervisor, order sender or trade permit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from .j2_public_n50_health_cycles_d421 import _owned_directory
from .market_data import DataValidationError
from .paper_intrahour_coordinator_d389 import PaperIntrahourDecision

_SCHEMA = "j5-paper-finite-lease-watch-d427-v1"
_FILENAME = "latest-paper-watch.json"
_MAX_BYTES = 4096
_MAX_AGE_MS = 180_000
_MAX_FUTURE_SKEW_MS = 5_000
_DECISIONS = frozenset(item.value for item in PaperIntrahourDecision)
_RECONCILE_DECISIONS = frozenset((
    "paper_stop_reconciliation_required",
    "paper_stop_unresolved",
    "paper_stop_terminal_review_required",
    "paper_target_reconciliation_required",
    "paper_target_terminal_review_required",
))
_RESERVATIONS = frozenset(("paper_stop_reserved", "paper_target_reserved"))
_FIELDS = frozenset((
    "schema_version", "status", "sampled_at_ms", "source",
    "configured_position_routes", "quote_events_forwarded",
    "quote_events_deferred", "hypothetical_reservations_observed",
    "reconciliation_events_observed", "subscription_acks",
    "owner_cohort_unchanged", "market_lease_completed",
    "finite_lease_ended", "full_position_coverage_verified",
    "continuous_supervision_verified", "native_stop_verified",
    "real_fills_verified", "live_trading_authorized",
    "orders_sent", "approved_for_signals",
))


class PaperWatchUnavailable(Exception):
    """No source path, symbol or account information in client errors."""


def _count(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _terminal(*, sampled_at_ms: int, status: str, routes: int = 0,
              forwarded: int = 0, deferred: int = 0, reservations: int = 0,
              reconciliation: int = 0, acks: int = 0,
              owner_unchanged: bool = False,
              lease_completed: bool = False) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA, "status": status,
        "sampled_at_ms": sampled_at_ms,
        "source": "real_public_websocket",
        "configured_position_routes": routes,
        "quote_events_forwarded": forwarded,
        "quote_events_deferred": deferred,
        "hypothetical_reservations_observed": reservations,
        "reconciliation_events_observed": reconciliation,
        "subscription_acks": acks,
        "owner_cohort_unchanged": owner_unchanged,
        "market_lease_completed": lease_completed,
        # A finished finite lease is not an actively supervised position.
        "finite_lease_ended": True,
        "full_position_coverage_verified": False,
        "continuous_supervision_verified": False,
        "native_stop_verified": False,
        "real_fills_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False, "approved_for_signals": False,
    }


def project_finite_paper_lease(source: dict, *, sampled_at_ms: int) -> dict:
    """Strictly classify real public D425 observations, never publish names.

    Reconciliation events count per-QUOTE decisions, not unique pending
    orders/positions. The journal may contain older unresolved intents that
    these event counts do not enumerate.
    """
    if (not _count(sampled_at_ms, 4_102_444_800_000)
            or sampled_at_ms < 1_600_000_000_000
            or type(source) is not dict
            or source.get("schema_version") != "j2-j4-current-n50-paper-lease-d410-v1"
            or source.get("data_mode") != "real_public_websocket"
            or source.get("status") not in (
                "finite_paper_lease_completed_with_fresh_scope",
                "finite_paper_lease_degraded_or_incomplete",
            )
            or source.get("underlying_ws_status") not in (
                "lease_completed", "lease_abstained",
                "public_market_frames_not_verified",
            )
            or any(source.get(k) is not False for k in (
                "orders_sent", "approved_for_live_use",
                "native_stop_verified", "continuous_24x7_verified",
                "universe_health_sufficient_for_new_entries",
            ))
            or type(source.get("owner_scope_unchanged_after_lease")) is not bool
            or type(source.get("real_market_frames_verified")) is not bool
            or type(source.get("paper_monitoring")) is not dict
            or type(source.get("paper_coverage_gate")) is not dict):
        raise DataValidationError("D427 requires real finite safe D410 result")
    pm = source["paper_monitoring"]
    gate = source["paper_coverage_gate"]
    if (pm.get("schema_version") != "paper-intrahour-quote-router-d391-v1"
            or gate.get("mode") != "fresh_held_position_quote_independent_of_n50"
            or any(pm.get(k) is not False for k in (
                "orders_sent", "native_stop_verified", "approved_for_live_use",
            ))
            or any(gate.get(k) is not False for k in (
                "orders_sent", "approved_for_live_use",
                "full_universe_required_for_existing_exits",
            ))
            or not _count(pm.get("configured_positions"), 100)
            or not 1 <= pm["configured_positions"] <= 50
            or not _count(gate.get("quote_frames_delivered_to_paper"), 100_000)
            or not _count(gate.get("quote_frames_deferred"), 100_000)
            or not _count(source.get("subscriptions_acknowledged"), 2)
            or not _count(source.get("ticker_frames_accepted"), 100_000)
            or not isinstance(pm.get("decision_counts"), dict)
            or any(type(k) is not str or k not in _DECISIONS
                   or not _count(v, 100_000)
                   for k, v in pm["decision_counts"].items())):
        raise DataValidationError("D427 PAPER decision projection invalid")
    counts = pm["decision_counts"]
    delivered = gate["quote_frames_delivered_to_paper"]
    if (sum(counts.values()) > delivered
            or delivered + gate["quote_frames_deferred"] >
               source["ticker_frames_accepted"]
            or (source["real_market_frames_verified"] and
                source["subscriptions_acknowledged"] < 1)):
        raise DataValidationError("D427 impossible PAPER frame count")
    reservations = sum(counts.get(k, 0) for k in _RESERVATIONS)
    reconciliation = sum(counts.get(k, 0) for k in _RECONCILE_DECISIONS)
    return _terminal(
        sampled_at_ms=sampled_at_ms,
        status="finite_paper_lease_ended",
        routes=pm["configured_positions"],
        forwarded=delivered,
        deferred=gate["quote_frames_deferred"],
        reservations=reservations,
        reconciliation=reconciliation,
        acks=source["subscriptions_acknowledged"],
        owner_unchanged=source["owner_scope_unchanged_after_lease"],
        lease_completed=source["underlying_ws_status"] == "lease_completed",
    )


def unavailable_finite_paper_lease(*, sampled_at_ms: int) -> dict:
    """Emit a *new* fail-closed sample after an owner/market/SQLite exception."""
    return _terminal(sampled_at_ms=sampled_at_ms,
                     status="finite_paper_lease_failed_closed")


def validate_paper_watch(data: object, *, now_ms: int) -> dict[str, Any]:
    """Safe renderable copy; a local file cannot assert protection by writing flags."""
    if (not _count(now_ms, 4_102_444_800_000)
            or now_ms < 1_600_000_000_000
            or type(data) is not dict or set(data) != _FIELDS):
        raise PaperWatchUnavailable("PAPER observation unavailable")
    r = data
    if (r.get("schema_version") != _SCHEMA
            or r.get("status") not in (
                "finite_paper_lease_ended",
                "finite_paper_lease_failed_closed",
            )
            or r.get("source") != "real_public_websocket"
            or not _count(r.get("sampled_at_ms"), 4_102_444_800_000)
            or not -_MAX_FUTURE_SKEW_MS <= now_ms - r["sampled_at_ms"] <= _MAX_AGE_MS
            or any(r.get(k) is not False for k in (
                "full_position_coverage_verified",
                "continuous_supervision_verified", "native_stop_verified",
                "real_fills_verified", "live_trading_authorized",
                "orders_sent", "approved_for_signals",
            ))
            or r.get("finite_lease_ended") is not True
            or type(r.get("owner_cohort_unchanged")) is not bool
            or type(r.get("market_lease_completed")) is not bool
            or any(not _count(r.get(k), bound) for k, bound in {
                "configured_position_routes": 50,
                "quote_events_forwarded": 100_000,
                "quote_events_deferred": 100_000,
                "hypothetical_reservations_observed": 100_000,
                "reconciliation_events_observed": 100_000,
                "subscription_acks": 2,
            }.items())
            or (r["status"] == "finite_paper_lease_failed_closed" and (
                r["configured_position_routes"] or r["quote_events_forwarded"]
                or r["quote_events_deferred"] or
                r["hypothetical_reservations_observed"] or
                r["reconciliation_events_observed"] or r["subscription_acks"]
                or r["owner_cohort_unchanged"] or r["market_lease_completed"]))
            or r["hypothetical_reservations_observed"] +
               r["reconciliation_events_observed"] >
               r["quote_events_forwarded"]
            or (r["quote_events_forwarded"] > 0 and r["subscription_acks"] == 0)
            or (r["market_lease_completed"] and r["subscription_acks"] == 0)):
        raise PaperWatchUnavailable("PAPER counts or status inconsistent")
    return {k: r[k] for k in sorted(_FIELDS)}


def publish_paper_watch(directory: Path, data: dict) -> None:
    """Atomic 0600 output inside pre-existing POSIX nonroot owner 0700 folder."""
    _owned_directory(directory)
    now_ms = __import__("time").time_ns() // 1_000_000
    try:
        validated = validate_paper_watch(data, now_ms=now_ms)
    except PaperWatchUnavailable as exc:
        raise DataValidationError("D427 unsafe watch output") from exc
    blob = json.dumps(validated, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
    if not 0 < len(blob) <= _MAX_BYTES:
        raise DataValidationError("D427 count-only output too large")
    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".paper-watch-", dir=directory)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        target = directory / _FILENAME
        if target.is_symlink() or (target.exists()
                                 and (not target.is_file()
                                      or target.stat().st_nlink != 1)):
            raise DataValidationError("D427 unsafe previous PAPER watch target")
        os.replace(tmp, target)
        tmp = None
        folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    finally:
        if tmp is not None:
            os.unlink(tmp)


def read_paper_watch(*, directory: Path, now_ms: int) -> dict:
    """Owner-only no-follow read; never open a SQLite file or network socket."""
    fd: int | None = None
    try:
        _owned_directory(directory)
        dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(_FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=dirfd)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1
                    or not 0 < info.st_size <= _MAX_BYTES
                    or not -_MAX_FUTURE_SKEW_MS <=
                    now_ms - info.st_mtime_ns // 1_000_000 <= _MAX_AGE_MS):
                raise PaperWatchUnavailable("PAPER owner watch unavailable")
            with os.fdopen(fd, "rb") as stream:
                fd = None
                blob = stream.read(_MAX_BYTES + 1)
        finally:
            os.close(dirfd)
        if not 0 < len(blob) <= _MAX_BYTES:
            raise PaperWatchUnavailable("PAPER report byte budget")
        return validate_paper_watch(json.loads(blob.decode("ascii")),
                                    now_ms=now_ms)
    except (DataValidationError, OSError, ValueError, TypeError,
            UnicodeError, json.JSONDecodeError):
        raise PaperWatchUnavailable("PAPER watch unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)
