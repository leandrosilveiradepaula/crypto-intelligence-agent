"""J2/PRE3: BTC regime and relative-strength RESEARCH on synthetic candles only.

Neither price history nor hypotheses are real/authenticated. All decisions are
made from two independent, strictly closed, gapless synthetic series at the
SAME ending UTC candle, without alignment by forward fill. There is no IO,
market data API, signal, order, leverage decision, or performance claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_feature_engine import (
    FeatureConfig, _MATH_CONTEXT, _numeric, compute_synthetic_features,
)


class HypotheticalBtcRegime(str, Enum):
    INSUFFICIENT_HISTORY = "insufficient_history"
    VOLATILITY_STRESS = "volatility_stress"
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    SIDEWAYS = "sideways"


@dataclass(frozen=True)
class BtcRelativeConfig:
    features: FeatureConfig
    momentum_bars: int
    btc_trend_threshold: Decimal
    btc_atr_stress_ratio: Decimal

    def __post_init__(self) -> None:
        if type(self.features) is not FeatureConfig:
            raise DataValidationError("explicit FeatureConfig required")
        if type(self.momentum_bars) is not int or not 2 <= self.momentum_bars <= 500:
            raise DataValidationError("momentum_bars must be integer 2..500")
        _numeric(self.btc_trend_threshold, "btc_trend_threshold",
                 strictly_positive=True)
        _numeric(self.btc_atr_stress_ratio, "btc_atr_stress_ratio",
                 strictly_positive=True)
        if self.btc_trend_threshold > Decimal(1):
            raise DataValidationError("trend threshold must not exceed 1")
        if self.btc_atr_stress_ratio > Decimal(1):
            raise DataValidationError("ATR stress ratio must not exceed 1")


@dataclass(frozen=True)
class SyntheticBtcRelativeObservation:
    exchange: str
    btc_symbol: str
    asset_symbol: str
    interval: str
    closed_at_ms: int
    earliest_research_at_ms: int
    decision_at_ms: int
    regime: HypotheticalBtcRegime
    btc_momentum: Decimal | None
    asset_momentum: Decimal | None
    relative_strength: Decimal | None
    btc_atr_to_close: Decimal | None
    overlapping_candles: int

    @property
    def quality(self) -> str:
        return "synthetic_fixture_hypothesis_only"

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def research_synthetic_btc_relative_regime(
    btc_candles: Sequence[ClosedCandle],
    asset_candles: Sequence[ClosedCandle],
    *,
    config: BtcRelativeConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
    btc_symbol: str = "BTCUSDT",
) -> SyntheticBtcRelativeObservation:
    """One causally available, same-venue and same-hour research observation.

    Momentum is close_t / close_(t-N) - 1 for each asset, with the same UTC
    endpoints. Relative strength is asset momentum minus BTC momentum (not a
    calibrated alpha). Stress takes priority over directional regime when
    Wilder ATR / BTC close is above the hypothetical threshold.

    BTC may have an earlier history than the candidate; matching history
    is aligned by time, never by index or by filling missing bars. If
    histories have no common last closed hour or a missing internal hour,
    the request is rejected rather than presenting a stale BTC regime.
    """
    if type(config) is not BtcRelativeConfig:
        raise DataValidationError("explicit BtcRelativeConfig required")
    if type(btc_symbol) is not str or btc_symbol != "BTCUSDT":
        raise DataValidationError("BTC benchmark identity must be explicit BTCUSDT")

    btc = compute_synthetic_features(
        btc_candles, config=config.features,
        decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
    )
    asset = compute_synthetic_features(
        asset_candles, config=config.features,
        decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
    )
    if btc.symbol != btc_symbol or asset.symbol == btc_symbol:
        raise DataValidationError("BTC benchmark and non-BTC asset required")
    if (btc.exchange != asset.exchange or btc.market != asset.market
            or btc.interval != asset.interval or btc.quality != asset.quality):
        raise DataValidationError("BTC and asset must share venue, market, interval and quality")
    if btc.rows[-1].close_time_ms != asset.rows[-1].close_time_ms:
        raise DataValidationError("BTC and asset last closed UTC candle must agree")

    btc_by_end = {row.close_time_ms: row for row in btc.rows}
    # All overlapping closed bars must match. Prior unmatched BTC bars are
    # legal; an asset internal gap was rejected by PRE1 before reaching here.
    common = [row for row in asset.rows if row.close_time_ms in btc_by_end]
    if not common or common[-1].close_time_ms != asset.rows[-1].close_time_ms:
        raise DataValidationError("no common latest closed UTC candle")
    if len(common) != min(len(btc.rows), len(asset.rows)):
        raise DataValidationError("aligned synthetic series contain an unmatched internal hour")

    latest = common[-1]
    regime = HypotheticalBtcRegime.INSUFFICIENT_HISTORY
    btc_return = asset_return = relative = atr_ratio = None
    with localcontext(_MATH_CONTEXT):
        btc_now = btc_by_end[latest.close_time_ms]
        if btc_now.atr_wilder is not None:
            atr_ratio = btc_now.atr_wilder / btc_now.close
        n = config.momentum_bars
        if len(common) > n and atr_ratio is not None:
            earlier = common[-n - 1]
            btc_then = btc_by_end[earlier.close_time_ms]
            btc_return = btc_now.close / btc_then.close - Decimal(1)
            asset_return = latest.close / earlier.close - Decimal(1)
            relative = asset_return - btc_return
            if atr_ratio >= config.btc_atr_stress_ratio:
                regime = HypotheticalBtcRegime.VOLATILITY_STRESS
            elif btc_return >= config.btc_trend_threshold:
                regime = HypotheticalBtcRegime.UPTREND
            elif btc_return <= -config.btc_trend_threshold:
                regime = HypotheticalBtcRegime.DOWNTREND
            else:
                regime = HypotheticalBtcRegime.SIDEWAYS

    return SyntheticBtcRelativeObservation(
        exchange=btc.exchange,
        btc_symbol=btc_symbol,
        asset_symbol=asset.symbol,
        interval=btc.interval,
        closed_at_ms=latest.close_time_ms,
        earliest_research_at_ms=latest.close_time_ms + close_safety_ms,
        decision_at_ms=decision_at_ms,
        regime=regime, btc_momentum=btc_return, asset_momentum=asset_return,
        relative_strength=relative, btc_atr_to_close=atr_ratio,
        overlapping_candles=len(common),
    )
