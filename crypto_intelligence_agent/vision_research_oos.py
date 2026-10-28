"""J1/J3 #243: descriptive monthly OOS direction diagnostic, never trading.

Each month is a complete previously validated OFFLINE Vision archive. Direction
of next close is known ex post; no fills, money, license or real edge.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from .market_data import DataValidationError
from .offline_vision_month import OfflineVisionMonth
from .offline_vision_series import assemble_offline_vision_months


@dataclass(frozen=True)
class VisionDirectionalFold:
    test_month_index: int
    test_first_open_ms: int
    selected_rule: str
    training_pairs: int
    training_continuation_hits: int
    training_reversal_hits: int
    training_baseline_hits: int
    oos_pairs: int
    oos_selected_hits: int
    oos_baseline_hits: int
    abstained_pairs: int


@dataclass(frozen=True)
class VisionDirectionalOOS:
    folds: tuple[VisionDirectionalFold, ...]

    @property
    def quality(self) -> str:
        return "unverified_offline_descriptive_ex_post_only"

    @property
    def source_authenticated(self) -> bool:
        return False

    @property
    def dataset_rights_authorized(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def out_of_sample_financial_returns_validated(self) -> bool:
        return False

    @property
    def ready_for_trading(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def _scores(candles) -> tuple[int, int, int, int, int, int]:
    """Use only adjacent closes INSIDE one calendar partition.

    At each index i>=1, previous movement is close[i]-close[i-1];
    the next movement is close[i+1]-close[i]. A decision at close[i]
    cannot fill at that close; outcomes are descriptive only.
    Zero returns are abstentions for both hypotheses.
    """
    continuation = reversal = up = down = count = abstain = 0
    for i in range(1, len(candles) - 1):
        a = candles[i].close - candles[i - 1].close
        b = candles[i + 1].close - candles[i].close
        if a == 0 or b == 0:
            abstain += 1
            continue
        count += 1
        continuation += int((a > 0) == (b > 0))
        reversal += int((a > 0) != (b > 0))
        up += int(b > 0)
        down += int(b < 0)
    return count, continuation, reversal, up, down, abstain


def diagnose_vision_monthly_direction(
    months: tuple[OfflineVisionMonth, ...], *, as_of_ms: int,
) -> VisionDirectionalOOS:
    """Fixed rules; select on full PRIOR months, then score next month.

    The existing assembler validates identity, bounds, UTC and all candles.
    A fold's candidate choice never consults its own test month. The baseline
    is the majoritarian next-bar direction in prior months only. Ties abstain.
    """
    validated = assemble_offline_vision_months(months, as_of_ms=as_of_ms)
    if len(validated.month_names) < 2:
        raise DataValidationError("at least two prevalidated months required")
    scores = [_scores(month.candles) for month in months]
    folds = []
    train_count = train_cont = train_rev = train_up = train_down = 0
    for idx in range(1, len(months)):
        prior = scores[idx - 1]
        train_count += prior[0]
        train_cont += prior[1]
        train_rev += prior[2]
        train_up += prior[3]
        train_down += prior[4]
        choice = (
            "continuation" if train_cont > train_rev
            else "reversal" if train_rev > train_cont else "abstain"
        )
        test_count, test_cont, test_rev, test_up, test_down, abstain = scores[idx]
        baseline = max(test_up, test_down) if train_up != train_down else 0
        if train_up > train_down:
            baseline = test_up
        elif train_down > train_up:
            baseline = test_down
        folds.append(VisionDirectionalFold(
            test_month_index=idx + 1,
            test_first_open_ms=months[idx].first_open_ms,
            selected_rule=choice,
            training_pairs=train_count,
            training_continuation_hits=train_cont,
            training_reversal_hits=train_rev,
            training_baseline_hits=max(train_up, train_down),
            oos_pairs=test_count,
            oos_selected_hits=(test_cont if choice == "continuation"
                               else test_rev if choice == "reversal" else 0),
            oos_baseline_hits=baseline,
            abstained_pairs=abstain,
        ))
    return VisionDirectionalOOS(tuple(folds))
