"""D393: read-only J3 cost stress on actual recorded D392 PAPER fill events.

This is deliberately NOT a fill simulator. It can value only explicit FILL
events already persisted in AUTO4, each paired to an independently declared
fixture price receipt. A pending/UNKNOWN position produces NO numeric payoff.

All rates, prices and funding events are supplied synthetic assumptions.
The existing J3/PRE2 evaluate_synthetic_costs owns cost arithmetic. No SQL
writes, market data, broker account, venue fee proof or liquidation claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path

from .market_data import DataValidationError
from .paper_position_inspection import inspect_paper_position
from .synthetic_order_lifecycle import (
    PaperOrderEventKind, PaperOrderStatus, PaperVenue, _id,
)
from .synthetic_position_state import SyntheticSide
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_cost_scenarios import (
    SyntheticCostScenario, SyntheticFundingEvent, BPS_DENOMINATOR,
    _amount, evaluate_synthetic_costs,
)
from .synthetic_partial_costed_replay import SyntheticPartialCostRates
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms

_ZERO = Decimal(0)


@dataclass(frozen=True)
class PaperDeclaredFillReference:
    """ONE separately invented research price, keyed to a real PAPER FILL."""

    intent_id: str
    event_id: str
    event_at_ms: int
    reference_exit_price_quote: Decimal

    def __post_init__(self) -> None:
        _id(self.intent_id, "PAPER cost reference intent")
        _id(self.event_id, "PAPER cost reference event")
        _utc_ms(self.event_at_ms, "PAPER cost reference event time")
        _amount(self.reference_exit_price_quote, "PAPER hypothetical fill price")


@dataclass(frozen=True)
class PaperClosedCostAudit:
    status: str
    paper_fill_count: int
    confirmed_remaining_units: Decimal
    pending_reserved_units: Decimal
    gross_reference_quote: Decimal | None
    entry_fee_quote: Decimal | None
    exit_fee_quote: Decimal | None
    entry_slippage_quote: Decimal | None
    exit_slippage_quote: Decimal | None
    signed_funding_quote: Decimal | None
    conditional_net_after_supplied_costs_quote: Decimal | None
    funding_events_supplied: int
    leverage_at_open: int | None

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "paper-closed-cost-audit-d393-v1",
            "status": self.status,
            "paper_fill_count": self.paper_fill_count,
            "confirmed_remaining_units": str(self.confirmed_remaining_units),
            "pending_reserved_units": str(self.pending_reserved_units),
            "gross_reference_quote": (None if self.gross_reference_quote is None
                                     else str(self.gross_reference_quote)),
            "entry_fee_quote": (None if self.entry_fee_quote is None
                               else str(self.entry_fee_quote)),
            "exit_fee_quote": (None if self.exit_fee_quote is None
                              else str(self.exit_fee_quote)),
            "entry_slippage_quote": (None if self.entry_slippage_quote is None
                                    else str(self.entry_slippage_quote)),
            "exit_slippage_quote": (None if self.exit_slippage_quote is None
                                   else str(self.exit_slippage_quote)),
            "signed_funding_quote": (None if self.signed_funding_quote is None
                                    else str(self.signed_funding_quote)),
            "conditional_net_after_supplied_costs_quote": (
                None if self.conditional_net_after_supplied_costs_quote is None
                else str(self.conditional_net_after_supplied_costs_quote)),
            "funding_events_supplied": self.funding_events_supplied,
            "leverage_at_open": self.leverage_at_open,
            "funding_calendar_complete": False,
            "market_data_authenticated": False,
            "venue_fills_verified": False,
            "venue_fees_verified": False,
            "liquidation_risk_verified": False,
            "net_pnl_verified": False,
            "financial_backtest_approved": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def audit_closed_paper_costs(
    position_path: str | Path,
    position_id: str,
    *,
    entry_reference_price_quote: Decimal,
    fill_references: tuple[PaperDeclaredFillReference, ...],
    cost_rates: SyntheticPartialCostRates,
    funding_events: tuple[SyntheticFundingEvent, ...] = (),
) -> PaperClosedCostAudit:
    """Read an existing PAPER ledger and conditionally value EXACT known fills.

    UNKNOWN/ACK/open balances return NO net value, even if favorable paper
    prices are supplied. For closed positions, every recorded FILL requires
    one matching reference for (intent ID, event ID, UTC-ms). No unrecorded
    reference can create a hypothetical trade.

    Funding is a supplied scenario, never a verified settlement calendar.
    A result marked 'conditional' cannot be used as a trading PnL or
    liquidation/risk certification.
    """
    if (type(cost_rates) is not SyntheticPartialCostRates
            or type(fill_references) is not tuple
            or len(fill_references) > 128
            or any(type(x) is not PaperDeclaredFillReference for x in fill_references)
            or type(funding_events) is not tuple
            or len(funding_events) > 64
            or any(type(x) is not SyntheticFundingEvent for x in funding_events)):
        raise DataValidationError("PAPER cost audit requires bounded typed fixture evidence")
    entry = _amount(entry_reference_price_quote, "PAPER assumed entry reference price")
    balance = inspect_paper_position(position_path, position_id).balance
    if balance.venue is not PaperVenue.BYBIT_V5:
        raise DataValidationError("PAPER cost audit only matches Bybit synthetic position")
    if balance.side not in (SyntheticSide.LONG, SyntheticSide.SHORT):
        raise DataValidationError("PAPER cost audit requires explicit direction")
    fills = [
        (order.intent.intent_id, event)
        for order in balance.exit_orders
        for event in order.events if event.kind is PaperOrderEventKind.FILL
    ]
    # A position with any unresolved, cancelled, rejected or open exposure
    # must not expose even a conditional net return.
    if (balance.confirmed_remaining_units != 0
            or balance.reserved_unfilled_units != 0
            or any(order.snapshot.status is not PaperOrderStatus.FILLED
                   for order in balance.exit_orders)
            or balance.filled_exit_units != balance.initial_confirmed_units):
        return PaperClosedCostAudit(
            "reconciliation_or_open_balance_no_cost_pnl",
            len(fills), balance.confirmed_remaining_units,
            balance.reserved_unfilled_units,
            None, None, None, None, None, None, None, 0,
            balance.leverage_at_intent,
        )
    if not fills:
        raise DataValidationError("PAPER cost audit has no explicit exit fills")
    # Deliberately strict: no duplicate reference even if economically identical.
    keyed: dict[tuple[str, str], PaperDeclaredFillReference] = {}
    for item in fill_references:
        key = (item.intent_id, item.event_id)
        if key in keyed:
            raise DataValidationError("PAPER duplicate cost price receipt")
        keyed[key] = item
    actual = {(intent_id, event.event_id) for intent_id, event in fills}
    if set(keyed) != actual:
        raise DataValidationError("PAPER price receipts do not bijectively match journal fills")
    chronology = sorted(fills, key=lambda x: x[1].event_at_ms)
    times = [e.event_at_ms for _, e in chronology]
    if (len(set(times)) != len(times)
            or any(not balance.opened_at_ms < at <= balance.as_of_ms for at in times)):
        raise DataValidationError("PAPER fills lack unambiguous causal chronology")
    for intent_id, event in chronology:
        if keyed[(intent_id, event.event_id)].event_at_ms != event.event_at_ms:
            raise DataValidationError("PAPER price reference timestamp mismatches persisted fill")
    direction = (ResearchDirection.LONG
                 if balance.side is SyntheticSide.LONG
                 else ResearchDirection.SHORT)
    multiplier = Decimal(1) if balance.side is SyntheticSide.LONG else Decimal(-1)
    entry_fee = exit_fee = entry_slip = exit_slip = gross = _ZERO
    with localcontext(_EXACT_CONTEXT):
        for intent_id, event in chronology:
            ref = keyed[(intent_id, event.event_id)]
            qty = event.filled_units
            breakdown = evaluate_synthetic_costs(SyntheticCostScenario(
                direction=direction,
                entry_at_ms=balance.opened_at_ms,
                exit_at_ms=event.event_at_ms,
                entry_hypothetical_notional_quote_units=entry * qty,
                exit_hypothetical_notional_quote_units=ref.reference_exit_price_quote * qty,
                entry_fee_bps=cost_rates.entry_fee_bps,
                exit_fee_bps=cost_rates.exit_fee_bps,
                entry_adverse_slippage_bps=cost_rates.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=cost_rates.exit_adverse_slippage_bps,
            ))
            entry_fee += breakdown.entry_fee_units
            exit_fee += breakdown.exit_fee_units
            entry_slip += breakdown.entry_slippage_cost_units
            exit_slip += breakdown.exit_slippage_cost_units
            gross += multiplier * (ref.reference_exit_price_quote - entry) * qty
        unique_funding: dict[str, SyntheticFundingEvent] = {}
        for event in funding_events:
            past = unique_funding.get(event.event_id)
            if past is not None:
                if past != event:
                    raise DataValidationError("PAPER conflicting funding event replay")
                continue
            if (event.event_at_ms in times
                    or not balance.opened_at_ms < event.event_at_ms < times[-1]):
                raise DataValidationError("PAPER funding time collides with fill or outside hold")
            remaining = (
                balance.initial_confirmed_units
                - sum((e.filled_units for _, e in chronology
                       if e.event_at_ms < event.event_at_ms), _ZERO)
            )
            if (remaining <= 0
                    or event.hypothetical_notional_quote_units != remaining * entry):
                raise DataValidationError("PAPER funding notional is not remaining reference balance")
            unique_funding[event.event_id] = event

        # Reuse J3's signed funding cost convention (LONG pays positive rate).
        last_exit = times[-1]
        funding_calc = evaluate_synthetic_costs(SyntheticCostScenario(
            direction=direction,
            entry_at_ms=balance.opened_at_ms,
            exit_at_ms=last_exit,
            entry_hypothetical_notional_quote_units=entry * balance.initial_confirmed_units,
            exit_hypothetical_notional_quote_units=entry * balance.initial_confirmed_units,
            entry_fee_bps=_ZERO, exit_fee_bps=_ZERO,
            entry_adverse_slippage_bps=_ZERO,
            exit_adverse_slippage_bps=_ZERO,
            funding_events=funding_events,
        ))
        signed_funding = funding_calc.signed_funding_cost_units
        net = gross - entry_fee - exit_fee - entry_slip - exit_slip - signed_funding
        return PaperClosedCostAudit(
            "conditional_closed_paper_cost_reference_only",
            len(chronology), balance.confirmed_remaining_units,
            balance.reserved_unfilled_units,
            gross, entry_fee, exit_fee, entry_slip, exit_slip,
            signed_funding, net, len(unique_funding),
            balance.leverage_at_intent,
        )
