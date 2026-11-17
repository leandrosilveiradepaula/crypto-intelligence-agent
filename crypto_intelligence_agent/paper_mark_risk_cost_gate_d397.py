"""D397: J3 mark-risk veto for a CLOSED, margin-receipted PAPER AUTO4 ledger.

Reuses D393 fill/cost audit and J3/PRE16 mark replay. Before displaying any
even CONDITIONAL synthetic result, this gate requires the opening AUTO2
receipt to match AUTO4, an explicit PIT maintenance-tier fixture and a
bounded, causal mark/trade observation path reaching the last stored fill.

A full-initial-notional mark proxy is intentionally conservative: it can
VETO a paper payoff; a clean discrete path does NOT certify survival,
margin equity, venue liquidation rules or live trading safety.

This module never creates a SQLite writer, reads the network, emits an
order, infers a fill from a mark, or authorizes real trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .market_data import DataValidationError, DataGapError
from .paper_closed_cost_audit_d393 import (
    PaperDeclaredFillReference, audit_closed_paper_costs,
)
from .paper_position_inspection import inspect_paper_position
from .synthetic_cost_scenarios import SyntheticFundingEvent
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_margin_envelope import SyntheticMarginBasis
from .synthetic_mark_replay import (
    SyntheticMarkReplayPlan, SyntheticMarkTick, SyntheticReplayState,
    replay_synthetic_mark_path,
)
from .synthetic_order_lifecycle import PaperOrderEventKind, PaperVenue
from .synthetic_partial_costed_replay import SyntheticPartialCostRates
from .synthetic_position_state import SyntheticSide
from .synthetic_risk_tiers import SyntheticRiskSnapshot


@dataclass(frozen=True)
class PaperMarkRiskCostResult:
    status: str
    initial_leverage_at_intent: int | None
    confirmed_remaining_units: Decimal
    mark_ticks_checked: int
    first_discrete_terminal_at_ms: int | None
    possible_liquidation_detected: bool
    conditional_net_after_risk_veto_quote: Decimal | None

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "paper-mark-risk-cost-gate-d397-v1",
            "status": self.status,
            "leverage_at_open_intent": self.initial_leverage_at_intent,
            "confirmed_remaining_units": str(self.confirmed_remaining_units),
            "mark_ticks_checked": self.mark_ticks_checked,
            "has_prior_discrete_terminal": self.first_discrete_terminal_at_ms is not None,
            "possible_liquidation_detected": self.possible_liquidation_detected,
            "conditional_net_after_risk_veto_quote": (
                None if self.conditional_net_after_risk_veto_quote is None
                else str(self.conditional_net_after_risk_veto_quote)
            ),
            "full_initial_notional_stress_proxy_only": True,
            "partial_derisking_in_mark_path_modeled": False,
            "risk_tiers_are_synthetic_fixtures": True,
            "intrabar_trajectory_verified": False,
            "venue_leverage_verified": False,
            "margin_collateral_verified": False,
            "liquidation_formula_verified": False,
            "venue_fills_verified": False,
            "net_pnl_verified": False,
            "out_of_sample_returns_validated": False,
            "orders_sent": False,
            "order_submission_enabled": False,
            "approved_for_live_use": False,
        }


def audit_paper_costs_with_prior_mark_risk(
    position_path: str | Path,
    position_id: str,
    *,
    opening_order_path: str | Path | None,
    entry_reference_price_quote: Decimal,
    fill_references: tuple[PaperDeclaredFillReference, ...],
    cost_rates: SyntheticPartialCostRates,
    mark_plan: SyntheticMarkReplayPlan,
    mark_ticks: tuple[SyntheticMarkTick, ...],
    max_tick_gap_ms: int,
    risk_snapshots: tuple[SyntheticRiskSnapshot, ...] | None = None,
    max_risk_snapshot_age_ms: int | None = None,
    funding_events: tuple[SyntheticFundingEvent, ...] = (),
) -> PaperMarkRiskCostResult:
    """Only expose a conditional PAPER net when the J3 discrete path is clean.

    All missing evidence ABSTAINS; contradictions among SUPPLIED evidence
    raise DataValidationError. This is not a venue liquidation decision.
    """
    if (type(mark_plan) is not SyntheticMarkReplayPlan
            or type(cost_rates) is not SyntheticPartialCostRates
            or type(fill_references) is not tuple
            or any(type(x) is not PaperDeclaredFillReference for x in fill_references)
            or type(mark_ticks) is not tuple
            or any(type(t) is not SyntheticMarkTick for t in mark_ticks)
            or type(max_tick_gap_ms) is not int
            or not 1 <= max_tick_gap_ms <= 86_400_000
            or type(funding_events) is not tuple
            or any(type(e) is not SyntheticFundingEvent for e in funding_events)):
        raise DataValidationError("D397 bounded typed PAPER risk inputs required")

    # No optional re-use of a writer constructor: AUTO2 and AUTO4 are sampled
    # solely via the existing mode=ro, digest-checked inspection routines.
    if opening_order_path is None:
        inspected = inspect_paper_position(position_path, position_id)
        return PaperMarkRiskCostResult(
            "abstain_open_journal_crosscheck_required",
            inspected.balance.leverage_at_intent,
            inspected.balance.confirmed_remaining_units, 0, None, False, None,
        )
    inspected = inspect_paper_position(
        position_path, position_id, opening_order_path=opening_order_path,
    )
    b = inspected.balance
    if b.venue is not PaperVenue.BYBIT_V5:
        raise DataValidationError("D397 only supports synthetic Bybit linear PAPER")
    if b.opening_margin_intent is None:
        return PaperMarkRiskCostResult(
            "abstain_immutable_open_margin_receipt_missing",
            None, b.confirmed_remaining_units, 0, None, False, None,
        )
    receipt = b.opening_margin_intent
    if (b.confirmed_remaining_units != 0
            or b.reserved_unfilled_units != 0
            or b.filled_exit_units != b.initial_confirmed_units):
        return PaperMarkRiskCostResult(
            "abstain_position_open_or_pending_reconciliation",
            b.leverage_at_intent, b.confirmed_remaining_units,
            0, None, False, None,
        )
    if risk_snapshots is None or not risk_snapshots:
        return PaperMarkRiskCostResult(
            "abstain_pit_maintenance_tiers_missing",
            b.leverage_at_intent, b.confirmed_remaining_units,
            0, None, False, None,
        )
    if (type(risk_snapshots) is not tuple
            or any(type(x) is not SyntheticRiskSnapshot for x in risk_snapshots)
            or type(max_risk_snapshot_age_ms) is not int
            or not 0 <= max_risk_snapshot_age_ms <= 86_400_000 * 31):
        raise DataValidationError("D397 requires bounded typed PIT risk snapshots")
    if not mark_ticks:
        return PaperMarkRiskCostResult(
            "abstain_mark_path_missing",
            b.leverage_at_intent, b.confirmed_remaining_units,
            0, None, False, None,
        )
    if (not 1 <= len(mark_ticks) <= 2048
            or len(fill_references) > 128
            or len(funding_events) > 64):
        raise DataValidationError("D397 research path/resource budget exceeded")

    plan = mark_plan
    direction = (
        ResearchDirection.LONG if b.side is SyntheticSide.LONG
        else ResearchDirection.SHORT
    )
    if (plan.direction is not direction
            or plan.entry_at_ms != b.opened_at_ms
            or plan.entry_price != entry_reference_price_quote
            or plan.entry_price != receipt.hypothetical_mark_quote
            or plan.quantity_base != b.initial_confirmed_units
            or plan.margin.quote_currency != "SYNTHETIC_" + receipt.quote_currency
            or plan.margin.requested_margin_quote != receipt.requested_margin_quote
            or plan.margin.leverage_at_intent != receipt.leverage_at_intent
            or plan.margin.entry_notional_quote != receipt.assumed_notional_quote
            or plan.entry_fee_bps != cost_rates.entry_fee_bps
            or plan.exit_fee_bps != cost_rates.exit_fee_bps
            or plan.entry_slippage_bps != cost_rates.entry_adverse_slippage_bps
            or plan.exit_slippage_bps != cost_rates.exit_adverse_slippage_bps):
        raise DataValidationError(
            "D397 mark risk assumptions disagree with immutable PAPER OPEN terms"
        )

    # The exact AUTO4 fill timeline and receipt bijection are audited by D393.
    # Do not infer a fill from any mark/trade point, regardless of profit.
    cost = audit_closed_paper_costs(
        position_path, position_id,
        entry_reference_price_quote=entry_reference_price_quote,
        fill_references=fill_references,
        cost_rates=cost_rates,
        funding_events=funding_events,
    )
    if cost.conditional_net_after_supplied_costs_quote is None:
        return PaperMarkRiskCostResult(
            "abstain_position_open_or_pending_reconciliation",
            b.leverage_at_intent, b.confirmed_remaining_units,
            0, None, False, None,
        )

    fills = [
        event for order in b.exit_orders for event in order.events
        if event.kind is PaperOrderEventKind.FILL
    ]
    times = [e.event_at_ms for e in fills]
    if (not fills or len(times) != len(set(times))):
        raise DataValidationError("D397 ambiguous PAPER fill chronology")
    if mark_ticks[-1].at_ms != max(times):
        raise DataValidationError("D397 mark replay must end at last PAPER fill")
    indexed = {tick.at_ms: tick for tick in mark_ticks}
    if len(indexed) != len(mark_ticks):
        raise DataValidationError("D397 duplicate mark tick timestamps")
    for ref in fill_references:
        tick = indexed.get(ref.event_at_ms)
        if tick is None or tick.trade_price != ref.reference_exit_price_quote:
            raise DataValidationError(
                "D397 every PAPER FILL must match a supplied observed trade tick"
            )

    replay = replay_synthetic_mark_path(
        plan, mark_ticks, funding_events,
        as_of_ms=b.as_of_ms,
        risk_snapshots=risk_snapshots,
        max_tick_gap_ms=max_tick_gap_ms,
        max_risk_snapshot_age_ms=max_risk_snapshot_age_ms,
    )

    # Detect concurrent checkpoint drift across the two separate read-only
    # queries. This is NOT an atomic transaction over AUTO2 and AUTO4.
    reread = inspect_paper_position(
        position_path, position_id, opening_order_path=opening_order_path,
    )
    if reread.balance != b:
        raise DataGapError("D397 PAPER position mutated between audit samples")

    if replay.state is SyntheticReplayState.LIQUIDATION_CONDITION:
        label = "abstain_prior_mark_liquidation_proxy"
    elif replay.state is SyntheticReplayState.CONDITIONAL_STOP:
        label = "abstain_prior_conditional_stop"
    elif replay.state is SyntheticReplayState.CONDITIONAL_TARGET:
        label = "abstain_prior_conditional_target"
    else:
        label = "conditional_closed_reference_after_discrete_mark_risk_gate"

    return PaperMarkRiskCostResult(
        label, b.leverage_at_intent, b.confirmed_remaining_units,
        len(replay.observations), replay.first_trigger_at_ms,
        replay.state is SyntheticReplayState.LIQUIDATION_CONDITION,
        (cost.conditional_net_after_supplied_costs_quote
         if replay.state is SyntheticReplayState.OPEN_UNRESOLVED else None),
    )
