"""J5/D422: owner-only read of the latest count-only N50 sample.

The only supported source is D421's atomic 0600 JSON inside a preexisting
0700 directory owned by the CURRENT unprivileged process. No symbols, prices,
private keys, J1 database, PAPER journals, HTTP clients or trading functions.
The caller may expose the result only via the separately gated LOOPBACK server.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

from .j2_public_n50_health_cycles_d421 import _PUBLIC_KEYS, _owned_directory
from .market_data import DataValidationError

_FILENAME = "latest-n50-public-health.json"
_MAX_BYTES = 4096
_MAX_AGE_MS = 180_000
_FUTURE_SKEW_MS = 5_000


class HealthUnavailable(Exception):
    """Generic rejection; never include a private path or source payload."""


def _count(value: object, upper: int) -> bool:
    return type(value) is int and 0 <= value <= upper


def validate_local_health(data: object, *, now_ms: int) -> dict[str, Any]:
    """The remote-facing read-only contract is STRICTER than the producer.

    Do not trust flags embedded in a writable-by-owner file. Neither an
    authenticated exchange source nor a currently usable ticker is claimed.
    """
    if (not _count(now_ms, 4_102_444_800_000)
            or now_ms < 1_600_000_000_000
            or type(data) is not dict or set(data) != _PUBLIC_KEYS):
        raise HealthUnavailable("count-only sample unavailable")
    r = data
    if (r.get("schema_version") != "j2-public-n50-finite-health-d421-v1"
            or r.get("status") not in (
                "finite_sample_all_fresh_at_end",
                "finite_sample_degraded_or_partial",
            )
            or r.get("data_mode") != "real_public_websocket"
            or any(r.get(k) is not False for k in (
                "signals_authorized", "orders_sent",
                "continuous_24x7_verified", "source_authenticated",
            ))
            or r.get("finite_sample_only") is not True
            or r.get("freshness_limit_ms") != 3000
            or type(r.get("owner_scope_unchanged")) is not bool
            or type(r.get("full_finite_duration_observed")) is not bool
            or not _count(r.get("sampled_at_ms"), 4_102_444_800_000)
            or not 1 <= now_ms - r["sampled_at_ms"] <= _MAX_AGE_MS
            or not _count(r.get("cycle"), 1_000_000)
            or r["cycle"] == 0):
        raise HealthUnavailable("count-only sample expired or denied")
    bounds = {
        "requested_contracts": 100,
        "observed_contracts": 100,
        "fresh_at_sample_end": 100,
        "expired_at_sample_end": 100,
        "never_received": 100,
        "received_ineligible": 100,
        "subscription_acks": 2,
        "reconnects": 2,
        "heartbeat_pings": 10_000,
        "heartbeat_pongs": 10_000,
        "frames_accepted": 200_000,
        "exchange_lagged_callbacks": 200_000,
    }
    if any(not _count(r.get(k), maximum) for k, maximum in bounds.items()):
        raise HealthUnavailable("bad sample count")
    total = r["requested_contracts"]
    observed = r["observed_contracts"]
    fresh = r["fresh_at_sample_end"]
    if (not 50 <= total <= 100
            or fresh + r["expired_at_sample_end"] != observed
            or observed + r["never_received"] + r["received_ineligible"] != total
            or r["subscription_acks"] < 1
            or r["reconnects"] > 1
            or r["heartbeat_pongs"] > r["heartbeat_pings"]
            or r["frames_accepted"] < observed
            or r["exchange_lagged_callbacks"] > r["frames_accepted"]
            or type(r.get("sample_seconds")) not in (int, float)
            or not 60 <= r["sample_seconds"] <= 930
            or (r["status"] == "finite_sample_all_fresh_at_end"
                and (fresh != total or not r["owner_scope_unchanged"]
                     or not r["full_finite_duration_observed"]))):
        raise HealthUnavailable("inconsistent health sample")
    # Exact producer allowlist; never accept an appended account, position,
    # symbol, source path or trading assertion even if a future code writes it.
    return {key: r[key] for key in sorted(_PUBLIC_KEYS)}


def read_local_health(*, directory: Path, now_ms: int) -> dict[str, Any]:
    """Never follow symlinks, accept world-readable files or serve stale data.

    Opening the DIRECTORY fd first and the FILE relative to it closes the
    rename/symlink race between checking a path and obtaining the file.
    """
    fd = None
    try:
        _owned_directory(directory)
        dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            dstat = os.fstat(dirfd)
            if (not stat.S_ISDIR(dstat.st_mode)
                    or dstat.st_uid != os.geteuid()
                    or stat.S_IMODE(dstat.st_mode) != 0o700):
                raise HealthUnavailable("private directory not admitted")
            fd = os.open(_FILENAME,
                         os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=dirfd)
            fstat = os.fstat(fd)
            if (not stat.S_ISREG(fstat.st_mode)
                    or fstat.st_uid != os.geteuid()
                    or stat.S_IMODE(fstat.st_mode) != 0o600
                    or fstat.st_nlink != 1
                    or not 0 < fstat.st_size <= _MAX_BYTES
                    or not -_FUTURE_SKEW_MS <=
                    now_ms - (fstat.st_mtime_ns // 1_000_000) <= _MAX_AGE_MS):
                raise HealthUnavailable("private file not admitted")
            with os.fdopen(fd, "rb") as handle:
                fd = None
                blob = handle.read(_MAX_BYTES + 1)
        finally:
            os.close(dirfd)
        if not 0 < len(blob) <= _MAX_BYTES:
            raise HealthUnavailable("sample over byte budget")
        decoded = json.loads(blob.decode("ascii"))
        return validate_local_health(decoded, now_ms=now_ms)
    except (DataValidationError, OSError, ValueError, TypeError,
            UnicodeError, json.JSONDecodeError):
        raise HealthUnavailable("count-only sample unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)
