"""J4: terminal runner close with exact, declared SYNTHETIC fill references.

Compose the existing J4 partial replay and J3 fees. No OHLC-derived fills,
PAPER ledger mutations, venue orders, real funding, or liquidation proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .market_data import DataValidationError
from .synthetic_cost_scenarios import (
    BPS_DENOMINATOR, SyntheticCostScenario, SyntheticFundingEvent,
    _amount, evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import (
    MAX_FIXTURE_EVENTS, _EVENT_ID, _EXACT_CONTEXT, _fixture_units, _utc_ms,
)
from .synthetic_partial_costed_replay import (
    SyntheticPartialCostRates, SyntheticPartialMarkFill,
    evaluate_synthetic_partial_costed_replay,
)
from .synthetic_position_state import (
    SyntheticPosition, SyntheticSide, _fixture_id,
)

_ZERO = Decimal(0)


@dataclass(frozen=True)
class SyntheticRunnerCloseMarkFill:
    """One fake terminal receipt; not a mark inferred from a price trigger."""

    fixture_position_id: str
    event_id: str
    filled_units: Decimal
    reference_exit_price_quote: Decimal
    event_at_ms: int

    def __post_init__(self) -> None:
        _fixture_id(self.fixture_position_id)
        if type(self.event_id) is not str or _EVENT_ID.fullmatch(self.event_id) is None:
            raise DataValidationError("runner closure requires bounded synthetic fill ID")
        _fixture_units(self.filled_units)
        _amount(self.reference_exit_price_quote, "synthetic runner close reference price")
        _utc_ms(self.event_at_ms, "runner event_at_ms")


@dataclass(frozen=True)
class SyntheticRunnerCostedClosure:
    """No assertion of execution, solvency, liquidation or real money PnL."""

    fixture_position_id: str
    side: SyntheticSide
    leverage_at_open: int
    initial_units: Decimal
    partial_filled_units: Decimal
    runner_closed_units: Decimal
    final_remaining_units: Decimal
    partial_realized_gross_reference_quote: Decimal
    runner_gross_reference_quote: Decimal
    total_gross_reference_quote: Decimal
    entry_fee_slippage_quote: Decimal
    partial_exit_fee_slippage_quote: Decimal
    runner_exit_fee_slippage_quote: Decimal
    signed_funding_cost_quote: Decimal
    hypothetical_net_closed_reference_quote: Decimal
    unique_partial_fill_count: int
    exact_duplicate_partial_fill_count: int
    exact_duplicate_runner_receipt_count: int
    unique_funding_count: int
    exact_duplicate_funding_count: int
    runner_closed_at_ms: int
    as_of_ms: int

    @property
    def quality(self) -> str:
        return "synthetic_runner_terminal_close_reference_only"

    @property
    def realized_pnl_verified(self) -> bool:
        return False

    @property
    def liquidation_risk_verified(self) -> bool:
        return False

    @property
    def venue_fees_verified(self) -> bool:
        return False

    @property
    def funding_settlement_verified(self) -> bool:
        return False

    @property
    def venue_fill_verified(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    def sanitized_report(self) -> dict[str, object]:
        return {
            "status": self.quality,
            "leverage_at_open": self.leverage_at_open,
            "initial_units": str(self.initial_units),
            "partial_filled_units": str(self.partial_filled_units),
            "runner_closed_units": str(self.runner_closed_units),
            "final_remaining_units": str(self.final_remaining_units),
            "partial_realized_gross_reference_quote": str(
                self.partial_realized_gross_reference_quote
            ),
            "runner_gross_reference_quote": str(self.runner_gross_reference_quote),
            "total_gross_reference_quote": str(self.total_gross_reference_quote),
            "entry_fee_slippage_quote": str(self.entry_fee_slippage_quote),
            "partial_exit_fee_slippage_quote": str(self.partial_exit_fee_slippage_quote),
            "runner_exit_fee_slippage_quote": str(self.runner_exit_fee_slippage_quote),
            "signed_funding_cost_quote": str(self.signed_funding_cost_quote),
            "hypothetical_net_closed_reference_quote": str(
                self.hypothetical_net_closed_reference_quote
            ),
            "unique_partial_fill_count": self.unique_partial_fill_count,
            "exact_duplicate_partial_fill_count": self.exact_duplicate_partial_fill_count,
            "unique_runner_receipt_count": 1,
            "exact_duplicate_runner_receipt_count": self.exact_duplicate_runner_receipt_count,
            "unique_funding_count": self.unique_funding_count,
            "exact_duplicate_funding_count": self.exact_duplicate_funding_count,
            "realized_pnl_verified": False,
            "liquidation_risk_verified": False,
            "venue_fees_verified": False,
            "funding_settlement_verified": False,
            "venue_fill_verified": False,
            "persistent_idempotency_verified": False,
            "financial_backtest_approved": False,
            "approved_for_live_use": False,
            "orders_sent": False,
        }


def evaluate_synthetic_runner_costed_closure(
    position: SyntheticPosition,
    partial_fills: tuple[SyntheticPartialMarkFill, ...],
    runner_receipts: tuple[SyntheticRunnerCloseMarkFill, ...],
    *,
    entry_reference_price_quote: Decimal,
    cost_rates: SyntheticPartialCostRates,
    as_of_ms: int,
    funding_events: tuple[SyntheticFundingEvent, ...] = (),
) -> SyntheticRunnerCostedClosure:
    """Close exactly the *declared* runner, with no additional opening cost.

    Replaying the same receipt ID and identical Decimal representation is
    idempotent only within this immutable call. All other receipts fail closed.
    A trailing mark or pending reduce-only intent is NOT an executed fill.
    """
    if (type(position) is not SyntheticPosition
            or type(cost_rates) is not SyntheticPartialCostRates
            or type(partial_fills) is not tuple
            or type(runner_receipts) is not tuple
            or not 1 <= len(runner_receipts) <= MAX_FIXTURE_EVENTS
            or any(type(x) is not SyntheticRunnerCloseMarkFill for x in runner_receipts)):
        raise DataValidationError("typed, bounded synthetic runner closure inputs required")

    cutoff = _utc_ms(as_of_ms, "as_of_ms")
    close = runner_receipts[0]
    if (close.fixture_position_id != position.fixture_position_id
            or not position.opened_at_ms < close.event_at_ms <= cutoff):
        raise DataValidationError("runner receipt position or UTC chronology invalid")
    for row in runner_receipts[1:]:
        if (row.fixture_position_id != close.fixture_position_id
                or row.event_id != close.event_id
                or row.event_at_ms != close.event_at_ms
                or row.filled_units.as_tuple() != close.filled_units.as_tuple()
                or row.reference_exit_price_quote.as_tuple()
                   != close.reference_exit_price_quote.as_tuple()):
            raise DataValidationError("runner receipt ID collision or duplicate closure")

    # Both the runner and funding must be strictly after the partial events;
    # simultaneous fills/funding have no provable order in this model.
    if type(partial_fills) is not tuple or any(
        type(row) is not SyntheticPartialMarkFill for row in partial_fills
    ):
        raise DataValidationError("typed partial fill evidence required")
    for marked in partial_fills:
        event = marked.bound_fill.event
        if event.event_id == close.event_id or event.event_at_ms >= close.event_at_ms:
            raise DataValidationError("runner closure collided with a partial fill")
    if type(funding_events) is not tuple or any(
        type(event) is not SyntheticFundingEvent for event in funding_events
    ):
        raise DataValidationError("typed funding evidence required")
    if any(event.event_at_ms >= close.event_at_ms for event in funding_events):
        raise DataValidationError("funding at or after the runner close is ambiguous")

    # Evaluate the last reference mark at the explicitly declared runner fill
    # time, not at the possibly later as_of clock. Funding and partials are
    # validated by the existing J4/PRE4 replay, not duplicated here.
    base = evaluate_synthetic_partial_costed_replay(
        position, partial_fills,
        entry_reference_price_quote=entry_reference_price_quote,
        last_reference_mark_quote=close.reference_exit_price_quote,
        mark_observed_at_ms=close.event_at_ms,
        max_mark_age_ms=0,
        as_of_ms=close.event_at_ms,
        cost_rates=cost_rates,
        funding_events=funding_events,
    )
    if (base.runner_floor_units <= 0
            or base.residual_units != base.runner_floor_units
            or close.filled_units != base.residual_units
            or base.initial_units != base.filled_units + close.filled_units):
        raise DataValidationError("runner close requires completely filled tranches and exact residual")

    direction = (ResearchDirection.LONG if position.side is SyntheticSide.LONG
                 else ResearchDirection.SHORT)
    with localcontext(_EXACT_CONTEXT):
        entry_notional = entry_reference_price_quote * close.filled_units
        exit_notional = close.reference_exit_price_quote * close.filled_units
        breakdown = evaluate_synthetic_costs(SyntheticCostScenario(
            direction=direction,
            entry_at_ms=position.opened_at_ms,
            exit_at_ms=close.event_at_ms,
            entry_hypothetical_notional_quote_units=entry_notional,
            exit_hypothetical_notional_quote_units=exit_notional,
            entry_fee_bps=cost_rates.entry_fee_bps,
            exit_fee_bps=cost_rates.exit_fee_bps,
            entry_adverse_slippage_bps=cost_rates.entry_adverse_slippage_bps,
            exit_adverse_slippage_bps=cost_rates.exit_adverse_slippage_bps,
        ))
        # Reuse J3's exit costs. J4/PRE4 already charged the ENTIRE entry
        # once; importing breakdown.entry_* here would double charge.
        runner_exit_cost = (
            breakdown.exit_fee_units + breakdown.exit_slippage_cost_units
        )
        gross = (base.realized_gross_reference_quote
                 + base.residual_mark_gross_reference_quote)
        net = (
            gross - base.entry_fee_slippage_quote
            - base.exit_fee_slippage_quote - runner_exit_cost
            - base.signed_funding_cost_quote
        )
        if net != base.hypothetical_net_mark_reference_quote - runner_exit_cost:
            raise DataValidationError("synthetic runner cost conservation failed")
        return SyntheticRunnerCostedClosure(
            fixture_position_id=position.fixture_position_id,
            side=position.side,
            leverage_at_open=base.leverage_at_open,
            initial_units=base.initial_units,
            partial_filled_units=base.filled_units,
            runner_closed_units=close.filled_units,
            final_remaining_units=_ZERO,
            partial_realized_gross_reference_quote=base.realized_gross_reference_quote,
            runner_gross_reference_quote=base.residual_mark_gross_reference_quote,
            total_gross_reference_quote=gross,
            entry_fee_slippage_quote=base.entry_fee_slippage_quote,
            partial_exit_fee_slippage_quote=base.exit_fee_slippage_quote,
            runner_exit_fee_slippage_quote=runner_exit_cost,
            signed_funding_cost_quote=base.signed_funding_cost_quote,
            hypothetical_net_closed_reference_quote=net,
            unique_partial_fill_count=base.unique_fill_count,
            exact_duplicate_partial_fill_count=base.exact_duplicate_fill_count,
            exact_duplicate_runner_receipt_count=len(runner_receipts) - 1,
            unique_funding_count=base.unique_funding_count,
            exact_duplicate_funding_count=base.exact_duplicate_funding_count,
            runner_closed_at_ms=close.event_at_ms,
            as_of_ms=cutoff,
        )
