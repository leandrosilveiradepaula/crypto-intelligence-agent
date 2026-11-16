"""D390: explicit opt-in connector from D386 to existing Bybit WS transport.

Public market data ONLY: no private channels, signing, API keys, order sender,
SQLite, service installer, or persistent 24x7 worker. The single finite lease
can be run only with all required gates explicitly provided by the caller.
"""
from __future__ import annotations

import os
import time
from typing import Callable

from .bybit_public_ticker_state_d385 import BybitPublicTickerBook
from .bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, TickerLeaseReport, supervise_public_tickers,
)
from .bybit_public_ws_once import StreamSession
from .market_data import DataValidationError

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
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Finite, sanitized market-only run. Not a production data service.

    Requires positive gates before even constructing the transport. An
    injected factory is intended solely for hermetic tests. Returning a
    report never certifies full N50 delivery or live trading.
    """
    if (type(allow_public_websocket) is not bool
            or type(confirm_personal_readonly_research) is not bool
            or type(confirm_region_eligible) is not bool):
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
    # No fork/daemon in this method. The only allowed real transport is
    # the public, fixed URL, and the dependency remains lazily imported.
    if os.name != "posix" and session_factory is None:
        raise DataValidationError("public_ws_real_transport_requires_posix")
    if session_factory is not None and not callable(session_factory):
        raise DataValidationError("public_ws_injected_transport_invalid")
    book = BybitPublicTickerBook(
        ranked_symbols=ranked_symbols,
        position_symbols=position_symbols,
        universe_at_ms=universe_at_ms,
    )
    try:
        report: TickerLeaseReport = supervise_public_tickers(
            session_factory=session_factory or _public_bybit_session,
            book=book, budget=budget, clock=clock, wall_ms=wall_ms,
            sleeper=sleeper,
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
        return values
    finally:
        # Even a completed finite lease is now closed, not a live source for
        # decisions: invalidate all in-memory quotes and subscription state.
        book.mark_disconnected()
