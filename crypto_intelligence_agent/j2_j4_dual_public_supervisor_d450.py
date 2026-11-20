"""D450: two existing Bybit public WS supervisors -> D449 PAPER callbacks.

Parallel, bounded kline.60 and tickers.* sessions are necessary: waiting
sequentially for an hour of candles would leave held stops unsupervised.
The existing J2 and D385 journals, ACK/clock/sequence validators are reused;
NO private channel, authenticated market data, live broker sender, cron,
daemon, release, or new financial ledger is introduced.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable

from .bybit_closed_stream_cache import (
    OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from .bybit_public_ticker_state_d385 import BybitPublicTickerBook
from .bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, supervise_public_tickers,
)
from .bybit_public_ws_once import _bounded_json
from .bybit_ws_supervisor import WSRunBudget, supervise_ws_research
from .j2_j4_public_paper_cycle_d449 import PublicPaperCycle
from .market_data import DataValidationError


@dataclass(frozen=True)
class DualPaperLeaseBudget:
    """Single bounded observation window, not a 24x7 protection service."""

    kline: WSRunBudget
    ticker: TickerLeaseBudget

    def __post_init__(self) -> None:
        if (type(self.kline) is not WSRunBudget
                or type(self.ticker) is not TickerLeaseBudget
                or self.kline.max_seconds != self.ticker.max_seconds
                or self.kline.max_sessions != 1
                or self.ticker.max_sessions != 1
                or self.kline.max_seconds > 3600):
            raise DataValidationError("D450 matched bounded public leases required")


def _denied(status: str) -> dict:
    return {
        "schema_version": "j2-j4-two-public-streams-paper-d450-v1",
        "status": status,
        "network_attempted": False,
        "journal_mutation_attempted": False,
        "orders_sent": False,
        "approved_for_live_use": False,
    }


def run_finite_n50_paper_streams(
    *, cycle: PublicPaperCycle,
    scope: OfflineReviewedStreamScope,
    journal_path: Path,
    budget: DualPaperLeaseBudget,
    allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    confirm_public_data_rights: bool = False,
    enable_hypothetical_paper_cycle: bool = False,
    kline_session_factory: Callable | None = None,
    ticker_session_factory: Callable | None = None,
    kline_clock_args: dict | None = None,
    ticker_clock_args: dict | None = None,
) -> dict:
    """Finite public-data + PAPER event loop, with testable socket injection.

    D386 and D385 deliver only post-ACK ticker callbacks; WS-WORK1 delivers
    only confirmed, appended, post-ACK kline frames. The D449 lock serializes
    their callbacks and D425 flock guards existing local PAPER exits.
    Requires explicit operator consent for ALL paths and can never send a
    real order. Injected factories always label the result OFFLINE regardless
    of their payload shape; real factories are lazily resolved only after
    all gates, only for the fixed Bybit V5 linear public WS endpoint.
    """
    flags = (
        allow_public_network, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        confirm_public_data_rights, enable_hypothetical_paper_cycle,
    )
    if any(type(f) is not bool for f in flags):
        raise DataValidationError("D450 explicit operator flags must be booleans")
    if not all(flags):
        return _denied("six_explicit_paper_public_data_optins_required")
    if (type(cycle) is not PublicPaperCycle
            or type(scope) is not OfflineReviewedStreamScope
            or not isinstance(journal_path, Path)
            or type(budget) is not DualPaperLeaseBudget
            or (kline_session_factory is None) != (ticker_session_factory is None)):
        raise DataValidationError("D450 typed two-stream PAPER inputs required")
    expected = frozenset(m.symbol for m in scope.contracts)
    if (expected != cycle._symbols
            or journal_path.resolve(strict=True) != cycle._closed.resolve(strict=True)):
        raise DataValidationError("D450 streams and PAPER cycle scope disagree")
    injections = kline_session_factory is not None
    if injections:
        if (not callable(kline_session_factory)
                or not callable(ticker_session_factory)
                or type(kline_clock_args) is not dict
                or type(ticker_clock_args) is not dict
                or any(not callable(v) for v in list(kline_clock_args.values()) + list(ticker_clock_args.values()))
                or set(kline_clock_args) != {"clock", "wall_ms", "sleeper"}
                or set(ticker_clock_args) != {"clock", "wall_ms", "sleeper"}):
            raise DataValidationError("D450 exact injected protocol test seams required")
    else:
        if (kline_clock_args is not None or ticker_clock_args is not None
                or os.name != "posix" or not hasattr(os, "geteuid")
                or os.geteuid() == 0):
            return _denied("owner_nonroot_public_session_required")
        # The sole supported real socket is the approved, public Bybit WSS.
        from .bybit_public_ws_once import ENDPOINT, _real_session_factory
        if ENDPOINT != "wss://stream.bybit.com/v5/public/linear":
            raise DataValidationError("D450 Bybit endpoint contract changed")
        kline_session_factory = _real_session_factory
        ticker_session_factory = _real_session_factory
        kline_clock_args = {}
        ticker_clock_args = {}

    if not 1 <= len(expected) <= 50:
        raise DataValidationError("D450 expected 1..50 Bybit linear research contracts")
    held_extra = tuple(sorted(cycle.monitored_symbols - expected))
    if len(held_extra) > 50:
        raise DataValidationError("D450 bounded outside-cohort held PAPER contracts")
    journal = SQLiteOfflineClosedStreamJournal(journal_path)
    book = BybitPublicTickerBook(
        ranked_symbols=tuple(sorted(expected)), position_symbols=held_extra,
        universe_at_ms=scope.observed_at_ms,
    )
    accepted = [0]

    def confirmed(raw: str | bytes, received_ms: int) -> None:
        parsed = _bounded_json(raw)
        if (type(parsed) is not dict or type(parsed.get("topic")) is not str
                or not parsed["topic"].startswith("kline.60.")
                or type(parsed.get("data")) is not list
                or len(parsed["data"]) != 1
                or type(parsed["data"][0]) is not dict
                or parsed["data"][0].get("confirm") is not True
                or type(parsed["data"][0].get("start")) is not int):
            raise DataValidationError("D450 only committed closed kline callback allowed")
        symbol = parsed["topic"][len("kline.60."):]
        cycle.on_confirmed_close(
            symbol=symbol, open_ms=parsed["data"][0]["start"],
            received_ms=received_ms,
        )
        accepted[0] += 1

    # Dual supervisors each own a separate socket. D449 callback lock and
    # AUTO2/AUTO4 transactions serialize their financial work; never create
    # a signal from the kline callback itself.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="cia-paper-dual") as pool:
        kline_future = pool.submit(
            supervise_ws_research,
            session_factory=kline_session_factory,
            scope=scope, journal=journal, budget=budget.kline,
            on_confirmed_frame=confirmed,
            **kline_clock_args,
        )
        ticker_future = pool.submit(
            supervise_public_tickers,
            session_factory=ticker_session_factory,
            book=book, budget=budget.ticker,
            on_quote=cycle.on_public_quote,
            on_session_reset=cycle.on_ticker_session_reset,
            **ticker_clock_args,
        )
        # Always await BOTH. Neither lease can be claimed to continue once
        # this method returns; a crash cannot leave an "active" status behind.
        kline_result = kline_future.result()
        ticker_result = ticker_future.result()
    complete = (
        kline_result.status == "ws_budget_ended_research_only"
        and ticker_result.status == "lease_completed"
    )
    return {
        "schema_version": "j2-j4-two-public-streams-paper-d450-v1",
        "status": (
            "finite_public_paper_research_closed"
            if complete else "finite_public_paper_research_degraded"
        ),
        "data_mode": (
            "injected_offline_protocol_replay"
            if injections else "public_ws_observed_unverified"
        ),
        "network_attempted": not injections,
        "kline_acks": kline_result.subscriptions_acknowledged,
        "ticker_acks": ticker_result.subscriptions_acknowledged,
        "accepted_closed_callbacks": accepted[0],
        "accepted_public_ticker_callbacks": ticker_result.ticker_frames_accepted,
        "kline_lease_status": kline_result.status,
        "ticker_lease_status": ticker_result.status,
        "session_continues_after_return": False,
        "native_stop_installed": False,
        "financial_backtest_approved": False,
        "marketwide_n50_verified": False,
        "paper_cycle": cycle.sanitized_report(),
        "orders_sent": False,
        "approved_for_live_use": False,
    }
