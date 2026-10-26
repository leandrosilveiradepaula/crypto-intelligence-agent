"""J3/PRE5: causal synthetic OOS observations, NEVER strategy validation.

Each hypothetical entry is researched using only its historical closed prefix.
A later close is an EX-POST directional observation, NOT an executable fill,
profit, forecast, independent event, or evidence of statistical edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, SyntheticEntryCandidate,
    research_synthetic_compression_breakouts,
)
from .synthetic_label_purging import (
    SyntheticLabelHorizonConfig, SyntheticPurgedPlan,
    purge_synthetic_label_horizons,
)
from .synthetic_position_state import SyntheticSide
from .synthetic_walk_forward import SyntheticWalkForwardPlan


MAX_REPLAY_EVENTS = 512


class DirectionalObservation(str, Enum):
    ALIGNED = "aligned"
    CONTRARY = "contrary"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class SyntheticOOSObservation:
    fold_number: int
    candidate_index: int
    candidate_closed_at_ms: int
    available_at_ms: int
    outcome_index: int
    outcome_closed_at_ms: int
    side: SyntheticSide
    outcome: DirectionalObservation
    hypothesis: SyntheticEntryCandidate


@dataclass(frozen=True)
class SyntheticOOSFoldAudit:
    fold_number: int
    eligible_indices: tuple[int, ...]
    abstained_indices: tuple[int, ...]
    observations: tuple[SyntheticOOSObservation, ...]

    @property
    def abstained_count(self) -> int:
        return len(self.abstained_indices)


@dataclass(frozen=True)
class SyntheticOOSResearchAudit:
    quality: str
    horizon_bars: int
    folds: tuple[SyntheticOOSFoldAudit, ...]

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def out_of_sample_results_validated(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def audit_synthetic_oos_hypotheses(
    candles: Sequence[ClosedCandle],
    *,
    plan: SyntheticWalkForwardPlan,
    purged: SyntheticPurgedPlan,
    horizon: SyntheticLabelHorizonConfig,
    strategy: CompressionBreakoutConfig,
) -> SyntheticOOSResearchAudit:
    """Replay J2 per eligible OOS candle, withholding every future candle.

    One declared strategy configuration, no fitting or optimization. PRE4
    validates the full source and purging plan prior to any J2 evaluation.
    """
    if type(strategy) is not CompressionBreakoutConfig:
        raise DataValidationError("explicit frozen J2 strategy configuration required")
    if type(purged) is not SyntheticPurgedPlan:
        raise DataValidationError("PRE4 purged plan required")
    expected = purge_synthetic_label_horizons(
        candles, plan=plan, config=horizon,
    )
    if purged != expected:
        raise DataValidationError("stale or inconsistent purged plan")
    count = sum(len(f.oos_indices) for f in purged.folds)
    if count > MAX_REPLAY_EVENTS:
        raise DataValidationError("too many OOS events for bounded causal replay")
    cs = tuple(candles)
    out: list[SyntheticOOSFoldAudit] = []
    for fold in purged.folds:
        observations: list[SyntheticOOSObservation] = []
        abstained: list[int] = []
        for i in fold.oos_indices:
            at = cs[i].close_time_ms + plan.close_safety_ms
            research = research_synthetic_compression_breakouts(
                cs[:i + 1], config=strategy,
                decision_at_ms=at, close_safety_ms=plan.close_safety_ms,
            )
            candidates = tuple(
                c for c in research.candidates if c.closed_at_ms == cs[i].close_time_ms
            )
            if len(candidates) > 1:
                raise DataValidationError("multiple candidates for same OOS candle")
            if not candidates:
                abstained.append(i)
                continue
            candidate = candidates[0]
            future = cs[i + horizon.horizon_bars]
            if future.close == candidate.close:
                result = DirectionalObservation.UNCHANGED
            elif ((future.close > candidate.close and candidate.side is SyntheticSide.LONG)
                    or (future.close < candidate.close and candidate.side is SyntheticSide.SHORT)):
                result = DirectionalObservation.ALIGNED
            else:
                result = DirectionalObservation.CONTRARY
            observations.append(SyntheticOOSObservation(
                fold_number=fold.number, candidate_index=i,
                candidate_closed_at_ms=candidate.closed_at_ms,
                available_at_ms=candidate.earliest_research_at_ms,
                outcome_index=i + horizon.horizon_bars,
                outcome_closed_at_ms=future.close_time_ms,
                side=candidate.side, outcome=result, hypothesis=candidate,
            ))
        out.append(SyntheticOOSFoldAudit(
            fold_number=fold.number, eligible_indices=fold.oos_indices,
            abstained_indices=tuple(abstained), observations=tuple(observations),
        ))
    return SyntheticOOSResearchAudit(
        quality="synthetic_fixture_ex_post_only",
        horizon_bars=horizon.horizon_bars, folds=tuple(out),
    )
