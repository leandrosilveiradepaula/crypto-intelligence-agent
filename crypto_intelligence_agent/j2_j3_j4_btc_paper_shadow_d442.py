"""D442: J2 public BTC tick -> J3 cost hurdle -> J4 AUTO4 PAPER shadow.

Single opt-in finite session. Reuses D441 REST instrument review, D386 ticker
supervision, J3/PRE2 Decimal cost engine and D426/D391/D389 AUTO4 reserved
exits. No J1 state, financial execution, invented market fills or real PnL.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, localcontext
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Callable

from .bybit_closed_stream_cache import OfflineReviewedStreamScope, _scope_contract_fingerprint
from .bybit_public_j1_transport import J1BybitCaptureError
from .bybit_public_ticker_optin_d390 import _public_bybit_session
from .bybit_public_ticker_state_d385 import BybitPublicTickerBook, BybitTickerQuote
from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget, supervise_public_tickers
from .j2_public_btc_scope_d441 import fetch_single_btc_scope_from_public_rest
from .j4_shadow_public_paper_pilot_d426 import (
    ShadowPaperPolicy, _eligible_anchor, _seed_paper_at_quote,
    _UNIT_QUANTUM, _MIN_RELATIVE_NOTIONAL,
)
from .market_data import DataGapError, DataValidationError
from .paper_position_reservations import SQLitePaperPositionJournal
from .synthetic_cost_scenarios import (
    BPS_DENOMINATOR, SyntheticCostScenario, _rate, evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import _EXACT_CONTEXT
from .synthetic_position_state import SyntheticSide

_POS_ID = "fixture_d426_ephemeral_position"
_MAX_MS = 4_102_444_800_000


@dataclass(frozen=True)
class CostedShadowPolicy:
    """Explicit J3 cost assumptions for D426's existing PAPER exit plan."""

    shadow: ShadowPaperPolicy
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_adverse_slippage_bps: Decimal
    exit_adverse_slippage_bps: Decimal

    def __post_init__(self) -> None:
        if type(self.shadow) is not ShadowPaperPolicy or self.shadow.symbol != "BTCUSDT":
            raise DataValidationError("D442 single BTCUSDT shadow policy required")
        for name in (
            "entry_fee_bps", "exit_fee_bps", "entry_adverse_slippage_bps",
            "exit_adverse_slippage_bps",
        ):
            value = getattr(self, name)
            _rate(value, name, signed=False)
            if value > Decimal("1000"):
                raise DataValidationError("D442 unrealistic cost research bound")


def _assumed_entry_cost_and_stop_margin_screen(
    quote: BybitTickerQuote, policy: CostedShadowPolicy,
) -> tuple[bool, bool]:
    """J3 necessary (NOT sufficient) screens before any fictitious PAPER open.

    First 30% target must exceed its declared pro-rata entry+exit costs.
    Separately, an immediate, fully filled hypothetical stop plus the
    same costs may not already exhaust the configured isolated margin.
    Neither screen models exchange liquidation, gap-through, funding,
    collateral, BBO fillability, maintenance tiers or actual trading.
    """
    shadow = policy.shadow
    mark = quote.mark_price
    with localcontext(_EXACT_CONTEXT):
        wanted = shadow.margin_quote * Decimal(shadow.leverage)
        units = (wanted / mark).quantize(_UNIT_QUANTUM, rounding=ROUND_DOWN)
        entry_notional = units * mark
        if (units <= 0 or entry_notional > wanted
                or entry_notional < wanted * _MIN_RELATIVE_NOTIONAL):
            raise DataValidationError("D442 synthetic quantity cannot match declared margin")
        side_long = shadow.side is SyntheticSide.LONG
        direction = ResearchDirection.LONG if side_long else ResearchDirection.SHORT
        first_target = (mark * (1 + shadow.target1_distance_bps / BPS_DENOMINATOR)
                        if side_long else
                        mark * (1 - shadow.target1_distance_bps / BPS_DENOMINATOR))
        hypothetical_stop = (
            mark * (1 - shadow.stop_distance_bps / BPS_DENOMINATOR)
            if side_long else
            mark * (1 + shadow.stop_distance_bps / BPS_DENOMINATOR))
        if first_target <= 0 or hypothetical_stop <= 0:
            raise DataValidationError("D442 hypothetical bracket invalid")

        def cost(quantity: Decimal, exit_price: Decimal) -> Decimal:
            breakdown = evaluate_synthetic_costs(SyntheticCostScenario(
                direction=direction,
                entry_at_ms=quote.received_at_ms,
                exit_at_ms=quote.received_at_ms + 1,
                entry_hypothetical_notional_quote_units=quantity * mark,
                exit_hypothetical_notional_quote_units=quantity * exit_price,
                entry_fee_bps=policy.entry_fee_bps,
                exit_fee_bps=policy.exit_fee_bps,
                entry_adverse_slippage_bps=policy.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=policy.exit_adverse_slippage_bps,
            ))
            return breakdown.total_signed_cost_units

        tranche = units * Decimal("0.30")
        expected_first_target_gross = tranche * abs(first_target - mark)
        first_target_positive = expected_first_target_gross > cost(tranche, first_target)
        # This is an optimistic immediate STOP at exactly the configured mark,
        # so a loss at or above the provided margin is a decisive veto.
        hypothetical_stop_loss = units * abs(hypothetical_stop - mark)
        stop_below_margin = (
            hypothetical_stop_loss + cost(units, hypothetical_stop)
            < shadow.margin_quote
        )
        return first_target_positive, stop_below_margin


def observe_costed_btc_paper_shadow_once(
    *, policy: CostedShadowPolicy,
    allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_hypothetical_paper_open: bool = False,
    budget: TickerLeaseBudget = TickerLeaseBudget(1, 20_000, 30),
    session_factory: Callable | None = None,
    offline_scope: OfflineReviewedStreamScope | None = None,
    clock: Callable[[], float] | None = None,
    wall_ms: Callable[[], int] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> dict:
    """Owner-only real session or explicitly labelled injected offline replay.

    Public WS prices can only reserve PAPER reduce-only EXIT intents in
    disposable AUTO4. An opening FILL, if created, is explicitly FABRICATED
    by D426 as a research anchor, never inferred from a Bybit message.
    """
    gates = (allow_public_network, allow_public_websocket,
             confirm_personal_readonly_research, confirm_region_eligible,
             allow_hypothetical_paper_open)
    denied = {
        "schema_version": "j2-j3-j4-btc-shadow-d442-v1",
        "status": "explicit_btc_paper_research_optins_required",
        "network_attempted": False, "j1_state_accessed": False,
        "orders_sent": False, "approved_for_live_use": False,
    }
    if any(type(g) is not bool for g in gates):
        raise DataValidationError("D442 explicit opt-in types required")
    if not all(gates):
        return denied
    if (type(policy) is not CostedShadowPolicy or type(budget) is not TickerLeaseBudget
            or budget.max_sessions != 1 or budget.max_seconds > 60
            or budget.max_frames > 100_000):
        raise DataValidationError("D442 bounded policy or budget required")
    real = session_factory is None
    if real:
        if offline_scope is not None or any(x is not None for x in (clock, wall_ms, sleeper)):
            raise DataValidationError("D442 no injected inputs on real public transport")
        if (os.name != "posix" or not hasattr(os, "geteuid")
                or not hasattr(os, "getuid") or os.getuid() != os.geteuid()
                or os.geteuid() == 0):
            return {**denied, "status": "unprivileged_owner_required"}
    else:
        if (not callable(session_factory) or
                type(offline_scope) is not OfflineReviewedStreamScope or
                not all(callable(x) for x in (clock, wall_ms, sleeper))):
            raise DataValidationError("D442 injected offline session must be explicit")

    if real:
        try:
            scope = fetch_single_btc_scope_from_public_rest()
        except (J1BybitCaptureError, DataGapError, DataValidationError,
                OSError, ValueError, TypeError):
            return {**denied, "status": "single_btc_public_rest_abstained",
                    "network_attempted": True}
        # REST network latency advances the wall clock. Reading the current
        # instant BEFORE GET would falsely mark every genuine scope future.
        current_ms = time.time_ns() // 1_000_000
    else:
        scope = offline_scope
        current_ms = wall_ms()
    if (type(current_ms) is not int or
            not 1_600_000_000_000 <= current_ms < _MAX_MS):
        raise DataValidationError("D442 observed market clock invalid")
    _scope_contract_fingerprint(scope)
    if (len(scope.contracts) != 1 or scope.contracts[0].symbol != "BTCUSDT"
            or not 0 <= current_ms - scope.observed_at_ms <= 30_000):
        raise DataValidationError("D442 single recent BTC metadata required")
    if Decimal(policy.shadow.leverage) > scope.contracts[0].max_leverage:
        return {**denied,
                "status": "declared_leverage_exceeds_observed_contract_cap",
                "network_attempted": real}
    clock_fn = time.monotonic if real else clock
    wall_fn = (lambda: time.time_ns() // 1_000_000) if real else wall_ms
    sleep_fn = time.sleep if real else sleeper
    book = BybitPublicTickerBook(
        ranked_symbols=("BTCUSDT",), universe_at_ms=scope.observed_at_ms,
    )
    seeded = followed = cost_blocked = stop_blocked = eligible = 0
    with TemporaryDirectory(prefix="cia-d442-btc-shadow-") as directory:
        paper = Path(directory) / "paper-positions.sqlite"
        router = None
        open_at_ms = None

        def reset_session() -> None:
            if router is not None:
                router.begin_new_market_session()

        def poll_held() -> None:
            if router is None:
                return
            now = wall_fn()
            # The seed quote is deliberately NOT forwarded as an exit quote.
            # Before the first later quote, use the seed reception time as
            # a bounded grace period; do not require a nonexistent router mark.
            if followed == 0:
                if open_at_ms is None or not 0 <= now - open_at_ms <= 3000:
                    raise DataGapError("paper_held_quote_silence_exceeded")
            elif router.fresh_held_contract_count(
                    at_ms=now, max_age_ms=3000) != 1:
                raise DataGapError("paper_held_quote_silence_exceeded")

        def route_quote(quote: BybitTickerQuote) -> None:
            nonlocal seeded, followed, cost_blocked, stop_blocked, eligible
            nonlocal router, open_at_ms
            if router is None:
                if not _eligible_anchor(quote, policy.shadow, scope.observed_at_ms):
                    return
                eligible += 1
                target_ok, stop_ok = _assumed_entry_cost_and_stop_margin_screen(
                    quote, policy)
                if not target_ok:
                    cost_blocked += 1
                if not stop_ok:
                    stop_blocked += 1
                if not target_ok or not stop_ok:
                    return
                router = _seed_paper_at_quote(paper, policy.shadow, quote)
                paper.chmod(0o600)
                open_at_ms = quote.received_at_ms
                seeded += 1
                return
            if open_at_ms is not None and quote.exchange_at_ms > open_at_ms:
                router.process(quote)
                followed += 1

        result = supervise_public_tickers(
            session_factory=(_public_bybit_session if real else session_factory),
            book=book, budget=budget, clock=clock_fn, wall_ms=wall_fn,
            sleeper=sleep_fn, on_quote=route_quote,
            on_session_reset=reset_session, on_acked_poll=poll_held,
        )
        decisions = ({} if router is None else
                     router.sanitized_report()["decision_counts"])
        count = 0
        if router is not None:
            count = len(SQLitePaperPositionJournal(paper).load(_POS_ID).exit_orders)
        if result.status != "lease_completed":
            status = "public_ticker_lease_abstained"
        elif not seeded:
            status = ("assumed_stop_margin_exhaustion_blocked"
                      if stop_blocked else
                      "assumed_first_partial_cost_hurdle_blocked"
                      if cost_blocked else "no_valid_public_shadow_anchor")
        elif not followed:
            status = "hypothetical_shadow_open_no_followup_quote"
        else:
            status = "public_quote_routed_to_costed_paper_reservations"
        return {
            "schema_version": "j2-j3-j4-btc-shadow-d442-v1",
            "status": status,
            "data_mode": ("public_ws_observed_unverified" if real
                          else "injected_offline_protocol_replay"),
            "network_attempted": real,
            "j1_state_accessed": False,
            "public_rest_contract_count": 1 if real else 0,
            "ticker_subscription_acks": result.subscriptions_acknowledged,
            "ticker_frames_accepted": result.ticker_frames_accepted,
            "ticker_failure_category": result.failure_category,
            "j3_cost_hurdle_evaluated": eligible,
            "j3_first_partial_cost_hurdle_blocked": cost_blocked,
            "j3_assumed_stop_margin_exhaustion_blocked": stop_blocked,
            "j3_cost_assumptions_declared": True,
            "j3_stop_execution_verified": False,
            "j3_real_margin_balance_verified": False,
            "j3_funding_known": False,
            "j3_liquidation_path_verified": False,
            "j3_out_of_sample_validated": False,
            "j4_hypothetical_filled_open_injected_explicitly": bool(seeded),
            "j4_quote_events_after_open": followed,
            "j4_reduce_only_reservations": count,
            "j4_decision_counts": decisions,
            "j4_order_fills_inferred_from_quotes": False,
            "j4_native_stop_verified": False,
            "paper_position_persisted": False,
            "marketwide_top50_verified": False,
            "entry_signal_generated": False,
            "orders_sent": False,
            "order_submission_enabled": False,
            "approved_for_live_use": False,
        }
