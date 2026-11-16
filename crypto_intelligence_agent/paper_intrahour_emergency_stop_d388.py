"""D388 / #676: emergency mark-price protective stop reservation in PAPER.

The existing AUTO4 position journal owns quantity/idempotency. A stop crossing
creates a hypothetical full-balance REDUCE_ONLY intent (tranche_step=-1);
it is NOT a venue-native stop, does not send any order or assume a fill.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path

from .bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from .market_data import DataValidationError, DataGapError
from .paper_position_inspection import inspect_paper_position
from .paper_position_reservations import SQLitePaperPositionJournal
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide, PaperOrderStatus,
    PaperVenue,
)
from .synthetic_manual_exit_replay import _utc_ms
from .synthetic_position_state import SyntheticSide


@dataclass(frozen=True)
class PaperEmergencyStopRule:
    stop_mark_price: Decimal
    max_quote_age_ms: int = 3_000

    def __post_init__(self) -> None:
        price = self.stop_mark_price
        if (type(price) is not Decimal or not price.is_finite() or price <= 0
                or len(price.as_tuple().digits) > 40
                or price.as_tuple().exponent < -24):
            raise DataValidationError("PAPER stop requires positive bounded mark Decimal")
        if (type(self.max_quote_age_ms) is not int
                or not 100 <= self.max_quote_age_ms <= 30_000):
            raise DataValidationError("PAPER emergency stop quote age invalid")


class PaperEmergencyStopState(str, Enum):
    HOLD = "mark_stop_not_triggered_paper_only"
    RESERVED = "full_balance_stop_reserved_paper_only"
    PENDING = "protective_stop_pending_reconciliation_paper_only"
    CLOSED = "protective_stop_explicit_fill_confirmed_paper_only"
    MANUAL_RECONCILIATION = "protective_stop_terminal_review_required_paper_only"
    OLDER_ORDER_UNRESOLVED = "older_exit_unresolved_no_new_stop_paper_only"
    STALE = "stop_quote_stale_or_absent_paper_only"


@dataclass(frozen=True)
class PaperEmergencyStopResult:
    state: PaperEmergencyStopState
    created_intent_id: str | None
    reserved_units: Decimal
    confirmed_remaining_units: Decimal
    protective_filled_units: Decimal

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "paper-emergency-stop-d388-v1",
            "state": self.state.value,
            "reserved_units": str(self.reserved_units),
            "confirmed_remaining_units": str(self.confirmed_remaining_units),
            "protective_filled_units": str(self.protective_filled_units),
            "stop_type": "hypothetical_mark_trigger_only",
            "native_stop_verified": False,
            "real_fill_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def native_stop_verified(self) -> bool:
        return False


def step_paper_emergency_stop(
    position_path: str | Path,
    position_id: str,
    *,
    rule: PaperEmergencyStopRule,
    quote: BybitTickerQuote,
    as_of_ms: int,
) -> PaperEmergencyStopResult:
    """Prioritize a PAPER emergency exit over planned tranches, without fills.

    Caller must invoke this before the partial-target handler on each quote.
    UNKNOWN or pending older partials block a competing full-balance stop
    reservation: reconciliation is REQUIRED rather than double-reserving.
    """
    cutoff = _utc_ms(as_of_ms, "PAPER stop evaluation cutoff")
    if type(rule) is not PaperEmergencyStopRule:
        raise DataValidationError("PAPER typed emergency stop rule required")
    if type(quote) is not BybitTickerQuote or quote.source != SOURCE:
        raise DataValidationError("Bybit public ticker fixture required")
    b = inspect_paper_position(position_path, position_id).balance
    if (b.venue is not PaperVenue.BYBIT_V5 or quote.symbol != b.symbol
            or b.side not in (SyntheticSide.LONG, SyntheticSide.SHORT)):
        raise DataValidationError("PAPER stop venue, symbol or side mismatch")
    if (cutoff < b.as_of_ms or quote.received_at_ms < b.as_of_ms
            or quote.exchange_at_ms < b.opened_at_ms
            or quote.exchange_at_ms > cutoff):
        raise DataGapError("PAPER stop time must follow position checkpoint")

    def report(state: PaperEmergencyStopState,
               intent_id: str | None = None, balance=b) -> PaperEmergencyStopResult:
        return PaperEmergencyStopResult(
            state, intent_id, balance.protective_reserved_unfilled_units,
            balance.confirmed_remaining_units, balance.protective_filled_units,
        )

    if b.protective_stop_seen:
        old = tuple(x for x in b.exit_orders if x.tranche_step == -1)
        if len(old) != 1:
            raise DataValidationError("PAPER protective stop ledger corrupt")
        if old[0].snapshot.requires_reconciliation:
            return report(PaperEmergencyStopState.PENDING)
        if (old[0].snapshot.status is PaperOrderStatus.FILLED
                and b.confirmed_remaining_units == 0):
            return report(PaperEmergencyStopState.CLOSED)
        return report(PaperEmergencyStopState.MANUAL_RECONCILIATION)

    if (cutoff < quote.received_at_ms
            or cutoff - quote.received_at_ms > rule.max_quote_age_ms
            or quote.received_at_ms - quote.exchange_at_ms > 30_000
            or not quote.has_positive_book_depth
            or quote.bid_price <= 0 or quote.ask_price <= 0
            or quote.bid_price > quote.ask_price):
        return report(PaperEmergencyStopState.STALE)
    mark = quote.mark_price
    if type(mark) is not Decimal or not mark.is_finite() or mark <= 0:
        return report(PaperEmergencyStopState.STALE)
    crossed = (mark <= rule.stop_mark_price if b.side is SyntheticSide.LONG
               else mark >= rule.stop_mark_price)
    if not crossed:
        return report(PaperEmergencyStopState.HOLD)
    if (b.confirmed_remaining_units <= 0 or b.reserved_unfilled_units != 0
            or any(o.snapshot.requires_reconciliation for o in b.exit_orders)
            or any(o.tranche_step == 0 for o in b.exit_orders)):
        return report(PaperEmergencyStopState.OLDER_ORDER_UNRESOLVED)

    digest = sha256(json.dumps(
        {"position": b.position_id, "plan": b.plan_version,
         "mark_stop": str(rule.stop_mark_price)},
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii")).hexdigest()[:32]
    intent = PaperOrderIntent(
        intent_id="fixture_emergencystop_" + digest,
        fixture_signal_id="fixture_stopsignal_" + digest,
        venue=PaperVenue.BYBIT_V5, symbol=b.symbol,
        position_side=b.side,
        side=(PaperOrderSide.SELL if b.side is SyntheticSide.LONG
              else PaperOrderSide.BUY),
        effect=PaperOrderEffect.REDUCE_ONLY,
        requested_units=b.confirmed_remaining_units,
        max_reducible_units=b.confirmed_remaining_units,
        created_at_ms=quote.received_at_ms,
    )
    saved = SQLitePaperPositionJournal(position_path).reserve_exit(
        b.position_id, -1, intent, as_of_ms=cutoff,
    )
    matching = [
        x for x in saved.exit_orders
        if x.tranche_step == -1 and x.intent.intent_id == intent.intent_id
    ]
    if (len(matching) != 1
            or not saved.protective_stop_seen
            or saved.protective_reserved_unfilled_units
               != b.confirmed_remaining_units):
        raise DataValidationError("PAPER protective stop not durably reserved")
    return report(PaperEmergencyStopState.RESERVED, intent.intent_id, saved)
