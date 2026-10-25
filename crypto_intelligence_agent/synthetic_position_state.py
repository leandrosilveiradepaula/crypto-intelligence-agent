"""J4/PRE3: immutable SYNTHETIC position-opening snapshot and replay binding.

NOT an account, position ledger, order, broker connector, real collateral or PnL
calculation. "Margin" is an abstract positive fixture quantity with NO
currency, price or implied notional. 50x is a RESEARCH SETTING, not a venue
cap or a recommendation. No I/O, persistence, market data or external rights.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import re

from .market_data import DataValidationError
from .synthetic_partial_exits import SyntheticExitPlan, _synthetic_units
from .synthetic_manual_exit_replay import (
    MAX_FIXTURE_EVENTS, SyntheticManualExitEvent, SyntheticTrancheProgress,
    _utc_ms, replay_synthetic_manual_exits,
)

# Technical research input bound only, not a promise that a venue permits it.
MAX_RESEARCH_LEVERAGE = 200
_FIXTURE_POSITION_ID = re.compile(r"fixture_[A-Za-z0-9_-]{1,48}")


class SyntheticSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class _ResearchOnly:
    """Non-overridable-by-constructor flags inherited by immutable records."""

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
    def venue_lot_step_verified(self) -> bool:
        return False

    @property
    def collateral_currency_verified(self) -> bool:
        return False

    @property
    def market_data_rights_verified(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        return False


def _research_leverage(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_RESEARCH_LEVERAGE:
        raise DataValidationError(
            "new synthetic leverage must be integer within research bounds"
        )
    return value


def _fixture_id(value: str) -> str:
    if type(value) is not str or _FIXTURE_POSITION_ID.fullmatch(value) is None:
        raise DataValidationError("position ID must be bounded fixture-only ASCII")
    return value


@dataclass(frozen=True)
class SyntheticLeverageSettings(_ResearchOnly):
    """A pure configuration VALUE; replacing it never changes old positions."""

    for_new_positions: int = 50

    def __post_init__(self) -> None:
        _research_leverage(self.for_new_positions)

    def with_new_position_leverage(self, leverage: int) -> "SyntheticLeverageSettings":
        return SyntheticLeverageSettings(_research_leverage(leverage))


@dataclass(frozen=True)
class SyntheticPosition(_ResearchOnly):
    fixture_position_id: str
    side: SyntheticSide
    opened_at_ms: int
    plan: SyntheticExitPlan
    synthetic_margin_units: Decimal
    leverage_at_open: int

    def __post_init__(self) -> None:
        _fixture_id(self.fixture_position_id)
        if type(self.side) is not SyntheticSide:
            raise DataValidationError("synthetic direction requires explicit LONG/SHORT enum")
        _utc_ms(self.opened_at_ms, "opened_at_ms")
        if type(self.plan) is not SyntheticExitPlan:
            raise DataValidationError("synthetic position requires immutable PRE1 exit plan")
        # Reuse the PRE1 fixture bounds. This is NOT real currency collateral.
        _synthetic_units(self.synthetic_margin_units)
        _research_leverage(self.leverage_at_open)


def open_synthetic_position(
    *, fixture_position_id: str, side: SyntheticSide,
    opened_at_ms: int, exit_plan: SyntheticExitPlan,
    synthetic_margin_units: Decimal, settings: SyntheticLeverageSettings,
) -> SyntheticPosition:
    """Capture leverage NOW; changing settings cannot retroactively alter it."""
    if type(settings) is not SyntheticLeverageSettings:
        raise DataValidationError("explicit immutable research leverage settings required")
    return SyntheticPosition(
        fixture_position_id=fixture_position_id, side=side,
        opened_at_ms=opened_at_ms, plan=exit_plan,
        synthetic_margin_units=synthetic_margin_units,
        leverage_at_open=settings.for_new_positions,
    )


@dataclass(frozen=True)
class SyntheticPositionExitFill:
    """Explicitly binds PRE2 event to ONE synthetic position fixture."""

    fixture_position_id: str
    event: SyntheticManualExitEvent

    def __post_init__(self) -> None:
        _fixture_id(self.fixture_position_id)
        if type(self.event) is not SyntheticManualExitEvent:
            raise DataValidationError("position fill must contain PRE2 synthetic event")


@dataclass(frozen=True)
class SyntheticPositionSnapshot(_ResearchOnly):
    fixture_position_id: str
    side: SyntheticSide
    opened_at_ms: int
    as_of_ms: int
    synthetic_margin_units: Decimal
    leverage_at_open: int
    initial_units: Decimal
    filled_total_units: Decimal
    remaining_units: Decimal
    residual_floor_units: Decimal
    progress: tuple[SyntheticTrancheProgress, ...]
    unique_event_count: int
    exact_duplicate_count: int
    latest_unique_event_at_ms: int | None


def replay_synthetic_position(
    position: SyntheticPosition,
    fills: tuple[SyntheticPositionExitFill, ...],
    *, as_of_ms: int,
) -> SyntheticPositionSnapshot:
    """Replay only fills that explicitly identify this FIXTURE position.

    Even with fixture_position_id binding, identifiers can be forged/reused:
    no persistent exactly-once accounting, venue lot validation or real fills.
    """
    if type(position) is not SyntheticPosition:
        raise DataValidationError("synthetic fixture position required")
    if type(fills) is not tuple or len(fills) > MAX_FIXTURE_EVENTS:
        raise DataValidationError("bounded immutable synthetic fill tuple required")
    if any(type(fill) is not SyntheticPositionExitFill for fill in fills):
        raise DataValidationError("invalid bound synthetic fill type")
    for fill in fills:
        if fill.fixture_position_id != position.fixture_position_id:
            raise DataValidationError("synthetic fill belongs to a different fixture position")
    result = replay_synthetic_manual_exits(
        position.plan, tuple(fill.event for fill in fills),
        plan_created_at_ms=position.opened_at_ms, as_of_ms=as_of_ms,
    )
    return SyntheticPositionSnapshot(
        fixture_position_id=position.fixture_position_id,
        side=position.side, opened_at_ms=position.opened_at_ms,
        as_of_ms=result.as_of_ms, synthetic_margin_units=position.synthetic_margin_units,
        leverage_at_open=position.leverage_at_open,
        initial_units=result.initial_units, filled_total_units=result.filled_total_units,
        remaining_units=result.remaining_units, residual_floor_units=result.residual_floor_units,
        progress=result.progress, unique_event_count=result.unique_event_count,
        exact_duplicate_count=result.exact_duplicate_count,
        latest_unique_event_at_ms=result.latest_unique_event_at_ms,
    )
