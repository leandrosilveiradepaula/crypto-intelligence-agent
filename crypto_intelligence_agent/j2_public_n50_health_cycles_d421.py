"""D421: repeat bounded public Bybit research leases and publish safe health.

ONE optional, explicitly invoked process; NO systemd installer, trading,
signals, account API, J1 writer, PAPER fills or private market data export.
Each D418 lease re-reads the current owner epoch, including after rotations.
Output is a single private, count-only, point-in-time local JSON snapshot.
"""
from __future__ import annotations

import fcntl
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Callable

from .market_data import DataGapError, DataValidationError

_SCHEMA = "j2-public-n50-finite-health-d421-v1"
_SOURCE = "j2-current-n50-sustained-market-observation-d418-v1"
_FILENAME = "latest-n50-public-health.json"
_LOCKFILE = ".n50-public-health.lock"
_MAX_MS = 4_102_444_800_000

# No symbols, prices, owner paths, raw provider errors or account fields.
_PUBLIC_KEYS = frozenset((
    "schema_version", "status", "sampled_at_ms", "cycle", "data_mode",
    "requested_contracts", "observed_contracts", "fresh_at_sample_end",
    "expired_at_sample_end", "never_received", "received_ineligible",
    "subscription_acks", "reconnects", "heartbeat_pings", "heartbeat_pongs",
    "frames_accepted", "exchange_lagged_callbacks", "sample_seconds",
    "owner_scope_unchanged", "full_finite_duration_observed",
    "finite_sample_only", "freshness_limit_ms", "signals_authorized",
    "orders_sent", "continuous_24x7_verified", "source_authenticated",
))


def _count(value: object, max_value: int) -> bool:
    return type(value) is int and 0 <= value <= max_value


def _failure(*, sampled_at_ms: int, cycle: int) -> dict:
    return {
        "schema_version": _SCHEMA,
        "status": "source_unavailable",
        "sampled_at_ms": sampled_at_ms, "cycle": cycle,
        "data_mode": "unavailable",
        "requested_contracts": 0, "observed_contracts": 0,
        "fresh_at_sample_end": 0, "expired_at_sample_end": 0,
        "never_received": 0, "received_ineligible": 0,
        "subscription_acks": 0, "reconnects": 0,
        "heartbeat_pings": 0, "heartbeat_pongs": 0,
        "frames_accepted": 0, "exchange_lagged_callbacks": 0,
        "sample_seconds": 0,
        "owner_scope_unchanged": False,
        "full_finite_duration_observed": False,
        "finite_sample_only": True,
        "freshness_limit_ms": 3000,
        "signals_authorized": False,
        "orders_sent": False,
        "continuous_24x7_verified": False,
        "source_authenticated": False,
    }


def project_public_health(
    source: object, *, sampled_at_ms: int, cycle: int,
) -> dict:
    """Project a D418 report with strict arithmetic, never copy extra keys.

    An unfinished or expired N50 is DEGRADATED, never sufficient for entries.
    A completed lease is not a live quote after its sample end.
    """
    if (not _count(sampled_at_ms, _MAX_MS - 1)
            or sampled_at_ms < 1_600_000_000_000
            or not _count(cycle, 1_000_000) or cycle < 1):
        raise DataValidationError("D421 sample clock/sequence invalid")
    if type(source) is not dict:
        raise DataValidationError("D421 source invalid")
    must_false = (
        "private_state_modified", "paper_position_state_changed",
        "paper_reservations_enabled", "quotes_persisted",
        "orders_sent", "approved_for_signals", "approved_for_live_use",
        "continuous_24x7_verified", "marketwide_top50_verified",
    )
    if (source.get("schema_version") != _SOURCE
            or source.get("status") not in (
                "sustained_market_observed_once",
                "sustained_market_degraded_or_partial",
                "sustained_owner_scope_changed_or_unavailable",
            )
            or source.get("data_mode") not in (
                "real_public_websocket", "injected_offline_fixture",
            )
            or any(source.get(k) is not False for k in must_false)
            or source.get("no_service_installed") is not True
            or type(source.get("owner_scope_unchanged_after_lease")) is not bool
            or type(source.get("full_finite_duration_observed")) is not bool
            or type(source.get("finite_current_owner_scope_observed_once")) is not bool
            or type(source.get("real_market_frames_verified")) is not bool):
        raise DataValidationError("D421 unsupported source or unsafe permissions")
    num_limits = {
        "requested_distinct_contracts": 100,
        "unique_distinct_contracts_observed": 100,
        "fresh_distinct_contracts_at_end": 100,
        "eligible_quote_expired_at_end_contracts": 100,
        "never_received_validated_quote_contracts": 100,
        "received_no_eligible_quote_contracts": 100,
        "subscription_acks": 2,
        "reconnects": 2,
        "heartbeat_pings": 10000,
        "heartbeat_pongs": 10000,
        "ticker_frames_accepted": 200_000,
        "exchange_lagged_quote_callbacks": 200_000,
    }
    if any(not _count(source.get(k), limit) for k, limit in num_limits.items()):
        raise DataValidationError("D421 invalid market counts")
    total = source["requested_distinct_contracts"]
    observed = source["unique_distinct_contracts_observed"]
    fresh = source["fresh_distinct_contracts_at_end"]
    expired = source["eligible_quote_expired_at_end_contracts"]
    never = source["never_received_validated_quote_contracts"]
    ineligible = source["received_no_eligible_quote_contracts"]
    mode = source["data_mode"]
    duration = source.get("observation_elapsed_seconds")
    if (type(duration) not in (int, float)
            or not math.isfinite(duration) or not 0 <= duration <= 930
            or not 50 <= total <= 100
            or fresh + expired != observed
            or fresh + expired + never + ineligible != total
            or source["subscription_acks"] < 1 and observed > 0
            or source["heartbeat_pongs"] > source["heartbeat_pings"]
            or source["reconnects"] > 1
            or source["ticker_frames_accepted"] < observed
            or (source["finite_current_owner_scope_observed_once"] is True
                and (source["status"] != "sustained_market_observed_once"
                     or not source["owner_scope_unchanged_after_lease"]
                     or not source["full_finite_duration_observed"]
                     or observed != total))
            or (mode == "injected_offline_fixture"
                and source["real_market_frames_verified"] is True)
            or (mode == "real_public_websocket"
                and source["real_market_frames_verified"] is not True)):
        raise DataValidationError("D421 noncausal market-health partition")
    sufficient_at_sample = (
        mode == "real_public_websocket"
        and source["finite_current_owner_scope_observed_once"] is True
        and fresh == total
    )
    result = {
        "schema_version": _SCHEMA,
        "status": (
            "finite_sample_all_fresh_at_end" if sufficient_at_sample
            else "finite_sample_degraded_or_partial"
        ),
        "sampled_at_ms": sampled_at_ms,
        "cycle": cycle, "data_mode": mode,
        "requested_contracts": total, "observed_contracts": observed,
        "fresh_at_sample_end": fresh, "expired_at_sample_end": expired,
        "never_received": never, "received_ineligible": ineligible,
        "subscription_acks": source["subscription_acks"],
        "reconnects": source["reconnects"],
        "heartbeat_pings": source["heartbeat_pings"],
        "heartbeat_pongs": source["heartbeat_pongs"],
        "frames_accepted": source["ticker_frames_accepted"],
        "exchange_lagged_callbacks": source["exchange_lagged_quote_callbacks"],
        "sample_seconds": round(duration, 3),
        "owner_scope_unchanged": source["owner_scope_unchanged_after_lease"],
        "full_finite_duration_observed": source["full_finite_duration_observed"],
        "finite_sample_only": True, "freshness_limit_ms": 3000,
        "signals_authorized": False, "orders_sent": False,
        "continuous_24x7_verified": False, "source_authenticated": False,
    }
    assert set(result) == _PUBLIC_KEYS
    return result


def _owned_directory(directory: Path) -> None:
    if (os.name != "posix" or not isinstance(directory, Path)
            or not directory.is_absolute()
            or directory.is_symlink()):
        raise DataValidationError("D421 private output directory invalid")
    try:
        attrs = directory.stat()
        if (not stat.S_ISDIR(attrs.st_mode)
                or stat.S_IMODE(attrs.st_mode) != 0o700
                or attrs.st_uid != os.geteuid()
                or directory.resolve(strict=True) != directory):
            raise DataValidationError("D421 output owner permissions invalid")
    except (OSError, RuntimeError):
        raise DataValidationError("D421 private output unavailable") from None


def publish_private_health(directory: Path, report: dict) -> None:
    """Atomic replacement of one count-only 0600 file, no J1/PAPER writes."""
    _owned_directory(directory)
    if type(report) is not dict or set(report) != _PUBLIC_KEYS:
        raise DataValidationError("D421 unsafe health publication")
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=True).encode("ascii")
    if not 0 < len(encoded) <= 4096:
        raise DataValidationError("D421 publication byte budget exceeded")
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".health-", dir=directory)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        target = directory / _FILENAME
        if target.is_symlink():
            raise DataValidationError("D421 unsafe prior health symlink")
        os.replace(temporary, target)
        temporary = None
        dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def run_readonly_health_cycles(
    *, cycles: int, probe: Callable[[], dict],
    publisher: Callable[[dict], None],
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
    gap_seconds: int = 3,
) -> dict:
    """Run 1-24 consecutive bounded D418 leases, never an unbounded daemon.

    Publishing source_unavailable REPLACES an older healthy report. A missing
    socket, rotation or malformed source cannot leave an old green report as
    the latest observation. An OSError during atomic publication is terminal.
    """
    if (type(cycles) is not int or not 1 <= cycles <= 24
            or type(gap_seconds) is not int or not 1 <= gap_seconds <= 60
            or not all(callable(x) for x in (probe, publisher, clock_ms, sleeper))):
        raise DataValidationError("D421 bounded cycle arguments invalid")
    degraded = 0
    last_status = "source_unavailable"
    for seq in range(1, cycles + 1):
        try:
            raw = probe()
            at = clock_ms()
            entry = project_public_health(raw, sampled_at_ms=at, cycle=seq)
        except (DataGapError, DataValidationError, OSError, RuntimeError,
                ValueError, TypeError, ImportError):
            at = clock_ms()
            if not _count(at, _MAX_MS - 1) or at < 1_600_000_000_000:
                raise DataValidationError("D421 bad wall clock on failure") from None
            entry = _failure(sampled_at_ms=at, cycle=seq)
        # A failed publish is never disguised as an successful cycle.
        publisher(entry)
        last_status = entry["status"]
        if last_status != "finite_sample_all_fresh_at_end":
            degraded += 1
        if seq < cycles:
            sleeper(gap_seconds)
    return {
        "schema_version": "j2-n50-private-health-cycles-d421-v1",
        "cycles_attempted": cycles, "cycles_published": cycles,
        "degraded_samples": degraded, "last_status": last_status,
        "single_writer_j1_unchanged": True,
        "continuous_24x7_verified": False,
        "orders_sent": False,
    }


def exclusive_private_health_lock(directory: Path):
    """Returns locked fd for caller to close. No wait/no duplicate instance."""
    _owned_directory(directory)
    fd = os.open(directory / _LOCKFILE,
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        attrs = os.fstat(fd)
        if (not stat.S_ISREG(attrs.st_mode) or attrs.st_uid != os.geteuid()
                or stat.S_IMODE(attrs.st_mode) != 0o600
                or attrs.st_nlink != 1):
            raise DataValidationError("D421 monitor lock owner invalid")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise
