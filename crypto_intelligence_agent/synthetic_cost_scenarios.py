"""J3/PRE2: exact arithmetic of HYPOTHETICAL costs in abstract quote units.

No fill is inferred from an OHLC barrier. A negative total cost caused by
funding receipts is NOT a profitable trade or net PnL. All venue schedules,
quote currencies, trade notionals and funding events here are user-supplied
SYNTHETIC fixtures, not factual market data or authorization to trade.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import re

from .market_data import DataValidationError
from .synthetic_intrabar_barriers import ResearchDirection

MAX_FUNDING_EVENTS = 64
MAX_UTC_MS = 253_402_300_799_999
MAX_AMOUNT_DIGITS = 40
MIN_AMOUNT_EXP = -18
MAX_AMOUNT_ADJUSTED_EXP = 24
MAX_BPS_DECIMAL_PLACES = 6
BPS_DENOMINATOR = Decimal(10_000)
# Rates and notionals have finite decimal expansions. This is ample for
# 40 digits of notional, 6 rate decimals, and 64 additions without rounding.
_EXACT_CONTEXT = Context(prec=512, rounding=ROUND_HALF_EVEN)
_EVENT_ID = re.compile(r"fixture_funding_[A-Za-z0-9_-]{1,40}")


def _time(value: int, name: str) -> int:
    if type(value) is not int or not 0 < value <= MAX_UTC_MS:
        raise DataValidationError(f"{name} requires bounded UTC-ms integer")
    return value


def _amount(value: Decimal, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise DataValidationError(f"{name} requires positive finite Decimal, never float")
    t = value.as_tuple()
    if (len(t.digits) > MAX_AMOUNT_DIGITS or t.exponent < MIN_AMOUNT_EXP
            or value.adjusted() > MAX_AMOUNT_ADJUSTED_EXP):
        raise DataValidationError(f"{name} exceeds synthetic Decimal bounds")
    return value


def _rate(value: Decimal, name: str, *, signed: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise DataValidationError(f"{name} requires exact finite Decimal")
    if value.as_tuple().exponent < -MAX_BPS_DECIMAL_PLACES:
        raise DataValidationError(f"{name} exceeds allowed decimal places")
    if (value < -BPS_DENOMINATOR if signed else value < 0) or value > BPS_DENOMINATOR:
        raise DataValidationError(f"{name} outside synthetic bps limit")
    return value


@dataclass(frozen=True)
class SyntheticFundingEvent:
    """User-declared fixture, not a real venue funding settlement."""

    event_id: str
    event_at_ms: int
    hypothetical_notional_quote_units: Decimal
    signed_funding_rate_bps: Decimal

    def __post_init__(self) -> None:
        if type(self.event_id) is not str or _EVENT_ID.fullmatch(self.event_id) is None:
            raise DataValidationError("funding event ID must be fixture-only bounded ASCII")
        _time(self.event_at_ms, "event_at_ms")
        _amount(self.hypothetical_notional_quote_units, "funding notional")
        _rate(self.signed_funding_rate_bps, "signed funding rate", signed=True)


@dataclass(frozen=True)
class SyntheticCostScenario:
    direction: ResearchDirection
    entry_at_ms: int
    exit_at_ms: int
    entry_hypothetical_notional_quote_units: Decimal
    exit_hypothetical_notional_quote_units: Decimal
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_adverse_slippage_bps: Decimal
    exit_adverse_slippage_bps: Decimal
    funding_events: tuple[SyntheticFundingEvent, ...] = ()

    def __post_init__(self) -> None:
        if type(self.direction) is not ResearchDirection:
            raise DataValidationError("cost scenario requires explicit research direction")
        if _time(self.entry_at_ms, "entry_at_ms") >= _time(self.exit_at_ms, "exit_at_ms"):
            raise DataValidationError("synthetic exit must occur after entry")
        _amount(self.entry_hypothetical_notional_quote_units, "entry notional")
        _amount(self.exit_hypothetical_notional_quote_units, "exit notional")
        for name in ("entry_fee_bps", "exit_fee_bps",
                     "entry_adverse_slippage_bps", "exit_adverse_slippage_bps"):
            _rate(getattr(self, name), name, signed=False)
        if (type(self.funding_events) is not tuple
                or len(self.funding_events) > MAX_FUNDING_EVENTS
                or any(type(e) is not SyntheticFundingEvent
                       for e in self.funding_events)):
            raise DataValidationError("funding fixtures must be a bounded immutable tuple")


@dataclass(frozen=True)
class SyntheticCostBreakdown:
    entry_fee_units: Decimal
    exit_fee_units: Decimal
    entry_slippage_cost_units: Decimal
    exit_slippage_cost_units: Decimal
    signed_funding_cost_units: Decimal
    fees_and_slippage_units: Decimal
    total_signed_cost_units: Decimal
    unique_funding_count: int
    exact_duplicate_count: int
    last_unique_funding_at_ms: int | None

    @property
    def quality(self) -> str:
        return "synthetic_cost_scenario_only"

    @property
    def venue_fee_schedule_verified(self) -> bool:
        return False

    @property
    def funding_schedule_verified(self) -> bool:
        return False

    @property
    def real_quote_currency_verified(self) -> bool:
        return False

    @property
    def fill_price_verified(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def net_pnl_verified(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def evaluate_synthetic_costs(scenario: SyntheticCostScenario) -> SyntheticCostBreakdown:
    """Compute only explicit hypothetical costs; no trade is ever filled here.

    Positive funding rate means LONG pays and SHORT receives in THIS synthetic
    convention. Negative rate reverses the sign. Actual venue settlement,
    timestamps, funding notional and cap may differ; not verified.
    """
    if type(scenario) is not SyntheticCostScenario:
        raise DataValidationError("explicit synthetic cost scenario required")
    with localcontext(_EXACT_CONTEXT):
        in_size = scenario.entry_hypothetical_notional_quote_units
        out_size = scenario.exit_hypothetical_notional_quote_units
        entry_fee = in_size * scenario.entry_fee_bps / BPS_DENOMINATOR
        exit_fee = out_size * scenario.exit_fee_bps / BPS_DENOMINATOR
        entry_slip = in_size * scenario.entry_adverse_slippage_bps / BPS_DENOMINATOR
        exit_slip = out_size * scenario.exit_adverse_slippage_bps / BPS_DENOMINATOR
        non_funding = entry_fee + exit_fee + entry_slip + exit_slip
        funding = Decimal(0)
        duplicates = 0
        last_time: int | None = None
        seen: dict[str, SyntheticFundingEvent] = {}
        for event in scenario.funding_events:
            earlier = seen.get(event.event_id)
            if earlier is not None:
                if (earlier.event_at_ms != event.event_at_ms
                        or earlier.hypothetical_notional_quote_units.as_tuple()
                        != event.hypothetical_notional_quote_units.as_tuple()
                        or earlier.signed_funding_rate_bps.as_tuple()
                        != event.signed_funding_rate_bps.as_tuple()):
                    raise DataValidationError("synthetic funding event ID has conflicting payload")
                duplicates += 1
                continue
            if not scenario.entry_at_ms < event.event_at_ms < scenario.exit_at_ms:
                raise DataValidationError("synthetic funding event outside open holding interval")
            if last_time is not None and event.event_at_ms <= last_time:
                raise DataValidationError("synthetic unique funding events must be strictly chronological")
            direction = (Decimal(1) if scenario.direction is ResearchDirection.LONG
                         else Decimal(-1))
            funding += (direction * event.hypothetical_notional_quote_units
                        * event.signed_funding_rate_bps / BPS_DENOMINATOR)
            seen[event.event_id] = event
            last_time = event.event_at_ms
        return SyntheticCostBreakdown(
            entry_fee_units=entry_fee, exit_fee_units=exit_fee,
            entry_slippage_cost_units=entry_slip,
            exit_slippage_cost_units=exit_slip,
            signed_funding_cost_units=funding,
            fees_and_slippage_units=non_funding,
            total_signed_cost_units=non_funding + funding,
            unique_funding_count=len(seen), exact_duplicate_count=duplicates,
            last_unique_funding_at_ms=last_time,
        )
