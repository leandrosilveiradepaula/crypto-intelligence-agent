"""J4/PRE4: hypothetical Decimal lot/step feasibility, SYNTHETIC ONLY.

A fixture matching exact arithmetic does NOT establish a real contract's
lot/step, collateral, minimum notional, trading permission, price or execution.
This module NEVER rounds an order or converts an abstract quantity into USD.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .market_data import DataValidationError
from .synthetic_partial_exits import plan_synthetic_partial_exits
from .synthetic_position_state import (
    SyntheticPosition, SyntheticPositionExitFill, replay_synthetic_position,
)

# A technical research bound on fixture rules, not a trading venue specification.
MAX_RULE_DIGITS = 40
MIN_RULE_EXPONENT = -18
MAX_RULE_ADJUSTED_EXPONENT = 24
# PRE1 can accumulate up to 64 exact percentage steps, PRE2 fills may have
# up to 640 significant digits. Keep modulo exact regardless of global context.
_EXACT_CONTEXT = Context(prec=2048, rounding=ROUND_HALF_EVEN)


def _bounded_rule(value: Decimal, label: str, *, zero_ok: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise DataValidationError(f"{label} must be finite exact Decimal")
    if value < 0 or (value == 0 and not zero_ok):
        raise DataValidationError(f"{label} must be positive or explicit zero")
    as_tuple = value.as_tuple()
    if (len(as_tuple.digits) > MAX_RULE_DIGITS
            or as_tuple.exponent < MIN_RULE_EXPONENT
            or value.adjusted() > MAX_RULE_ADJUSTED_EXPONENT):
        raise DataValidationError(f"{label} exceeds research fixture bounds")
    return value


@dataclass(frozen=True)
class SyntheticLotFixture:
    """The caller's UNVERIFIED, hypothetical size rules, not venue metadata."""

    size_step_units: Decimal
    minimum_exit_units: Decimal
    minimum_nonzero_remaining_units: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        _bounded_rule(self.size_step_units, "size_step_units", zero_ok=False)
        _bounded_rule(self.minimum_exit_units, "minimum_exit_units", zero_ok=False)
        _bounded_rule(
            self.minimum_nonzero_remaining_units,
            "minimum_nonzero_remaining_units", zero_ok=True,
        )

    @property
    def venue_contract_verified(self) -> bool:
        return False


@dataclass(frozen=True)
class SyntheticTrancheLotCheck:
    tranche_step: int
    planned_units: Decimal
    exact_step_multiple: bool
    meets_fixture_exit_minimum: bool


@dataclass(frozen=True)
class SyntheticFillLotCheck:
    unique_event_ordinal: int
    tranche_step: int
    filled_units: Decimal
    exact_step_multiple: bool
    meets_fixture_exit_minimum: bool


@dataclass(frozen=True)
class SyntheticLotFeasibility:
    fixture_position_id: str
    initial_units: Decimal
    planned_remaining_units: Decimal
    current_remaining_units: Decimal
    initial_step_multiple: bool
    planned_remaining_step_multiple: bool
    planned_remaining_minimum_ok: bool
    current_remaining_step_multiple: bool
    current_remaining_minimum_ok: bool
    tranche_checks: tuple[SyntheticTrancheLotCheck, ...]
    fill_checks: tuple[SyntheticFillLotCheck, ...]
    unique_event_count: int
    exact_duplicate_count: int

    @property
    def arithmetically_compatible(self) -> bool:
        return (
            self.initial_step_multiple
            and self.planned_remaining_step_multiple
            and self.planned_remaining_minimum_ok
            and self.current_remaining_step_multiple
            and self.current_remaining_minimum_ok
            and all(
                row.exact_step_multiple and row.meets_fixture_exit_minimum
                for row in self.tranche_checks
            )
            and all(
                row.exact_step_multiple and row.meets_fixture_exit_minimum
                for row in self.fill_checks
            )
        )

    @property
    def quality(self) -> str:
        return "synthetic_lot_rule_fixture_only"

    @property
    def venue_lot_step_verified(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def collateral_currency_verified(self) -> bool:
        return False

    @property
    def external_rights_verified(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        return False


def assess_synthetic_lot_feasibility(
    position: SyntheticPosition,
    fixture: SyntheticLotFixture,
    fills: tuple[SyntheticPositionExitFill, ...] = (),
    *,
    as_of_ms: int,
) -> SyntheticLotFeasibility:
    """Check exact hypothetical quantity steps; NEVER quantize or place orders.

    PRE3/PRE2 validate position IDs, chronological replay, conflicts and
    overfills before evaluating lot arithmetic. Repeated valid IDs are
    evaluated once; two distinct IDs for the same economic fill remain
    indistinguishable and are NOT certified as unique.
    """
    if type(position) is not SyntheticPosition:
        raise DataValidationError("synthetic fixture position required")
    if type(fixture) is not SyntheticLotFixture:
        raise DataValidationError("synthetic lot rule fixture required")
    # Fail closed on replay errors, cross-position fill, future timestamps,
    # conflicts or mutated event representation before checking step sizes.
    current = replay_synthetic_position(position, fills, as_of_ms=as_of_ms)
    planned = plan_synthetic_partial_exits(position.plan)
    with localcontext(_EXACT_CONTEXT):
        step = fixture.size_step_units

        def multiple(units: Decimal) -> bool:
            return units % step == 0

        def remaining_minimum(units: Decimal) -> bool:
            # An exact full close has no nonzero remainder minimum.
            return (units == 0
                    or units >= fixture.minimum_nonzero_remaining_units)

        tranches = tuple(
            SyntheticTrancheLotCheck(
                tranche_step=row.step_number, planned_units=row.exit_units,
                exact_step_multiple=multiple(row.exit_units),
                meets_fixture_exit_minimum=(
                    row.exit_units >= fixture.minimum_exit_units
                ),
            )
            for row in planned.allocations
        )
        unique: set[str] = set()
        events: list[SyntheticFillLotCheck] = []
        for envelope in fills:
            event = envelope.event
            if event.event_id in unique:
                continue  # PRE2 has already checked matching payload
            unique.add(event.event_id)
            events.append(SyntheticFillLotCheck(
                unique_event_ordinal=len(events) + 1,
                tranche_step=event.tranche_step,
                filled_units=event.filled_units,
                exact_step_multiple=multiple(event.filled_units),
                meets_fixture_exit_minimum=(
                    event.filled_units >= fixture.minimum_exit_units
                ),
            ))
        if len(events) != current.unique_event_count:
            raise DataValidationError("synthetic fixture replay count conflict")
        return SyntheticLotFeasibility(
            fixture_position_id=position.fixture_position_id,
            initial_units=planned.initial_units,
            planned_remaining_units=planned.remaining_units,
            current_remaining_units=current.remaining_units,
            initial_step_multiple=multiple(planned.initial_units),
            planned_remaining_step_multiple=multiple(planned.remaining_units),
            planned_remaining_minimum_ok=remaining_minimum(planned.remaining_units),
            current_remaining_step_multiple=multiple(current.remaining_units),
            current_remaining_minimum_ok=remaining_minimum(current.remaining_units),
            tranche_checks=tranches, fill_checks=tuple(events),
            unique_event_count=current.unique_event_count,
            exact_duplicate_count=current.exact_duplicate_count,
        )
