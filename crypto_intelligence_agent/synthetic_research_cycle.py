"""J3/PRE7: bounded causal orchestration for synthetic J2/J3 research.

No live/PAPER orders, authentic market data, inferred fills, or financial edge.
OOS barrier windows end at the recorded label horizon AND the fold boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_financial_scenarios import (
    MAX_SCENARIOS, ConditionalFinancialResult, ConditionalFinancialScenario,
    evaluate_conditional_financial_scenarios,
)
from .synthetic_intrabar_barriers import (
    ObservationKind, ResearchDirection, SyntheticBarrierObservation,
    SyntheticBarrierPlan, observe_synthetic_intrabar_barriers,
)
from .synthetic_label_purging import (
    SyntheticLabelHorizonConfig, SyntheticPurgedPlan, purge_synthetic_label_horizons,
)
from .synthetic_oos_replay import (
    SyntheticOOSResearchAudit, audit_synthetic_oos_hypotheses,
)
from .synthetic_position_state import SyntheticSide
from .synthetic_walk_forward import (
    SyntheticWalkForwardConfig, SyntheticWalkForwardPlan,
    plan_synthetic_walk_forward,
)


@dataclass(frozen=True)
class SyntheticResearchCycleConfig:
    strategy: CompressionBreakoutConfig
    walk_forward: SyntheticWalkForwardConfig
    horizon: SyntheticLabelHorizonConfig
    close_safety_ms: int = 1_000

    def __post_init__(self) -> None:
        if (type(self.strategy) is not CompressionBreakoutConfig
                or type(self.walk_forward) is not SyntheticWalkForwardConfig
                or type(self.horizon) is not SyntheticLabelHorizonConfig):
            raise DataValidationError("cycle requires explicit J2/PRE3/PRE4 configurations")
        if (type(self.close_safety_ms) is not int
                or not 0 <= self.close_safety_ms <= 86_400_000):
            raise DataValidationError("cycle close safety must be bounded UTC milliseconds")


@dataclass(frozen=True)
class SyntheticResearchCycleEvent:
    fold_number: int
    candidate_index: int
    candidate_available_at_ms: int
    observation_end_exclusive_index: int
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
        """Count J2 hypotheses before any PRE7 conditional refusal."""
        return sum(len(fold.observations) for fold in self.oos.folds)

    @property
    def j2_abstention_count(self) -> int:
        return sum(len(fold.abstained_indices) for fold in self.oos.folds)

    @property
    def pre7_refusal_count(self) -> int:
        return sum(event.abstention_reason is not None for event in self.events)

    @property
    def abstention_count(self) -> int:
        return self.j2_abstention_count + self.pre7_refusal_count

    @property
    def conditional_branch_count(self) -> int:
        """Alternatives, NOT independent trades or a portfolio PnL."""
        return sum(len(event.conditional_results) for event in self.events)

    @property
    def approved_for_live_use(self) -> bool:
        return False

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
    def net_pnl_verified(self) -> bool:
        return False


def run_synthetic_research_cycle(
    candles: Sequence[ClosedCandle],
    *,
    config: SyntheticResearchCycleConfig,
    decision_at_ms: int,
    barrier_plans: Mapping[int, SyntheticBarrierPlan],
    financial_scenarios: Mapping[int, tuple[ConditionalFinancialScenario, ...]],
) -> SyntheticResearchCycle:
    """Run only causally available, fixed-horizon OOS research fixtures.

    Signal evaluation is delegated to PRE5, which receives historical prefixes.
    A hypothetical barrier plan cannot be observed until the first full
    candle whose OPEN is at/after the J2 close+close_safety availability.
    It also cannot consume bars beyond its PRE4 OOS outcome or test fold.
    """
    if (type(config) is not SyntheticResearchCycleConfig
            or type(barrier_plans) is not dict
            or type(financial_scenarios) is not dict):
        raise DataValidationError("explicit typed cycle config and dict assumptions required")

    cs = tuple(candles)
    plan = plan_synthetic_walk_forward(
        cs, config=config.walk_forward, decision_at_ms=decision_at_ms,
        close_safety_ms=config.close_safety_ms,
    )
    purged = purge_synthetic_label_horizons(
        cs, plan=plan, config=config.horizon,
    )
    oos = audit_synthetic_oos_hypotheses(
        cs, plan=plan, purged=purged, horizon=config.horizon,
        strategy=config.strategy,
    )
    fold_by_number = {fold.number: fold for fold in plan.folds}
    candidate_indices = {
        item.candidate_index for fold in oos.folds for item in fold.observations
    }
    for label, entries in (("barrier", barrier_plans), ("financial", financial_scenarios)):
        if (len(entries) > len(candidate_indices)
                or any(type(k) is not int or k not in candidate_indices for k in entries)):
            raise DataValidationError(label + " assumptions contain non-candidate OOS keys")
    if any(type(p) is not SyntheticBarrierPlan for p in barrier_plans.values()):
        raise DataValidationError("barrier plans must have exact typed PRE1 contracts")
    for branch_group in financial_scenarios.values():
        if (type(branch_group) is not tuple
                or not 1 <= len(branch_group) <= MAX_SCENARIOS
                or any(type(branch) is not ConditionalFinancialScenario for branch in branch_group)):
            raise DataValidationError("financial assumptions must contain typed bounded branches")
    if not financial_scenarios.keys() <= barrier_plans.keys():
        raise DataValidationError("financial assumptions require corresponding barrier plans")

    events: list[SyntheticResearchCycleEvent] = []
    for fold in oos.folds:
        selected_fold = fold_by_number.get(fold.fold_number)
        if selected_fold is None:
            raise DataValidationError("OOS fold missing in original walk-forward plan")
        for item in fold.observations:
            index = item.candidate_index
            candidate = item.hypothesis
            if (not selected_fold.test_start <= index < selected_fold.test_end
                    or not index < item.outcome_index < selected_fold.test_end):
                raise DataValidationError("OOS candidate/outcome crosses its declared test fold")
            # PRE4 fixes the ex-post label horizon; never borrow a subsequent
            # OOS fold or a later period to find a favourable STOP/TARGET.
            end = min(selected_fold.test_end, item.outcome_index + 1)
            eligible = next((
                j for j in range(index + 1, end)
                if cs[j].open_time_ms >= candidate.earliest_research_at_ms
            ), None)
            def emit(
                first: int | None,
                observed: SyntheticBarrierObservation | None,
                results: tuple[ConditionalFinancialResult, ...],
                refusal: str | None,
            ) -> None:
                events.append(SyntheticResearchCycleEvent(
                    fold_number=fold.fold_number,
                    candidate_index=index,
                    candidate_available_at_ms=candidate.earliest_research_at_ms,
                    observation_end_exclusive_index=end,
                    first_eligible_candle_index=first,
                    barrier_observation=observed,
                    conditional_results=results,
                    abstention_reason=refusal,
                ))

            if eligible is None:
                emit(None, None, (), "no_eligible_candle_within_oos_horizon")
                continue

            barrier = barrier_plans.get(index)
            if barrier is None:
                emit(eligible, None, (), "missing_explicit_barrier_plan")
                continue
            expected_side = (ResearchDirection.LONG if candidate.side is SyntheticSide.LONG
                             else ResearchDirection.SHORT)
            if (barrier.side is not expected_side
                    or barrier.hypothetical_entry_price != candidate.close
                    or barrier.plan_created_at_ms != candidate.earliest_research_at_ms):
                raise DataValidationError(
                    "barrier plan must match exact candidate side/close/availability"
                )

            # Bound the observation clock to the last ALLOWED OOS bar, not
            # the global replay decision, which may be days in the future.
            as_of = cs[end - 1].close_time_ms + config.close_safety_ms
            observed = observe_synthetic_intrabar_barriers(
                barrier, cs[eligible:end], as_of_ms=as_of,
                close_safety_ms=config.close_safety_ms,
            )
            if observed.kind is ObservationKind.NO_LEVEL_REACHED:
                emit(eligible, observed, (), "no_barrier_reached_within_oos_horizon")
                continue
            branches = financial_scenarios.get(index)
            if branches is None:
                emit(eligible, observed, (), "missing_explicit_financial_assumption")
                continue

            # This pure fixture chooses a conservative, explicit hypothetical
            # entry at the FIRST eligible candle open. It never reconstructs
            # a mid-candle fill or exposure while an earlier bar is omitted.
            # Financial cost timestamps cannot predate that observed opening.
            for row in branches:
                if row.costs.entry_at_ms != cs[eligible].open_time_ms:
                    raise DataValidationError(
                        "hypothetical entry must be timestamped at first eligible OOS open"
                    )
            results = evaluate_conditional_financial_scenarios(
                observed, branches, barrier_plan=barrier,
            )
            emit(eligible, observed, results, None)

    return SyntheticResearchCycle(plan, purged, oos, tuple(events))
