"""J3/PRE7 causal orchestration of existing synthetic research modules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_financial_scenarios import ConditionalFinancialScenario, ConditionalFinancialResult, evaluate_conditional_financial_scenarios
from .synthetic_intrabar_barriers import ResearchDirection, SyntheticBarrierObservation, SyntheticBarrierPlan, observe_synthetic_intrabar_barriers
from .synthetic_label_purging import SyntheticLabelHorizonConfig, SyntheticPurgedPlan, purge_synthetic_label_horizons
from .synthetic_oos_replay import SyntheticOOSResearchAudit, audit_synthetic_oos_hypotheses
from .synthetic_position_state import SyntheticSide
from .synthetic_walk_forward import SyntheticWalkForwardConfig, SyntheticWalkForwardPlan, plan_synthetic_walk_forward


@dataclass(frozen=True)
class SyntheticResearchCycleConfig:
    strategy: CompressionBreakoutConfig
    walk_forward: SyntheticWalkForwardConfig
    horizon: SyntheticLabelHorizonConfig
    close_safety_ms: int = 1_000

    def __post_init__(self) -> None:
        if type(self.strategy) is not CompressionBreakoutConfig or type(self.walk_forward) is not SyntheticWalkForwardConfig or type(self.horizon) is not SyntheticLabelHorizonConfig:
            raise DataValidationError("cycle requires explicit J2/PRE3/PRE4 configurations")
        if type(self.close_safety_ms) is not int or not 0 <= self.close_safety_ms <= 86_400_000:
            raise DataValidationError("cycle close safety must be bounded UTC milliseconds")


@dataclass(frozen=True)
class SyntheticResearchCycleEvent:
    candidate_index: int
    candidate_available_at_ms: int
    first_eligible_candle_index: int | None
    barrier_observation: SyntheticBarrierObservation | None
    conditional_results: tuple[ConditionalFinancialResult, ...]
    abstention_reason: str | None


@dataclass(frozen=True)
class SyntheticResearchCycle:
    walk_forward: SyntheticWalkForwardPlan
    purged: SyntheticPurgedPlan
    oos: SyntheticOOSResearchAudit
    events: tuple[SyntheticResearchCycleEvent, ...]

    @property
    def signal_count(self) -> int:
        return len(self.events)
    @property
    def abstention_count(self) -> int:
        return sum(event.abstention_reason is not None for event in self.events)
    @property
    def conditional_branch_count(self) -> int:
        return sum(len(event.conditional_results) for event in self.events)
    @property
    def approved_for_live_use(self) -> bool: return False
    @property
    def orders_sent(self) -> bool: return False
    @property
    def financial_backtest_approved(self) -> bool: return False
    @property
    def out_of_sample_results_validated(self) -> bool: return False
    @property
    def net_pnl_verified(self) -> bool: return False


def run_synthetic_research_cycle(
    candles: Sequence[ClosedCandle], *, config: SyntheticResearchCycleConfig,
    decision_at_ms: int, barrier_plans: Mapping[int, SyntheticBarrierPlan],
    financial_scenarios: Mapping[int, tuple[ConditionalFinancialScenario, ...]],
) -> SyntheticResearchCycle:
    """Replay OOS candidates causally; branches are supplied, never fabricated."""
    if type(config) is not SyntheticResearchCycleConfig or type(barrier_plans) is not dict or type(financial_scenarios) is not dict:
        raise DataValidationError("typed cycle configuration and immutable-style mappings required")
    cs = tuple(candles)
    plan = plan_synthetic_walk_forward(cs, config=config.walk_forward, decision_at_ms=decision_at_ms, close_safety_ms=config.close_safety_ms)
    purged = purge_synthetic_label_horizons(cs, plan=plan, config=config.horizon)
    oos = audit_synthetic_oos_hypotheses(cs, plan=plan, purged=purged, horizon=config.horizon, strategy=config.strategy)
    events: list[SyntheticResearchCycleEvent] = []
    for fold in oos.folds:
        for item in fold.observations:
            index = item.candidate_index
            candidate = item.hypothesis
            expected_side = ResearchDirection.LONG if candidate.side is SyntheticSide.LONG else ResearchDirection.SHORT
            eligible = next((j for j in range(index + 1, len(cs)) if cs[j].open_time_ms >= candidate.earliest_research_at_ms), None)
            if eligible is None:
                events.append(SyntheticResearchCycleEvent(index, candidate.earliest_research_at_ms, None, None, (), "no_future_candle_after_close_safety"))
                continue
            barrier = barrier_plans.get(index)
            if type(barrier) is not SyntheticBarrierPlan:
                events.append(SyntheticResearchCycleEvent(index, candidate.earliest_research_at_ms, eligible, None, (), "missing_explicit_barrier_plan"))
                continue
            if barrier.side is not expected_side or barrier.hypothetical_entry_price != candidate.close or barrier.plan_created_at_ms != candidate.earliest_research_at_ms:
                raise DataValidationError("barrier plan must bind exact causal candidate side, close and availability")
            observation = observe_synthetic_intrabar_barriers(barrier, cs[eligible:], as_of_ms=decision_at_ms, close_safety_ms=config.close_safety_ms)
            branches = financial_scenarios.get(index)
            if observation.kind.value == "no_level_reached":
                events.append(SyntheticResearchCycleEvent(index, candidate.earliest_research_at_ms, eligible, observation, (), "no_barrier_reached"))
            elif type(branches) is not tuple:
                events.append(SyntheticResearchCycleEvent(index, candidate.earliest_research_at_ms, eligible, observation, (), "missing_explicit_financial_assumption"))
            else:
                results = evaluate_conditional_financial_scenarios(observation, branches, barrier_plan=barrier)
                events.append(SyntheticResearchCycleEvent(index, candidate.earliest_research_at_ms, eligible, observation, results, None))
    return SyntheticResearchCycle(plan, purged, oos, tuple(events))
