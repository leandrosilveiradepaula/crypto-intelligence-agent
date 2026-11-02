"""J1/OPS11: deterministic, zero-I/O UTC rotation planning for bounded WS leases.

No network, clock reads, file operations, orders, or service activation.
A protected end is an operational scheduling preference, not proof of delivery.
"""
from __future__ import annotations

from .market_data import DataValidationError

HOUR_SECONDS = 3600
POST_CLOSE_TARGET_SECONDS = 180
ALIGNMENT_SECONDS = 300
MIN_LEASE_SECONDS = 300
MAX_LEASE_SECONDS = 3590


def plan_post_close_lease(*, now_utc_ms: int, max_seconds: int = MAX_LEASE_SECONDS
                          ) -> int:
    """Return lease seconds ending after, not at, an hourly UTC boundary.

    Prefer ending 3 minutes after the next closed hour, with no truncated
    lease below 300s and no extension beyond the max 3590s. If the desired
    target lies too near or too far, use a 300s alignment lease: its end
    remains between 3 and 8m10s after a closed-hour boundary.

    This avoids scheduled rotations at the hourly close but cannot protect
    against transport drops, provider delays, or wall-clock jumps.
    """
    if (type(now_utc_ms) is not int or now_utc_ms <= 0
            or type(max_seconds) is not int or max_seconds != MAX_LEASE_SECONDS):
        raise DataValidationError("UTC rotation plan requires positive milliseconds and 3590s cap")
    phase = (now_utc_ms // 1000) % HOUR_SECONDS
    desired = HOUR_SECONDS - phase + POST_CLOSE_TARGET_SECONDS
    # Floor to seconds for deterministic lease budgets. A subsecond clock
    # never silently raises the requested max or shortens the protected gap.
    if MIN_LEASE_SECONDS <= desired <= max_seconds:
        return desired
    return ALIGNMENT_SECONDS
