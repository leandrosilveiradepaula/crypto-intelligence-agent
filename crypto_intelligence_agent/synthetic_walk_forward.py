"""J3/PRE3: temporal WALK-FORWARD SPLIT PLAN on SYNTHETIC OHLCV ONLY.

A split plan is NOT a backtest or evaluated out-of-sample performance.
No parameter fitting, trade labels, model selection, fill/cost/liquidation
simulation, market data rights, network, money or order permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_feature_engine import (
    MAX_CANDLES, validate_synthetic_closed_candles,
)


MAX_FOLDS = 512


@dataclass(frozen=True)
class SyntheticWalkForwardConfig:
    """Fixed-length rolling history and disjoint test periods.

    stride_bars >= test_bars makes test blocks disjoint across folds;
    earlier tested bars MAY enter subsequent training windows, as they were
    already historical by the later fold. Gap bars are NOT scored or fitted.
    Gap is not a proven purge for overlapping return labels (none modeled).
    """

    train_bars: int
    gap_bars: int
    test_bars: int
    stride_bars: int

    def __post_init__(self) -> None:
        if type(self.train_bars) is not int or not 2 <= self.train_bars <= MAX_CANDLES:
            raise DataValidationError("train_bars must be integer 2..10000")
        if type(self.gap_bars) is not int or not 0 <= self.gap_bars <= MAX_CANDLES:
            raise DataValidationError("gap_bars must be integer 0..10000")
        if type(self.test_bars) is not int or not 1 <= self.test_bars <= MAX_CANDLES:
            raise DataValidationError("test_bars must be integer 1..10000")
        if (type(self.stride_bars) is not int
                or not self.test_bars <= self.stride_bars <= MAX_CANDLES):
            raise DataValidationError(
                "stride_bars must be integer between test_bars and 10000"
            )


@dataclass(frozen=True)
class SyntheticWalkForwardFold:
    """Half-open bar indices and UTC boundaries, no prices/labels/returns."""

    number: int
    train_start: int
    train_end: int
    gap_start: int
    gap_end: int
    test_start: int
    test_end: int
    train_first_open_ms: int
    train_last_closed_ms: int
    train_available_at_ms: int
    test_first_open_ms: int
    test_last_closed_ms: int

    @property
    def training_bars(self) -> int:
        return self.train_end - self.train_start

    @property
    def embargo_bars(self) -> int:
        return self.gap_end - self.gap_start

    @property
    def testing_bars(self) -> int:
        return self.test_end - self.test_start


@dataclass(frozen=True)
class SyntheticWalkForwardPlan:
    exchange: str
    symbol: str
    interval: str
    quality: str
    decision_at_ms: int
    close_safety_ms: int
    observed_candle_count: int
    config: SyntheticWalkForwardConfig
    folds: tuple[SyntheticWalkForwardFold, ...]

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def out_of_sample_results_validated(self) -> bool:
        return False

    @property
    def real_market_data_verified(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def plan_synthetic_walk_forward(
    candles: Sequence[ClosedCandle],
    *,
    config: SyntheticWalkForwardConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
) -> SyntheticWalkForwardPlan:
    """Plan rolling train/gap/test folds with no partial final fold.

    Every supplied candle is checked FIRST against the decision's cutoff;
    malicious future bars cannot be hidden by choosing a short test window.
    The final training candle plus close safety must already be observable
    when the test window first opens. No use is made of test-period values.
    """
    if type(config) is not SyntheticWalkForwardConfig:
        raise DataValidationError("explicit synthetic walk-forward config required")
    cs = validate_synthetic_closed_candles(
        candles, decision_at_ms=decision_at_ms,
        close_safety_ms=close_safety_ms,
    )
    required = config.train_bars + config.gap_bars + config.test_bars
    if len(cs) < required:
        raise DataValidationError("no complete train/gap/test split in synthetic series")
    fold_list: list[SyntheticWalkForwardFold] = []
    train_start = 0
    previous_test_end = 0
    while train_start + required <= len(cs):
        train_end = train_start + config.train_bars
        test_start = train_end + config.gap_bars
        test_end = test_start + config.test_bars
        available = cs[train_end - 1].close_time_ms + close_safety_ms
        if available > cs[test_start].open_time_ms:
            raise DataValidationError(
                "training data not closed and available before test starts; increase gap"
            )
        if test_start < previous_test_end:
            raise DataValidationError("walk-forward OOS test windows overlap")
        if len(fold_list) >= MAX_FOLDS:
            raise DataValidationError("too many walk-forward folds for offline resource bound")
        fold_list.append(SyntheticWalkForwardFold(
            number=len(fold_list) + 1,
            train_start=train_start, train_end=train_end,
            gap_start=train_end, gap_end=test_start,
            test_start=test_start, test_end=test_end,
            train_first_open_ms=cs[train_start].open_time_ms,
            train_last_closed_ms=cs[train_end - 1].close_time_ms,
            train_available_at_ms=available,
            test_first_open_ms=cs[test_start].open_time_ms,
            test_last_closed_ms=cs[test_end - 1].close_time_ms,
        ))
        previous_test_end = test_end
        train_start += config.stride_bars
    return SyntheticWalkForwardPlan(
        exchange=cs[0].exchange, symbol=cs[0].symbol,
        interval=cs[0].interval, quality=cs[0].quality,
        decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
        observed_candle_count=len(cs), config=config,
        folds=tuple(fold_list),
    )
