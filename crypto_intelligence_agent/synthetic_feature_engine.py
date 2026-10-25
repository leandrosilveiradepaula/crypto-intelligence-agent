"""Causal, decimal-exact-as-represented feature research on SYNTHETIC candles.

This is J2 preparatory math, not a signal engine, historical market dataset,
validated indicator edge, live data adapter or permission to trade. The
only accepted input quality is synthetic_fixture until J1 receives independent
data/provenance/rights validation. No IO, no network, no positions or orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Sequence

from .market_data import (
    MARKET, ClosedCandle, DataGapError, DataValidationError,
    interval_duration_ms, interval_open_aligned,
)

MAX_CANDLES = 10_000
MAX_PERIOD = 500
MAX_DIGITS = 40
MIN_DECIMAL_EXP = -24
MAX_ADJUSTED_EXP = 35
SYNTHETIC_QUALITY = "synthetic_fixture"
_MATH_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class FeatureConfig:
    """Period values are explicit research hypotheses, never trade thresholds."""

    ema_period: int
    atr_period: int
    extrema_period: int
    quote_volume_period: int

    def __post_init__(self) -> None:
        for name in (
            "ema_period", "atr_period", "extrema_period",
            "quote_volume_period",
        ):
            period = getattr(self, name)
            if type(period) is not int or not 2 <= period <= MAX_PERIOD:
                raise DataValidationError(
                    f"{name} must be an integer between 2 and {MAX_PERIOD}"
                )


@dataclass(frozen=True)
class CausalFeatureRow:
    open_time_ms: int
    close_time_ms: int
    close: Decimal
    simple_return: Decimal | None
    ema_close: Decimal | None
    true_range: Decimal
    atr_wilder: Decimal | None
    preceding_high: Decimal | None
    preceding_low: Decimal | None
    quote_volume_to_prior_mean: Decimal | None

    @property
    def approved_for_signals(self) -> bool:
        """Computed values alone never approve a strategy or venue."""
        return False


@dataclass(frozen=True)
class SyntheticFeatureSeries:
    exchange: str
    market: str
    symbol: str
    interval: str
    quality: str
    decision_at_ms: int
    config: FeatureConfig
    rows: tuple[CausalFeatureRow, ...]

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False


def _numeric(value: Decimal, name: str, *, strictly_positive: bool) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise DataValidationError(f"{name} requires finite Decimal, never float")
    t = value.as_tuple()
    if (len(t.digits) > MAX_DIGITS or t.exponent < MIN_DECIMAL_EXP
            or value.adjusted() > MAX_ADJUSTED_EXP):
        raise DataValidationError(f"{name} exceeds supported numeric bounds")
    if value < 0 or (strictly_positive and value == 0):
        raise DataValidationError(f"{name} must be positive or nonnegative")


def _checked_candles(
    candles: Sequence[ClosedCandle], *, decision_at_ms: int, close_safety_ms: int,
) -> tuple[ClosedCandle, ...]:
    if (type(decision_at_ms) is not int or decision_at_ms <= 0
            or type(close_safety_ms) is not int or close_safety_ms < 0
            or close_safety_ms > 86_400_000):
        raise DataValidationError("invalid UTC decision time or close safety")
    if type(candles) not in (tuple, list) or not 1 <= len(candles) <= MAX_CANDLES:
        raise DataValidationError("need 1 to 10000 candles in one ordered sequence")
    first = candles[0]
    if type(first) is not ClosedCandle:
        raise DataValidationError("input must be canonical ClosedCandle values")
    if (first.market != MARKET or first.quality != SYNTHETIC_QUALITY
            or any(type(v) is not str or not v for v in (
                first.exchange, first.symbol, first.interval,
            ))):
        raise DataValidationError("feature research requires one synthetic perpetual series")
    duration = interval_duration_ms(first.interval)
    identity = (first.exchange, first.market, first.symbol, first.interval, first.quality)
    previous_open = None
    for c in candles:
        if type(c) is not ClosedCandle:
            raise DataValidationError("mixed or arbitrary candle objects")
        if (c.exchange, c.market, c.symbol, c.interval, c.quality) != identity:
            raise DataValidationError("cannot mix venues, assets, intervals or quality")
        if (type(c.open_time_ms) is not int or type(c.close_time_ms) is not int
                or not interval_open_aligned(c.interval, c.open_time_ms)
                or c.close_time_ms != c.open_time_ms + duration - 1):
            raise DataValidationError("candle does not satisfy its closed UTC interval")
        if c.close_time_ms + close_safety_ms > decision_at_ms:
            raise DataValidationError("future or unclosed candle at research decision")
        if previous_open is not None and c.open_time_ms != previous_open + duration:
            raise DataGapError("non-contiguous or duplicated candles in feature history")
        previous_open = c.open_time_ms
        for field in ("open", "high", "low", "close"):
            _numeric(getattr(c, field), field, strictly_positive=True)
        for field in ("base_volume", "quote_volume"):
            _numeric(getattr(c, field), field, strictly_positive=False)
        if c.high < max(c.open, c.close, c.low) or c.low > min(c.open, c.close, c.high):
            raise DataValidationError("invalid high/low ordering")
    return tuple(candles)


def compute_synthetic_features(
    candles: Sequence[ClosedCandle],
    *,
    config: FeatureConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
) -> SyntheticFeatureSeries:
    """Compute causal values using only current/past closed synthetic candles.

    EMA seeds with SMA of the first N closes (not with close[0]).
    True range at index zero is high-low; afterwards it also considers the
    distance from previous close. Wilder ATR seeds with SMA of N true ranges.
    Extrema and average quote volume use the PREVIOUS N candles, not current.
    Warm-up or undefined zero-volume denominators yield None, never fake zero.
    Precision is a fixed 50-digit decimal context, independent of globals.
    """
    if type(config) is not FeatureConfig:
        raise DataValidationError("an explicit FeatureConfig is required")
    cs = _checked_candles(
        candles, decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
    )
    rows: list[CausalFeatureRow] = []
    with localcontext(_MATH_CONTEXT):
        alpha = Decimal(2) / Decimal(config.ema_period + 1)
        ema: Decimal | None = None
        atr: Decimal | None = None
        ranges: list[Decimal] = []
        for i, c in enumerate(cs):
            last_close = cs[i - 1].close if i else None
            simple_return = ((c.close / last_close) - 1) if last_close is not None else None
            true_range = (c.high - c.low) if last_close is None else max(
                c.high - c.low, abs(c.high - last_close), abs(c.low - last_close),
            )
            ranges.append(true_range)
            ep = config.ema_period
            if i == ep - 1:
                ema = sum((row.close for row in cs[:ep]), Decimal(0)) / Decimal(ep)
            elif i >= ep:
                assert ema is not None
                ema = ema + alpha * (c.close - ema)
            ap = config.atr_period
            if i == ap - 1:
                atr = sum(ranges[:ap], Decimal(0)) / Decimal(ap)
            elif i >= ap:
                assert atr is not None
                atr = (atr * Decimal(ap - 1) + true_range) / Decimal(ap)

            high = low = ratio = None
            xp = config.extrema_period
            if i >= xp:
                prior = cs[i - xp:i]
                high = max(prev.high for prev in prior)
                low = min(prev.low for prev in prior)
            vp = config.quote_volume_period
            if i >= vp:
                prior_total = sum(
                    (prev.quote_volume for prev in cs[i - vp:i]), Decimal(0),
                )
                if prior_total > 0:
                    ratio = c.quote_volume / (prior_total / Decimal(vp))
            rows.append(CausalFeatureRow(
                open_time_ms=c.open_time_ms,
                close_time_ms=c.close_time_ms,
                close=c.close,
                simple_return=simple_return,
                ema_close=ema,
                true_range=true_range,
                atr_wilder=atr,
                preceding_high=high,
                preceding_low=low,
                quote_volume_to_prior_mean=ratio,
            ))
    return SyntheticFeatureSeries(
        exchange=cs[0].exchange, market=cs[0].market,
        symbol=cs[0].symbol, interval=cs[0].interval,
        quality=SYNTHETIC_QUALITY, decision_at_ms=decision_at_ms,
        config=config, rows=tuple(rows),
    )
