"""J2/PRE2: causal compression/breakout HYPOTHESES on synthetic candles only.

This research evaluator is NOT a signal approval, trading strategy, forecast,
risk gate, order-intent generator, market-feed adapter or profitability claim.
It reuses PRE1 indicators and never accesses an exchange, database or network.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .market_data import ClosedCandle, DataValidationError
from .synthetic_feature_engine import (
    FeatureConfig, SyntheticFeatureSeries, _MATH_CONTEXT, _numeric,
    compute_synthetic_features,
)
from .synthetic_position_state import SyntheticSide


MAX_LOOKBACK = 500
MAX_COOLDOWN = 500
STRATEGY_ID = "synthetic_compression_breakout_v1"


@dataclass(frozen=True)
class CompressionBreakoutConfig:
    """Explicit research assumptions, NOT optimized trading parameters."""

    features: FeatureConfig
    compression_bars: int
    baseline_bars: int
    max_atr_ratio: Decimal
    min_quote_volume_ratio: Decimal
    cooldown_bars: int = 0

    def __post_init__(self) -> None:
        if type(self.features) is not FeatureConfig:
            raise DataValidationError("PRE1 FeatureConfig is required")
        for key in ("compression_bars", "baseline_bars"):
            value = getattr(self, key)
            if type(value) is not int or not 2 <= value <= MAX_LOOKBACK:
                raise DataValidationError(f"{key} must be integer 2..500")
        if type(self.cooldown_bars) is not int or not 0 <= self.cooldown_bars <= MAX_COOLDOWN:
            raise DataValidationError("cooldown_bars must be integer 0..500")
        _numeric(self.max_atr_ratio, "max_atr_ratio", strictly_positive=True)
        if self.max_atr_ratio > Decimal(1):
            raise DataValidationError("compression ratio threshold must be <= 1")
        _numeric(
            self.min_quote_volume_ratio, "min_quote_volume_ratio",
            strictly_positive=True,
        )
        if self.min_quote_volume_ratio < Decimal(1):
            raise DataValidationError("volume multiplier must be >= 1")


@dataclass(frozen=True)
class SyntheticEntryCandidate:
    """A historical fixture observation, NEVER an order or calibrated probability."""

    strategy_id: str
    exchange: str
    symbol: str
    interval: str
    side: SyntheticSide
    closed_at_ms: int
    earliest_research_at_ms: int
    close: Decimal
    prior_breakout_level: Decimal
    ema_close: Decimal
    atr_recent_mean: Decimal
    atr_baseline_mean: Decimal
    atr_compression_ratio: Decimal
    volume_to_prior_mean: Decimal

    @property
    def quality(self) -> str:
        return "synthetic_fixture_hypothesis_only"

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


@dataclass(frozen=True)
class SyntheticEntryResearch:
    strategy_id: str
    exchange: str
    symbol: str
    interval: str
    decision_at_ms: int
    close_safety_ms: int
    config: CompressionBreakoutConfig
    evaluated_candle_count: int
    candidates: tuple[SyntheticEntryCandidate, ...]

    @property
    def quality(self) -> str:
        return "synthetic_fixture_hypothesis_only"

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def _prior_atr_means(
    series: SyntheticFeatureSeries, i: int, config: CompressionBreakoutConfig,
) -> tuple[Decimal, Decimal] | None:
    """Return prior compressed/baseline ATR means, EXCLUDING candidate candle.

    The baseline window precedes the compressed window without overlap.
    Missing/zero ATR fails closed rather than fabricating compression.
    """
    recent_start = i - config.compression_bars
    baseline_start = recent_start - config.baseline_bars
    if baseline_start < 0:
        return None
    baseline = series.rows[baseline_start:recent_start]
    recent = series.rows[recent_start:i]
    values = [r.atr_wilder for r in (*baseline, *recent)]
    if any(x is None or x <= 0 for x in values):
        return None
    b_mean = sum((r.atr_wilder for r in baseline), Decimal(0)) / Decimal(len(baseline))
    r_mean = sum((r.atr_wilder for r in recent), Decimal(0)) / Decimal(len(recent))
    if b_mean <= 0 or r_mean <= 0:
        return None
    return r_mean, b_mean


def research_synthetic_compression_breakouts(
    candles: tuple[ClosedCandle, ...] | list[ClosedCandle],
    *,
    config: CompressionBreakoutConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
) -> SyntheticEntryResearch:
    """Evaluate one explicitly configured, long/short, causal hypothesis.

    A close strictly crossing the HIGH/LOW of preceding candles and on the
    matching EMA side is considered only when PREVIOUS ATR bars are compressed
    relative to an earlier baseline and quote-volume ratio meets its minimum.
    The candidate candle never enters either compression ATR window. All
    candles must be closed synthetic fixtures; historical listings, rights and
    real economic OHLCV are deliberately outside this module.

    Cooldown suppresses candidates within N later candles of ANY prior emitted
    candidate; it is NOT a position or trading exposure limiter.
    """
    if type(config) is not CompressionBreakoutConfig:
        raise DataValidationError("explicit CompressionBreakoutConfig required")
    features = compute_synthetic_features(
        candles, config=config.features,
        decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
    )
    candidates: list[SyntheticEntryCandidate] = []
    last_emitted_index: int | None = None
    with localcontext(_MATH_CONTEXT):
        for i, row in enumerate(features.rows):
            if (last_emitted_index is not None
                    and i - last_emitted_index <= config.cooldown_bars):
                continue
            if (row.ema_close is None or row.preceding_high is None
                    or row.preceding_low is None
                    or row.quote_volume_to_prior_mean is None
                    or row.quote_volume_to_prior_mean < config.min_quote_volume_ratio):
                continue
            prior = _prior_atr_means(features, i, config)
            if prior is None:
                continue
            recent, baseline = prior
            ratio = recent / baseline
            if ratio > config.max_atr_ratio:
                continue
            if row.close > row.preceding_high and row.close > row.ema_close:
                direction = SyntheticSide.LONG
                level = row.preceding_high
            elif row.close < row.preceding_low and row.close < row.ema_close:
                direction = SyntheticSide.SHORT
                level = row.preceding_low
            else:
                continue
            candidates.append(SyntheticEntryCandidate(
                strategy_id=STRATEGY_ID,
                exchange=features.exchange, symbol=features.symbol,
                interval=features.interval, side=direction,
                closed_at_ms=row.close_time_ms,
                earliest_research_at_ms=row.close_time_ms + close_safety_ms,
                close=row.close, prior_breakout_level=level,
                ema_close=row.ema_close,
                atr_recent_mean=recent, atr_baseline_mean=baseline,
                atr_compression_ratio=ratio,
                volume_to_prior_mean=row.quote_volume_to_prior_mean,
            ))
            last_emitted_index = i
    return SyntheticEntryResearch(
        strategy_id=STRATEGY_ID,
        exchange=features.exchange, symbol=features.symbol,
        interval=features.interval, decision_at_ms=decision_at_ms,
        close_safety_ms=close_safety_ms, config=config,
        evaluated_candle_count=len(features.rows), candidates=tuple(candidates),
    )
