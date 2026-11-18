"""D428 — bounded multi-lease trial for EXISTING persisted PAPER positions.

Reuse one D391 router and ONE D425 financial-journal lock across multiple
independent D410 public Bybit WS leases. A new lease requires ACK and fresh
snapshot; old AUTO4 reservations remain pending. Abort rather than fill,
re-submit, disguise a gap or claim continuous venue protection.

Explicitly NOT an installed 24x7 daemon, market signal, trade or real stop.
The opt-in owner-only D427 file records FINISHED lease observations, never
a guarantee of active supervision. No account, signer, orders or J1 writes.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable

from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .j2_j4_current_n50_paper_lease_d410 import run_current_n50_paper_lease_once
from .j2_public_n50_health_cycles_d421 import _owned_directory
from .j4_private_paper_ws_operator_d425 import (
    _private_directory, exclusive_paper_operator_lock,
    load_private_paper_routes,
)
from .j5_paper_watch_d427 import (
    project_finite_paper_lease, publish_paper_watch,
    unavailable_finite_paper_lease,
)
from .market_data import DataGapError, DataValidationError

_SCHEMA = "j4-bounded-paper-supervision-trial-d428-v1"
_MAX_WALL_MS = 4_102_444_800_000


@dataclass(frozen=True)
class PaperTrialBudget:
    max_leases: int = 3
    lease_seconds: int = 20
    max_total_seconds: int = 90
    max_interlease_gap_ms: int = 5_000
    max_frames_per_lease: int = 25_000

    def __post_init__(self) -> None:
        if (any(type(getattr(self, k)) is not int for k in (
                "max_leases", "lease_seconds", "max_total_seconds",
                "max_interlease_gap_ms", "max_frames_per_lease"))
                or not 2 <= self.max_leases <= 4
                or not 10 <= self.lease_seconds <= 60
                or not self.max_leases * self.lease_seconds
                    <= self.max_total_seconds <= 300
                or not 100 <= self.max_interlease_gap_ms <= 15_000
                or not 1 <= self.max_frames_per_lease <= 100_000
                or self.max_frames_per_lease * self.max_leases > 100_000):
            raise DataValidationError("D428 invalid bounded PAPER trial budget")


def _safe_time(clock: Callable[[], float]) -> float:
    t = clock()
    if type(t) not in (int, float) or not math.isfinite(t):
        raise DataValidationError("D428 monotonic clock unavailable")
    return float(t)


def _safe_wall(wall_ms: Callable[[], int]) -> int:
    t = wall_ms()
    if type(t) is not int or not 1_600_000_000_000 <= t <= _MAX_WALL_MS:
        raise DataValidationError("D428 UTC clock unavailable")
    return t


def _result(
    status: str, *, attempted: int = 0, completed: int = 0,
    forwarded: int = 0, reserved: int = 0, reconciliation: int = 0,
    largest_gap_ms: int = 0, last_watch_at_ms: int | None = None,
) -> dict:
    """Only counts. In particular no private position ID, symbol or price."""
    return {
        "schema_version": _SCHEMA,
        "status": status,
        "leases_attempted": attempted,
        "leases_with_fresh_position_quotes": completed,
        "quotes_forwarded_to_paper": forwarded,
        "synthetic_exit_reservation_events": reserved,
        "reconciliation_required_events": reconciliation,
        "largest_interlease_gap_ms": largest_gap_ms,
        "last_terminal_watch_at_ms": last_watch_at_ms,
        "finite_trial_ended": True,
        "active_position_supervision_verified": False,
        "continuous_24x7_verified": False,
        "full_position_coverage_verified": False,
        "native_stop_verified": False,
        "real_fills_verified": False,
        "open_new_positions_authorized": False,
        "orders_sent": False,
        "live_trading_authorized": False,
        "approved_for_live_use": False,
        "approved_for_signals": False,
    }


def _validate_separate_directories(
    *, state_directory: Path, private_paper_directory: Path,
    watch_directory: Path,
) -> None:
    if (os.name != "posix" or os.geteuid() == 0
            or any(not isinstance(p, Path) or not p.is_absolute()
                   for p in (state_directory, private_paper_directory, watch_directory))):
        raise DataValidationError("D428 nonroot POSIX private paths required")
    _private_directory(private_paper_directory)
    _owned_directory(watch_directory)
    # The watch is neither the financial journal nor inside the J1 root.
    watch = watch_directory.resolve(strict=True)
    paper = private_paper_directory.resolve(strict=True)
    owner = state_directory.resolve(strict=False)
    if (watch == paper or watch == owner
            or watch.is_relative_to(paper)
            or watch.is_relative_to(owner)
            or paper.is_relative_to(watch)
            or owner.is_relative_to(watch)):
        raise DataValidationError("D428 watch must be separate from J1 and AUTO4")


def run_bounded_paper_trial(
    *, state_directory: Path, private_paper_directory: Path,
    watch_directory: Path,
    allow_private_pointer_read: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_synthetic_paper_reservations: bool = False,
    allow_multiple_finite_leases: bool = False,
    allow_paper_watch_output: bool = False,
    budget: PaperTrialBudget = PaperTrialBudget(),
    session_factory: Callable | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """One strictly bounded experimental multi-lease PAPER observation.

    The lock lasts across the ENTIRE trial, preventing a competing D425
    session from mutating the same journal between leases. Reuse the same
    router so its exchange-time watermark survives each subscription reset.
    Persistent AUTO4 reservations remain authoritative after any failure.
    At the beginning, publish a fail-closed watch to supersede an older one;
    a new finished watch is published only after each valid lease.
    """
    gates = (
        allow_private_pointer_read, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        allow_synthetic_paper_reservations, allow_multiple_finite_leases,
        allow_paper_watch_output,
    )
    if any(type(g) is not bool for g in gates):
        raise DataValidationError("D428 gate types must be bool")
    if not all(gates):
        return _result("explicit_seven_optins_required")
    if (type(budget) is not PaperTrialBudget
            or not all(callable(x) for x in (clock, wall_ms, sleeper))
            or session_factory is not None and not callable(session_factory)):
        raise DataValidationError("D428 invalid budget or dependency")
    _validate_separate_directories(
        state_directory=state_directory,
        private_paper_directory=private_paper_directory,
        watch_directory=watch_directory,
    )

    attempted = completed = forwarded = reserved = reconcile = largest_gap = 0
    last_watch_ms = None
    previous_end = None
    previous_decisions: dict[str, int] = {}
    initial_clock = _safe_time(clock)
    lock_fd = exclusive_paper_operator_lock(private_paper_directory)
    try:
        # Never let an old green-looking snapshot survive until the first
        # new session finishes; this report explicitly denies coverage.
        publish_paper_watch(
            watch_directory,
            unavailable_finite_paper_lease(sampled_at_ms=_safe_wall(wall_ms)),
        )
        router = load_private_paper_routes(private_paper_directory)

        def abort(reason: str) -> dict:
            nonlocal last_watch_ms
            try:
                new_ms = _safe_wall(wall_ms)
                publish_paper_watch(
                    watch_directory,
                    unavailable_finite_paper_lease(sampled_at_ms=new_ms),
                )
                last_watch_ms = new_ms
            except (OSError, DataValidationError, ValueError, TypeError):
                # A protected file may remain stale; the reader expires it
                # independently. Never hide original financial uncertainty.
                reason = "paper_watch_publication_unavailable"
            return _result(
                reason, attempted=attempted, completed=completed,
                forwarded=forwarded, reserved=reserved,
                reconciliation=reconcile, largest_gap_ms=largest_gap,
                last_watch_at_ms=last_watch_ms,
            )

        for _ in range(budget.max_leases):
            now = _safe_time(clock)
            elapsed = now - initial_clock
            if elapsed < 0 or elapsed + budget.lease_seconds > budget.max_total_seconds:
                return abort("trial_time_budget_exceeded")
            if previous_end is not None:
                delta = now - previous_end
                if delta < 0 or delta * 1000 > budget.max_interlease_gap_ms:
                    return abort("interlease_feed_gap_exceeded")
                largest_gap = max(largest_gap, int(delta * 1000))
            attempted += 1
            try:
                report = run_current_n50_paper_lease_once(
                    state_directory=state_directory,
                    paper_router=router,
                    allow_private_pointer_read=True,
                    allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    allow_synthetic_paper_reservations=True,
                    budget=TickerLeaseBudget(
                        max_sessions=2,
                        max_frames=budget.max_frames_per_lease,
                        max_seconds=budget.lease_seconds,
                    ),
                    session_factory=session_factory,
                    clock=clock, wall_ms=wall_ms, sleeper=sleeper,
                )
                # The SAME D391 router deliberately survives each lease,
                # including its causal watermark and cumulative counters.
                # D427 requires per-lease counts, so project only the
                # monotonic DECISION DELTA without resetting AUTO4 or router.
                raw = report.get("paper_monitoring")
                if type(raw) is not dict or type(raw.get("decision_counts")) is not dict:
                    raise DataValidationError("D428 missing PAPER decision counters")
                current = raw["decision_counts"]
                if (any(type(k) is not str or type(n) is not int or n < 0
                        for k, n in current.items())
                        or any(k not in current or current[k] < n
                               for k, n in previous_decisions.items())):
                    raise DataValidationError("D428 PAPER counters regressed")
                per_lease = {
                    key: n - previous_decisions.get(key, 0)
                    for key, n in current.items()
                }
                sanitized = {
                    **report,
                    "paper_monitoring": {**raw, "decision_counts": per_lease},
                }
                end_ms = _safe_wall(wall_ms)
                observation = project_finite_paper_lease(
                    sanitized, sampled_at_ms=end_ms,
                )
                previous_decisions = dict(current)
                publish_paper_watch(watch_directory, observation)
                last_watch_ms = end_ms
            except (DataGapError, DataValidationError, OSError,
                    TypeError, ValueError, OverflowError, RuntimeError,
                    ArithmeticError, sqlite3.Error):
                # An intent might have been reserved just before failure.
                # No retries for this lease, rollback assertion or FILL.
                return abort("paper_lease_failed_review_existing_journal")
            # Validate per-held-position freshness independently of marketwide
            # N50 coverage. An unrelated quiet coin must not veto a stop,
            # but a session with NO held quote does not count as supervision.
            if (observation["market_lease_completed"] is not True
                    or observation["owner_cohort_unchanged"] is not True
                    or observation["configured_position_routes"] < 1
                    or observation["quote_events_forwarded"] < 1
                    or report.get("existing_paper_position_quote_processed") is not True):
                return abort("held_paper_feed_unverified_or_owner_changed")
            completed += 1
            forwarded += observation["quote_events_forwarded"]
            reserved += observation["hypothetical_reservations_observed"]
            reconcile += observation["reconciliation_events_observed"]
            previous_end = _safe_time(clock)
        return _result(
            "bounded_trial_completed_no_live_protection",
            attempted=attempted, completed=completed,
            forwarded=forwarded, reserved=reserved,
            reconciliation=reconcile, largest_gap_ms=largest_gap,
            last_watch_at_ms=last_watch_ms,
        )
    finally:
        os.close(lock_fd)
