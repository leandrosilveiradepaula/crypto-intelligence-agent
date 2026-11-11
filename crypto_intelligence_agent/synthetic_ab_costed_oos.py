"""J3: compare two J2 synthetic hypotheses on the SAME purged OOS schedule.

Not a financial backtest: the signal-close and future-close prices are ex-post
REFERENCE marks, never executable fills. Fees/slippage/funding are explicit
hypothetical fixtures; no stops, mark-price liquidation or margin simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_cost_scenarios import (
    SyntheticCostScenario, SyntheticFundingEvent,
    evaluate_synthetic_costs, _amount, _rate,
)
from .synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, research_synthetic_compression_breakouts,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_label_purging import (
    SyntheticLabelHorizonConfig, SyntheticPurgedPlan,
    purge_synthetic_label_horizons,
)
from .synthetic_oos_replay import MAX_REPLAY_EVENTS
from .synthetic_position_state import SyntheticSide
from .synthetic_trend_pullback import (
    TrendPullbackConfig, research_synthetic_trend_pullbacks,
)
from .synthetic_walk_forward import SyntheticWalkForwardPlan

_EXACT = Context(prec=512)
_A = "synthetic_compression_breakout_v1"
_B = "synthetic_trend_pullback_v1"


@dataclass(frozen=True)
class SyntheticABCostAssumptions:
    """Quote unit and bps fixtures; not exchange schedules or real leverage."""

    entry_notional_quote_units: Decimal
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_slippage_bps: Decimal
    exit_slippage_bps: Decimal
    signed_funding_rate_bps: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        _amount(self.entry_notional_quote_units, "synthetic entry notional")
        for attr in ("entry_fee_bps", "exit_fee_bps",
                     "entry_slippage_bps", "exit_slippage_bps"):
            _rate(getattr(self, attr), attr, signed=False)
        _rate(self.signed_funding_rate_bps, "signed_funding_rate_bps", signed=True)


@dataclass(frozen=True)
class SyntheticABEvent:
    fold_number: int
    entry_index: int
    outcome_index: int
    strategy_id: str
    side: SyntheticSide
    observed_at_ms: int
    matured_at_ms: int
    ex_post_gross_mark_change_quote_units: Decimal
    assumed_total_signed_cost_quote_units: Decimal
    ex_post_net_mark_change_quote_units: Decimal

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False


@dataclass(frozen=True)
class SyntheticABFold:
    number: int
    eligible_indices: tuple[int, ...]
    strategy_a: tuple[SyntheticABEvent, ...]
    strategy_b: tuple[SyntheticABEvent, ...]


@dataclass(frozen=True)
class SyntheticABComparison:
    """Same OOS opportunities and assumptions; absence of trades is explicit."""

    folds: tuple[SyntheticABFold, ...]
    horizon_bars: int
    input_observed_candles: int

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def out_of_sample_results_validated(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    def sanitized_report(self) -> dict:
        def summary(strategy: str) -> dict:
            events = [
                e for fold in self.folds
                for e in (fold.strategy_a if strategy == _A else fold.strategy_b)
            ]
            with localcontext(_EXACT):
                gross = sum(
                    (e.ex_post_gross_mark_change_quote_units for e in events),
                    Decimal(0),
                )
                costs = sum(
                    (e.assumed_total_signed_cost_quote_units for e in events),
                    Decimal(0),
                )
                net = sum(
                    (e.ex_post_net_mark_change_quote_units for e in events),
                    Decimal(0),
                )
            return {
                "hypothesis_id": strategy,
                "candidate_count": len(events),
                "ex_post_gross_mark_change_quote_units": format(gross, "f"),
                "assumed_signed_cost_quote_units": format(costs, "f"),
                "ex_post_net_mark_change_quote_units": format(net, "f"),
                "positive_ex_post_net_marks": sum(
                    e.ex_post_net_mark_change_quote_units > 0 for e in events
                ),
            }

        return {
            "schema_version": "j3-synthetic-ab-same-purged-folds-v1",
            "quality": "synthetic_ex_post_reference_only",
            "folds": len(self.folds),
            "identical_oos_candidate_opportunity_count": sum(
                len(f.eligible_indices) for f in self.folds
            ),
            "horizon_bars": self.horizon_bars,
            "strategy_a": summary(_A),
            "strategy_b": summary(_B),
            "fill_prices_verified": False,
            "fees_and_funding_venue_verified": False,
            "intrabar_liquidation_validated": False,
            "out_of_sample_results_validated": False,
            "financial_backtest_approved": False,
            "orders_sent": False,
        }


def _event(
    *, side: SyntheticSide, signal_close: Decimal, outcome_close: Decimal,
    available_at_ms: int, outcome_at_ms: int, fold_number: int,
    entry_index: int, outcome_index: int, strategy_id: str,
    costs: SyntheticABCostAssumptions,
) -> SyntheticABEvent:
    if (type(side) is not SyntheticSide
            or type(signal_close) is not Decimal or signal_close <= 0
            or type(outcome_close) is not Decimal or outcome_close <= 0
            or available_at_ms >= outcome_at_ms):
        raise DataValidationError("invalid synthetic mark reference")
    with localcontext(_EXACT):
        side_sign = Decimal(1) if side is SyntheticSide.LONG else Decimal(-1)
        gross = costs.entry_notional_quote_units * (
            outcome_close / signal_close - Decimal(1)
        ) * side_sign
        exit_size = costs.entry_notional_quote_units * (
            outcome_close / signal_close
        )
        funding = ()
        if costs.signed_funding_rate_bps:
            funding = (SyntheticFundingEvent(
                event_id="fixture_funding_ab_single",
                event_at_ms=available_at_ms + (outcome_at_ms - available_at_ms)//2,
                hypothetical_notional_quote_units=costs.entry_notional_quote_units,
                signed_funding_rate_bps=costs.signed_funding_rate_bps,
            ),)
        scenario = SyntheticCostScenario(
            direction=(ResearchDirection.LONG if side is SyntheticSide.LONG
                       else ResearchDirection.SHORT),
            entry_at_ms=available_at_ms, exit_at_ms=outcome_at_ms,
            entry_hypothetical_notional_quote_units=costs.entry_notional_quote_units,
            exit_hypothetical_notional_quote_units=exit_size,
            entry_fee_bps=costs.entry_fee_bps, exit_fee_bps=costs.exit_fee_bps,
            entry_adverse_slippage_bps=costs.entry_slippage_bps,
            exit_adverse_slippage_bps=costs.exit_slippage_bps,
            funding_events=funding,
        )
        paid = evaluate_synthetic_costs(scenario).total_signed_cost_units
        return SyntheticABEvent(
            fold_number=fold_number, entry_index=entry_index,
            outcome_index=outcome_index, strategy_id=strategy_id,
            side=side, observed_at_ms=available_at_ms,
            matured_at_ms=outcome_at_ms,
            ex_post_gross_mark_change_quote_units=gross,
            assumed_total_signed_cost_quote_units=paid,
            ex_post_net_mark_change_quote_units=gross - paid,
        )


def compare_synthetic_ab_costed_oos(
    candles: Sequence[ClosedCandle], *,
    plan: SyntheticWalkForwardPlan,
    purged: SyntheticPurgedPlan,
    horizon: SyntheticLabelHorizonConfig,
    strategy_a: CompressionBreakoutConfig,
    strategy_b: TrendPullbackConfig,
    costs: SyntheticABCostAssumptions,
) -> SyntheticABComparison:
    """Evaluate both *frozen* strategies on identical, mature OOS indices.

    Neither strategy sees an outcome candle when deciding. The future mark is
    used ONLY after its OOS index is selected. This is intentionally only an
    ex-post screening bridge, not a fill/stop/funding schedule backtest.
    """
    if (type(strategy_a) is not CompressionBreakoutConfig
            or type(strategy_b) is not TrendPullbackConfig
            or type(costs) is not SyntheticABCostAssumptions):
        raise DataValidationError("two fixed strategies and costs required")
    expected = purge_synthetic_label_horizons(candles, plan=plan, config=horizon)
    if type(purged) is not SyntheticPurgedPlan or purged != expected:
        raise DataValidationError("stale or inconsistent purged OOS schedule")
    count = sum(len(f.oos_indices) for f in purged.folds)
    if count > MAX_REPLAY_EVENTS:
        raise DataValidationError("OOS study exceeds resource bound")
    cs = tuple(candles)
    result = []
    for fold in purged.folds:
        a_events, b_events = [], []
        for i in fold.oos_indices:
            prefix = cs[:i+1]
            seen_at = cs[i].close_time_ms + plan.close_safety_ms
            a = research_synthetic_compression_breakouts(
                prefix, config=strategy_a, decision_at_ms=seen_at,
                close_safety_ms=plan.close_safety_ms,
            )
            b = research_synthetic_trend_pullbacks(
                prefix, config=strategy_b, decision_at_ms=seen_at,
                close_safety_ms=plan.close_safety_ms,
            )
            for candidates, chosen, strategy_id in (
                (a.candidates, a_events, _A),
                (b.candidates, b_events, _B),
            ):
                latest = [
                    c for c in candidates
                    if (c.closed_at_ms if strategy_id == _A
                        else c.trigger_closed_at_ms) == cs[i].close_time_ms
                ]
                if len(latest) > 1:
                    raise DataValidationError("duplicate OOS candidate at same close")
                if not latest:
                    continue
                c = latest[0]
                if (c.strategy_id != strategy_id
                        or c.earliest_research_at_ms != seen_at):
                    raise DataValidationError("candidate not causal or unknown")
                future = cs[i + horizon.horizon_bars]
                chosen.append(_event(
                    side=c.side, signal_close=cs[i].close,
                    outcome_close=future.close,
                    available_at_ms=seen_at,
                    outcome_at_ms=future.close_time_ms,
                    fold_number=fold.number,
                    entry_index=i, outcome_index=i + horizon.horizon_bars,
                    strategy_id=strategy_id, costs=costs,
                ))
        result.append(SyntheticABFold(
            number=fold.number, eligible_indices=fold.oos_indices,
            strategy_a=tuple(a_events), strategy_b=tuple(b_events),
        ))
    return SyntheticABComparison(
        folds=tuple(result), horizon_bars=horizon.horizon_bars,
        input_observed_candles=len(cs),
    )
