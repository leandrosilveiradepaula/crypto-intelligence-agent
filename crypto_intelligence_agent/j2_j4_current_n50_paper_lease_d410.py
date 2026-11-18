"""D410 — finite public Bybit N50 -> AUTO4 PAPER without manual ticker list.

Owner J1 cohort is read-only. The existing D390/D386/D385 receiver and D391
PAPER coordinator are reused as-is; no separate strategy engine, broker
connection, order submission, shadow journal, installer or live account.
This is an opt-in bounded research operator, NOT a 24x7 deployment.
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import Callable

from .bybit_public_ticker_optin_d390 import run_readonly_bybit_ticker_lease
from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .bybit_public_ws_once import StreamSession
from .j2_current_j1_n50_public_scope_d406 import read_current_j1_n50_scope
from .market_data import DataGapError, DataValidationError
from .paper_intrahour_quote_router_d391 import PaperIntrahourQuoteRouter

_BUDGET = TickerLeaseBudget(max_sessions=1, max_frames=12_000, max_seconds=20)


def run_current_n50_paper_lease_once(
    *, state_directory: Path,
    paper_router: PaperIntrahourQuoteRouter,
    allow_private_pointer_read: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_synthetic_paper_reservations: bool = False,
    guard_held_feed_during_lease: bool = False,
    budget: TickerLeaseBudget = _BUDGET,
    session_factory: Callable[[], StreamSession] | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Run ONE bounded subscription; protect held PAPER positions independently.

    The supplied typed router has already checked the existing AUTO4
    position IDs, stop/target policy and netting; its symbols are derived
    automatically. A missing position outside N50 is subscribed rather than
    dropped or silently substituted. All gates are checked before owner
    pointer reads, quote callbacks or socket construction.

    A valid ACKed, current quote for a held PAPER contract may trigger a
    hypothetical stop/partial even when unrelated N50 contracts are silent.
    Requiring every unrelated market ticker would withhold stops for no
    position-specific reason. Incomplete N50 still degrades universe health,
    blocking any assertion of entry/strategy readiness. Reconnect invalidates
    the quote state; each new session needs ACK and new valid snapshots.
    Revalidating owner epoch after the lease catches rotations; synthetic
    reservations remain in AUTO4 for explicit reconciliation.
    """
    if any(type(g) is not bool for g in (
        allow_private_pointer_read, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        allow_synthetic_paper_reservations, guard_held_feed_during_lease,
    )):
        raise DataValidationError("D410 owner/public/PAPER gate type invalid")
    if not all((
        allow_private_pointer_read, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        allow_synthetic_paper_reservations,
    )):
        return {
            "schema_version": "j2-j4-current-n50-paper-lease-d410-v1",
            "status": "owner_market_and_paper_optin_required",
            "owner_scope_read": False,
            "network_attempted": False,
            "paper_journal_mutation_attempted": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
    if (not isinstance(state_directory, Path) or not state_directory.is_absolute()
            or type(paper_router) is not PaperIntrahourQuoteRouter
            or type(budget) is not TickerLeaseBudget
            or budget.max_sessions > 2 or budget.max_seconds > 60
            or budget.max_frames > 100_000
            or (session_factory is not None and not callable(session_factory))
            or not all(callable(c) for c in (clock, wall_ms, sleeper))):
        raise DataValidationError("D410 bounded owner/PAPER source invalid")
    before_ms = wall_ms()
    current = read_current_j1_n50_scope(
        state_directory=state_directory, now_ms=before_ms,
        allow_private_pointer_read=True,
    )
    monitored = paper_router.monitored_symbols
    extra = tuple(sorted(monitored - set(current.symbols)))
    if len(current.symbols) != 50 or len(set(current.symbols) | monitored) > 100:
        raise DataValidationError("D410 N50 plus position roster unsupported")
    raw = run_readonly_bybit_ticker_lease(
        ranked_symbols=current.symbols,
        position_symbols=extra,
        universe_at_ms=current.activated_at_ms,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        budget=budget, session_factory=session_factory,
        paper_router=paper_router, measure_public_coverage=True,
        require_fresh_held_position_for_paper=True,
        guard_held_feed_during_lease=guard_held_feed_during_lease,
        clock=clock, wall_ms=wall_ms, sleeper=sleeper,
    )
    try:
        after = read_current_j1_n50_scope(
            state_directory=state_directory, now_ms=wall_ms(),
            allow_private_pointer_read=True,
        )
        unchanged = (
            after.activated_at_ms == current.activated_at_ms
            and after.ranked_scope_sha256 == current.ranked_scope_sha256
            and after.metadata_sha256 == current.metadata_sha256
            and after.symbols == current.symbols
        )
    except (DataGapError, DataValidationError):
        unchanged = False
    complete_market_coverage = (
        unchanged
        and raw["status"] == "lease_completed"
        and raw["finite_coverage_observed_once"] is True
        and raw["finite_coverage_fresh_at_end"] is True
    )
    position_events_processed = raw["paper_coverage_gate"][
        "quote_frames_delivered_to_paper"
    ] > 0
    # A diagnostic can never assert continuously monitored financial safety:
    # a completed finite lease is CLOSED and PAPER has no native exchange stop.
    return {
        **raw,
        "schema_version": "j2-j4-current-n50-paper-lease-d410-v1",
        "status": (
            "finite_paper_lease_completed_with_fresh_scope"
            if complete_market_coverage
            else "finite_paper_lease_degraded_or_incomplete"
        ),
        "existing_paper_position_quote_processed": position_events_processed,
        "unrelated_n50_silence_blocks_protective_paper_exits": False,
        "universe_health_sufficient_for_new_entries": False,
        "underlying_ws_status": raw["status"],
        "data_mode": (
            "real_public_websocket" if session_factory is None
            else "injected_offline_fixture"
        ),
        "real_market_frames_verified": (
            session_factory is None
            and raw["subscriptions_acknowledged"] > 0
            and raw["ticker_frames_accepted"] > 0
        ),
        "position_contracts_derived_from_existing_auto4_router": len(monitored),
        "positions_outside_n50_subscribed": len(extra),
        "owner_scope_read": True,
        "owner_scope_unchanged_after_lease": unchanged,
        "j1_source_was_written": False,
        "paper_journal_mutation_possible": True,
        "paper_fills_from_tickers": False,
        "continuous_24x7_verified": False,
        "native_stop_verified": False,
        "risk_safety_verified": False,
        "orders_sent": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
    }
