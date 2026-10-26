"""J3/PRE4: conservative horizon purging for SYNTHETIC walk-forward folds.

All windows are index/availability constraints, not computed future returns.
No labels, PnL, fills, optimization, network, orders or live market data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_feature_engine import validate_synthetic_closed_candles
from .synthetic_walk_forward import (
    SyntheticWalkForwardPlan, SyntheticWalkForwardFold,
)


@dataclass(frozen=True)
class SyntheticLabelHorizonConfig:
    """Fixed, declared-before-evaluation horizon in closed bars.

    A candidate at index i observes its outcome at i + horizon_bars.
    An OOS event is retained only if that outcome belongs to the same test
    block. A training event must have matured BEFORE the test first opens.
    """

    horizon_bars: int

    def __post_init__(self) -> None:
        if type(self.horizon_bars) is not int or not 1 <= self.horizon_bars <= 10_000:
            raise DataValidationError("horizon_bars must be integer 1..10000")


@dataclass(frozen=True)
class SyntheticPurgedFold:
    number: int
    train_indices: tuple[int, ...]
    purged_train_indices: tuple[int, ...]
    oos_indices: tuple[int, ...]
    censored_oos_indices: tuple[int, ...]

    @property
    def train_count(self) -> int:
        return len(self.train_indices)

    @property
    def oos_count(self) -> int:
        return len(self.oos_indices)


@dataclass(frozen=True)
class SyntheticPurgedPlan:
    quality: str
    config: SyntheticLabelHorizonConfig
    folds: tuple[SyntheticPurgedFold, ...]

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


def purge_synthetic_label_horizons(
    candles: Sequence[ClosedCandle],
    *,
    plan: SyntheticWalkForwardPlan,
    config: SyntheticLabelHorizonConfig,
) -> SyntheticPurgedPlan:
    """Restrict PRE3 folds to mature train and fully observed test horizons.

    This is intentionally stricter than generic event-based purged CV:
    no variable label endpoints, trade labels or financial scores exist.
    """
    if type(plan) is not SyntheticWalkForwardPlan:
        raise DataValidationError("PRE3 walk-forward plan required")
    if type(config) is not SyntheticLabelHorizonConfig:
        raise DataValidationError("explicit label horizon config required")
    cs = validate_synthetic_closed_candles(
        candles, decision_at_ms=plan.decision_at_ms,
        close_safety_ms=plan.close_safety_ms,
    )
    if (len(cs) != plan.observed_candle_count
            or cs[0].exchange != plan.exchange
            or cs[0].symbol != plan.symbol
            or cs[0].interval != plan.interval
            or cs[0].quality != plan.quality):
        raise DataValidationError("PRE3 plan does not match supplied candles")
    # Recompute and compare the entire PRE3 plan to detect stale or forged
    # fold boundaries, timestamp shifts and inconsistent config.
    from .synthetic_walk_forward import plan_synthetic_walk_forward
    expected = plan_synthetic_walk_forward(
        cs, config=plan.config, decision_at_ms=plan.decision_at_ms,
        close_safety_ms=plan.close_safety_ms,
    )
    if expected != plan:
        raise DataValidationError("PRE3 plan or candle timeline mismatch")

    h = config.horizon_bars
    results: list[SyntheticPurgedFold] = []
    for fold in plan.folds:
        if type(fold) is not SyntheticWalkForwardFold:
            raise DataValidationError("invalid PRE3 fold")
        eligible_train: list[int] = []
        purged_train: list[int] = []
        for i in range(fold.train_start, fold.train_end):
            end = i + h
            if (end >= fold.test_start
                    or cs[end].close_time_ms + plan.close_safety_ms
                    > fold.test_first_open_ms):
                purged_train.append(i)
            else:
                eligible_train.append(i)
        eligible_test: list[int] = []
        censored_test: list[int] = []
        for i in range(fold.test_start, fold.test_end):
            # Test labels never borrow bars from later OOS folds or gap.
            if i + h < fold.test_end:
                eligible_test.append(i)
            else:
                censored_test.append(i)
        if not eligible_train or not eligible_test:
            raise DataValidationError(
                "no eligible training or OOS labels for declared horizon"
            )
        results.append(SyntheticPurgedFold(
            number=fold.number,
            train_indices=tuple(eligible_train),
            purged_train_indices=tuple(purged_train),
            oos_indices=tuple(eligible_test),
            censored_oos_indices=tuple(censored_test),
        ))
    return SyntheticPurgedPlan(
        quality=plan.quality, config=config, folds=tuple(results)
    )
