"""D443: monitor an EXISTING persisted BTCUSDT AUTO4 PAPER position without J1.

This is the held-position counterpart to D442's ephemeral scenario. It reuses
D425 private owner route manifest/flock, D441 public REST identity snapshot,
D390/D385/D386 public ticker supervision, D391/D389 and the EXISTING AUTO4
financial journal. Only synthetic reduce-only RESERVATIONS may be written.
No fake fills, new positions, order placement, exchange account or daemon.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .bybit_closed_stream_cache import (
    OfflineReviewedStreamScope, _scope_contract_fingerprint,
)
from .bybit_public_j1_transport import J1BybitCaptureError
from .bybit_public_ticker_optin_d390 import run_readonly_bybit_ticker_lease
from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .j2_public_btc_scope_d441 import fetch_single_btc_scope_from_public_rest
from .j4_private_paper_ws_operator_d425 import (
    exclusive_paper_operator_lock, load_private_paper_routes,
)
from .market_data import DataValidationError, DataGapError
from .paper_intrahour_quote_router_d391 import PaperIntrahourQuoteRouter


def run_held_paper_lease(
    *, router: PaperIntrahourQuoteRouter, scope: OfflineReviewedStreamScope,
    budget: TickerLeaseBudget,
    session_factory: Callable, clock: Callable, wall_ms: Callable,
    sleeper: Callable,
) -> dict:
    """In-memory transport orchestration, typed offline test seam.

    Caller must already hold the AUTO4 owner flock for a REAL session.
    Router may mutate only its PRE-EXISTING PAPER journal via D391.
    """
    if (type(router) is not PaperIntrahourQuoteRouter
            or not 1 <= len(router.monitored_symbols) <= 50
            or type(scope) is not OfflineReviewedStreamScope
            or type(budget) is not TickerLeaseBudget
            or budget.max_sessions != 1 or budget.max_seconds > 60
            or budget.max_frames > 100_000
            or any(not callable(x) for x in (
                session_factory, clock, wall_ms, sleeper))):
        raise DataValidationError("D443 existing held BTC PAPER and bounded WS required")
    _scope_contract_fingerprint(scope)
    current = wall_ms()
    if (type(current) is not int
            or len(scope.contracts) != len(router.monitored_symbols)
            or frozenset(x.symbol for x in scope.contracts)
               != router.monitored_symbols
            or not 0 <= current - scope.observed_at_ms <= 30_000):
        raise DataValidationError("D445 current exact held PAPER instruments required")
    result = run_readonly_bybit_ticker_lease(
        ranked_symbols=tuple(sorted(router.monitored_symbols)),
        position_symbols=tuple(sorted(router.monitored_symbols)),
        universe_at_ms=scope.observed_at_ms,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        budget=budget,
        session_factory=session_factory,
        paper_router=router,
        measure_public_coverage=True,
        require_fresh_held_position_for_paper=True,
        guard_held_feed_during_lease=True,
        clock=clock, wall_ms=wall_ms, sleeper=sleeper,
    )
    gate = result.get("paper_coverage_gate", {})
    delivered = gate.get("quote_frames_delivered_to_paper", 0)
    fresh = result.get("finite_coverage_fresh_at_end") is True
    complete = result.get("status") == "lease_completed"
    return {
        "schema_version": "j2-j4-existing-held-paper-lease-d445-v1",
        "held_position_contracts": len(router.monitored_symbols),
        "status": ("finite_held_paper_quote_observed_unverified"
                   if complete and fresh and delivered > 0
                   else "finite_held_paper_degraded_abstain"),
        "public_subscription_acks": result.get("subscriptions_acknowledged", 0),
        "ticker_frames_accepted": result.get("ticker_frames_accepted", 0),
        "held_quote_frames_forwarded": delivered,
        "held_quote_frames_deferred": gate.get("quote_frames_deferred", 0),
        "held_quote_fresh_at_lease_end": bool(complete and fresh),
        "failure_category": result.get("failure_category"),
        "paper_counts": result.get("paper_monitoring", {}),
        "existing_auto4_journal_reused": True,
        "new_paper_position_created": False,
        "synthetic_fill_inferred_from_ticker": False,
        "paper_journal_mutation_may_have_occurred": delivered > 0,
        "session_continues_after_return": False,
        "native_stop_verified": False,
        "j3_venue_costs_and_liquidation_verified": False,
        "marketwide_top50_verified": False,
        "j1_state_accessed": False,
        "orders_sent": False,
        "order_submission_enabled": False,
        "approved_for_live_use": False,
    }



def run_held_btc_paper_lease(
    *, router: PaperIntrahourQuoteRouter, scope: OfflineReviewedStreamScope,
    budget: TickerLeaseBudget, session_factory: Callable,
    clock: Callable, wall_ms: Callable, sleeper: Callable,
) -> dict:
    """Backward-compatible D443 BTC-only entrypoint."""
    if (type(router) is not PaperIntrahourQuoteRouter
            or router.monitored_symbols != frozenset({"BTCUSDT"})):
        raise DataValidationError("D443 BTC-only research scope required")
    report = run_held_paper_lease(
        router=router, scope=scope, budget=budget,
        session_factory=session_factory, clock=clock,
        wall_ms=wall_ms, sleeper=sleeper,
    )
    report["schema_version"] = "j2-j4-existing-btc-paper-lease-d443-v1"
    return report


def observe_existing_btc_paper_once(
    *, private_paper_directory: Path | None = None,
    allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_private_paper_reservations: bool = False,
    budget: TickerLeaseBudget = TickerLeaseBudget(1, 20_000, 30),
    session_factory: Callable | None = None,
    offline_scope: OfflineReviewedStreamScope | None = None,
    offline_router: PaperIntrahourQuoteRouter | None = None,
    clock: Callable | None = None,
    wall_ms: Callable | None = None,
    sleeper: Callable | None = None,
) -> dict:
    """Five independent gates. Real path holds owner flock throughout lease.

    In an offline test, an already-created router and fake session must be
    explicitly injected. In real mode, ANY test hook is forbidden.
    """
    gates = (allow_public_network, allow_public_websocket,
             confirm_personal_readonly_research, confirm_region_eligible,
             allow_private_paper_reservations)
    denied = {
        "schema_version": "j2-j4-existing-btc-paper-lease-d443-v1",
        "status": "explicit_held_paper_and_public_market_optins_required",
        "network_attempted": False, "private_paper_journal_accessed": False,
        "j1_state_accessed": False, "orders_sent": False,
        "approved_for_live_use": False,
    }
    if any(type(flag) is not bool for flag in gates):
        raise DataValidationError("D443 research flags must be boolean")
    if not all(gates):
        return denied
    if (type(budget) is not TickerLeaseBudget or budget.max_sessions != 1
            or budget.max_seconds > 60 or budget.max_frames > 100_000):
        raise DataValidationError("D443 finite held PAPER lease budget invalid")
    real = session_factory is None
    if not real:
        if (not callable(session_factory)
                or type(offline_scope) is not OfflineReviewedStreamScope
                or type(offline_router) is not PaperIntrahourQuoteRouter
                or any(not callable(x) for x in (clock, wall_ms, sleeper))
                or private_paper_directory is not None):
            raise DataValidationError("D443 explicit injected offline seam required")
        output = run_held_btc_paper_lease(
            router=offline_router, scope=offline_scope, budget=budget,
            session_factory=session_factory, clock=clock,
            wall_ms=wall_ms, sleeper=sleeper,
        )
        output.update(data_mode="injected_offline_protocol_replay",
                      network_attempted=False, private_paper_journal_accessed=True)
        return output

    if (offline_scope is not None or offline_router is not None
            or any(x is not None for x in (clock, wall_ms, sleeper))):
        raise DataValidationError("D443 real public session cannot accept offline hooks")
    if (os.name != "posix" or not hasattr(os, "geteuid")
            or not hasattr(os, "getuid") or os.getuid() != os.geteuid()
            or os.geteuid() == 0):
        return {**denied, "status": "unprivileged_owner_required"}
    if (not isinstance(private_paper_directory, Path)
            or not private_paper_directory.is_absolute()
            or any(part.startswith("j1-") for part in private_paper_directory.parts)):
        raise DataValidationError("D443 dedicated existing PAPER directory required")

    fd = exclusive_paper_operator_lock(private_paper_directory)
    try:
        router = load_private_paper_routes(private_paper_directory)
        if router.monitored_symbols != frozenset({"BTCUSDT"}):
            raise DataValidationError("D443 existing PAPER route must be single BTCUSDT")
        try:
            scope = fetch_single_btc_scope_from_public_rest()
        except (J1BybitCaptureError, DataGapError, DataValidationError,
                OSError, ValueError, TypeError):
            return {**denied, "status": "single_btc_public_rest_abstained",
                    "network_attempted": True,
                    "private_paper_journal_accessed": True}
        import time
        try:
            output = run_held_btc_paper_lease(
                router=router, scope=scope, budget=budget,
                session_factory=_public_session_only,
                clock=time.monotonic,
                wall_ms=lambda: time.time_ns() // 1_000_000,
                sleeper=time.sleep,
            )
        except (DataGapError, DataValidationError, OSError, RuntimeError, ValueError, TypeError):
            return {**denied, "status": "held_paper_public_lease_failed_closed",
                    "network_attempted": True,
                    "private_paper_journal_accessed": True}
        output.update(
            data_mode="public_ws_observed_unverified",
            network_attempted=True, private_paper_journal_accessed=True,
        )
        return output
    finally:
        os.close(fd)


def _public_session_only():
    # No network connection until every owner + private journal + REST gate.
    from .bybit_public_ticker_optin_d390 import _public_bybit_session
    return _public_bybit_session()
