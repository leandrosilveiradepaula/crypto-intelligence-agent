"""J3/PRE1: OHLC-only SYNTHETIC barrier observations, NEVER fills or PnL.

OHLC high/low cannot tell which level was touched first inside the candle.
Gap-through observations are also NOT executions at the selected limit.
Even a sole target touch cannot prove profitability: venue liquidation, mark
price, maintenance margin, funding, fees and fills are NOT modeled.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_feature_engine import (
    validate_synthetic_closed_candles,
    validate_synthetic_research_price,
)


class ResearchDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class SyntheticBarrier(str, Enum):
    STOP = "stop"
    TARGET = "target"
    HYPOTHETICAL_LIQUIDATION = "hypothetical_liquidation"


class ObservationKind(str, Enum):
    NO_LEVEL_REACHED = "no_level_reached"
    OPEN_AT_OR_BEYOND_LEVEL = "open_at_or_beyond_level"
    SINGLE_LEVEL_RANGE = "single_level_range"
    MULTIPLE_LEVELS_UNORDERED = "multiple_levels_unordered"


@dataclass(frozen=True)
class SyntheticBarrierPlan:
    """Thresholds are hypothetical and MUST predate the observed OHLC bars."""

    side: ResearchDirection
    hypothetical_entry_price: Decimal
    stop_level: Decimal
    target_level: Decimal
    plan_created_at_ms: int
    hypothetical_liquidation_level: Decimal | None = None

    def __post_init__(self) -> None:
        if type(self.side) is not ResearchDirection:
            raise DataValidationError("research direction requires an explicit enum")
        if type(self.plan_created_at_ms) is not int or self.plan_created_at_ms <= 0:
            raise DataValidationError("synthetic plan requires positive UTC-ms timestamp")
        for label in ("hypothetical_entry_price", "stop_level", "target_level"):
            validate_synthetic_research_price(getattr(self, label), label)
        if self.hypothetical_liquidation_level is not None:
            validate_synthetic_research_price(
                self.hypothetical_liquidation_level, "hypothetical_liquidation_level"
            )
        entry, stop, target = (
            self.hypothetical_entry_price, self.stop_level, self.target_level
        )
        if self.side is ResearchDirection.LONG:
            if not stop < entry < target:
                raise DataValidationError("LONG synthetic bracket requires stop < entry < target")
        else:
            if not target < entry < stop:
                raise DataValidationError("SHORT synthetic bracket requires target < entry < stop")
        liq = self.hypothetical_liquidation_level
        if liq is not None and (
            liq == stop
            or (self.side is ResearchDirection.LONG and liq >= entry)
            or (self.side is ResearchDirection.SHORT and liq <= entry)
        ):
            raise DataValidationError("hypothetical liquidation level must be distinct and adverse")


@dataclass(frozen=True)
class SyntheticBarrierObservation:
    """First observable level event, with NO implied execution ordering."""

    exchange: str
    symbol: str
    interval: str
    plan_created_at_ms: int
    as_of_ms: int
    available_closed_candles: int
    examined_closed_candles: int
    kind: ObservationKind
    levels_reached: tuple[SyntheticBarrier, ...]
    first_candidate_index: int | None
    first_candidate_open_time_ms: int | None
    first_candidate_close_time_ms: int | None

    @property
    def quality(self) -> str:
        return "synthetic_intrabar_observation_only"

    @property
    def intrabar_path_verified(self) -> bool:
        return False

    @property
    def fill_price_verified(self) -> bool:
        return False

    @property
    def liquidation_formula_verified(self) -> bool:
        return False

    @property
    def profitable_trade_verified(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def observe_synthetic_intrabar_barriers(
    plan: SyntheticBarrierPlan,
    candles: Sequence[ClosedCandle],
    *,
    as_of_ms: int,
    close_safety_ms: int = 1_000,
) -> SyntheticBarrierObservation:
    """Detect the first *observable* threshold reach; refuse intrabar order.

    Validation applies to ALL supplied bars before scan: caller cannot pass a
    future/mixed/malformed bar and hide it behind a hit earlier in the batch.
    Only the first candidate candle is reported; follow-on risk/stop management
    is outside this preparatory research module. Market data must be SYNTHETIC.
    """
    if type(plan) is not SyntheticBarrierPlan:
        raise DataValidationError("explicit synthetic barrier plan required")
    cs = validate_synthetic_closed_candles(
        candles, decision_at_ms=as_of_ms, close_safety_ms=close_safety_ms,
    )
    if plan.plan_created_at_ms > cs[0].open_time_ms:
        raise DataValidationError("synthetic barrier plan cannot start after first observed open")

    direction = plan.side
    levels: tuple[tuple[SyntheticBarrier, Decimal], ...] = (
        (SyntheticBarrier.STOP, plan.stop_level),
        (SyntheticBarrier.TARGET, plan.target_level),
    )
    if plan.hypothetical_liquidation_level is not None:
        levels += ((
            SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,
            plan.hypothetical_liquidation_level,
        ),)

    def at_or_beyond(candle_open: Decimal, level: Decimal, name: SyntheticBarrier) -> bool:
        if name is SyntheticBarrier.TARGET:
            return (candle_open >= level if direction is ResearchDirection.LONG
                    else candle_open <= level)
        return (candle_open <= level if direction is ResearchDirection.LONG
                else candle_open >= level)

    def inside_range(candle: ClosedCandle, level: Decimal, name: SyntheticBarrier) -> bool:
        if name is SyntheticBarrier.TARGET:
            return (candle.high >= level if direction is ResearchDirection.LONG
                    else candle.low <= level)
        return (candle.low <= level if direction is ResearchDirection.LONG
                else candle.high >= level)

    for i, candle in enumerate(cs):
        open_levels = tuple(
            name for name, price in levels
            if at_or_beyond(candle.open, price, name)
        )
        if open_levels:
            reached = open_levels
            kind = ObservationKind.OPEN_AT_OR_BEYOND_LEVEL
        else:
            reached = tuple(
                name for name, price in levels
                if inside_range(candle, price, name)
            )
            if len(reached) >= 2:
                kind = ObservationKind.MULTIPLE_LEVELS_UNORDERED
            elif len(reached) == 1:
                kind = ObservationKind.SINGLE_LEVEL_RANGE
            else:
                continue
        return SyntheticBarrierObservation(
            exchange=candle.exchange, symbol=candle.symbol, interval=candle.interval,
            plan_created_at_ms=plan.plan_created_at_ms, as_of_ms=as_of_ms,
            available_closed_candles=len(cs), examined_closed_candles=i + 1,
            kind=kind, levels_reached=reached,
            first_candidate_index=i, first_candidate_open_time_ms=candle.open_time_ms,
            first_candidate_close_time_ms=candle.close_time_ms,
        )
    first = cs[0]
    return SyntheticBarrierObservation(
        exchange=first.exchange, symbol=first.symbol, interval=first.interval,
        plan_created_at_ms=plan.plan_created_at_ms, as_of_ms=as_of_ms,
        available_closed_candles=len(cs), examined_closed_candles=len(cs),
        kind=ObservationKind.NO_LEVEL_REACHED, levels_reached=(),
        first_candidate_index=None, first_candidate_open_time_ms=None,
        first_candidate_close_time_ms=None,
    )
