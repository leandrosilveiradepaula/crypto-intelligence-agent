"""D398: exposure-aware discrete mark stress AFTER recorded PAPER partial fills.

D397's conservative *full opening notional* veto is always run FIRST.
D398 may refine a D397 full-notional liquidation proxy only after matching
realized PAPER FILL events, margin receipt, PIT risk tiers, mark/trade ticks,
and all hypothetical costs. No inferred fills, cross-file writer, new
financial engine, venue margin guarantee, or live orders.

At each observed tick: mark-to-market and maintenance are tested BEFORE
any same-timestamp fill; only then is that fill allowed to reduce exposure
for subsequent ticks. Realized synthetic proceeds are NOT treated as
fresh margin injections. Entry fees are charged once on the initial notional;
exit costs and funding use the existing J3/PRE2 calculator.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path

from .market_data import DataGapError, DataValidationError
from .paper_closed_cost_audit_d393 import (
    PaperDeclaredFillReference, audit_closed_paper_costs,
)
from .paper_mark_risk_cost_gate_d397 import (
    audit_paper_costs_with_prior_mark_risk,
)
from .paper_position_inspection import inspect_paper_position
from .synthetic_cost_scenarios import (
    SyntheticCostScenario, SyntheticFundingEvent, evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import _EXACT_CONTEXT
from .synthetic_mark_replay import SyntheticMarkReplayPlan, SyntheticMarkTick
from .synthetic_order_lifecycle import PaperOrderEventKind
from .synthetic_partial_costed_replay import SyntheticPartialCostRates
from .synthetic_risk_tiers import SyntheticRiskSnapshot, maintenance_for_mark

ZERO = Decimal(0)


@dataclass(frozen=True)
class PaperPartialDeriskRiskResult:
    status: str
    leverage_at_open_intent: int | None
    mark_ticks_checked: int
    confirmed_paper_fills_applied: int
    full_notional_proxy_vetoed: bool
    first_discrete_terminal_at_ms: int | None
    conditional_net_after_partial_risk_quote: Decimal | None

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "paper-partial-derisk-risk-d398-v1",
            "status": self.status,
            "leverage_at_open_intent": self.leverage_at_open_intent,
            "mark_ticks_checked": self.mark_ticks_checked,
            "confirmed_paper_fills_applied": self.confirmed_paper_fills_applied,
            "full_notional_proxy_vetoed": self.full_notional_proxy_vetoed,
            "has_discrete_terminal": self.first_discrete_terminal_at_ms is not None,
            "conditional_net_after_partial_risk_quote": (
                None if self.conditional_net_after_partial_risk_quote is None
                else str(self.conditional_net_after_partial_risk_quote)
            ),
            "partial_derisking_applies_after_explicit_fill_only": True,
            "liquidation_checked_before_same_tick_fill": True,
            "no_unobserved_intrabar_ticks_assumed": True,
            "margin_added_from_fills": False,
            "funding_calendar_complete": False,
            "risk_tiers_authenticated_by_venue": False,
            "venue_leverage_verified": False,
            "venue_liquidation_verified": False,
            "liquidation_formula_verified": False,
            "net_pnl_verified": False,
            "orders_sent": False,
            "order_submission_enabled": False,
            "approved_for_live_use": False,
        }


def audit_paper_partial_derisk_mark_risk(
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
) -> PaperPartialDeriskRiskResult:
    """Conservative, offline, *post-fill* de-risking; no safety certification.

    This function requires D397's full validation to complete before any
    synthetic equity estimate is reported. A terminal STOP or TARGET in D397
    remains a veto, regardless of quantity releases. Only its *liquidation*
    proxy may be refined by the explicitly recorded partial-fill timeline.
    """
    legacy = audit_paper_costs_with_prior_mark_risk(
        position_path, position_id,
        opening_order_path=opening_order_path,
        entry_reference_price_quote=entry_reference_price_quote,
        fill_references=fill_references,
        cost_rates=cost_rates,
        mark_plan=mark_plan,
        mark_ticks=mark_ticks,
        max_tick_gap_ms=max_tick_gap_ms,
        risk_snapshots=risk_snapshots,
        max_risk_snapshot_age_ms=max_risk_snapshot_age_ms,
        funding_events=funding_events,
    )
    def out(
        status: str, checked: int = 0, fills: int = 0,
        terminal: int | None = None, net: Decimal | None = None,
    ) -> PaperPartialDeriskRiskResult:
        return PaperPartialDeriskRiskResult(
            status, legacy.initial_leverage_at_intent, checked, fills,
            legacy.possible_liquidation_detected,
            terminal, net,
        )
    if legacy.status not in (
        "conditional_closed_reference_after_discrete_mark_risk_gate",
        "abstain_prior_mark_liquidation_proxy",
    ):
        return out(legacy.status)
    if risk_snapshots is None or max_risk_snapshot_age_ms is None:
        # D397 must have required both; this guard prevents accidental
        # relaxed calling semantics after future changes.
        raise DataValidationError("D398 requires exact PIT risk snapshots")

    inspected = inspect_paper_position(
        position_path, position_id, opening_order_path=opening_order_path,
    )
    b = inspected.balance
    recorded = {
        (order.intent.intent_id, event.event_id): event
        for order in b.exit_orders
        for event in order.events if event.kind is PaperOrderEventKind.FILL
    }
    ordered = sorted(fill_references, key=lambda x: x.event_at_ms)
    if len(recorded) != len(ordered) or any(
        (r.intent_id, r.event_id) not in recorded for r in ordered
    ):
        raise DataValidationError("D398 recorded fills and receipts disagree")
    if not ordered or not mark_ticks:
        raise DataValidationError("D398 missing closed PAPER fill/tick trajectory")
    for e in ordered:
        recorded_event = recorded[(e.intent_id, e.event_id)]
        if recorded_event.event_at_ms != e.event_at_ms:
            raise DataValidationError("D398 conflicting recorded fill chronology")

    # D397/D393 have already validated exactly one matching trade tick per
    # FILL, chrono, gap/freshness, typed leverage and cost assumptions, tier
    # identity, and no cross-journal write. Reuse that evidence intact.
    audited = audit_closed_paper_costs(
        position_path, position_id,
        entry_reference_price_quote=entry_reference_price_quote,
        fill_references=fill_references,
        cost_rates=cost_rates,
        funding_events=funding_events,
    )
    expected = audited.conditional_net_after_supplied_costs_quote
    if expected is None:
        return out("abstain_closed_costs_unavailable")

    # The PRE2 calculator is the sole source of hypothetical fees,
    # slippage and signed funding. Do not charge new entry fees per partial.
    entry_costs = evaluate_synthetic_costs(SyntheticCostScenario(
        direction=mark_plan.direction,
        entry_at_ms=mark_plan.entry_at_ms,
        exit_at_ms=mark_ticks[-1].at_ms,
        entry_hypothetical_notional_quote_units=mark_plan.margin.entry_notional_quote,
        exit_hypothetical_notional_quote_units=mark_plan.margin.entry_notional_quote,
        entry_fee_bps=cost_rates.entry_fee_bps,
        exit_fee_bps=ZERO,
        entry_adverse_slippage_bps=cost_rates.entry_adverse_slippage_bps,
        exit_adverse_slippage_bps=ZERO,
    ))
    entry_cost = entry_costs.entry_fee_units + entry_costs.entry_slippage_cost_units
    sign = Decimal(1) if mark_plan.direction is ResearchDirection.LONG else Decimal(-1)
    remaining = b.initial_confirmed_units
    gross_realized = ZERO
    paid_exit_cost = ZERO
    observed = 0
    next_fill = 0
    last_funding = ZERO

    with localcontext(_EXACT_CONTEXT):
        for tick in mark_ticks:
            current_funding = tuple(
                event for event in funding_events if event.event_at_ms < tick.at_ms
            )
            funding_breakdown = evaluate_synthetic_costs(SyntheticCostScenario(
                direction=mark_plan.direction,
                entry_at_ms=mark_plan.entry_at_ms,
                exit_at_ms=tick.at_ms,
                entry_hypothetical_notional_quote_units=mark_plan.margin.entry_notional_quote,
                exit_hypothetical_notional_quote_units=mark_plan.margin.entry_notional_quote,
                entry_fee_bps=ZERO, exit_fee_bps=ZERO,
                entry_adverse_slippage_bps=ZERO,
                exit_adverse_slippage_bps=ZERO,
                funding_events=current_funding,
            ))
            last_funding = funding_breakdown.signed_funding_cost_units
            snapshot = next(
                s for s in reversed(risk_snapshots)
                if s.effective_at_ms <= tick.at_ms
            )
            requirement = maintenance_for_mark(
                snapshot, mark_notional_quote=remaining * tick.mark_price,
                close_reserve_quote=mark_plan.reserve_for_close_quote,
            )
            equity = (
                mark_plan.margin.requested_margin_quote + gross_realized
                + sign * (tick.mark_price - mark_plan.entry_price) * remaining
                - entry_cost - paid_exit_cost - last_funding
            )
            observed += 1

            # At a timestamp shared by a quote and a FILL, the mark tests
            # the PRE-FILL quantity. A 'stop/target' also wins over FILL.
            if equity <= requirement:
                return out(
                    "abstain_partial_risk_liquidation_proxy", observed,
                    next_fill, tick.at_ms,
                )
            if ((
                tick.trade_price <= mark_plan.stop_price
                or tick.trade_price >= mark_plan.target_price
            ) if sign == 1 else (
                tick.trade_price >= mark_plan.stop_price
                or tick.trade_price <= mark_plan.target_price
            )):
                return out(
                    "abstain_partial_risk_prior_stop_or_target", observed,
                    next_fill, tick.at_ms,
                )

            if next_fill < len(ordered) and ordered[next_fill].event_at_ms == tick.at_ms:
                ref = ordered[next_fill]
                qty = recorded[(ref.intent_id, ref.event_id)].filled_units
                if qty <= ZERO or qty > remaining:
                    raise DataValidationError("D398 impossible PAPER filled quantity")
                breakdown = evaluate_synthetic_costs(SyntheticCostScenario(
                    direction=mark_plan.direction,
                    entry_at_ms=mark_plan.entry_at_ms,
                    exit_at_ms=tick.at_ms,
                    entry_hypothetical_notional_quote_units=mark_plan.entry_price * qty,
                    exit_hypothetical_notional_quote_units=ref.reference_exit_price_quote * qty,
                    entry_fee_bps=ZERO,
                    exit_fee_bps=cost_rates.exit_fee_bps,
                    entry_adverse_slippage_bps=ZERO,
                    exit_adverse_slippage_bps=cost_rates.exit_adverse_slippage_bps,
                ))
                gross_realized += sign * (
                    ref.reference_exit_price_quote - mark_plan.entry_price
                ) * qty
                paid_exit_cost += (
                    breakdown.exit_fee_units + breakdown.exit_slippage_cost_units
                )
                remaining -= qty
                next_fill += 1

        if remaining != ZERO or next_fill != len(ordered):
            raise DataValidationError("D398 mark path did not reconcile all PAPER fills")
        reconciled_net = gross_realized - entry_cost - paid_exit_cost - last_funding
        if reconciled_net != expected:
            raise DataValidationError("D398 incremental equity disagrees with D393 costs")

    # D397 and D398 have independent RO samples: detect a concurrent
    # checkpoint drift and never return costs from an obsolete ledger.
    after = inspect_paper_position(
        position_path, position_id, opening_order_path=opening_order_path,
    )
    if after.balance != b:
        raise DataGapError("D398 PAPER journals changed during risk replay")

    return out(
        "conditional_closed_after_observed_partial_derisk_proxy",
        observed, next_fill, net=expected,
    )
