"""D513: independent moving averages and causal pivot-band trend research.

Original implementation of the published mathematical idea of Pivot Point
SuperTrend (LonesomeTheBlue, TradingView, 2020). Strict extrema and neutral
initialization are explicit choices, not a claim of exact Pine parity.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from .market_data import ClosedCandle, DataValidationError
from .synthetic_feature_engine import _MATH_CONTEXT


@dataclass(frozen=True)
class MovingAverageSlot:
    enabled: bool
    period: int

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.period) is not int
                or not 2 <= self.period <= 120):
            raise DataValidationError("D513 moving average needs bool and period 2..120")


@dataclass(frozen=True)
class PivotSuperTrend:
    enabled: bool
    pivot_period: int
    atr_period: int
    atr_factor: Decimal

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.pivot_period) is not int
                or not 1 <= self.pivot_period <= 50
                or type(self.atr_period) is not int or not 1 <= self.atr_period <= 120
                or type(self.atr_factor) is not Decimal or not self.atr_factor.is_finite()
                or not Decimal("0.1") <= self.atr_factor <= Decimal(100)
                or self.atr_factor.as_tuple().exponent < -6):
            raise DataValidationError("D513 invalid Pivot SuperTrend parameters")


@dataclass(frozen=True)
class BollingerBands:
    """D521 population standard deviation of N closed prices; optional gate."""
    enabled: bool
    period: int = 20
    deviations: Decimal = Decimal(2)
    mode: str = "breakout"

    def __post_init__(self):
        if (type(self.enabled) is not bool
                or type(self.period) is not int or not 2 <= self.period <= 120
                or type(self.deviations) is not Decimal
                or not self.deviations.is_finite()
                or not Decimal("0.1") <= self.deviations <= Decimal(10)
                or self.deviations.as_tuple().exponent < -6
                or type(self.mode) is not str or self.mode not in ("breakout", "reentry")):
            raise DataValidationError("D521 invalid Bollinger configuration")

    def as_json(self):
        return {"enabled": self.enabled, "period": self.period,
                "deviations": format(self.deviations, "f"), "mode": self.mode}


def parse_bollinger(value):
    if (type(value) is not dict or set(value) != {"enabled", "period", "deviations", "mode"}
            or type(value["deviations"]) is not str or not 1 <= len(value["deviations"]) <= 24):
        raise DataValidationError("D521 exact Bollinger settings required")
    try:
        deviations = Decimal(value["deviations"])
    except InvalidOperation as exc:
        raise DataValidationError("D521 invalid Bollinger deviations") from exc
    return BollingerBands(value["enabled"], value["period"], deviations, value["mode"])


@dataclass(frozen=True)
class RelativeStrengthIndex:
    """Wilder RSI of the asset, not its performance relative to BTC.

    Directional momentum zone: long_min < RSI <= long_max;
    SHORT uses the mirrored zone. RSI 50 is neutral.
    """
    enabled: bool
    period: int = 14
    long_min: int = 50
    long_max: int = 70

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.period) is not int
                or not 2 <= self.period <= 120
                or type(self.long_min) is not int or type(self.long_max) is not int
                or not 50 <= self.long_min < self.long_max <= 100):
            raise DataValidationError("D523 invalid asset RSI configuration")

    def as_json(self):
        return {"enabled": self.enabled, "period": self.period,
                "long_min": self.long_min, "long_max": self.long_max}


def parse_rsi(value):
    if type(value) is not dict or set(value) != {"enabled", "period", "long_min", "long_max"}:
        raise DataValidationError("D523 exact asset RSI settings required")
    return RelativeStrengthIndex(value["enabled"], value["period"],
                                 value["long_min"], value["long_max"])


def wilder_rsi(closes: tuple[Decimal, ...], config: RelativeStrengthIndex):
    """Causal SMA seed over N changes, then Wilder smoothing; flat = 50."""
    if type(config) is not RelativeStrengthIndex:
        raise DataValidationError("D523 typed asset RSI configuration required")
    n = config.period
    result = []
    gain = loss = Decimal(0)
    zero = Decimal(0)
    with localcontext(_MATH_CONTEXT):
        for i, close in enumerate(closes):
            if i == 0:
                result.append(None)
                continue
            change = close - closes[i-1]
            up, down = max(zero, change), max(zero, -change)
            if i <= n:
                gain += up
                loss += down
                if i < n:
                    result.append(None)
                    continue
                gain /= n
                loss /= n
            else:
                gain = (gain*(n-1)+up)/n
                loss = (loss*(n-1)+down)/n
            value = Decimal(50) if gain == loss == 0 else Decimal(100)*gain/(gain+loss)
            # Stable inclusive/exclusive zone boundaries despite repeating
            # decimal Wilder averages. Resolution is explicit, not a tick size.
            result.append(value.quantize(Decimal("0.000000000001")))
    return tuple(result)


def rsi_directions(closes: tuple[Decimal, ...], config: RelativeStrengthIndex):
    return tuple(None if v is None else
                 1 if config.long_min < v <= config.long_max else
                 -1 if 100-config.long_max <= v < 100-config.long_min else 0
                 for v in wilder_rsi(closes, config))


@dataclass(frozen=True)
class IndicatorSelection:
    ema: tuple[MovingAverageSlot, ...]
    sma: tuple[MovingAverageSlot, ...]
    pivot_supertrend: PivotSuperTrend
    # None means the legacy profile has no Bollinger field. Preserve its JSON.
    bollinger: BollingerBands | None = None
    rsi: RelativeStrengthIndex | None = None

    def __post_init__(self):
        for slots in (self.ema, self.sma):
            if (type(slots) is not tuple or len(slots) != 3
                    or any(type(x) is not MovingAverageSlot for x in slots)):
                raise DataValidationError("D513 three independent slots per MA family required")
            periods = tuple(x.period for x in slots if x.enabled)
            if any(a >= b for a, b in zip(periods, periods[1:])):
                raise DataValidationError("D513 enabled periods must increase within each MA family")
        if type(self.pivot_supertrend) is not PivotSuperTrend:
            raise DataValidationError("D513 explicit pivot parameters required")
        if self.bollinger is not None and type(self.bollinger) is not BollingerBands:
            raise DataValidationError("D521 typed Bollinger parameters required")
        if self.rsi is not None and type(self.rsi) is not RelativeStrengthIndex:
            raise DataValidationError("D523 typed asset RSI parameters required")

    @property
    def active(self) -> bool:
        return (any(x.enabled for x in self.ema + self.sma)
                or self.pivot_supertrend.enabled
                or (self.bollinger is not None and self.bollinger.enabled)
                or (self.rsi is not None and self.rsi.enabled))

    def minimum_closed_bars(self, volume_period: int) -> int:
        if not self.active:
            return 24
        periods = [x.period + 2 for x in self.ema + self.sma if x.enabled]
        pivot = self.pivot_supertrend
        if pivot.enabled:
            periods.append(max(2 * pivot.pivot_period + 3, pivot.atr_period + 2))
        if self.bollinger is not None and self.bollinger.enabled:
            periods.append(self.bollinger.period + 2)
        if self.rsi is not None and self.rsi.enabled:
            periods.append(self.rsi.period + 2)
        return max(24, volume_period + 1, *periods)

    def as_json(self) -> dict:
        def slots(values):
            return [{"enabled": x.enabled, "period": x.period} for x in values]
        p = self.pivot_supertrend
        result = {"ema": slots(self.ema), "sma": slots(self.sma),
                "pivot_supertrend": {"enabled": p.enabled, "pivot_period": p.pivot_period,
                                     "atr_period": p.atr_period,
                                     "atr_factor": format(p.atr_factor, "f")}}
        if self.bollinger is not None:
            result["bollinger"] = self.bollinger.as_json()
        if self.rsi is not None:
            result["rsi"] = self.rsi.as_json()
        return result


def parse_indicator_selection(value: object) -> IndicatorSelection:
    legacy = {"ema", "sma", "pivot_supertrend"}
    if (type(value) is not dict or not legacy <= set(value)
            or set(value) - (legacy | {"bollinger", "rsi"})):
        raise DataValidationError("D513 exact indicator selection required")
    def slots(name):
        rows = value[name]
        if type(rows) is not list or len(rows) != 3:
            raise DataValidationError("D513 three slots required")
        out = []
        for row in rows:
            if type(row) is not dict or set(row) != {"enabled", "period"}:
                raise DataValidationError("D513 invalid moving average slot")
            out.append(MovingAverageSlot(row["enabled"], row["period"]))
        return tuple(out)
    p = value["pivot_supertrend"]
    if type(p) is not dict or set(p) != {"enabled", "pivot_period", "atr_period", "atr_factor"}:
        raise DataValidationError("D513 invalid pivot settings")
    factor = p["atr_factor"]
    if type(factor) is not str or not 1 <= len(factor) <= 24:
        raise DataValidationError("D513 exact decimal string required")
    try:
        decimal = Decimal(factor)
    except InvalidOperation as exc:
        raise DataValidationError("D513 invalid pivot factor") from exc
    return IndicatorSelection(slots("ema"), slots("sma"),
                              PivotSuperTrend(p["enabled"], p["pivot_period"],
                                              p["atr_period"], decimal),
                              parse_bollinger(value["bollinger"]) if "bollinger" in value else None,
                              parse_rsi(value["rsi"]) if "rsi" in value else None)


def moving_average(closes: tuple[Decimal, ...], period: int, *, exponential: bool
                   ) -> tuple[Decimal | None, ...]:
    """SMA: last N closes; EMA: SMA seed and causal updates."""
    result = []
    previous = None
    with localcontext(_MATH_CONTEXT):
        alpha = Decimal(2) / Decimal(period + 1)
        for i, close in enumerate(closes):
            if i + 1 < period:
                result.append(None)
                continue
            if not exponential or previous is None:
                previous = sum(closes[i + 1 - period:i + 1], Decimal(0)) / Decimal(period)
            else:
                previous += alpha * (close - previous)
            result.append(previous)
    return tuple(result)


def pivot_trend(candles: tuple[ClosedCandle, ...], config: PivotSuperTrend
                ) -> tuple[int | None, ...]:
    """Confirm pivots only on the present bar, never backdate reversals."""
    result = []
    period = config.pivot_period
    center = atr = lower = upper = None
    tr_seed = []
    trend = 0
    with localcontext(_MATH_CONTEXT):
        for i, candle in enumerate(candles):
            prior_close = candles[i - 1].close if i else None
            tr = (candle.high - candle.low if prior_close is None else
                  max(candle.high - candle.low, abs(candle.high - prior_close),
                      abs(candle.low - prior_close)))
            if atr is None:
                tr_seed.append(tr)
                if len(tr_seed) == config.atr_period:
                    atr = sum(tr_seed, Decimal(0)) / Decimal(config.atr_period)
            else:
                atr = (atr * (config.atr_period - 1) + tr) / config.atr_period
            if i >= 2 * period:
                j = i - period
                swing = candles[j]
                neighbors = candles[j - period:j] + candles[j + 1:i + 1]
                high = all(swing.high > x.high for x in neighbors)
                low = all(swing.low < x.low for x in neighbors)
                pivot = swing.high if high else swing.low if low else None
                if pivot is not None:
                    center = pivot if center is None else (2 * center + pivot) / 3
            if center is None or atr is None:
                result.append(None)
                continue
            raw_lower = center - config.atr_factor * atr
            raw_upper = center + config.atr_factor * atr
            old_lower, old_upper = lower, upper
            if old_lower is not None and old_upper is not None:
                if candle.close > old_upper:
                    trend = 1
                elif candle.close < old_lower:
                    trend = -1
            lower = (max(raw_lower, old_lower)
                     if old_lower is not None and prior_close > old_lower else raw_lower)
            upper = (min(raw_upper, old_upper)
                     if old_upper is not None and prior_close < old_upper else raw_upper)
            result.append(trend)
    return tuple(result)


def bollinger_bands(closes: tuple[Decimal, ...], config: BollingerBands):
    """SMA and population sigma; each band uses only its own closed prefix."""
    if type(config) is not BollingerBands:
        raise DataValidationError("D521 typed Bollinger configuration required")
    result = []
    with localcontext(_MATH_CONTEXT):
        n = Decimal(config.period)
        for i in range(len(closes)):
            if i + 1 < config.period:
                result.append(None)
                continue
            window = closes[i+1-config.period:i+1]
            mean = sum(window, Decimal(0)) / n
            sigma = (sum(((x-mean)**2 for x in window), Decimal(0))/n).sqrt()
            width = config.deviations*sigma
            result.append((mean-width, mean, mean+width))
    return tuple(result)


def bollinger_directions(closes: tuple[Decimal, ...], config: BollingerBands):
    """Breakout is a directional state; reentry is a one-bar causal event."""
    bands = bollinger_bands(closes, config)
    result = []
    for i, band in enumerate(bands):
        if band is None or (config.mode == "reentry" and (i == 0 or bands[i-1] is None)):
            result.append(None)
            continue
        lower, mid, upper = band
        close = closes[i]
        if lower == upper:
            result.append(0)
        elif config.mode == "breakout":
            result.append(1 if close > upper else -1 if close < lower else 0)
        else:
            prev_lower, _, prev_upper = bands[i-1]
            prev = closes[i-1]
            inside = lower <= close <= upper
            result.append(1 if inside and prev < prev_lower else
                          -1 if inside and prev > prev_upper else 0)
    return tuple(result)


def combination_directions(candles: tuple[ClosedCandle, ...], selection: IndicatorSelection
                           ) -> tuple[int | None, ...]:
    """All active families agree; insufficient warmup is None; disagreement is 0.

    One MA: price versus MA. Two: fast versus slow. Three: first two
    versus each other plus price on the same side of the third.
    """
    closes = tuple(c.close for c in candles)
    families = []
    for slots, exponential in ((selection.ema, True), (selection.sma, False)):
        selected = tuple(x for x in slots if x.enabled)
        if not selected:
            continue
        series = tuple(moving_average(closes, x.period, exponential=exponential)
                       for x in selected)
        states = []
        for i, close in enumerate(closes):
            values = [s[i] for s in series]
            if any(x is None for x in values):
                states.append(None)
                continue
            a, b = (close, values[0]) if len(values) == 1 else (values[0], values[1])
            side = 1 if a > b else -1 if a < b else 0
            if len(values) == 3:
                if ((side == 1 and close <= values[2])
                        or (side == -1 and close >= values[2])):
                    side = 0
            states.append(side)
        families.append(tuple(states))
    if selection.pivot_supertrend.enabled:
        families.append(pivot_trend(candles, selection.pivot_supertrend))
    if selection.bollinger is not None and selection.bollinger.enabled:
        families.append(bollinger_directions(closes, selection.bollinger))
    if selection.rsi is not None and selection.rsi.enabled:
        families.append(rsi_directions(closes, selection.rsi))
    if not families:
        return (0,) * len(candles)
    result = []
    for states in zip(*families):
        if any(x is None for x in states):
            result.append(None)
        elif all(x == 1 for x in states):
            result.append(1)
        elif all(x == -1 for x in states):
            result.append(-1)
        else:
            result.append(0)
    return tuple(result)
