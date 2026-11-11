"""J2: causal trend/pullback/resumption strategy for synthetic PAPER research.

One closed-candle series, no live orders, no data fetching, no fitted ML.
The trend EMA slope and pullback bar are fully observed before the trigger.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .market_data import ClosedCandle, DataValidationError
from .synthetic_feature_engine import (
    FeatureConfig, _MATH_CONTEXT, _numeric, compute_synthetic_features,
)
from .synthetic_position_state import SyntheticSide

STRATEGY_ID = "synthetic_trend_pullback_v1"


@dataclass(frozen=True)
class TrendPullbackConfig:
    features: FeatureConfig
    min_ema_slope_atr: Decimal
    min_volume_ratio: Decimal
    max_trigger_extension_atr: Decimal
    cooldown_bars: int = 0

    def __post_init__(self) -> None:
        if type(self.features) is not FeatureConfig:
            raise DataValidationError("explicit feature configuration required")
        for name in ("min_ema_slope_atr", "max_trigger_extension_atr"):
            _numeric(getattr(self, name), name, strictly_positive=True)
        _numeric(self.min_volume_ratio, "min_volume_ratio", strictly_positive=True)
        if (self.min_ema_slope_atr > Decimal(10)
                or self.max_trigger_extension_atr > Decimal(10)
                or self.min_volume_ratio > Decimal(100)
                or type(self.cooldown_bars) is not int
                or not 0 <= self.cooldown_bars <= 500):
            raise DataValidationError("invalid trend/pullback parameter bounds")


@dataclass(frozen=True)
class TrendPullbackCandidate:
    strategy_id: str
    exchange: str
    symbol: str
    interval: str
    side: SyntheticSide
    trigger_closed_at_ms: int
    earliest_research_at_ms: int
    trigger_close: Decimal
    trigger_level: Decimal
    ema_at_trigger: Decimal
    ema_slope_atr: Decimal
    volume_ratio: Decimal

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False


@dataclass(frozen=True)
class TrendPullbackResearch:
    strategy_id: str
    exchange: str
    symbol: str
    interval: str
    evaluated_candle_count: int
    candidates: tuple[TrendPullbackCandidate, ...]

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False


def research_synthetic_trend_pullbacks(
    candles: tuple[ClosedCandle, ...] | list[ClosedCandle], *,
    config: TrendPullbackConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
) -> TrendPullbackResearch:
    """Trigger only on a close resuming beyond the PRIOR pullback candle.

    LONG: EMA rose over two bars BEFORE the pullback, previous close <= EMA
    (pullback), and current close crosses previous high and current EMA.
    SHORT is symmetric. EMA slope normalized by PREVIOUS ATR, with no
    intrabar/future information. This is a hypothesis, not a calibrated edge.
    """
    if type(config) is not TrendPullbackConfig:
        raise DataValidationError("TrendPullbackConfig required")
    f = compute_synthetic_features(
        candles, config=config.features,
        decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
    )
    out: list[TrendPullbackCandidate] = []
    last_idx: int | None = None
    with localcontext(_MATH_CONTEXT):
        for i in range(3, len(f.rows)):
            if last_idx is not None and i - last_idx <= config.cooldown_bars:
                continue
            # Measure the trend BEFORE the pullback bar; using the pullback
            # in the slope can reverse the sign of a valid correction.
            antecedent, prior2, prior, current = (
                f.rows[i-3], f.rows[i-2], f.rows[i-1], f.rows[i]
            )
            if (antecedent.ema_close is None or prior2.ema_close is None
                    or prior.ema_close is None or current.ema_close is None
                    or prior2.atr_wilder is None or prior2.atr_wilder <= 0
                    or prior.atr_wilder is None or prior.atr_wilder <= 0
                    or current.quote_volume_to_prior_mean is None
                    or current.quote_volume_to_prior_mean < config.min_volume_ratio):
                continue
            slope = (prior2.ema_close - antecedent.ema_close) / prior2.atr_wilder
            # The pullback is fully closed; the trigger uses its fixed high/low.
            if (slope >= config.min_ema_slope_atr
                    and prior.close <= prior.ema_close
                    and current.close > candles[i-1].high
                    and current.close > current.ema_close):
                side = SyntheticSide.LONG
                level = candles[i-1].high
            elif (slope <= -config.min_ema_slope_atr
                    and prior.close >= prior.ema_close
                    and current.close < candles[i-1].low
                    and current.close < current.ema_close):
                side = SyntheticSide.SHORT
                level = candles[i-1].low
            else:
                continue
            if abs(current.close - level) > (
                prior.atr_wilder * config.max_trigger_extension_atr
            ):
                continue
            out.append(TrendPullbackCandidate(
                strategy_id=STRATEGY_ID, exchange=f.exchange, symbol=f.symbol,
                interval=f.interval, side=side,
                trigger_closed_at_ms=current.close_time_ms,
                earliest_research_at_ms=current.close_time_ms + close_safety_ms,
                trigger_close=current.close, trigger_level=level,
                ema_at_trigger=current.ema_close, ema_slope_atr=slope,
                volume_ratio=current.quote_volume_to_prior_mean,
            ))
            last_idx = i
    return TrendPullbackResearch(
        strategy_id=STRATEGY_ID, exchange=f.exchange, symbol=f.symbol,
        interval=f.interval, evaluated_candle_count=len(f.rows),
        candidates=tuple(out),
    )
