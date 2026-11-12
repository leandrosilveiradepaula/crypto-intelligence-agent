"""J4: costed partial exits and residual PAPER marks, SYNTHETIC ONLY.

This composes the already-validated J4/PRE1-3 quantity replay with J3/PRE2
explicit hypothetical fee/slippage arithmetic. No OHLC-derived fills,
account balance, venue fees, mark provenance, liquidation model, order sender,
network, storage or inferred safety at 50x. Prices are supplied fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .market_data import DataValidationError
from .synthetic_cost_scenarios import (
    BPS_DENOMINATOR, MAX_FUNDING_EVENTS, SyntheticCostScenario,
    SyntheticFundingEvent, _amount, _rate, evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import (
    MAX_FIXTURE_EVENTS, _EXACT_CONTEXT, _utc_ms,
)
from .synthetic_position_state import (
    SyntheticPosition, SyntheticPositionExitFill, SyntheticSide,
    replay_synthetic_position,
)

MAX_MARK_AGE_MS = 604_800_000
_ZERO = Decimal(0)


@dataclass(frozen=True)
class SyntheticPartialMarkFill:
    """A declared reference price bound to ONE fictitious exit fill."""

    bound_fill: SyntheticPositionExitFill
    reference_exit_price_quote: Decimal

    def __post_init__(self) -> None:
        if type(self.bound_fill) is not SyntheticPositionExitFill:
            raise DataValidationError("typed synthetic bound exit fill required")
        _amount(self.reference_exit_price_quote, "synthetic exit reference price")


@dataclass(frozen=True)
class SyntheticPartialCostRates:
    """All four rates are explicit research assumptions, never venue quotes."""

    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_adverse_slippage_bps: Decimal
    exit_adverse_slippage_bps: Decimal

    def __post_init__(self) -> None:
        for name in (
            "entry_fee_bps", "exit_fee_bps",
            "entry_adverse_slippage_bps", "exit_adverse_slippage_bps",
        ):
            _rate(getattr(self, name), name, signed=False)


@dataclass(frozen=True)
class SyntheticPartialCostedReplay:
    """Marked reference NOT a brokerage PnL, margin balance or stop."""

    fixture_position_id: str
    side: SyntheticSide
    leverage_at_open: int
    initial_units: Decimal
    filled_units: Decimal
    residual_units: Decimal
    runner_floor_units: Decimal
    realized_gross_reference_quote: Decimal
    residual_mark_gross_reference_quote: Decimal
    entry_fee_slippage_quote: Decimal
    exit_fee_slippage_quote: Decimal
    signed_funding_cost_quote: Decimal
    hypothetical_net_mark_reference_quote: Decimal
    unique_fill_count: int
    exact_duplicate_fill_count: int
    unique_funding_count: int
    exact_duplicate_funding_count: int
    as_of_ms: int
    mark_observed_at_ms: int

    @property
    def quality(self) -> str:
        return "synthetic_partial_exit_mark_reference_only"

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def realized_pnl_verified(self) -> bool:
        return False

    @property
    def venue_fees_verified(self) -> bool:
        return False

    @property
    def funding_settlement_verified(self) -> bool:
        return False

    @property
    def liquidation_risk_verified(self) -> bool:
        return False

    @property
    def actual_margin_return_available(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    def sanitized_report(self) -> dict[str, object]:
        return {
            "status": self.quality,
            "leverage_at_open": self.leverage_at_open,
            "filled_units": str(self.filled_units),
            "residual_units": str(self.residual_units),
            "runner_floor_units": str(self.runner_floor_units),
            "realized_gross_reference_quote": str(self.realized_gross_reference_quote),
            "residual_mark_gross_reference_quote": str(
                self.residual_mark_gross_reference_quote
            ),
            "entry_fee_slippage_quote": str(self.entry_fee_slippage_quote),
            "exit_fee_slippage_quote": str(self.exit_fee_slippage_quote),
            "signed_funding_cost_quote": str(self.signed_funding_cost_quote),
            "hypothetical_net_mark_reference_quote": str(
                self.hypothetical_net_mark_reference_quote
            ),
            "unique_fill_count": self.unique_fill_count,
            "exact_duplicate_fill_count": self.exact_duplicate_fill_count,
            "unique_funding_count": self.unique_funding_count,
            "exact_duplicate_funding_count": self.exact_duplicate_funding_count,
            "financial_backtest_approved": False,
            "realized_pnl_verified": False,
            "venue_fees_verified": False,
            "funding_settlement_verified": False,
            "liquidation_risk_verified": False,
            "actual_margin_return_available": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def evaluate_synthetic_partial_costed_replay(
    position: SyntheticPosition,
    marked_fills: tuple[SyntheticPartialMarkFill, ...],
    *,
    entry_reference_price_quote: Decimal,
    last_reference_mark_quote: Decimal,
    mark_observed_at_ms: int,
    max_mark_age_ms: int,
    as_of_ms: int,
    cost_rates: SyntheticPartialCostRates,
    funding_events: tuple[SyntheticFundingEvent, ...] = (),
) -> SyntheticPartialCostedReplay:
    """Never infer a fill, backfill a price, update position or send an order.

    Entry/exit prices and latest mark are supplied research references. Fees
    and slippage are applied to the entire initial entry and to the actually
    declared unique partial exits (never to the untouched runner). Hypothetical
    funding uses entry-price notional of the remaining *fixture* units at its
    declared time, not a venue mark/collateral settlement.
    """
    if (type(position) is not SyntheticPosition
            or type(cost_rates) is not SyntheticPartialCostRates
            or type(marked_fills) is not tuple
            or len(marked_fills) > MAX_FIXTURE_EVENTS
            or any(type(f) is not SyntheticPartialMarkFill for f in marked_fills)
            or type(funding_events) is not tuple
            or len(funding_events) > MAX_FUNDING_EVENTS
            or any(type(e) is not SyntheticFundingEvent for e in funding_events)):
        raise DataValidationError("bounded typed synthetic position and mark fixtures required")
    entry = _amount(entry_reference_price_quote, "synthetic entry reference price")
    mark = _amount(last_reference_mark_quote, "synthetic last mark reference")
    cutoff = _utc_ms(as_of_ms, "as_of_ms")
    observed = _utc_ms(mark_observed_at_ms, "mark_observed_at_ms")
    if (type(max_mark_age_ms) is not int
            or not 0 <= max_mark_age_ms <= MAX_MARK_AGE_MS
            or not position.opened_at_ms < observed <= cutoff
            or cutoff - observed > max_mark_age_ms):
        raise DataValidationError("future or stale synthetic mark reference")
    snapshots = tuple(x.bound_fill for x in marked_fills)
    snapshot = replay_synthetic_position(position, snapshots, as_of_ms=cutoff)
    seen_fills: dict[str, SyntheticPartialMarkFill] = {}
    distinct: list[SyntheticPartialMarkFill] = []
    duplicate_fills = 0
    for row in marked_fills:
        event = row.bound_fill.event
        if (event.event_at_ms <= position.opened_at_ms
                or event.event_at_ms > observed):
            raise DataValidationError("reference fill cannot precede entry or exceed known mark")
        past = seen_fills.get(event.event_id)
        if past is not None:
            if (past.bound_fill != row.bound_fill
                    or past.bound_fill.event.filled_units.as_tuple()
                       != event.filled_units.as_tuple()
                    or past.reference_exit_price_quote.as_tuple()
                       != row.reference_exit_price_quote.as_tuple()):
                raise DataValidationError("duplicate synthetic fill has conflicting price or payload")
            duplicate_fills += 1
            continue
        seen_fills[event.event_id] = row
        distinct.append(row)
    if (len(distinct) != snapshot.unique_event_count
            or duplicate_fills != snapshot.exact_duplicate_count):
        raise DataValidationError("position replay and marked fills disagree")

    direction = (ResearchDirection.LONG
                 if position.side is SyntheticSide.LONG
                 else ResearchDirection.SHORT)
    multiplier = Decimal(1) if position.side is SyntheticSide.LONG else Decimal(-1)
    with localcontext(_EXACT_CONTEXT):
        opened_notional = entry * snapshot.initial_units
        _amount(opened_notional, "synthetic opening reference notional")
        entry_cost = (
            opened_notional
            * (cost_rates.entry_fee_bps + cost_rates.entry_adverse_slippage_bps)
            / BPS_DENOMINATOR
        )
        realized = _ZERO
        exit_cost = _ZERO
        for marked in distinct:
            event = marked.bound_fill.event
            amount = event.filled_units
            exit_price = marked.reference_exit_price_quote
            entry_part = entry * amount
            exit_part = exit_price * amount
            # Reuse J3/PRE2 cost arithmetic rather than a second fee engine.
            breakdown = evaluate_synthetic_costs(SyntheticCostScenario(
                direction=direction,
                entry_at_ms=position.opened_at_ms,
                exit_at_ms=event.event_at_ms,
                entry_hypothetical_notional_quote_units=entry_part,
                exit_hypothetical_notional_quote_units=exit_part,
                entry_fee_bps=cost_rates.entry_fee_bps,
                exit_fee_bps=cost_rates.exit_fee_bps,
                entry_adverse_slippage_bps=cost_rates.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=cost_rates.exit_adverse_slippage_bps,
            ))
            exit_cost += breakdown.exit_fee_units + breakdown.exit_slippage_cost_units
            realized += multiplier * (exit_price - entry) * amount

        unique_funding: dict[str, SyntheticFundingEvent] = {}
        last_funding_at = None
        duplicate_funding = 0
        funding_cost = _ZERO
        for event in funding_events:
            past = unique_funding.get(event.event_id)
            if past is not None:
                if (event.event_at_ms != past.event_at_ms
                        or event.hypothetical_notional_quote_units.as_tuple()
                        != past.hypothetical_notional_quote_units.as_tuple()
                        or event.signed_funding_rate_bps.as_tuple()
                        != past.signed_funding_rate_bps.as_tuple()):
                    raise DataValidationError("conflicting synthetic funding event ID")
                duplicate_funding += 1
                continue
            if (not position.opened_at_ms < event.event_at_ms <= observed
                    or (last_funding_at is not None
                        and event.event_at_ms <= last_funding_at)
                    or any(x.bound_fill.event.event_at_ms == event.event_at_ms
                           for x in distinct)):
                raise DataValidationError("synthetic funding has ambiguous or future chronology")
            remaining_at_event = (
                snapshot.initial_units
                - sum(
                    (row.bound_fill.event.filled_units for row in distinct
                     if row.bound_fill.event.event_at_ms < event.event_at_ms),
                    _ZERO,
                )
            )
            if (remaining_at_event <= 0
                    or event.hypothetical_notional_quote_units
                    != remaining_at_event * entry):
                raise DataValidationError(
                    "synthetic funding notional must equal remaining entry-price reference"
                )
            funding_cost += (
                multiplier * event.hypothetical_notional_quote_units
                * event.signed_funding_rate_bps / BPS_DENOMINATOR
            )
            unique_funding[event.event_id] = event
            last_funding_at = event.event_at_ms
        residual_gross = (
            multiplier * (mark - entry) * snapshot.remaining_units
        )
        if (snapshot.initial_units
                != snapshot.filled_total_units + snapshot.remaining_units
                or snapshot.remaining_units < snapshot.residual_floor_units):
            raise DataValidationError("partial exit or runner quantity conservation failed")
        net = realized + residual_gross - entry_cost - exit_cost - funding_cost
        return SyntheticPartialCostedReplay(
            fixture_position_id=position.fixture_position_id,
            side=position.side,
            leverage_at_open=position.leverage_at_open,
            initial_units=snapshot.initial_units,
            filled_units=snapshot.filled_total_units,
            residual_units=snapshot.remaining_units,
            runner_floor_units=snapshot.residual_floor_units,
            realized_gross_reference_quote=realized,
            residual_mark_gross_reference_quote=residual_gross,
            entry_fee_slippage_quote=entry_cost,
            exit_fee_slippage_quote=exit_cost,
            signed_funding_cost_quote=funding_cost,
            hypothetical_net_mark_reference_quote=net,
            unique_fill_count=len(distinct),
            exact_duplicate_fill_count=duplicate_fills,
            unique_funding_count=len(unique_funding),
            exact_duplicate_funding_count=duplicate_funding,
            as_of_ms=cutoff,
            mark_observed_at_ms=observed,
        )
