"""J4/PRE2: deterministic REPLAY of fictitious manual partial fills.

This has no executor, exchange, keys, market prices, account, trading signal,
real position, persistent ledger, PnL, margin or funding. Event identifiers
only deduplicate this in-memory replay; they are NOT exchange execution IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import re

from .market_data import DataValidationError
from .synthetic_partial_exits import (
    SyntheticExitPlan, plan_synthetic_partial_exits,
)

MAX_FIXTURE_EVENTS = 512
MAX_EVENT_SIGNIFICANT_DIGITS = 640
MIN_EVENT_EXPONENT = -600
MAX_EVENT_ADJUSTED_EXPONENT = 24
MAX_UTC_MS = 253_402_300_799_999
_EVENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}")
_EXACT_CONTEXT = Context(prec=2048, rounding=ROUND_HALF_EVEN)


def _utc_ms(value: int, name: str) -> int:
    if type(value) is not int or not 0 < value <= MAX_UTC_MS:
        raise DataValidationError(f"{name} must be bounded positive UTC-ms integer")
    return value


def _fixture_units(value: Decimal) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise DataValidationError("fixture filled units require positive finite Decimal")
    t = value.as_tuple()
    if (len(t.digits) > MAX_EVENT_SIGNIFICANT_DIGITS
            or t.exponent < MIN_EVENT_EXPONENT
            or value.adjusted() > MAX_EVENT_ADJUSTED_EXPONENT):
        raise DataValidationError("fixture filled units exceed bounded exact precision")
    return value


@dataclass(frozen=True)
class SyntheticManualExitEvent:
    event_id: str
    tranche_step: int
    filled_units: Decimal
    event_at_ms: int

    def __post_init__(self) -> None:
        if type(self.event_id) is not str or _EVENT_ID.fullmatch(self.event_id) is None:
            raise DataValidationError("synthetic event id requires bounded ASCII identifier")
        if type(self.tranche_step) is not int or not 1 <= self.tranche_step <= 64:
            raise DataValidationError("synthetic tranche step must be integer 1..64")
        _fixture_units(self.filled_units)
        _utc_ms(self.event_at_ms, "event_at_ms")


@dataclass(frozen=True)
class SyntheticTrancheProgress:
    tranche_step: int
    planned_units: Decimal
    filled_units: Decimal
    outstanding_units: Decimal


@dataclass(frozen=True)
class SyntheticManualExitReplay:
    plan_created_at_ms: int
    as_of_ms: int
    initial_units: Decimal
    residual_floor_units: Decimal
    filled_total_units: Decimal
    remaining_units: Decimal
    progress: tuple[SyntheticTrancheProgress, ...]
    unique_event_count: int
    exact_duplicate_count: int
    latest_unique_event_at_ms: int | None

    @property
    def quality(self) -> str:
        return "synthetic_fixture_only"

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        return False

    @property
    def venue_lot_units_verified(self) -> bool:
        return False


def replay_synthetic_manual_exits(
    plan: SyntheticExitPlan,
    events: tuple[SyntheticManualExitEvent, ...],
    *,
    plan_created_at_ms: int,
    as_of_ms: int,
) -> SyntheticManualExitReplay:
    """Apply only unique, properly ordered synthetic fill events to a plan.

    Idempotent by (event_id, exact payload) WITHIN one replay. If a client
    invents a new ID for the same economic fill, duplication cannot be
    detected here. No persistent exactly-once guarantee is claimed.
    """
    if type(plan) is not SyntheticExitPlan:
        raise DataValidationError("synthetic plan is mandatory")
    created = _utc_ms(plan_created_at_ms, "plan_created_at_ms")
    cutoff = _utc_ms(as_of_ms, "as_of_ms")
    if created > cutoff:
        raise DataValidationError("as_of_ms precedes synthetic plan creation")
    if type(events) is not tuple or len(events) > MAX_FIXTURE_EVENTS:
        raise DataValidationError("synthetic event fixture must be immutable and bounded")
    if any(type(e) is not SyntheticManualExitEvent for e in events):
        raise DataValidationError("synthetic event fixture contains wrong type")
    schedule = plan_synthetic_partial_exits(plan)
    targets = tuple(row.exit_units for row in schedule.allocations)

    with localcontext(_EXACT_CONTEXT):
        filled = [Decimal(0) for _ in targets]
        total_filled = Decimal(0)
        previous_event_at_ms: int | None = None
        seen: dict[str, SyntheticManualExitEvent] = {}
        duplicate_count = 0
        for event in events:
            old = seen.get(event.event_id)
            if old is not None:
                if old != event:
                    raise DataValidationError("synthetic event id has conflicting payload")
                duplicate_count += 1
                continue
            if not created <= event.event_at_ms <= cutoff:
                raise DataValidationError("synthetic fill event is outside plan/as-of window")
            if previous_event_at_ms is not None and event.event_at_ms < previous_event_at_ms:
                raise DataValidationError("synthetic unique fill events are not chronological")
            index = event.tranche_step - 1
            if index >= len(targets):
                raise DataValidationError("synthetic fill references absent exit tranche")
            first_outstanding = next(
                (i for i, required in enumerate(targets) if filled[i] < required), None
            )
            if first_outstanding is None or index != first_outstanding:
                raise DataValidationError("synthetic fill must complete prior tranche first")
            new_filled = filled[index] + event.filled_units
            if new_filled > targets[index]:
                raise DataValidationError("synthetic fill exceeds allocated tranche quantity")
            filled[index] = new_filled
            total_filled += event.filled_units
            if (total_filled > schedule.initial_units
                    or schedule.initial_units - total_filled < schedule.residual_floor_units):
                raise DataValidationError("synthetic fill violates position or runner reserve")
            previous_event_at_ms = event.event_at_ms
            seen[event.event_id] = event

        progress = tuple(
            SyntheticTrancheProgress(
                tranche_step=i + 1,
                planned_units=target,
                filled_units=filled[i],
                outstanding_units=target - filled[i],
            )
            for i, target in enumerate(targets)
        )
        remaining = schedule.initial_units - total_filled
        if (remaining < 0 or remaining < schedule.residual_floor_units
                or total_filled + remaining != schedule.initial_units
                or any(p.filled_units + p.outstanding_units != p.planned_units
                       for p in progress)):
            raise DataValidationError("synthetic manual replay conservation violated")
        return SyntheticManualExitReplay(
            plan_created_at_ms=created,
            as_of_ms=cutoff,
            initial_units=schedule.initial_units,
            residual_floor_units=schedule.residual_floor_units,
            filled_total_units=total_filled,
            remaining_units=remaining,
            progress=progress,
            unique_event_count=len(seen),
            exact_duplicate_count=duplicate_count,
            latest_unique_event_at_ms=previous_event_at_ms,
        )
