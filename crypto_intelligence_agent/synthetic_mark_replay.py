"""J3/PRE16: synthetic tick replay with declared mark and trade prices.

All prices/timestamps are supplied fixtures; no OHLC ordering, venue margin
formula, order placement, or actual liquidation/fill is inferred.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum

from .market_data import DataValidationError
from .synthetic_cost_scenarios import (
    SyntheticCostScenario, SyntheticFundingEvent, evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_margin_envelope import SyntheticMarginBasis
from .synthetic_feature_engine import validate_synthetic_research_price
from .synthetic_manual_exit_replay import _utc_ms

_CTX = Context(prec=512, rounding=ROUND_HALF_EVEN)
MAX_TICKS = 2048


@dataclass(frozen=True)
class SyntheticMarkTick:
    at_ms: int
    mark_price: Decimal
    trade_price: Decimal

    def __post_init__(self) -> None:
        _utc_ms(self.at_ms, "tick")
        validate_synthetic_research_price(self.mark_price, "mark")
        validate_synthetic_research_price(self.trade_price, "trade")


@dataclass(frozen=True)
class SyntheticMarkReplayPlan:
    direction: ResearchDirection
    entry_at_ms: int
    entry_price: Decimal
    quantity_base: Decimal
    stop_price: Decimal
    target_price: Decimal
    margin: SyntheticMarginBasis
    maintenance_rate_bps: Decimal
    reserve_for_close_quote: Decimal
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_slippage_bps: Decimal
    exit_slippage_bps: Decimal

    def __post_init__(self) -> None:
        from .synthetic_cost_scenarios import _amount, _rate
        if type(self.direction) is not ResearchDirection:
            raise DataValidationError("explicit position direction required")
        _utc_ms(self.entry_at_ms, "entry")
        for name in ("entry_price", "stop_price", "target_price"):
            validate_synthetic_research_price(getattr(self, name), name)
        _amount(self.quantity_base, "quantity")
        if type(self.margin) is not SyntheticMarginBasis:
            raise DataValidationError("explicit margin basis required")
        _rate(self.maintenance_rate_bps, "maintenance rate", signed=False)
        for name in ("entry_fee_bps", "exit_fee_bps",
                     "entry_slippage_bps", "exit_slippage_bps"):
            _rate(getattr(self, name), name, signed=False)
        if (type(self.reserve_for_close_quote) is not Decimal
                or not self.reserve_for_close_quote.is_finite()
                or self.reserve_for_close_quote < 0):
            raise DataValidationError("nonnegative exact reserve required")
        _amount(self.reserve_for_close_quote + Decimal("0.000000000000000001"),
                "reserve bounds")
        with localcontext(_CTX):
            if self.quantity_base * self.entry_price != self.margin.entry_notional_quote:
                raise DataValidationError("entry quantity and price disagree with margin")
        if self.direction is ResearchDirection.LONG:
            if not self.stop_price < self.entry_price < self.target_price:
                raise DataValidationError("LONG bracket invalid")
        elif not self.target_price < self.entry_price < self.stop_price:
            raise DataValidationError("SHORT bracket invalid")


class SyntheticReplayState(str, Enum):
    OPEN_UNRESOLVED = "open_unresolved"
    CONDITIONAL_STOP = "conditional_stop"
    CONDITIONAL_TARGET = "conditional_target"
    LIQUIDATION_CONDITION = "liquidation_condition"


@dataclass(frozen=True)
class SyntheticMarkObservation:
    at_ms: int
    mark_price: Decimal
    trade_price: Decimal
    maintenance_requirement_quote: Decimal
    equity_at_mark_quote: Decimal
    signed_funding_paid_quote: Decimal
    state: SyntheticReplayState


@dataclass(frozen=True)
class SyntheticMarkReplayResult:
    state: SyntheticReplayState
    observations: tuple[SyntheticMarkObservation, ...]
    first_trigger_at_ms: int | None
    assumed_exit_trade_price: Decimal | None
    conditional_net_quote: Decimal | None
    worst_mark_equity_quote: Decimal
    entry_fee_and_slippage_quote: Decimal

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def liquidation_formula_verified(self) -> bool:
        return False

    @property
    def fill_price_verified(self) -> bool:
        return False

    @property
    def net_pnl_verified(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False


def replay_synthetic_mark_path(
    plan: SyntheticMarkReplayPlan,
    ticks: tuple[SyntheticMarkTick, ...],
    funding_events: tuple[SyntheticFundingEvent, ...] = (),
    *, as_of_ms: int,
) -> SyntheticMarkReplayResult:
    """Evaluate each supplied timestamp exactly once, liquidation before exits.

    PRE2 remains the only fee, slippage and signed-funding calculator.
    Funding events must lie STRICTLY between entry and a tick; no ambiguous
    same-time ordering. Funding notional is an independent declared fixture.
    """
    from .synthetic_cost_scenarios import _time
    if (type(plan) is not SyntheticMarkReplayPlan or type(ticks) is not tuple
            or not 1 <= len(ticks) <= MAX_TICKS
            or any(type(t) is not SyntheticMarkTick for t in ticks)
            or type(funding_events) is not tuple
            or any(type(f) is not SyntheticFundingEvent for f in funding_events)):
        raise DataValidationError("bounded typed synthetic tick/funding inputs required")
    _time(as_of_ms, "as_of")
    times = [t.at_ms for t in ticks]
    if (times != sorted(set(times)) or times[0] <= plan.entry_at_ms
            or times[-1] > as_of_ms):
        raise DataValidationError("ticks must be strictly chronological and fully observed")
    event_times = [f.event_at_ms for f in funding_events]
    if (len(funding_events) > 64 or len(set(event_times)) != len(event_times)
            or event_times != sorted(event_times)
            or any(not plan.entry_at_ms < time < times[-1]
                   or time in times for time in event_times)):
        raise DataValidationError("funding events must be unique ordered and between ticks")
    if len({f.event_id for f in funding_events}) != len(funding_events):
        raise DataValidationError("funding identifiers must be unique")

    observations = []
    total_entry_cost = None
    worst = None
    for tick in ticks:
        active_funding = tuple(e for e in funding_events if e.event_at_ms < tick.at_ms)
        with localcontext(_CTX):
            entry_notion = plan.margin.entry_notional_quote
            mark_notion = tick.mark_price * plan.quantity_base
            trade_notion = tick.trade_price * plan.quantity_base
            zero_exit = SyntheticCostScenario(
                plan.direction, plan.entry_at_ms, tick.at_ms,
                entry_notion, trade_notion,
                plan.entry_fee_bps, Decimal(0),
                plan.entry_slippage_bps, Decimal(0), active_funding,
            )
            accrued = evaluate_synthetic_costs(zero_exit)
            entry_cost = accrued.entry_fee_units + accrued.entry_slippage_cost_units
            total_entry_cost = entry_cost
            sign = Decimal(1) if plan.direction is ResearchDirection.LONG else Decimal(-1)
            gross_mark = sign * (tick.mark_price - plan.entry_price) * plan.quantity_base
            equity = (plan.margin.requested_margin_quote + gross_mark
                      - entry_cost - accrued.signed_funding_cost_units)
            maintenance = (mark_notion * plan.maintenance_rate_bps
                           / Decimal(10000) + plan.reserve_for_close_quote)
            liquidation = equity <= maintenance
            if liquidation:
                state = SyntheticReplayState.LIQUIDATION_CONDITION
            elif ((tick.trade_price <= plan.stop_price if sign == 1
                   else tick.trade_price >= plan.stop_price)):
                state = SyntheticReplayState.CONDITIONAL_STOP
            elif ((tick.trade_price >= plan.target_price if sign == 1
                   else tick.trade_price <= plan.target_price)):
                state = SyntheticReplayState.CONDITIONAL_TARGET
            else:
                state = SyntheticReplayState.OPEN_UNRESOLVED
            observations.append(SyntheticMarkObservation(
                tick.at_ms, tick.mark_price, tick.trade_price, maintenance,
                equity, accrued.signed_funding_cost_units, state,
            ))
            worst = equity if worst is None else min(worst, equity)
            if state is SyntheticReplayState.LIQUIDATION_CONDITION:
                return SyntheticMarkReplayResult(
                    state, tuple(observations), tick.at_ms, None,
                    None, worst, entry_cost,
                )
            if state is not SyntheticReplayState.OPEN_UNRESOLVED:
                exit_costs = evaluate_synthetic_costs(SyntheticCostScenario(
                    plan.direction, plan.entry_at_ms, tick.at_ms,
                    entry_notion, trade_notion,
                    plan.entry_fee_bps, plan.exit_fee_bps,
                    plan.entry_slippage_bps, plan.exit_slippage_bps,
                    active_funding,
                ))
                gross_trade = sign * (tick.trade_price - plan.entry_price) * plan.quantity_base
                return SyntheticMarkReplayResult(
                    state, tuple(observations), tick.at_ms,
                    tick.trade_price, gross_trade - exit_costs.total_signed_cost_units,
                    worst, entry_cost,
                )
    return SyntheticMarkReplayResult(
        SyntheticReplayState.OPEN_UNRESOLVED, tuple(observations),
        None, None, None, worst, total_entry_cost,
    )
