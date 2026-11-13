"""J3/PRE29: suppress synthetic runner PnL if a prior mark-path terminal is seen.

The J3 mark replay keeps INITIAL notional through every tick: a deliberately
conservative stress proxy, NOT a reduced-size liquidation simulation. A clean
discrete path does not establish intrabar survival or a venue fill.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .market_data import DataValidationError
from .synthetic_cost_scenarios import SyntheticFundingEvent
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import _EXACT_CONTEXT
from .synthetic_mark_replay import (
    SyntheticMarkReplayPlan, SyntheticMarkTick, SyntheticReplayState,
    replay_synthetic_mark_path,
)
from .synthetic_partial_costed_replay import (
    SyntheticPartialCostRates, SyntheticPartialMarkFill,
)
from .synthetic_position_state import SyntheticPosition, SyntheticSide
from .synthetic_risk_tiers import SyntheticRiskSnapshot
from .synthetic_runner_costed_close import (
    SyntheticRunnerCloseMarkFill, evaluate_synthetic_runner_costed_closure,
)

_STATES = {
    SyntheticReplayState.LIQUIDATION_CONDITION:
        "abstain_full_notional_mark_liquidation_proxy",
    SyntheticReplayState.CONDITIONAL_STOP:
        "abstain_prior_conditional_stop",
    SyntheticReplayState.CONDITIONAL_TARGET:
        "abstain_prior_conditional_target",
    SyntheticReplayState.OPEN_UNRESOLVED:
        "conditional_reference_no_discrete_terminal_observed",
}


@dataclass(frozen=True)
class SyntheticRunnerRiskGate:
    """Safe read-only research projection, never a venue decision."""

    status: str
    initial_leverage: int
    checked_mark_ticks: int
    first_terminal_at_ms: int | None
    worst_full_notional_mark_equity_quote: Decimal
    hypothetical_net_if_no_unobserved_events_quote: Decimal | None
    runner_closed_units: Decimal
    funding_event_count: int

    @property
    def liquidation_risk_verified(self) -> bool:
        return False

    @property
    def intrabar_trajectory_verified(self) -> bool:
        return False

    @property
    def venue_fills_verified(self) -> bool:
        return False

    @property
    def real_pnl_verified(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    def sanitized_report(self) -> dict[str, object]:
        return {
            "status": self.status,
            "initial_leverage": self.initial_leverage,
            "checked_mark_ticks": self.checked_mark_ticks,
            "has_prior_discrete_terminal": self.first_terminal_at_ms is not None,
            "worst_full_notional_mark_equity_quote": str(
                self.worst_full_notional_mark_equity_quote
            ),
            "hypothetical_net_if_no_unobserved_events_quote": (
                str(self.hypothetical_net_if_no_unobserved_events_quote)
                if self.hypothetical_net_if_no_unobserved_events_quote is not None
                else None
            ),
            "runner_closed_units": str(self.runner_closed_units),
            "funding_event_count": self.funding_event_count,
            "full_initial_notional_proxy_only": True,
            "partial_derisking_in_mark_path_modeled": False,
            "liquidation_risk_verified": False,
            "intrabar_trajectory_verified": False,
            "venue_fills_verified": False,
            "real_pnl_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
        }


def evaluate_synthetic_runner_risk_gate(
    position: SyntheticPosition,
    partial_fills: tuple[SyntheticPartialMarkFill, ...],
    runner_receipts: tuple[SyntheticRunnerCloseMarkFill, ...],
    *,
    entry_reference_price_quote: Decimal,
    cost_rates: SyntheticPartialCostRates,
    mark_plan: SyntheticMarkReplayPlan,
    mark_ticks: tuple[SyntheticMarkTick, ...],
    as_of_ms: int,
    max_tick_gap_ms: int,
    funding_events: tuple[SyntheticFundingEvent, ...] = (),
    risk_snapshots: tuple[SyntheticRiskSnapshot, ...] | None = None,
    max_risk_snapshot_age_ms: int | None = None,
) -> SyntheticRunnerRiskGate:
    """Veto rather than score a runner close when J3 sees any prior terminal.

    The sole admissible final mark tick is the declared terminal receipt time.
    Every partial exit must have an exactly matching declared trade tick; no
    mark, trigger or OHLC may be promoted to a fill. Missing coverage ABSTAINS
    via DataValidationError instead of granting a favorable result.
    """
    if (type(position) is not SyntheticPosition
            or type(mark_plan) is not SyntheticMarkReplayPlan
            or type(cost_rates) is not SyntheticPartialCostRates
            or type(mark_ticks) is not tuple
            or type(partial_fills) is not tuple
            or type(runner_receipts) is not tuple
            or not runner_receipts
            or type(as_of_ms) is not int
            or type(max_tick_gap_ms) is not int
            or not 1 <= max_tick_gap_ms <= 86_400_000
            or type(funding_events) is not tuple
            or any(type(f) is not SyntheticFundingEvent for f in funding_events)):
        raise DataValidationError("typed bounded runner risk research inputs required")
    if (not mark_ticks or any(type(t) is not SyntheticMarkTick for t in mark_ticks)
            or any(type(f) is not SyntheticPartialMarkFill for f in partial_fills)
            or any(type(f) is not SyntheticRunnerCloseMarkFill for f in runner_receipts)):
        raise DataValidationError("complete typed runner, partial and mark fixture required")

    first_receipt = runner_receipts[0]
    if (as_of_ms != first_receipt.event_at_ms
            or mark_ticks[-1].at_ms != first_receipt.event_at_ms):
        raise DataValidationError("runner close must coincide with final observed trade tick")

    direction = (ResearchDirection.LONG if position.side is SyntheticSide.LONG
                 else ResearchDirection.SHORT)
    if (mark_plan.direction is not direction
            or mark_plan.entry_at_ms != position.opened_at_ms
            or mark_plan.entry_price != entry_reference_price_quote
            or mark_plan.quantity_base != position.plan.initial_units
            or mark_plan.margin.quote_currency != "SYNTHETIC_USDT"
            or mark_plan.margin.leverage_at_intent != position.leverage_at_open
            or mark_plan.margin.requested_margin_quote != position.synthetic_margin_units
            or mark_plan.entry_fee_bps != cost_rates.entry_fee_bps
            or mark_plan.exit_fee_bps != cost_rates.exit_fee_bps
            or mark_plan.entry_slippage_bps != cost_rates.entry_adverse_slippage_bps
            or mark_plan.exit_slippage_bps != cost_rates.exit_adverse_slippage_bps):
        raise DataValidationError("runner and mark proxy contracts disagree")

    # Catch absent / misbound prices before any conditional PnL is exposed.
    indexed: dict[int, SyntheticMarkTick] = {tick.at_ms: tick for tick in mark_ticks}
    if len(indexed) != len(mark_ticks):
        raise DataValidationError("ambiguous mark tick time")
    for p in partial_fills:
        tick = indexed.get(p.bound_fill.event.event_at_ms)
        if tick is None or tick.trade_price != p.reference_exit_price_quote:
            raise DataValidationError("partial fill lacks matching observed trade tick")
    if mark_ticks[-1].trade_price != first_receipt.reference_exit_price_quote:
        raise DataValidationError("runner receipt lacks matching final trade tick")

    if (len(set(f.event_id for f in funding_events)) != len(funding_events)
            or len(set(f.event_at_ms for f in funding_events)) != len(funding_events)):
        raise DataValidationError("risk comparison cannot use ambiguous funding events")

    # J4 validates all tranche arithmetic / fee accounting / funding sizing.
    closed = evaluate_synthetic_runner_costed_closure(
        position, partial_fills, runner_receipts,
        entry_reference_price_quote=entry_reference_price_quote,
        cost_rates=cost_rates, as_of_ms=as_of_ms,
        funding_events=funding_events,
    )
    # J3 retains full initial notional even after fictitious partial reductions.
    # Such a path can VETO, never prove liquidations or actual safety.
    mark = replay_synthetic_mark_path(
        mark_plan, mark_ticks, funding_events,
        as_of_ms=as_of_ms,
        risk_snapshots=risk_snapshots,
        max_tick_gap_ms=max_tick_gap_ms,
        max_risk_snapshot_age_ms=max_risk_snapshot_age_ms,
    )
    with localcontext(_EXACT_CONTEXT):
        if (mark.state is SyntheticReplayState.OPEN_UNRESOLVED
                and mark.observations[-1].signed_funding_paid_quote
                    != closed.signed_funding_cost_quote):
            raise DataValidationError("mark and costed runner funding disagree")
    return SyntheticRunnerRiskGate(
        status=_STATES[mark.state],
        initial_leverage=position.leverage_at_open,
        checked_mark_ticks=len(mark.observations),
        first_terminal_at_ms=mark.first_trigger_at_ms,
        worst_full_notional_mark_equity_quote=mark.worst_mark_equity_quote,
        hypothetical_net_if_no_unobserved_events_quote=(
            closed.hypothetical_net_closed_reference_quote
            if mark.state is SyntheticReplayState.OPEN_UNRESOLVED else None
        ),
        runner_closed_units=closed.runner_closed_units,
        funding_event_count=closed.unique_funding_count,
    )
