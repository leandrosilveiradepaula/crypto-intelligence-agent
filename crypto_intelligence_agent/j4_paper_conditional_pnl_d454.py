"""D454: conditional realized PAPER PnL from immutable priced AUTO2/AUTO4 fills.

No extra financial ledger. Every price must be part of the canonical FILL
event persisted by D448 or D394 and matched against exact AUTO2 opening and
D448 immutable policy. BBO and fee/slippage models are HYPOTHETICAL only.
Funding, liquidation, taxes and venue-native execution remain UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path

from .j4_automatic_entry_materializer_d448 import _read_plan, _read_policy
from .j4_private_paper_ws_operator_d425 import _private_directory, _JOURNAL
from .market_data import DataValidationError
from .paper_margin_receipt import META_PREFIX, PaperMarginIntentReceipt
from .paper_order_store import (
    SQLitePaperOrderJournal, _TABLES as _ORDER_TABLES, _VERSION as _ORDER_VERSION,
)
from .paper_position_inspection import _read_database, inspect_paper_position
from .synthetic_cost_scenarios import SyntheticCostScenario, evaluate_synthetic_costs
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import _EXACT_CONTEXT
from .synthetic_order_lifecycle import PaperOrderEventKind, PaperVenue
from .synthetic_position_state import SyntheticSide


@dataclass(frozen=True)
class ConditionalPaperPnL:
    """Not an account balance or net trading PnL; funding is never silently 0."""

    status: str
    priced_entry_units: Decimal | None
    realized_exit_units: Decimal
    gross_realized_reference_quote: Decimal | None
    allocated_entry_fee_quote: Decimal | None
    exit_fee_quote: Decimal | None
    allocated_entry_slippage_quote: Decimal | None
    exit_slippage_quote: Decimal | None
    conditional_realized_before_funding_quote: Decimal | None
    outstanding_entry_cost_quote: Decimal | None
    leverage_at_open: int | None
    priced_fill_events: int

    def sanitized_report(self) -> dict[str, object]:
        def v(number):
            return None if number is None else format(number, "f")
        return {
            "schema_version": "d454-paper-conditional-priced-fills-v1",
            "status": self.status,
            "priced_entry_units": v(self.priced_entry_units),
            "realized_exit_units": v(self.realized_exit_units),
            "gross_realized_reference_quote": v(self.gross_realized_reference_quote),
            "entry_fee_allocated_quote": v(self.allocated_entry_fee_quote),
            "exit_fee_quote": v(self.exit_fee_quote),
            "entry_slippage_allocated_quote": v(self.allocated_entry_slippage_quote),
            "exit_slippage_quote": v(self.exit_slippage_quote),
            "conditional_realized_before_funding_quote":
                v(self.conditional_realized_before_funding_quote),
            "outstanding_entry_cost_quote": v(self.outstanding_entry_cost_quote),
            "leverage_at_open": self.leverage_at_open,
            "priced_fill_events": self.priced_fill_events,
            "funding_calendar_verified": False,
            "funding_settlement_unknown": True,
            "true_realized_net_pnl_available": False,
            "source_is_hypothetical_post_latency_bbo": True,
            "venue_fill_verified": False,
            "venue_fee_schedule_verified": False,
            "liquidation_verified": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def conditional_paper_pnl_from_existing_fills(
    *, private_paper_directory: Path, position_id: str,
) -> ConditionalPaperPnL:
    """Read through checked AUTO2+AUTO4 journals and original signed-like plan.

    A legacy quantity-only event returns no numeric price PnL. A pending
    REDUCE_ONLY has no simulated FILL, hence contributes zero realized units.
    All costs come from immutable D448 policy and the existing J3 cost model.
    """
    home = _private_directory(private_paper_directory)
    order_path = home / "paper-orders.sqlite"
    position_path = home / _JOURNAL
    view = inspect_paper_position(
        position_path, position_id, opening_order_path=order_path,
    ).balance
    if view.venue is not PaperVenue.BYBIT_V5:
        raise DataValidationError("D454 expects existing Bybit PAPER position only")
    with _read_database(
        order_path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION,
    ) as conn:
        opening = SQLitePaperOrderJournal._checked_entry(
            conn, view.opening_intent_id,
        )
        row = conn.execute(
            "SELECT value FROM paper_order_meta WHERE key=?",
            (META_PREFIX + view.opening_intent_id,),
        ).fetchone()
        if row is None:
            raise DataValidationError("D454 missing original PAPER margin receipt")
        receipt = PaperMarginIntentReceipt.deserialize(row["value"])
        receipt.verify_intent(opening.intent)
    planned = _read_plan(home, opening.intent, receipt)
    policy = _read_policy(planned["policy"])
    entrance = [event for event in opening.events
                if event.kind is PaperOrderEventKind.FILL]
    exits = [
        (order.intent, event)
        for order in view.exit_orders
        for event in order.events
        if event.kind is PaperOrderEventKind.FILL
    ]
    exit_qty = sum((e.filled_units for _, e in exits), Decimal(0))
    if (len(entrance) != 1
            or entrance[0].filled_units != view.initial_confirmed_units
            or any(not event.event_at_ms >= entrance[0].event_at_ms
                   for _, event in exits)):
        raise DataValidationError("D454 inconsistent opening/exit FILL chronology")
    if (entrance[0].hypothetical_reference_price_quote is None
            or any(event.hypothetical_reference_price_quote is None
                   for _, event in exits)):
        return ConditionalPaperPnL(
            "legacy_unpriced_fill_no_pnl", None, exit_qty,
            None, None, None, None, None, None, None,
            view.leverage_at_intent, 0,
        )
    price = entrance[0].hypothetical_reference_price_quote
    direction = (ResearchDirection.LONG
                 if view.side is SyntheticSide.LONG else ResearchDirection.SHORT)
    multiplier = Decimal(1) if view.side is SyntheticSide.LONG else Decimal(-1)
    gross = entry_fee = exit_fee = entry_slip = exit_slip = Decimal(0)
    with localcontext(_EXACT_CONTEXT):
        for intent, event in exits:
            reference = event.hypothetical_reference_price_quote
            cost = evaluate_synthetic_costs(SyntheticCostScenario(
                direction=direction,
                entry_at_ms=entrance[0].event_at_ms,
                exit_at_ms=event.event_at_ms,
                entry_hypothetical_notional_quote_units=price * event.filled_units,
                exit_hypothetical_notional_quote_units=reference * event.filled_units,
                entry_fee_bps=policy.entry_fee_bps,
                exit_fee_bps=policy.exit_fee_bps,
                entry_adverse_slippage_bps=policy.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=policy.exit_adverse_slippage_bps,
            ))
            gross += multiplier * (reference - price) * event.filled_units
            entry_fee += cost.entry_fee_units
            exit_fee += cost.exit_fee_units
            entry_slip += cost.entry_slippage_cost_units
            exit_slip += cost.exit_slippage_cost_units
        remaining = view.initial_confirmed_units - exit_qty
        outstanding_entry_cost = (price * remaining *
                                  (policy.entry_fee_bps +
                                   policy.entry_adverse_slippage_bps) / Decimal(10000))
        net = gross - entry_fee - exit_fee - entry_slip - exit_slip
    return ConditionalPaperPnL(
        status="conditional_paper_reference_before_unverified_funding",
        priced_entry_units=view.initial_confirmed_units,
        realized_exit_units=exit_qty,
        gross_realized_reference_quote=gross,
        allocated_entry_fee_quote=entry_fee,
        exit_fee_quote=exit_fee,
        allocated_entry_slippage_quote=entry_slip,
        exit_slippage_quote=exit_slip,
        conditional_realized_before_funding_quote=net,
        outstanding_entry_cost_quote=outstanding_entry_cost,
        leverage_at_open=view.leverage_at_intent,
        priced_fill_events=1 + len(exits),
    )
