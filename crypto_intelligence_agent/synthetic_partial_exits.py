"""Pure J4/PRE1 partial-exit percentage arithmetic, SYNTHETIC units only.

No market data, fees, contract size, price, position persistence, trailing,
orders or execution. A percentage plan is NOT a tradable order plan. Units
are abstract and intentionally unbound to exchange lot/step specifications.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum

from .market_data import DataValidationError

MAX_TRANCHES = 64  # Resource bound for research fixture, not a product target
MAX_PERCENT_SCALE = 6
MAX_UNIT_DIGITS = 40
MIN_UNIT_EXP = -18
MAX_UNIT_ADJUSTED_EXP = 24
# 40 significant input digits + 64 x (6 percentage places + "/100" two
# more places) fits with room to conserve EVERY exact Decimal tranche.
_EXACT_CONTEXT = Context(prec=640, rounding=ROUND_HALF_EVEN)
_ONE_HUNDRED = Decimal(100)


class ExitBasis(str, Enum):
    INITIAL_POSITION = "INITIAL_POSITION"
    REMAINING_BALANCE = "REMAINING_BALANCE"


def _synthetic_units(value: Decimal) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise DataValidationError("synthetic initial units must be positive finite Decimal")
    raw = value.as_tuple()
    if (len(raw.digits) > MAX_UNIT_DIGITS or raw.exponent < MIN_UNIT_EXP
            or value.adjusted() > MAX_UNIT_ADJUSTED_EXP):
        raise DataValidationError("synthetic initial units exceed research precision bounds")
    return value


def _percent(value: Decimal, name: str, *, allow_zero: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise DataValidationError(f"{name} must be finite Decimal, never float")
    if value.as_tuple().exponent < -MAX_PERCENT_SCALE:
        raise DataValidationError(f"{name} exceeds supported decimal percentage places")
    if value < 0 or value > _ONE_HUNDRED or (not allow_zero and value == 0):
        raise DataValidationError(f"{name} outside valid percentage range")
    return value


@dataclass(frozen=True)
class SyntheticExitTranche:
    basis: ExitBasis
    percent: Decimal

    def __post_init__(self) -> None:
        if type(self.basis) is not ExitBasis:
            raise DataValidationError("exit basis must be an explicit enum")
        _percent(self.percent, "tranche percent", allow_zero=False)


@dataclass(frozen=True)
class SyntheticExitPlan:
    """A finite ordered fixture, not a real or fillable position."""

    initial_units: Decimal
    tranches: tuple[SyntheticExitTranche, ...]
    residual_floor_percent: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        _synthetic_units(self.initial_units)
        if (type(self.tranches) is not tuple
                or not 1 <= len(self.tranches) <= MAX_TRANCHES
                or any(type(step) is not SyntheticExitTranche for step in self.tranches)):
            raise DataValidationError("need 1..64 immutable synthetic exit tranches")
        floor = _percent(self.residual_floor_percent,
                         "residual floor percent", allow_zero=True)
        if floor == _ONE_HUNDRED:
            raise DataValidationError("100% runner reserve is incompatible with exits")


@dataclass(frozen=True)
class SyntheticExitAllocation:
    step_number: int
    basis: ExitBasis
    percent: Decimal
    remaining_before_units: Decimal
    exit_units: Decimal
    remaining_after_units: Decimal
    exited_cumulative_units: Decimal

    @property
    def order_capable(self) -> bool:
        return False


@dataclass(frozen=True)
class SyntheticExitSchedule:
    initial_units: Decimal
    residual_floor_units: Decimal
    exited_total_units: Decimal
    remaining_units: Decimal
    allocations: tuple[SyntheticExitAllocation, ...]

    @property
    def quality(self) -> str:
        return "synthetic_percentage_research_only"

    @property
    def approved_for_live_execution(self) -> bool:
        return False

    @property
    def exchange_lot_size_verified(self) -> bool:
        return False

    @property
    def position_accounting_verified(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def plan_synthetic_partial_exits(
    plan: SyntheticExitPlan,
) -> SyntheticExitSchedule:
    """Conserve abstract quantity exactly; reject over-exit, never clip silently.

    INITIAL_POSITION percent applies to the immutable initial units.
    REMAINING_BALANCE percent applies to what remains just before the step.
    Runner floor always applies to initial units, not remaining balance.
    There is NO exchange-specific lot quantization or simulation of fills.
    """
    if type(plan) is not SyntheticExitPlan:
        raise DataValidationError("explicit synthetic exit plan required")
    # Every multiplication has finite decimal expansion. Input bounds and a
    # fixed ample context make these bounded 64-step calculations exact,
    # independent of the caller's global Decimal context.
    with localcontext(_EXACT_CONTEXT):
        initial = plan.initial_units
        floor = initial * plan.residual_floor_percent / _ONE_HUNDRED
        remaining = initial
        exited = Decimal(0)
        allocations: list[SyntheticExitAllocation] = []
        for i, step in enumerate(plan.tranches, start=1):
            quantity_before = remaining
            reference = (initial if step.basis is ExitBasis.INITIAL_POSITION
                         else quantity_before)
            requested = reference * step.percent / _ONE_HUNDRED
            if requested <= 0:
                raise DataValidationError("exit amount must be strictly positive")
            if requested > quantity_before:
                raise DataValidationError(
                    f"synthetic exit step {i} would exceed remaining quantity"
                )
            if requested > quantity_before - floor:
                raise DataValidationError(
                    f"synthetic exit step {i} violates initial-position runner reserve"
                )
            remaining = quantity_before - requested
            exited += requested
            allocations.append(SyntheticExitAllocation(
                step_number=i, basis=step.basis, percent=step.percent,
                remaining_before_units=quantity_before, exit_units=requested,
                remaining_after_units=remaining, exited_cumulative_units=exited,
            ))
        if remaining < floor or remaining < 0 or exited + remaining != initial:
            raise DataValidationError("synthetic exit conservation invariant violated")
        return SyntheticExitSchedule(
            initial_units=initial, residual_floor_units=floor,
            exited_total_units=exited, remaining_units=remaining,
            allocations=tuple(allocations),
        )
