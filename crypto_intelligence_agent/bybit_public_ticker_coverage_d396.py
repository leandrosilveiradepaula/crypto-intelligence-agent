"""D396: bounded, read-only PUBLIC ticker coverage across changing N50 scopes.

Composition of D385's BybitTickerBook and D386's bounded supervisor.
No independent socket implementation, N50 ranking algorithm, financial
journal, scheduler, service, REST call, private endpoint, or order sender.

A successful subscription ACK, a few ticker frames, or a healthy timer does
NOT prove all N50 instruments were covered. A finite scope is marked complete
only after distinct *usable* quotes for all 50 ranked instruments and ALL
position instruments, including held symbols outside the current N50.

This is an injected transport test/pilot building block; any real public WS
lease still requires a separate explicit network/region/release gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import time
from typing import Callable

from .bybit_public_ticker_state_d385 import BybitPublicTickerBook, BybitTickerQuote
from .bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, TickerLeaseReport, supervise_public_tickers,
)
from .bybit_public_ws_once import StreamSession
from .market_data import DataGapError, DataValidationError

MAX_EPOCHS = 4
MAX_SECONDS_PER_EPOCH = 60
MAX_FRAMES_PER_EPOCH = 100_000


@dataclass(frozen=True)
class TickerUniverseEpoch:
    """Caller-supplied point-in-time membership; not an eligibility claim."""

    ranked_symbols: tuple[str, ...]
    position_symbols: tuple[str, ...]
    universe_at_ms: int

    def __post_init__(self) -> None:
        if (type(self.ranked_symbols) is not tuple
                or len(self.ranked_symbols) != 50
                or type(self.position_symbols) is not tuple):
            raise DataValidationError("D396 requires exactly fifty ranked symbols")
        # Reuse D385's original currency, uniqueness, overlap and size checks.
        BybitPublicTickerBook(
            ranked_symbols=self.ranked_symbols,
            position_symbols=self.position_symbols,
            universe_at_ms=self.universe_at_ms,
        )

    @property
    def monitored(self) -> frozenset[str]:
        return frozenset(self.ranked_symbols) | frozenset(self.position_symbols)

    def private_scope_digest(self) -> str:
        payload = json.dumps({
            "ranked": sorted(self.ranked_symbols),
            "positions": sorted(self.position_symbols),
            "at_ms": self.universe_at_ms,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(payload.encode("ascii")).hexdigest()


def _lag_p95_bucket(report: TickerLeaseReport) -> str | None:
    """Histogram bucket of the P95, NOT a fabricated millisecond estimate."""
    bins = (
        (report.latency_0_to_100ms, "0_to_100ms"),
        (report.latency_101_to_1000ms, "101_to_1000ms"),
        (report.latency_1001_to_5000ms, "1001_to_5000ms"),
        (report.latency_over_5000ms, "over_5000ms"),
    )
    count = sum(k for k, _ in bins)
    if count == 0:
        return None
    threshold = (95 * count + 99) // 100
    cumulative = 0
    for n, label in bins:
        cumulative += n
        if cumulative >= threshold:
            return label
    raise DataValidationError("D396 latency histogram inconsistent")


@dataclass(frozen=True)
class TickerEpochCoverage:
    scope_sha256: str
    ranked_count: int
    position_count: int
    monitored_count: int
    usable_ranked_observed: int
    usable_positions_observed: int
    usable_monitored_observed: int
    fresh_monitored_at_lease_end: int
    subscriptions_acknowledged: int
    frames_seen: int
    ticker_frames_accepted: int
    reconnects: int
    p95_lag_bucket: str | None
    status: str
    failure_category: str | None

    def sanitized_report(self) -> dict:
        return {
            "scope_sha256": self.scope_sha256,
            "ranked_count": self.ranked_count,
            "position_count": self.position_count,
            "monitored_count": self.monitored_count,
            "usable_ranked_observed": self.usable_ranked_observed,
            "usable_positions_observed": self.usable_positions_observed,
            "usable_monitored_observed": self.usable_monitored_observed,
            "fresh_monitored_at_lease_end": self.fresh_monitored_at_lease_end,
            "subscriptions_acknowledged": self.subscriptions_acknowledged,
            "frames_seen": self.frames_seen,
            "ticker_frames_accepted": self.ticker_frames_accepted,
            "reconnects": self.reconnects,
            "p95_lag_bucket": self.p95_lag_bucket,
            "status": self.status,
            "failure_category": self.failure_category,
        }


@dataclass(frozen=True)
class TickerCoveragePilotReport:
    status: str
    planned_epochs: int
    attempted_epochs: int
    ranked_rotations: int
    all_observed_coverage: bool
    epochs: tuple[TickerEpochCoverage, ...]

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "bybit-public-n50-coverage-pilot-d396-v1",
            "status": self.status,
            "planned_epochs": self.planned_epochs,
            "attempted_epochs": self.attempted_epochs,
            "ranked_rotations": self.ranked_rotations,
            "all_observed_coverage": self.all_observed_coverage,
            "epochs": [x.sanitized_report() for x in self.epochs],
            "coverage_is_historical_per_finite_lease": True,
            "live_quote_cache_available_after_lease": False,
            "continuous_24x7_verified": False,
            "marketwide_top50_verified": False,
            "p95_is_binned_not_exact_ms": True,
            "no_unbounded_quote_buffer": True,
            "source_authenticated": False,
            "orders_sent": False,
            "order_submission_enabled": False,
            "approved_for_live_use": False,
        }


def run_finite_public_ticker_coverage_pilot(
    *,
    epochs: tuple[TickerUniverseEpoch, ...],
    session_factories: tuple[Callable[[], StreamSession], ...],
    budget: TickerLeaseBudget = TickerLeaseBudget(
        max_sessions=2, max_frames=256, max_seconds=5,
    ),
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> TickerCoveragePilotReport:
    """Execute at most four finite, independent read-only D386 leases.

    The injected scope is supplied externally and MUST already be eligible,
    PIT-authenticated and rights-cleared before any real pilot. This method
    does not fetch/rank symbols or open a socket itself.

    After ANY incomplete lease, no later scope is attempted. This prevents
    a successful later membership from hiding a failed earlier one. The
    returned coverage describes distinct USABLE quotes seen during each lease,
    not current continuous service availability.
    """
    if (type(epochs) is not tuple or not 2 <= len(epochs) <= MAX_EPOCHS
            or any(type(e) is not TickerUniverseEpoch for e in epochs)
            or type(session_factories) is not tuple
            or len(session_factories) != len(epochs)
            or any(not callable(f) for f in session_factories)
            or type(budget) is not TickerLeaseBudget
            or budget.max_seconds > MAX_SECONDS_PER_EPOCH
            or budget.max_frames > MAX_FRAMES_PER_EPOCH
            or budget.max_frames < 52
            or not callable(clock)
            or not callable(wall_ms) or not callable(sleeper)):
        raise DataValidationError("D396 bounded injected pilot configuration invalid")
    for previous, next_scope in zip(epochs, epochs[1:]):
        if next_scope.universe_at_ms <= previous.universe_at_ms:
            raise DataGapError("D396 point-in-time scope timestamps not increasing")
        # No externally confirmed position-close event exists in this pilot.
        # Therefore it is NOT safe to silently remove a held instrument.
        if not set(previous.position_symbols).issubset(next_scope.position_symbols):
            raise DataGapError("D396 open positions cannot silently disappear")
    rotations = sum(
        set(a.ranked_symbols) != set(b.ranked_symbols)
        for a, b in zip(epochs, epochs[1:])
    )
    results: list[TickerEpochCoverage] = []
    for epoch, factory in zip(epochs, session_factories):
        now = wall_ms()
        if type(now) is not int or now < epoch.universe_at_ms:
            raise DataGapError("D396 future scope or invalid wall clock before socket")
        book = BybitPublicTickerBook(
            ranked_symbols=epoch.ranked_symbols,
            position_symbols=epoch.position_symbols,
            universe_at_ms=epoch.universe_at_ms,
        )
        seen: set[str] = set()
        ranked = set(epoch.ranked_symbols)
        positions = set(epoch.position_symbols)

        def observe(quote: BybitTickerQuote) -> None:
            # A positive-depth ticker can be counted once per symbol even if
            # that symbol sends many repeated updates. No prices are stored.
            if book.current(quote.symbol, at_ms=quote.received_at_ms) is not None:
                seen.add(quote.symbol)

        try:
            lease = supervise_public_tickers(
                session_factory=factory,
                book=book, budget=budget,
                clock=clock, wall_ms=wall_ms, sleeper=sleeper,
                on_quote=observe,
            )
            report_at = wall_ms()
            if type(report_at) is not int or report_at < epoch.universe_at_ms:
                raise DataGapError("D396 invalid measurement clock")
            fresh = book.sanitized_report(at_ms=report_at)["fresh_quotes"]
            covered = ranked.issubset(seen) and positions.issubset(seen)
            complete = (
                lease.status == "lease_completed"
                and lease.subscriptions_acknowledged >= 1
                and covered
            )
            results.append(TickerEpochCoverage(
                scope_sha256=epoch.private_scope_digest(),
                ranked_count=len(ranked), position_count=len(positions),
                monitored_count=len(epoch.monitored),
                usable_ranked_observed=len(ranked & seen),
                usable_positions_observed=len(positions & seen),
                usable_monitored_observed=len(seen),
                fresh_monitored_at_lease_end=fresh,
                subscriptions_acknowledged=lease.subscriptions_acknowledged,
                frames_seen=lease.frames_seen,
                ticker_frames_accepted=lease.ticker_frames_accepted,
                reconnects=lease.reconnects,
                p95_lag_bucket=_lag_p95_bucket(lease),
                status=("finite_coverage_observed" if complete
                        else "finite_coverage_insufficient"),
                failure_category=lease.failure_category,
            ))
            if not complete:
                return TickerCoveragePilotReport(
                    "abstained_incomplete_coverage", len(epochs),
                    len(results), rotations, False, tuple(results),
                )
        finally:
            # A completed probe can never be mistaken for a live feed.
            book.mark_disconnected()
    return TickerCoveragePilotReport(
        "finite_samples_observed_not_continuous",
        len(epochs), len(results), rotations, True, tuple(results),
    )
