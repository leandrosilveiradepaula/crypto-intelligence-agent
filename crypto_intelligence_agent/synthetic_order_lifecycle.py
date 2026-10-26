"""J4/AUTO1: deterministic PAPER order-intent lifecycle, never a broker.

Complementary to J4/PRE1 (exit percentages) and PRE2/PRE3 (synthetic
position/fill replay). Events are HYPOTHETICAL; no API, account, network,
persistent ledger, real order, execution price, fees, liquidation or PnL.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
import re

from .market_data import DataValidationError
from .synthetic_manual_exit_replay import (
    MAX_FIXTURE_EVENTS, _EXACT_CONTEXT, _fixture_units, _utc_ms,
)
from .synthetic_position_state import SyntheticSide


_ID = re.compile(r"fixture_[A-Za-z0-9_-]{1,56}")
_SYMBOL = re.compile(r"[A-Z0-9]{4,25}")


class PaperVenue(str, Enum):
    BINANCE_USDM = "binance_usdm"
    BYBIT_V5 = "bybit_v5"


class PaperOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PaperOrderEffect(str, Enum):
    OPEN = "OPEN"
    REDUCE_ONLY = "REDUCE_ONLY"


class PaperOrderEventKind(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN = "UNKNOWN"
    FILL = "FILL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PaperOrderStatus(str, Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN = "UNKNOWN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


def _id(value: str, field: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise DataValidationError(f"{field} must be bounded synthetic fixture identifier")
    return value


@dataclass(frozen=True)
class PaperOrderIntent:
    """A desired PAPER change; NEVER an exchange request or order placement."""

    intent_id: str
    fixture_signal_id: str
    venue: PaperVenue
    symbol: str
    position_side: SyntheticSide
    side: PaperOrderSide
    effect: PaperOrderEffect
    requested_units: Decimal
    created_at_ms: int
    max_reducible_units: Decimal | None = None

    def __post_init__(self) -> None:
        _id(self.intent_id, "intent_id")
        _id(self.fixture_signal_id, "fixture_signal_id")
        if self.intent_id == self.fixture_signal_id:
            raise DataValidationError("paper intent and signal require distinct identities")
        if type(self.venue) is not PaperVenue:
            raise DataValidationError("paper venue must be explicitly selected")
        if type(self.symbol) is not str or _SYMBOL.fullmatch(self.symbol) is None:
            raise DataValidationError("paper symbol requires bounded uppercase venue ticker")
        if (type(self.position_side) is not SyntheticSide
                or type(self.side) is not PaperOrderSide
                or type(self.effect) is not PaperOrderEffect):
            raise DataValidationError("paper order direction/effect requires explicit enums")
        _fixture_units(self.requested_units)
        _utc_ms(self.created_at_ms, "created_at_ms")
        expected_entry = (PaperOrderSide.BUY if self.position_side is SyntheticSide.LONG
                          else PaperOrderSide.SELL)
        if self.effect is PaperOrderEffect.OPEN:
            if self.side is not expected_entry or self.max_reducible_units is not None:
                raise DataValidationError("paper opening direction or reduce-only balance invalid")
        else:
            if self.side is expected_entry:
                raise DataValidationError("reduce-only exit cannot open or enlarge position")
            if self.max_reducible_units is None:
                raise DataValidationError("reduce-only fixture needs bounded position balance")
            _fixture_units(self.max_reducible_units)
            if self.requested_units > self.max_reducible_units:
                raise DataValidationError("paper exit exceeds synthetic position balance")

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        return False


@dataclass(frozen=True)
class PaperOrderEvent:
    event_id: str
    kind: PaperOrderEventKind
    event_at_ms: int
    filled_units: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        _id(self.event_id, "event_id")
        if type(self.kind) is not PaperOrderEventKind:
            raise DataValidationError("paper event kind must be explicit enum")
        _utc_ms(self.event_at_ms, "event_at_ms")
        if self.kind is PaperOrderEventKind.FILL:
            _fixture_units(self.filled_units)
        elif type(self.filled_units) is not Decimal or self.filled_units.as_tuple() != Decimal(0).as_tuple():
            raise DataValidationError("only a paper FILL can change filled quantity")


@dataclass(frozen=True)
class PaperOrderSnapshot:
    intent_id: str
    venue: PaperVenue
    effect: PaperOrderEffect
    status: PaperOrderStatus
    requested_units: Decimal
    filled_total_units: Decimal
    unfilled_units: Decimal
    as_of_ms: int
    unique_event_count: int
    exact_duplicate_count: int
    last_unique_event_at_ms: int | None

    @property
    def requires_reconciliation(self) -> bool:
        return self.status in {
            PaperOrderStatus.PENDING, PaperOrderStatus.ACKNOWLEDGED,
            PaperOrderStatus.UNKNOWN, PaperOrderStatus.PARTIALLY_FILLED,
        }

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
    def quality(self) -> str:
        return "synthetic_order_events_only"


def replay_paper_order(
    intent: PaperOrderIntent, events: tuple[PaperOrderEvent, ...], *, as_of_ms: int,
) -> PaperOrderSnapshot:
    """Replay explicit hypothetical events without fabricating ACK or FILL.

    Same ID + same exact payload is idempotent IN THIS REPLAY only. A timeout
    produces UNKNOWN, never automatic retry or assumption of rejection.
    An async fill may precede an ACK. No persistence/network is implemented.
    """
    if type(intent) is not PaperOrderIntent:
        raise DataValidationError("validated synthetic paper intent required")
    cutoff = _utc_ms(as_of_ms, "as_of_ms")
    if cutoff < intent.created_at_ms:
        raise DataValidationError("paper replay precedes creation of intent")
    if type(events) is not tuple or len(events) > MAX_FIXTURE_EVENTS:
        raise DataValidationError("bounded immutable paper event tuple required")
    if any(type(event) is not PaperOrderEvent for event in events):
        raise DataValidationError("paper event type mismatch")

    status = PaperOrderStatus.PENDING
    filled = Decimal(0)
    last_time = None
    seen: dict[str, PaperOrderEvent] = {}
    duplicates = 0
    with localcontext(_EXACT_CONTEXT):
        for event in events:
            prior = seen.get(event.event_id)
            if prior is not None:
                if (prior.kind is not event.kind
                        or prior.event_at_ms != event.event_at_ms
                        or prior.filled_units.as_tuple() != event.filled_units.as_tuple()):
                    raise DataValidationError("conflicting reuse of paper event ID")
                duplicates += 1
                continue
            if not intent.created_at_ms <= event.event_at_ms <= cutoff:
                raise DataValidationError("paper order event outside causal UTC window")
            if last_time is not None and event.event_at_ms < last_time:
                raise DataValidationError("unique paper event out of chronological order")
            if status in (PaperOrderStatus.CANCELLED, PaperOrderStatus.REJECTED):
                raise DataValidationError("paper terminal order cannot accept more events")
            kind = event.kind
            if kind is PaperOrderEventKind.ACKNOWLEDGED:
                if status is PaperOrderStatus.FILLED:
                    # Late ACK is not an additional fill and cannot reverse closure.
                    pass
                elif filled > 0:
                    status = PaperOrderStatus.PARTIALLY_FILLED
                else:
                    status = PaperOrderStatus.ACKNOWLEDGED
            elif kind is PaperOrderEventKind.UNKNOWN:
                if status is PaperOrderStatus.FILLED:
                    raise DataValidationError("filled paper order cannot become UNKNOWN")
                status = PaperOrderStatus.UNKNOWN
            elif kind is PaperOrderEventKind.FILL:
                if status is PaperOrderStatus.FILLED:
                    raise DataValidationError("paper fill after fully filled order")
                filled += event.filled_units
                if filled > intent.requested_units:
                    raise DataValidationError("paper order overfill")
                status = (PaperOrderStatus.FILLED if filled == intent.requested_units
                          else PaperOrderStatus.PARTIALLY_FILLED)
            elif kind is PaperOrderEventKind.REJECTED:
                if filled != 0 or status is PaperOrderStatus.FILLED:
                    raise DataValidationError("paper rejection after a fill conflicts with ledger")
                status = PaperOrderStatus.REJECTED
            elif kind is PaperOrderEventKind.CANCELLED:
                if status is PaperOrderStatus.FILLED:
                    raise DataValidationError("paper cancellation after full fill")
                status = PaperOrderStatus.CANCELLED
            else:
                raise DataValidationError("unrecognized paper order event")
            last_time = event.event_at_ms
            seen[event.event_id] = event

    return PaperOrderSnapshot(
        intent_id=intent.intent_id, venue=intent.venue, effect=intent.effect,
        status=status, requested_units=intent.requested_units,
        filled_total_units=filled, unfilled_units=intent.requested_units - filled,
        as_of_ms=cutoff, unique_event_count=len(seen),
        exact_duplicate_count=duplicates, last_unique_event_at_ms=last_time,
    )
