"""D435: mathematical research on unverified public Bybit closed candles.

Separate from synthetic data validation, AUTO2, RiskGate, fill modelling and
real-money orders. A *hypothesis* is never an entry recommendation or signal.
Only the newest fully closed candle is classified at each decision timestamp.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from types import SimpleNamespace

from .j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from .market_data import (
    ClosedCandle, DataGapError, DataValidationError, MARKET,
    interval_open_aligned,
)
from .synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, _prior_atr_means,
)
from .synthetic_feature_engine import (
    CausalFeatureRow, MAX_CANDLES, _MATH_CONTEXT, _numeric,
)
from .synthetic_position_state import SyntheticSide
from .j2_configurable_indicators_d513 import combination_directions

_QUALITY = "bybit_public_ws_confirmed_unverified"
_REST_HISTORICAL_QUALITY = "bybit_public_rest_historical_closed_unverified"
_MIXED_STATUS = "research_only_mixed_rest24_ws1_closed_series"
_STATUS = "research_only_public_closed_series"
_HOUR_MS = 3_600_000


@dataclass(frozen=True)
class ObservedBybitHypothesis:
    side: SyntheticSide
    closed_at_ms: int
    earliest_research_at_ms: int
    close: Decimal
    prior_breakout_level: Decimal | None
    ema_close: Decimal | None
    atr_compression_ratio: Decimal | None
    quote_volume_to_prior_mean: Decimal
    journal_digest_sha256: str
    entry_rule: str = "breakout"

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


@dataclass(frozen=True)
class ObservedBybitResearch:
    status: str
    evaluated_candle_count: int
    hypotheses: tuple[ObservedBybitHypothesis, ...]
    journal_digest_sha256: str

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def _validated_observed_candles(
    series: BybitClosedResearchSeries, *,
    decision_at_ms: int, close_safety_ms: int,
    allow_rest_historical_research: bool = False,
    allow_causal_rest_ws_warmup: bool = False,
) -> tuple[ClosedCandle, ...]:
    if (type(series) is not BybitClosedResearchSeries
            or series.status not in (
                (_STATUS, _MIXED_STATUS) if allow_causal_rest_ws_warmup
                else (_STATUS,)
            )
            or type(decision_at_ms) is not int or decision_at_ms <= 0
            or type(close_safety_ms) is not int
            or type(allow_rest_historical_research) is not bool
            or type(allow_causal_rest_ws_warmup) is not bool
            or (allow_rest_historical_research and allow_causal_rest_ws_warmup)
            or not 1 <= close_safety_ms <= 60_000):
        raise DataValidationError("observed J2 research needs a valid typed decision")
    if (type(series.journal_digest_sha256) is not str
            or len(series.journal_digest_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in series.journal_digest_sha256)
            or type(series.scope_registry_sha256) is not str
            or len(series.scope_registry_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in series.scope_registry_sha256)):
        raise DataValidationError("observed research requires journal and PIT digests")
    candles = series.candles
    if type(candles) is not tuple or not 24 <= len(candles) <= MAX_CANDLES:
        raise DataGapError("observed J2 research requires bounded 24h+ history")
    first = candles[0]
    if type(first) is not ClosedCandle:
        raise DataValidationError("observed J2 candles must be canonical")
    identity = (first.exchange, first.market, first.symbol, first.interval)
    mixed = allow_causal_rest_ws_warmup and series.status == _MIXED_STATUS
    if mixed:
        if (not 25 <= len(candles) <= 123
                or any(c.quality != _REST_HISTORICAL_QUALITY
                       for c in candles[:-1])
                or candles[-1].quality != _QUALITY):
            raise DataValidationError("D462 requires 24 REST historical and final WS confirmed")
    allowed_quality = (
        (_REST_HISTORICAL_QUALITY,) if mixed else
        (_QUALITY, _REST_HISTORICAL_QUALITY)
        if allow_rest_historical_research else (_QUALITY,)
    )
    if (first.exchange != "bybit_v5_public" or first.market != MARKET
            or first.interval != "1h" or first.quality not in allowed_quality
            or not first.symbol.endswith("USDT")):
        raise DataValidationError("observed J2 source is not supported")
    for i, c in enumerate(candles):
        if type(c) is not ClosedCandle or (
            c.exchange, c.market, c.symbol, c.interval
        ) != identity or (
            not mixed and c.quality != first.quality
        ):
            raise DataValidationError("observed J2 mixed series identity")
        if (type(c.open_time_ms) is not int
                or type(c.close_time_ms) is not int
                or not interval_open_aligned("1h", c.open_time_ms)
                or c.close_time_ms != c.open_time_ms + _HOUR_MS - 1
                or c.close_time_ms + close_safety_ms > decision_at_ms):
            raise DataValidationError("observed candle is future, open or off-grid")
        if i and c.open_time_ms != candles[i - 1].open_time_ms + _HOUR_MS:
            raise DataGapError("observed research has a gap or duplicate candle")
        for key in ("open", "high", "low", "close"):
            _numeric(getattr(c, key), key, strictly_positive=True)
        for key in ("base_volume", "quote_volume"):
            _numeric(getattr(c, key), key, strictly_positive=False)
        if c.high < max(c.open, c.close, c.low) or c.low > min(
            c.open, c.close, c.high
        ):
            raise DataValidationError("observed OHLC prices are inconsistent")
    if candles[-1].close_time_ms + close_safety_ms != decision_at_ms:
        raise DataGapError("observed research decision does not match last closed hour")
    return candles


def evaluate_observed_bybit_research(
    series: BybitClosedResearchSeries, *,
    config: CompressionBreakoutConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1,
    allow_rest_historical_research: bool = False,
    allow_causal_rest_ws_warmup: bool = False,
) -> ObservedBybitResearch:
    """Research the latest completed candle without granting an AUTO2 signal.

    J2 indicator definitions match the synthetic engine: SMA-seeded EMA,
    Wilder ATR, preceding (exclusive) extrema and quote-volume mean. Compression
    windows use only ATR values BEFORE the candidate. Cooldown accounts for
    earlier historical hypotheses but these are never returned as current.
    """
    if type(config) is not CompressionBreakoutConfig:
        raise DataValidationError("explicit J2 compression config required")
    cs = _validated_observed_candles(
        series, decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
        allow_rest_historical_research=allow_rest_historical_research,
        allow_causal_rest_ws_warmup=allow_causal_rest_ws_warmup,
    )
    custom = config.entry_mode == "indicator_combo"
    if custom and len(cs) < config.indicators.minimum_closed_bars(
            config.features.quote_volume_period):
        return ObservedBybitResearch(
            status="observed_no_hypothesis",
            evaluated_candle_count=len(cs), hypotheses=(),
            journal_digest_sha256=series.journal_digest_sha256,
        )
    custom_states = combination_directions(cs, config.indicators) if custom else ()
    rows: list[CausalFeatureRow] = []
    cross_periods = (
        config.ema_cross_periods if config.entry_mode == "ema_cross" else ()
    )
    cross_state: list[Decimal | None] = [None for _ in cross_periods]
    cross_history: list[tuple[Decimal | None, ...]] = []
    with localcontext(_MATH_CONTEXT):
        ema: Decimal | None = None
        atr: Decimal | None = None
        alpha = Decimal(2) / Decimal(config.features.ema_period + 1)
        ranges: list[Decimal] = []
        for i, c in enumerate(cs):
            previous_close = cs[i - 1].close if i else None
            simple_return = (
                c.close / previous_close - 1 if previous_close is not None else None
            )
            true_range = (
                c.high - c.low if previous_close is None else max(
                    c.high - c.low, abs(c.high - previous_close),
                    abs(c.low - previous_close),
                )
            )
            ranges.append(true_range)
            # D503: SMA-seeded, causal EMA history, no future candles or float.
            for index, period in enumerate(cross_periods):
                if i == period - 1:
                    cross_state[index] = (
                        sum((x.close for x in cs[:period]), Decimal(0))
                        / Decimal(period)
                    )
                elif i >= period:
                    alpha_cross = Decimal(2) / Decimal(period + 1)
                    cross_state[index] = (
                        cross_state[index] + alpha_cross
                        * (c.close - cross_state[index])
                    )
            cross_history.append(tuple(cross_state))
            ep = config.features.ema_period
            ap = config.features.atr_period
            if i == ep - 1:
                ema = sum((x.close for x in cs[:ep]), Decimal(0)) / Decimal(ep)
            elif i >= ep:
                ema = ema + alpha * (c.close - ema)
            if i == ap - 1:
                atr = sum(ranges[:ap], Decimal(0)) / Decimal(ap)
            elif i >= ap:
                atr = (atr * Decimal(ap - 1) + true_range) / Decimal(ap)
            xp = config.features.extrema_period
            vp = config.features.quote_volume_period
            high = low = volume_ratio = None
            if i >= xp:
                prior = cs[i - xp:i]
                high = max(x.high for x in prior)
                low = min(x.low for x in prior)
            if i >= vp:
                total = sum((x.quote_volume for x in cs[i - vp:i]), Decimal(0))
                if total > 0:
                    volume_ratio = c.quote_volume / (total / Decimal(vp))
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
                quote_volume_to_prior_mean=volume_ratio,
            ))
        # _prior_atr_means uses only .rows; never create a synthetic
        # feature series or reclassify observed market quality as synthetic.
        feature_view = SimpleNamespace(rows=tuple(rows))
        last_emitted_index: int | None = None
        current: list[ObservedBybitHypothesis] = []
        for i, row in enumerate(rows):
            if (last_emitted_index is not None
                    and i - last_emitted_index <= config.cooldown_bars):
                continue
            if (row.quote_volume_to_prior_mean is None
                    or row.quote_volume_to_prior_mean < config.min_quote_volume_ratio):
                continue
            prior_means = _prior_atr_means(feature_view, i, config)
            # ATR compression is mandatory only for legacy breakout.
            # In EMA-cross, unavailable ATR history is a nullable
            # observation, never a veto or a fabricated numeric ratio.
            if prior_means is None:
                if config.entry_mode == "breakout":
                    continue
                ratio = None
            else:
                recent, baseline = prior_means
                ratio = recent / baseline
            if custom:
                if (i == 0 or custom_states[i] not in (1, -1)
                        or custom_states[i - 1] is None
                        or custom_states[i - 1] == custom_states[i]):
                    continue
                side = SyntheticSide.LONG if custom_states[i] == 1 else SyntheticSide.SHORT
                breakout = None
                ema_reference = None
                ratio = None
            elif config.entry_mode == "ema_cross":
                # A latest-bar EMA fast/mid crossing requires the close on
                # the same side of a third, independently configured EMA.
                # Breakout and ATR-compression gates do not apply here.
                if i < cross_periods[-1] + 1:
                    continue
                previous = cross_history[i - 1]
                current_cross_emas = cross_history[i]
                if any(v is None for v in previous + current_cross_emas):
                    continue
                fast, middle, trend = current_cross_emas
                was_fast, was_middle, _ = previous
                if was_fast <= was_middle and fast > middle and row.close > trend:
                    side = SyntheticSide.LONG
                elif was_fast >= was_middle and fast < middle and row.close < trend:
                    side = SyntheticSide.SHORT
                else:
                    continue
                breakout = (
                    row.preceding_high if side is SyntheticSide.LONG
                    else row.preceding_low
                )
                ema_reference = row.ema_close if row.ema_close is not None else trend
            else:
                if (row.ema_close is None or row.preceding_high is None
                        or row.preceding_low is None
                        or ratio is None or ratio > config.max_atr_ratio):
                    continue
                if row.close > row.preceding_high and row.close > row.ema_close:
                    side, breakout = SyntheticSide.LONG, row.preceding_high
                elif row.close < row.preceding_low and row.close < row.ema_close:
                    side, breakout = SyntheticSide.SHORT, row.preceding_low
                else:
                    continue
                ema_reference = row.ema_close
            last_emitted_index = i
            if i == len(rows) - 1:
                current.append(ObservedBybitHypothesis(
                    side=side,
                    closed_at_ms=row.close_time_ms,
                    earliest_research_at_ms=row.close_time_ms + close_safety_ms,
                    close=row.close,
                    prior_breakout_level=breakout,
                    ema_close=ema_reference,
                    atr_compression_ratio=ratio,
                    quote_volume_to_prior_mean=row.quote_volume_to_prior_mean,
                    journal_digest_sha256=series.journal_digest_sha256,
                    entry_rule=config.entry_mode,
                ))
    return ObservedBybitResearch(
        status=("observed_hypothesis_not_authorized"
                if current else "observed_no_hypothesis"),
        evaluated_candle_count=len(rows),
        hypotheses=tuple(current),
        journal_digest_sha256=series.journal_digest_sha256,
    )
