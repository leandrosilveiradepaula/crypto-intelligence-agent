"""D394: bounded causal PAPER-only fill hypothesis from a *later* public BBO.

A D389 reservation is NOT a fill. Only a separately observed, post-latency
BybitTickerQuote can conditionally supply an explicitly HYPOTHETICAL FILL.
This is a research model assuming a limited fraction of displayed top-of-book
size was available; it is not an execution forecast, trade tape, orderbook
queue simulation, private broker receipt or liquidation/risk certification.

Opt-in writes exclusively to the existing synthetic AUTO4 PAPER ledger. The
caller must carry the returned D393 price receipt through the test/replay;
no second financial journal, API key, socket, live order or real venue action.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path

from .bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from .market_data import DataGapError, DataValidationError
from .paper_closed_cost_audit_d393 import PaperDeclaredFillReference
from .paper_position_inspection import inspect_paper_position
from .paper_position_reservations import SQLitePaperPositionJournal
from .synthetic_cost_scenarios import BPS_DENOMINATOR, _rate
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)

_ZERO = Decimal(0)


@dataclass(frozen=True)
class PaperObservedFillAssumptions:
    """Explicit simulator assumptions, never inferred venue conditions."""

    min_quote_after_intent_ms: int = 150
    max_quote_age_ms: int = 3000
    max_intent_wait_ms: int = 60_000
    max_spread_bps: Decimal = Decimal(30)
    max_top_level_participation_bps: Decimal = Decimal(2500)

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("min_quote_after_intent_ms", 1, 60_000),
            ("max_quote_age_ms", 100, 30_000),
            ("max_intent_wait_ms", 100, 3_600_000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise DataValidationError("invalid PAPER fill simulator duration: " + name)
        _rate(self.max_spread_bps, "max simulator BBO spread", signed=False)
        _rate(self.max_top_level_participation_bps, "simulator participation", signed=False)
        if self.max_top_level_participation_bps <= 0:
            raise DataValidationError("PAPER top-book participation must be positive")


class PaperFillDecision(str, Enum):
    DISABLED = "offline_paper_optin_required"
    TOO_EARLY = "await_later_post_latency_observation"
    STALE = "stale_or_noncausal_market_observation"
    TOO_WIDE = "spread_above_simulation_assumption"
    NO_LIQUIDITY = "insufficient_displayed_top_level_liquidity"
    TIMED_OUT = "simulated_intent_expired_requires_reconciliation"
    BLOCKED = "paper_order_uncertain_or_terminal"
    ALREADY_RECORDED = "same_public_quote_already_applied"
    ASSUMED_PARTIAL = "hypothetical_partial_fill_recorded"
    ASSUMED_FULL = "hypothetical_full_fill_recorded"


@dataclass(frozen=True)
class PaperObservedFillResult:
    decision: PaperFillDecision
    recorded_units: Decimal
    remaining_order_units: Decimal
    receipt: PaperDeclaredFillReference | None
    event: PaperOrderEvent | None

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "paper-observed-fill-d394-v1",
            "decision": self.decision.value,
            "recorded_units": str(self.recorded_units),
            "remaining_order_units": str(self.remaining_order_units),
            "assumed_fill_recorded": self.decision in (
                PaperFillDecision.ASSUMED_PARTIAL, PaperFillDecision.ASSUMED_FULL,
            ),
            "independent_post_latency_quote_required": True,
            "top_of_book_fill_assumption_only": True,
            "real_orderbook_queue_verified": False,
            "venue_fill_verified": False,
            "liquidation_risk_verified": False,
            "slippage_applied_by_this_stage": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def _checked_market(quote: BybitTickerQuote) -> None:
    """Dataclass construction alone is not sufficient source validation."""
    if type(quote) is not BybitTickerQuote or quote.source != SOURCE:
        raise DataValidationError("D394 requires D385 typed unverified Bybit ticker")
    _utc_ms(quote.exchange_at_ms, "D394 exchange clock")
    _utc_ms(quote.received_at_ms, "D394 reception clock")
    if type(quote.cross_sequence) is not int or quote.cross_sequence < 1:
        raise DataValidationError("D394 cross sequence invalid")
    if (type(quote.symbol) is not str
            or not quote.symbol.endswith("USDT")
            or not 5 <= len(quote.symbol) <= 25):
        raise DataValidationError("D394 symbol shape invalid")
    for name in ("bid_price", "ask_price", "mark_price", "bid_size", "ask_size"):
        value = getattr(quote, name)
        if type(value) is not Decimal or not value.is_finite() or value < 0:
            raise DataValidationError("D394 invalid Decimal quote field")
    if (quote.bid_price <= 0 or quote.ask_price <= 0
            or quote.mark_price <= 0 or quote.bid_price > quote.ask_price
            or quote.exchange_at_ms > quote.received_at_ms):
        raise DataValidationError("D394 quote violates BBO/UTC invariants")


def apply_causal_paper_fill_assumption(
    position_path: str | Path, position_id: str, intent_id: str,
    *,
    quote: BybitTickerQuote,
    as_of_ms: int,
    policy: PaperObservedFillAssumptions,
    enable_synthetic_ledger_fills: bool = False,
) -> PaperObservedFillResult:
    """Optionally append ONE explicitly hypothetical AUTO4 FILL after latency.

    Never treats a D389 target/stop trigger quote as execution evidence:
    the exchange-produced BBO timestamp must be strictly later than
    intent creation plus a configured latency. Uses only a bounded fraction
    of BBO size, rounded DOWN to the position's synthetic lot step. Reusing
    the identical (intent, quote CS, exchange UTC) event cannot double-fill
    the ledger. Price receipts are separately supplied to D393; slippage
    must be charged there rather than silently double charged here.
    """
    if type(policy) is not PaperObservedFillAssumptions:
        raise DataValidationError("explicit D394 assumptions required")
    if type(enable_synthetic_ledger_fills) is not bool:
        raise DataValidationError("D394 opt-in must be boolean")
    cutoff = _utc_ms(as_of_ms, "D394 accounting clock")
    _checked_market(quote)
    view = inspect_paper_position(position_path, position_id).balance
    found = [o for o in view.exit_orders if o.intent.intent_id == intent_id]
    if len(found) != 1:
        raise DataValidationError("D394 requires exactly one reserved AUTO4 exit")
    order = found[0]
    intent = order.intent
    if (view.venue is not PaperVenue.BYBIT_V5 or intent.venue is not PaperVenue.BYBIT_V5
            or intent.effect is not PaperOrderEffect.REDUCE_ONLY
            or intent.symbol != quote.symbol or view.symbol != quote.symbol
            or intent.max_reducible_units is None):
        raise DataValidationError("D394 PAPER position, exit and quote do not match")

    def result(decision: PaperFillDecision, *, units: Decimal = _ZERO,
               receipt: PaperDeclaredFillReference | None = None,
               event: PaperOrderEvent | None = None,
               remaining: Decimal | None = None) -> PaperObservedFillResult:
        return PaperObservedFillResult(
            decision, units,
            order.snapshot.unfilled_units if remaining is None else remaining,
            receipt, event,
        )

    if not enable_synthetic_ledger_fills:
        return result(PaperFillDecision.DISABLED)
    # No write for unresolved UNKNOWN or a terminal/rejected/cancelled order.
    if order.snapshot.status not in (
        PaperOrderStatus.PENDING, PaperOrderStatus.ACKNOWLEDGED,
        PaperOrderStatus.PARTIALLY_FILLED,
    ):
        return result(PaperFillDecision.BLOCKED)
    if (quote.received_at_ms < view.as_of_ms or cutoff < view.as_of_ms
            or cutoff < quote.received_at_ms
            or cutoff - quote.received_at_ms > policy.max_quote_age_ms
            or quote.received_at_ms - quote.exchange_at_ms > policy.max_quote_age_ms):
        return result(PaperFillDecision.STALE)
    if quote.exchange_at_ms < intent.created_at_ms + policy.min_quote_after_intent_ms:
        return result(PaperFillDecision.TOO_EARLY)
    if quote.received_at_ms - intent.created_at_ms > policy.max_intent_wait_ms:
        return result(PaperFillDecision.TIMED_OUT)

    # ID is stable for this precise *causal observation*, not for economics.
    # An already applied quote never produces another reference/price receipt.
    key = json.dumps(
        [position_id, intent_id, quote.exchange_at_ms, quote.cross_sequence],
        separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    event_id = "fixture_assumedfill_" + sha256(key).hexdigest()[:30]
    if any(e.event_id == event_id for e in order.events):
        return result(PaperFillDecision.ALREADY_RECORDED)

    with localcontext(_EXACT_CONTEXT):
        spread_bps = ((quote.ask_price - quote.bid_price)
                      * BPS_DENOMINATOR / quote.mark_price)
        if spread_bps > policy.max_spread_bps:
            return result(PaperFillDecision.TOO_WIDE)
        depth = (quote.bid_size if intent.side is PaperOrderSide.SELL
                 else quote.ask_size)
        cap = depth * policy.max_top_level_participation_bps / BPS_DENOMINATOR
        quantity = min(cap, order.snapshot.unfilled_units)
        lot = view.synthetic_lot_step_units
        if quantity < lot:
            return result(PaperFillDecision.NO_LIQUIDITY)
        quantity -= quantity % lot
        if quantity <= 0:
            return result(PaperFillDecision.NO_LIQUIDITY)
        bbo = (quote.bid_price if intent.side is PaperOrderSide.SELL
               else quote.ask_price)
        event = PaperOrderEvent(
            event_id, PaperOrderEventKind.FILL,
            quote.received_at_ms, quantity,
            hypothetical_reference_price_quote=bbo,
        )
        receipt = PaperDeclaredFillReference(
            intent_id, event_id, quote.received_at_ms, bbo,
        )
        # AUTO4 uses BEGIN IMMEDIATE, checks cap and persists exact events.
        # In-flight conflicting writers fail its existing gates, never retry.
        saved = SQLitePaperPositionJournal(position_path).append_exit_events(
            position_id, intent_id, (event,), as_of_ms=cutoff,
        )
        updated = [o for o in saved.exit_orders if o.intent.intent_id == intent_id]
        if (len(updated) != 1
                or not any(e.event_id == event_id for e in updated[0].events)):
            raise DataValidationError("D394 hypothetical event not durably bound")
        remaining = updated[0].snapshot.unfilled_units
        return result(
            PaperFillDecision.ASSUMED_FULL if remaining == 0
            else PaperFillDecision.ASSUMED_PARTIAL,
            units=quantity, receipt=receipt, event=event,
            remaining=remaining,
        )
