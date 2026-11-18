"""D390: explicit opt-in connector from D386 to existing Bybit WS transport.

Public market data ONLY: no private channels, signing, API keys, order sender,
SQLite, service installer, or persistent 24x7 worker. The single finite lease
can be run only with all required gates explicitly provided by the caller.
"""
from __future__ import annotations

import os
import time
from typing import Callable

from .bybit_public_ticker_state_d385 import (
    BybitPublicTickerBook, BybitTickerQuote, MAX_QUOTE_AGE_MS,
)
from .bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, TickerLeaseReport, supervise_public_tickers,
)
from .bybit_public_ws_once import StreamSession
from .market_data import DataValidationError
from .paper_intrahour_quote_router_d391 import PaperIntrahourQuoteRouter

_ALLOWED_WS_HOST = "wss://stream.bybit.com/v5/public/linear"


def _public_bybit_session() -> StreamSession:
    """Lazy reuse of approved J1 public transport, never imports account APIs."""
    from .bybit_public_ws_once import ENDPOINT, _real_session_factory
    if ENDPOINT != _ALLOWED_WS_HOST:
        raise DataValidationError("Bybit public endpoint unexpectedly changed")
    return _real_session_factory()


def run_readonly_bybit_ticker_lease(
    *,
    ranked_symbols: tuple[str, ...],
    position_symbols: tuple[str, ...] = (),
    universe_at_ms: int,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    budget: TickerLeaseBudget = TickerLeaseBudget(
        max_sessions=1, max_frames=2048, max_seconds=35,
    ),
    session_factory: Callable[[], StreamSession] | None = None,
    paper_router: PaperIntrahourQuoteRouter | None = None,
    measure_public_coverage: bool = False,
    diagnose_public_freshness: bool = False,
    require_complete_fresh_scope_for_paper: bool = False,
    require_fresh_held_position_for_paper: bool = False,
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Finite, sanitized market-only run. Not a production data service.

    Requires positive gates before even constructing the transport. An
    injected factory is intended solely for hermetic tests. Returning a
    report never certifies full N50 delivery or live trading.
    D401: optionally route validated, post-ACK snapshots/deltas into the
    existing PAPER AUTO4 router. It may reserve fictional exits only, and
    requires all PAPER positions to belong to the subscribed ticker scope.
    D405 can optionally count unique, causal positive-depth quotes from the
    LAST subscription session. This is bounded in memory to the monitored
    set and never persists symbols, prices, position IDs or snapshots.
    D410: optionally fail closed on all unobserved/stale N50+position
    subscriptions: a PAPER callback can receive a tick only after every
    monitored contract has a fresh causal positive-book observation in
    the CURRENT acknowledged WS session. Default behavior is unchanged.
    D411: a safer opt-in for managing EXISTING PAPER positions dispatches a
    quote only when that held contract itself has a current valid quote.
    D416: optional count-only breakdown distinguishes a never-delivered valid
    quote, an ineligible arrival, and an eligible quote expired at lease end.
    The exchange timestamp governs final freshness; receipt does not renew it.
    Global N50 freshness remains a separate research/entry health metric:
    missing unrelated assets must never disable protective position exits.
    """
    if (type(allow_public_websocket) is not bool
            or type(confirm_personal_readonly_research) is not bool
            or type(confirm_region_eligible) is not bool
            or type(measure_public_coverage) is not bool
            or type(diagnose_public_freshness) is not bool
            or type(require_complete_fresh_scope_for_paper) is not bool
            or type(require_fresh_held_position_for_paper) is not bool):
        raise DataValidationError("public_ws_gate_type_invalid")
    if (allow_public_websocket is not True
            or confirm_personal_readonly_research is not True
            or confirm_region_eligible is not True):
        return {
            "schema_version": "bybit-public-readonly-probe-d390-v1",
            "status": "owner_opt_in_required_no_network",
            "ticker_frames_accepted": 0,
            "subscription_acknowledged": False,
            "public_data_only": True,
            "no_service_installed": True,
            "marketwide_top50_verified": False,
            "orders_sent": False,
            "order_submission_enabled": False,
            "approved_for_live_use": False,
        }
    if diagnose_public_freshness and not measure_public_coverage:
        raise DataValidationError("public_ws_freshness_diagnostic_requires_coverage")
    # No fork/daemon in this method. The only allowed real transport is
    # the public, fixed URL, and the dependency remains lazily imported.
    if os.name != "posix" and session_factory is None:
        raise DataValidationError("public_ws_real_transport_requires_posix")
    if session_factory is not None and not callable(session_factory):
        raise DataValidationError("public_ws_injected_transport_invalid")
    if paper_router is not None and type(paper_router) is not PaperIntrahourQuoteRouter:
        raise DataValidationError("public_ws_paper_router_requires_existing_typed_journal")
    book = BybitPublicTickerBook(
        ranked_symbols=ranked_symbols,
        position_symbols=position_symbols,
        universe_at_ms=universe_at_ms,
    )
    if paper_router is not None and not paper_router.monitored_symbols.issubset(
        set(ranked_symbols) | set(position_symbols)
    ):
        raise DataValidationError("public_ws_paper_position_outside_subscription")
    if require_complete_fresh_scope_for_paper and (
        paper_router is None or not measure_public_coverage
    ):
        raise DataValidationError("public_ws_paper_coverage_gate_requires_monitor")
    if require_fresh_held_position_for_paper and (
        paper_router is None or not measure_public_coverage
        or require_complete_fresh_scope_for_paper
    ):
        raise DataValidationError("public_ws_held_position_gate_requires_monitor")
    rank_set, position_set = set(ranked_symbols), set(position_symbols)
    monitored = rank_set | position_set
    # The causal exchange timestamp, NOT only the socket receipt timestamp,
    # determines whether the quote is still fresh at the end of the lease.
    seen_this_session: dict[str, tuple[int, int]] = {}
    validated_this_session: set[str] = set()
    exchange_lagged_this_session: set[str] = set()
    exchange_lagged_callbacks = 0
    paper_frames_deferred = 0
    paper_frames_routed = 0
    unrelated_frames_ignored_for_paper = 0

    def session_reset() -> None:
        nonlocal exchange_lagged_callbacks
        # A previous socket's quotes cannot prove a new socket's coverage.
        seen_this_session.clear()
        validated_this_session.clear()
        exchange_lagged_this_session.clear()
        exchange_lagged_callbacks = 0
        if paper_router is not None:
            paper_router.begin_new_market_session()

    def observed_quote(quote: BybitTickerQuote) -> None:
        nonlocal paper_frames_deferred, paper_frames_routed
        nonlocal unrelated_frames_ignored_for_paper, exchange_lagged_callbacks
        if measure_public_coverage:
            if diagnose_public_freshness:
                validated_this_session.add(quote.symbol)
                if (quote.received_at_ms - quote.exchange_at_ms >
                        MAX_QUOTE_AGE_MS):
                    exchange_lagged_callbacks += 1
                    exchange_lagged_this_session.add(quote.symbol)
            # The exchange clock must be causal relative to the supplied
            # point-in-time scope; no inferred synthetic/retrospective ticks.
            if (quote.symbol in monitored
                    and quote.exchange_at_ms >= universe_at_ms
                    and 0 <= quote.received_at_ms - quote.exchange_at_ms
                           <= MAX_QUOTE_AGE_MS
                    and quote.has_positive_book_depth):
                seen_this_session[quote.symbol] = (
                    quote.received_at_ms, quote.exchange_at_ms,
                )
        if paper_router is not None:
            if require_fresh_held_position_for_paper:
                # Monitoring N50 is NOT a condition for protecting a held
                # contract. Separate market breadth health from exit routing.
                # Tick validation, ACK and snapshot causality are already
                # enforced upstream in D385/D386.
                if quote.symbol not in paper_router.monitored_symbols:
                    unrelated_frames_ignored_for_paper += 1
                    return
                if (quote.symbol not in seen_this_session
                        or seen_this_session[quote.symbol][0] != quote.received_at_ms
                        or not quote.has_positive_book_depth
                        or not 0 <= quote.received_at_ms - quote.exchange_at_ms
                               <= MAX_QUOTE_AGE_MS):
                    paper_frames_deferred += 1
                    return
            if require_complete_fresh_scope_for_paper and (
                not monitored.issubset(seen_this_session)
                or any(
                    not 0 <= quote.received_at_ms - seen_this_session[symbol][1]
                    <= MAX_QUOTE_AGE_MS for symbol in monitored
                )
            ):
                # No incomplete coverage can dispatch a synthetic financial
                # reservation; the next fresh tick must re-establish the gate.
                paper_frames_deferred += 1
                return
            paper_router.process(quote)
            paper_frames_routed += 1

    needs_callback = measure_public_coverage or paper_router is not None
    try:
        report: TickerLeaseReport = supervise_public_tickers(
            session_factory=session_factory or _public_bybit_session,
            book=book, budget=budget, clock=clock, wall_ms=wall_ms,
            sleeper=sleeper,
            on_quote=observed_quote if needs_callback else None,
            on_session_reset=session_reset if needs_callback else None,
        )
        values = report.sanitized_report()
        # A subscribe ACK does not prove even one current price observation.
        if report.ticker_frames_accepted == 0:
            values["status"] = "public_market_frames_not_verified"
        values["schema_version"] = "bybit-public-readonly-probe-d390-v1"
        values["public_data_only"] = True
        values["no_service_installed"] = True
        values["marketwide_top50_verified"] = False
        values["approved_for_live_use"] = False
        if paper_router is not None:
            # Only count-only metadata; never include instrument, price or IDs.
            values["paper_monitoring"] = paper_router.sanitized_report()
            if require_complete_fresh_scope_for_paper:
                values["paper_coverage_gate"] = {
                    "mode": "complete_fresh_scope_current_ws_session_only",
                    "quote_frames_deferred": paper_frames_deferred,
                    "quote_frames_delivered_to_paper": paper_frames_routed,
                    "orders_sent": False,
                    "approved_for_live_use": False,
                }
            if require_fresh_held_position_for_paper:
                values["paper_coverage_gate"] = {
                    "mode": "fresh_held_position_quote_independent_of_n50",
                    "quote_frames_deferred": paper_frames_deferred,
                    "quote_frames_delivered_to_paper": paper_frames_routed,
                    "unrelated_market_frames_ignored_for_paper":
                        unrelated_frames_ignored_for_paper,
                    "full_universe_required_for_existing_exits": False,
                    "orders_sent": False,
                    "approved_for_live_use": False,
                }
        if measure_public_coverage:
            stop_ms = wall_ms()
            if type(stop_ms) is not int or stop_ms < universe_at_ms:
                raise DataValidationError("public_ws_measurement_clock_invalid")
            sampled = set(seen_this_session)
            fresh = {
                symbol for symbol, (_, exchange_ms) in seen_this_session.items()
                if 0 <= stop_ms - exchange_ms <= MAX_QUOTE_AGE_MS
            }
            # "complete" here covers ONLY this finite lease; no assertion
            # about future delivery, publisher reliability, orders or stops.
            observed_all = monitored.issubset(sampled)
            fresh_all = monitored.issubset(fresh)
            values.update({
                "requested_ranked_contracts": len(rank_set),
                "requested_position_contracts": len(position_set),
                "requested_distinct_contracts": len(monitored),
                "unique_ranked_contracts_observed": len(rank_set & sampled),
                "unique_position_contracts_observed": len(position_set & sampled),
                "unique_distinct_contracts_observed": len(sampled),
                "fresh_distinct_contracts_at_end": len(fresh),
                "finite_coverage_observed_once": (
                    observed_all and report.status == "lease_completed"
                    and report.subscriptions_acknowledged >= 1),
                "finite_coverage_fresh_at_end": (
                    fresh_all and report.status == "lease_completed"
                    and report.subscriptions_acknowledged >= 1),
                "coverage_applies_to_final_session_only": True,
                "scope_independently_verified": False,
                "continuous_24x7_verified": False,
            })
            if diagnose_public_freshness:
                # Four disjoint count-only cohorts cover the final session.
                # Validated callbacks may be ineligible due to exchange age,
                # nonpositive depth or the prior point-in-time scope.
                values.update({
                    "freshness_evaluated_by_exchange_timestamp": True,
                    "validated_quote_contracts": len(validated_this_session),
                    "never_received_validated_quote_contracts": len(
                        monitored - validated_this_session),
                    "received_no_eligible_quote_contracts": len(
                        validated_this_session - sampled),
                    "eligible_quote_expired_at_end_contracts": len(
                        sampled - fresh),
                    "exchange_lagged_quote_callbacks": exchange_lagged_callbacks,
                    "exchange_lagged_quote_contracts": len(
                        exchange_lagged_this_session),
                })
        return values
    finally:
        # Even a completed finite lease is now closed, not a live source for
        # decisions: invalidate all in-memory quotes and subscription state.
        book.mark_disconnected()
