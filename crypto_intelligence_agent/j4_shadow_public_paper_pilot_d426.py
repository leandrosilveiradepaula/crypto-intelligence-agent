"""D426: one bounded Bybit public WS lease with an EPHEMERAL PAPER shadow.

The first fresh, post-subscribe-ACK quote anchors a fictional position. Later
quotes pass through the EXISTING D391/D389 stop-first AUTO4 router. Unlike D425
this diagnostic needs no user-provisioned PAPER journal or trigger manifest.
No position survives this function, no venue order/fill is inferred and no
source is authenticated. It is NOT a signal generator, trading daemon, or
an authorized production service.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, localcontext
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Callable

from .bybit_public_ticker_state_d385 import (
    BybitPublicTickerBook, BybitTickerQuote, MAX_QUOTE_AGE_MS, _symbols,
)
from .bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, supervise_public_tickers,
)
from .bybit_public_ticker_optin_d390 import _public_bybit_session
from .bybit_public_ws_once import StreamSession
from .j2_current_j1_n50_public_scope_d406 import read_current_j1_n50_scope
from .market_data import DataGapError, DataValidationError
from .paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from .paper_intrahour_quote_router_d391 import (
    PaperIntrahourQuoteRouter, PaperQuoteRoute,
)
from .paper_intrahour_target_step_d387 import PaperIntrahourTargetPolicy
from .paper_position_reservations import SQLitePaperPositionJournal
from .synthetic_manual_exit_replay import _EXACT_CONTEXT
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from .synthetic_partial_exits import ExitBasis, SyntheticExitPlan, SyntheticExitTranche
from .synthetic_position_state import SyntheticSide

_SCHEMA = "j4-ephemeral-public-paper-shadow-d426-v1"
_POS_ID = "fixture_d426_ephemeral_position"
_PLAN = "d426-shadow-market-observation-v1"
_10000 = Decimal("10000")
_UNIT_QUANTUM = Decimal("0.000000000001")
_MIN_RELATIVE_NOTIONAL = Decimal("0.9999")


@dataclass(frozen=True)
class ShadowPaperPolicy:
    symbol: str
    side: SyntheticSide
    margin_quote: Decimal = Decimal("3")
    leverage: int = 50
    stop_distance_bps: Decimal = Decimal("100")
    target1_distance_bps: Decimal = Decimal("10")
    target2_distance_bps: Decimal = Decimal("20")
    max_entry_spread_bps: Decimal = Decimal("30")

    def __post_init__(self) -> None:
        if (type(self.symbol) is not str
                or _symbols((self.symbol,), maximum=1) != (self.symbol,)
                or type(self.side) is not SyntheticSide
                or type(self.leverage) is not int
                or not 1 <= self.leverage <= 100
                or not _decimal(self.margin_quote, positive=True)
                or not Decimal("0.01") <= self.margin_quote <= Decimal("10000")):
            raise DataValidationError("D426 hypothetical PAPER opening policy invalid")
        for n in ("stop_distance_bps", "target1_distance_bps",
                  "target2_distance_bps", "max_entry_spread_bps"):
            if not _decimal(getattr(self, n), positive=n != "max_entry_spread_bps"):
                raise DataValidationError("D426 hypothetical threshold must be Decimal")
        if (not Decimal("0") < self.stop_distance_bps <= Decimal("1000")
                or not Decimal("0") < self.target1_distance_bps
                    < self.target2_distance_bps <= Decimal("1000")
                or not Decimal("0") <= self.max_entry_spread_bps <= Decimal("100")):
            raise DataValidationError("D426 hypothetical distances/entry spread invalid")


def _decimal(n: object, *, positive: bool) -> bool:
    if type(n) is not Decimal or not n.is_finite():
        return False
    t = n.as_tuple()
    return (0 < len(t.digits) <= 40 and -18 <= t.exponent <= 24
            and (n > 0 if positive else n >= 0))


def _eligible_anchor(quote: BybitTickerQuote, policy: ShadowPaperPolicy,
                     universe_at_ms: int) -> bool:
    if (type(quote) is not BybitTickerQuote
            or quote.symbol != policy.symbol
            or quote.exchange_at_ms < universe_at_ms
            or not 0 <= quote.received_at_ms - quote.exchange_at_ms
                       <= MAX_QUOTE_AGE_MS
            or not quote.has_positive_book_depth
            or not 0 < quote.bid_price <= quote.ask_price
            or quote.mark_price <= 0):
        return False
    with localcontext(_EXACT_CONTEXT):
        spread_bps = (quote.ask_price - quote.bid_price) * _10000 / quote.mark_price
        max_mark_deviation_bps = max(
            abs(quote.bid_price - quote.mark_price),
            abs(quote.ask_price - quote.mark_price),
        ) * _10000 / quote.mark_price
    return (spread_bps <= policy.max_entry_spread_bps
            and max_mark_deviation_bps <= Decimal("500"))


def _seed_paper_at_quote(
    journal_path: Path, policy: ShadowPaperPolicy, anchor: BybitTickerQuote,
) -> PaperIntrahourQuoteRouter:
    """Create a *fictitious* filled entry at observed MARK (not an execution).

    The effective margin can be marginally below the configured amount due to
    SYNTHETIC base-unit quantization. It may never exceed the request or
    silently drift more than 1 bp. The quantum is NOT a Bybit lot specification.
    """
    with localcontext(_EXACT_CONTEXT):
        wanted_notional = policy.margin_quote * Decimal(policy.leverage)
        units = (wanted_notional / anchor.mark_price).quantize(
            _UNIT_QUANTUM, rounding=ROUND_DOWN,
        )
        effective_notional = units * anchor.mark_price
        if (units <= 0 or effective_notional > wanted_notional
                or effective_notional < wanted_notional * _MIN_RELATIVE_NOTIONAL):
            raise DataValidationError("D426 hypothetical units cannot track requested margin")
        step = units / Decimal(100)
        stop_ratio = policy.stop_distance_bps / _10000
        t1_ratio = policy.target1_distance_bps / _10000
        t2_ratio = policy.target2_distance_bps / _10000
        if policy.side is SyntheticSide.LONG:
            stop = anchor.mark_price * (1 - stop_ratio)
            targets = (
                anchor.mark_price * (1 + t1_ratio),
                anchor.mark_price * (1 + t2_ratio),
            )
            open_side = PaperOrderSide.BUY
        else:
            stop = anchor.mark_price * (1 + stop_ratio)
            targets = (
                anchor.mark_price * (1 - t1_ratio),
                anchor.mark_price * (1 - t2_ratio),
            )
            open_side = PaperOrderSide.SELL
    if min(stop, *targets) <= 0:
        raise DataValidationError("D426 hypothetical barrier invalid")

    # This is an EXPLICIT, GENERATED FIXTURE FILL to establish scenario state,
    # never inferred from the public market or a Bybit ACK. No AUTO2 or
    # collateral/venue margin receipt is generated.
    opening = PaperOrderIntent(
        intent_id="fixture_d426_open", fixture_signal_id="fixture_d426_not_signal",
        venue=PaperVenue.BYBIT_V5, symbol=policy.symbol,
        position_side=policy.side, side=open_side,
        effect=PaperOrderEffect.OPEN, requested_units=units,
        created_at_ms=anchor.received_at_ms - 1,
    )
    store = SQLitePaperPositionJournal(journal_path)
    store.create_position(
        position_id=_POS_ID, opening_intent=opening,
        opening_events=(PaperOrderEvent(
            "fixture_d426_fabricated_open_fill_for_research",
            PaperOrderEventKind.FILL, anchor.received_at_ms, units,
        ),),
        exit_plan=SyntheticExitPlan(
            initial_units=units,
            tranches=(
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal(30)),
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal(20)),
            ),
            residual_floor_percent=Decimal(50),
        ),
        plan_version=_PLAN, synthetic_lot_step_units=step,
        as_of_ms=anchor.received_at_ms,
    )
    return PaperIntrahourQuoteRouter(
        position_path=journal_path,
        routes=(PaperQuoteRoute(
            _POS_ID,
            PaperEmergencyStopRule(stop, max_quote_age_ms=MAX_QUOTE_AGE_MS),
            PaperIntrahourTargetPolicy(
                _PLAN, targets, max_quote_age_ms=MAX_QUOTE_AGE_MS,
            ),
        ),),
    )


def observe_shadow_paper_once(
    *, state_directory: Path,
    policy: ShadowPaperPolicy,
    allow_private_pointer_read: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_hypothetical_paper_open: bool = False,
    budget: TickerLeaseBudget = TickerLeaseBudget(
        max_sessions=1, max_frames=100_000, max_seconds=30,
    ),
    session_factory: Callable[[], StreamSession] | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """One public market lease with ephemeral fictional opening and exits.

    No private files or socket until *all* five explicit gates. Every test
    can use an injected fake session, but only an independently gated owner
    can run a real finite pilot on an approved host.
    """
    gates = (
        allow_private_pointer_read, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        allow_hypothetical_paper_open,
    )
    if any(type(g) is not bool for g in gates):
        raise DataValidationError("D426 public PAPER gate types invalid")
    if not all(gates):
        return {
            "schema_version": _SCHEMA,
            "status": "explicit_owner_market_shadow_optins_required",
            "owner_scope_read": False, "network_attempted": False,
            "synthetic_open_created": False, "orders_sent": False,
            "approved_for_live_use": False,
        }
    if (type(policy) is not ShadowPaperPolicy
            or not isinstance(state_directory, Path)
            or not state_directory.is_absolute()
            or type(budget) is not TickerLeaseBudget
            or budget.max_seconds > 60 or budget.max_frames > 100_000
            or budget.max_sessions > 2
            or not all(callable(c) for c in (clock, wall_ms, sleeper))
            or (session_factory is not None and not callable(session_factory))
            or (session_factory is None
                and (os.name != "posix" or os.geteuid() == 0))):
        raise DataValidationError("D426 scope, budget or platform invalid")
    started_ms = wall_ms()
    current = read_current_j1_n50_scope(
        state_directory=state_directory,
        now_ms=started_ms, allow_private_pointer_read=True,
    )
    if len(current.symbols) != 50:
        raise DataValidationError("D426 owner N50 scope incomplete")
    extra = () if policy.symbol in current.symbols else (policy.symbol,)
    ticker_book = BybitPublicTickerBook(
        ranked_symbols=current.symbols, position_symbols=extra,
        universe_at_ms=current.activated_at_ms,
    )
    shadow_seeded = False
    followed = 0
    candidate_skipped = 0
    owner_unchanged = False

    with TemporaryDirectory(prefix="cia-d426-shadow-") as directory:
        journal = Path(directory) / "paper-positions.sqlite"
        router: PaperIntrahourQuoteRouter | None = None
        open_at_ms: int | None = None

        def new_session() -> None:
            if router is not None:
                router.begin_new_market_session()

        def quote_received(quote: BybitTickerQuote) -> None:
            nonlocal router, shadow_seeded, followed
            nonlocal candidate_skipped, open_at_ms
            if quote.symbol != policy.symbol:
                return
            if router is None:
                if not _eligible_anchor(quote, policy, current.activated_at_ms):
                    candidate_skipped += 1
                    return
                router = _seed_paper_at_quote(journal, policy, quote)
                journal.chmod(0o600)
                open_at_ms = quote.received_at_ms
                shadow_seeded = True
                return
            # The seed quote is never recycled as its own exit trigger.
            # Event exchange time must follow the hypothetical opening.
            if open_at_ms is None or quote.exchange_at_ms <= open_at_ms:
                candidate_skipped += 1
                return
            router.process(quote)
            followed += 1

        result = supervise_public_tickers(
            session_factory=session_factory or _public_bybit_session,
            book=ticker_book, budget=budget,
            clock=clock, wall_ms=wall_ms, sleeper=sleeper,
            on_quote=quote_received, on_session_reset=new_session,
        )
        try:
            after = read_current_j1_n50_scope(
                state_directory=state_directory,
                now_ms=wall_ms(), allow_private_pointer_read=True,
            )
            owner_unchanged = (
                after.activated_at_ms == current.activated_at_ms
                and after.ranked_scope_sha256 == current.ranked_scope_sha256
                and after.metadata_sha256 == current.metadata_sha256
                and after.symbols == current.symbols
            )
        except (DataGapError, DataValidationError):
            owner_unchanged = False
        decisions = {} if router is None else router.sanitized_report()["decision_counts"]
        try:
            reserved = 0
            if router is not None:
                bal = SQLitePaperPositionJournal(journal).load(_POS_ID)
                reserved = len(bal.exit_orders)
        except (DataGapError, DataValidationError):
            reserved = 0
        status = (
            "owner_scope_changed_or_unavailable" if not owner_unchanged
            else "public_lease_degraded_or_abstained"
                if result.status != "lease_completed"
            else "no_valid_shadow_anchor" if not shadow_seeded
            else "shadow_opened_no_followup_quote" if followed == 0
            else "shadow_public_quote_routed_paper_only"
        )
        return {
            "schema_version": _SCHEMA,
            "status": status,
            "data_mode": ("injected_offline_fixture"
                          if session_factory is not None
                          else "real_public_websocket"),
            "owner_scope_read": True,
            "owner_scope_unchanged_after_lease": owner_unchanged,
            "subscribed_contracts": len(current.symbols) + len(extra),
            "subscription_acks": result.subscriptions_acknowledged,
            "ticker_frames_accepted": result.ticker_frames_accepted,
            "reconnects": result.reconnects,
            "market_failure_category": result.failure_category,
            "synthetic_open_created": shadow_seeded,
            "synthetic_entry_fill_fabricated_for_research": shadow_seeded,
            "position_quote_events_after_open": followed,
            "position_quote_events_deferred": candidate_skipped,
            "synthetic_exit_intents_reserved": reserved,
            "paper_decision_counts": decisions,
            "configured_leverage": policy.leverage,
            "requested_margin_quote_synthetic_only": str(policy.margin_quote),
            "requested_margin_is_actual_collateral": False,
            "market_quote_is_executable_fill": False,
            "fixture_venue_lot_step_verified": False,
            "marketwide_top50_verified": False,
            "entry_signal_generated": False,
            "native_stop_verified": False,
            "synthetic_position_persisted_after_run": False,
            "continuous_24x7_verified": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
