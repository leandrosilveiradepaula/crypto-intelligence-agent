"""D387 / #676: automatic PAPER target-triggered partial exit reservation.

A valid intrahour Bybit public ticker quote can reserve an existing J4/AUTO4
REDUCE_ONLY fixture intent. This has no exchange sender and never fabricates
order ACK, execution, realized PnL, native stops or margin safety.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
from hashlib import sha256
import json
import re
from pathlib import Path

from .bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from .market_data import DataGapError, DataValidationError
from .paper_position_inspection import inspect_paper_position
from .paper_position_reservations import SQLitePaperPositionJournal
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from .synthetic_position_state import SyntheticSide

_VERSION = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")
_MAX_BPS = Decimal("10000")


@dataclass(frozen=True)
class PaperIntrahourTargetPolicy:
    plan_version: str
    prices: tuple[Decimal, ...]
    max_quote_age_ms: int = 3_000
    max_spread_bps: Decimal = Decimal("30")

    def __post_init__(self) -> None:
        if type(self.plan_version) is not str or _VERSION.fullmatch(self.plan_version) is None:
            raise DataValidationError("PAPER target policy version invalid")
        if (type(self.prices) is not tuple or
                not 1 <= len(self.prices) <= 64):
            raise DataValidationError("PAPER target levels count invalid")
        for price in self.prices:
            if (type(price) is not Decimal or not price.is_finite() or price <= 0
                    or len(price.as_tuple().digits) > 40
                    or price.as_tuple().exponent < -24):
                raise DataValidationError("PAPER target price must be bounded positive Decimal")
        if (type(self.max_quote_age_ms) is not int or
                not 100 <= self.max_quote_age_ms <= 30_000):
            raise DataValidationError("PAPER quote age budget invalid")
        if (type(self.max_spread_bps) is not Decimal
                or not self.max_spread_bps.is_finite()
                or not 0 <= self.max_spread_bps < _MAX_BPS):
            raise DataValidationError("PAPER spread cap must be finite Decimal bps")


class PaperAutoTargetState(str, Enum):
    HOLD = "no_target_trigger_paper_only"
    RESERVED = "reduce_only_intent_reserved_paper_only"
    PENDING = "existing_order_pending_reconciliation_paper_only"
    MANUAL_RECONCILIATION = "terminal_order_needs_review_paper_only"
    STALE = "stale_or_unusable_quote_abstained_paper_only"
    SPREAD = "spread_guard_abstained_paper_only"
    DONE = "planned_tranches_completed_paper_only"
    RUNNER = "runner_already_under_separate_management_paper_only"


@dataclass(frozen=True)
class PaperAutoTargetStep:
    state: PaperAutoTargetState
    tranche_step: int | None
    intent_id: str | None
    reserved_units: Decimal
    remaining_units: Decimal
    leverage_at_intent: int | None

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def native_stop_verified(self) -> bool:
        return False

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "paper-intrahour-auto-target-d387-v1",
            "state": self.state.value,
            "tranche_step": self.tranche_step,
            "reserved_units": str(self.reserved_units),
            "remaining_units": str(self.remaining_units),
            "leverage_at_intent": self.leverage_at_intent,
            "margin_accepted_by_venue": False,
            "native_stop_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
            "real_fill_verified": False,
            "net_pnl_verified": False,
        }


def _levels_valid(prices: tuple[Decimal, ...], side: SyntheticSide) -> bool:
    ordered = zip(prices, prices[1:])
    if side is SyntheticSide.LONG:
        return all(a < b for a, b in ordered)
    if side is SyntheticSide.SHORT:
        return all(a > b for a, b in ordered)
    return False


def _stable_id(position_id: str, plan_version: str, step: int, target: Decimal) -> str:
    encoded = json.dumps(
        {"position_id": position_id, "plan_version": plan_version,
         "step": step, "target": str(target)},
        separators=(",", ":"), sort_keys=True,
    ).encode("ascii")
    return sha256(encoded).hexdigest()[:32]


def step_paper_intrahour_target(
    position_path: str | Path,
    position_id: str,
    *,
    policy: PaperIntrahourTargetPolicy,
    quote: BybitTickerQuote,
    as_of_ms: int,
) -> PaperAutoTargetStep:
    """PAPER event -> at most ONE durable partial reduce-only reservation.

    Calls the existing AUTO4 position journal transaction. Price touches are
    hypothetical barriers, NOT confirmed fills. A prior UNKNOWN/ACK/partial
    fill is never retried; cancellation/rejection requires human or separately
    validated reconciliation. Actual stop/runner exits remain separate.
    """
    cutoff = _utc_ms(as_of_ms, "PAPER target cutoff")
    if type(policy) is not PaperIntrahourTargetPolicy:
        raise DataValidationError("explicit PAPER target policy required")
    if type(quote) is not BybitTickerQuote or quote.source != SOURCE:
        raise DataValidationError("Bybit typed public quote required in PAPER")
    before = inspect_paper_position(position_path, position_id)
    b = before.balance
    if (b.venue is not PaperVenue.BYBIT_V5 or quote.symbol != b.symbol
            or policy.plan_version != b.plan_version
            or len(policy.prices) != len(b.tranches)
            or not _levels_valid(policy.prices, b.side)):
        raise DataValidationError("PAPER target plan/venue/position mismatch")
    if (cutoff < b.as_of_ms or quote.received_at_ms < b.as_of_ms
            or quote.exchange_at_ms < b.opened_at_ms
            or quote.exchange_at_ms > quote.received_at_ms + 5_000
            or quote.exchange_at_ms > cutoff):
        raise DataGapError("PAPER target noncausal position/quote time")

    def outcome(state: PaperAutoTargetState, step: int | None = None,
                intent_id: str | None = None, balance=b) -> PaperAutoTargetStep:
        return PaperAutoTargetStep(
            state, step, intent_id, balance.reserved_unfilled_units,
            balance.confirmed_remaining_units, balance.leverage_at_intent,
        )

    # Pending reconciliations are checked BEFORE evaluating the next price.
    if any(x.tranche_step == 0 for x in b.exit_orders):
        return outcome(PaperAutoTargetState.RUNNER, 0)
    for order in b.exit_orders:
        if order.snapshot.requires_reconciliation:
            return outcome(PaperAutoTargetState.PENDING, order.tranche_step)
        if order.snapshot.status.value in ("CANCELLED", "REJECTED"):
            return outcome(PaperAutoTargetState.MANUAL_RECONCILIATION, order.tranche_step)

    if cutoff < quote.received_at_ms or cutoff - quote.received_at_ms > policy.max_quote_age_ms:
        return outcome(PaperAutoTargetState.STALE)
    if (not quote.has_positive_book_depth or
            quote.bid_price > quote.ask_price or
            quote.mark_price <= 0 or quote.bid_price <= 0 or quote.ask_price <= 0):
        return outcome(PaperAutoTargetState.STALE)
    with localcontext(_EXACT_CONTEXT):
        spread_bps = (quote.ask_price - quote.bid_price) * _MAX_BPS / quote.mark_price
    if spread_bps > policy.max_spread_bps:
        return outcome(PaperAutoTargetState.SPREAD)
    # Use BBO on the *exit side*, never Last/Mark as a guaranteed fill.
    observed_exit_price = (quote.bid_price if b.side is SyntheticSide.LONG
                           else quote.ask_price)
    for step, (target, tranche) in enumerate(zip(policy.prices, b.tranches), start=1):
        if tranche.filled_units == tranche.target_units:
            continue
        if tranche.reserved_unfilled_units:
            return outcome(PaperAutoTargetState.PENDING, step)
        if tranche.filled_units != 0 or tranche.unallocated_units != tranche.target_units:
            # An earlier partial/cancelled state cannot silently be retried.
            return outcome(PaperAutoTargetState.MANUAL_RECONCILIATION, step)
        crossed = (observed_exit_price >= target if b.side is SyntheticSide.LONG
                   else observed_exit_price <= target)
        if not crossed:
            return outcome(PaperAutoTargetState.HOLD, step)
        digest = _stable_id(b.position_id, b.plan_version, step, target)
        intent = PaperOrderIntent(
            intent_id="fixture_autotarget_" + digest,
            fixture_signal_id="fixture_targetsignal_" + digest,
            venue=PaperVenue.BYBIT_V5, symbol=b.symbol,
            position_side=b.side,
            side=(PaperOrderSide.SELL if b.side is SyntheticSide.LONG
                  else PaperOrderSide.BUY),
            effect=PaperOrderEffect.REDUCE_ONLY,
            requested_units=tranche.unallocated_units,
            max_reducible_units=b.confirmed_remaining_units,
            created_at_ms=quote.received_at_ms,
        )
        # BEGIN IMMEDIATE inside AUTO4 rechecks all totals and reservations.
        reserved = SQLitePaperPositionJournal(position_path).reserve_exit(
            b.position_id, step, intent, as_of_ms=cutoff,
        )
        candidates = [
            x for x in reserved.exit_orders
            if x.tranche_step == step and x.intent.intent_id == intent.intent_id
        ]
        if (len(candidates) != 1 or
                candidates[0].reserved_unfilled_units != tranche.unallocated_units):
            raise DataValidationError("PAPER automatic target reservation not reproducible")
        return outcome(PaperAutoTargetState.RESERVED, step, intent.intent_id, reserved)
    return outcome(PaperAutoTargetState.DONE)
