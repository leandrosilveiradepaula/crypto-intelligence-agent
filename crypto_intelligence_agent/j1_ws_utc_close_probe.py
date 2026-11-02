"""OPS16: deterministic UTC close-window gate for a one-shot public WS probe.

No HTTP, socket, filesystem or market access. Never schedules recurring work.
Only the disposable GitHub owner-comment job may use the wall-clock wait.
"""
from __future__ import annotations

import time
from typing import Callable

from .bybit_closed_stream_cache import HOUR_MS
from .market_data import DataValidationError

LEAD_SECONDS = 30
MAX_WAIT_SECONDS = 1_200
ARRIVAL_TOLERANCE_MS = 5_000


def plan_close_window(*, now_utc_ms: int, lead_seconds: int = LEAD_SECONDS,
                      max_wait_seconds: int = MAX_WAIT_SECONDS) -> tuple[int, int]:
    """Return (wait_ms, expected_probe_start_utc_ms), or fail closed.

    Only the immediately next UTC hour is eligible, and a runner may not
    idle longer than 20 minutes. Starts nominally 30s before the close, so
    the already-reviewed 90s WS probe crosses the hourly boundary.
    """
    if (type(now_utc_ms) is not int or now_utc_ms <= HOUR_MS
            or type(lead_seconds) is not int or not 15 <= lead_seconds <= 45
            or type(max_wait_seconds) is not int
            or not 0 <= max_wait_seconds <= MAX_WAIT_SECONDS):
        raise DataValidationError("invalid bounded UTC close probe window")
    target_ms = (now_utc_ms // HOUR_MS + 1) * HOUR_MS - lead_seconds * 1_000
    wait_ms = target_ms - now_utc_ms
    if wait_ms < 0 or wait_ms > max_wait_seconds * 1_000:
        raise DataValidationError("UTC close probe start outside permitted window")
    return wait_ms, target_ms


def await_close_window(*, clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
                       sleeper: Callable[[float], None] = time.sleep) -> int:
    """Wait once and re-check UTC wall time; never retry a missed window."""
    if not callable(clock_ms) or not callable(sleeper):
        raise DataValidationError("invalid UTC clock capabilities")
    wait_ms, target_ms = plan_close_window(now_utc_ms=clock_ms())
    if wait_ms:
        sleeper(wait_ms / 1_000)
    observed_ms = clock_ms()
    if (type(observed_ms) is not int
            or not target_ms <= observed_ms <= target_ms + ARRIVAL_TOLERANCE_MS):
        raise DataValidationError("UTC close window missed or wall clock jumped")
    return target_ms
