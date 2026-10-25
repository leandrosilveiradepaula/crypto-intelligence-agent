"""Offline Kraken Futures trade-candle staging; volume units remain unverified.

This module deliberately DOES NOT build ClosedCandle or save market data.
Kraken's chart schema exposes 'volume' but does not establish the base-asset
and quote-asset volumes required by our canonical data contract. Deriving
quote volume using candle close/VWAP would fabricate precision.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping

from .market_data import (
    DataGapError, DataValidationError, interval_duration_ms,
    interval_open_aligned,
)


SOURCE = "kraken_futures_trade_candle_research"
KRAKEN_RESOLUTIONS = frozenset({
    "1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d", "1w",
})
MAX_CANDLES = 500
MAX_INT64 = (1 << 63) - 1
# Chart public docs say number<int64>, but live run #40201488833 returned
# decimal strings on all 27 candles. Preserve units UNKNOWN in both cases.
_RAW_DECIMAL_STRING = re.compile(r"(?:0|[1-9][0-9]{0,18})(?:\.[0-9]{1,18})?")


@dataclass(frozen=True)
class KrakenTradeCandleStaging:
    """Verified closed OHLC, but trade-volume quantity is NOT normalized."""

    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    raw_trade_volume_unverified: Decimal
    raw_volume_unit: str = "unverified"
    source: str = SOURCE


@dataclass(frozen=True)
class KrakenStagedCandlePage:
    """One exact, contiguous, closed time window; no base/quote volume."""

    symbol: str
    interval: str
    start_open_ms: int
    end_open_ms: int
    candles: tuple[KrakenTradeCandleStaging, ...]
    provider_reports_more_candles: bool


def _check_window(
    *, interval: str, start_open_ms: int, end_open_ms: int,
    max_candles: int,
) -> tuple[int, int]:
    if not isinstance(interval, str) or interval not in KRAKEN_RESOLUTIONS:
        raise DataValidationError("unsupported Kraken trade-candle resolution")
    if (type(start_open_ms) is not int or type(end_open_ms) is not int
            or start_open_ms < 0 or end_open_ms <= start_open_ms):
        raise DataValidationError("Kraken candle window must be ascending UTC milliseconds")
    if type(max_candles) is not int or not 1 <= max_candles <= MAX_CANDLES:
        raise ValueError("max_candles must be between 1 and 500")
    duration = interval_duration_ms(interval)
    if (not interval_open_aligned(interval, start_open_ms)
            or not interval_open_aligned(interval, end_open_ms)
            or (end_open_ms - start_open_ms) % duration != 0):
        raise DataValidationError("Kraken candle window is not on its UTC resolution grid")
    expected = (end_open_ms - start_open_ms) // duration
    if expected > max_candles:
        raise DataValidationError("requested Kraken candle page exceeds configured limit")
    return duration, expected


def epoch_ms_window_to_kraken_seconds(
    *, interval: str, start_open_ms: int, end_open_ms: int, max_candles: int = MAX_CANDLES,
) -> tuple[int, int]:
    """Convert aligned UTC boundaries to the API's documented epoch seconds.

    Actual inclusive/exclusive behavior of server 'from'/'to' must be checked
    with the response; it is not inferred or guaranteed by this conversion.
    """
    _check_window(
        interval=interval, start_open_ms=start_open_ms,
        end_open_ms=end_open_ms, max_candles=max_candles,
    )
    return start_open_ms // 1_000, end_open_ms // 1_000


def _decimal_price(value: Any, field: str) -> Decimal:
    # Kraken documents OHLC as decimal strings. Strict typing avoids binary
    # float coercion and ungrounded numerical precision.
    if not isinstance(value, str) or not value or len(value) > 90:
        raise DataValidationError(f"Kraken candle {field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise DataValidationError(f"Kraken candle {field} contains an invalid decimal") from error
    if not parsed.is_finite() or parsed <= 0:
        raise DataValidationError(f"Kraken candle {field} must be finite and positive")
    return parsed


def _raw_trade_volume(value: Any) -> Decimal:
    """Strictly parse documented int64 OR observed fixed-point decimal string.

    This is an opaque *trade volume measurement*, NOT base/quote volume.
    Never route float/bool through Decimal(str(x)); never infer notional.
    """
    if type(value) is int:
        if value < 0 or value > MAX_INT64:
            raise DataValidationError("Kraken raw volume integer exceeds nonnegative int64")
        return Decimal(value)
    if type(value) is not str or _RAW_DECIMAL_STRING.fullmatch(value) is None:
        raise DataValidationError("Kraken raw volume requires int64 or bounded decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite() or parsed > MAX_INT64:
        raise DataValidationError("Kraken raw volume is out of permitted range")
    return parsed


def stage_kraken_trade_candles(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    interval: str,
    start_open_ms: int,
    end_open_ms: int,
    observed_at_ms: int,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_CANDLES,
) -> KrakenStagedCandlePage:
    """Validate an exact closed window without claiming verified volume units.

    Does not make HTTP requests or construct canonical ClosedCandle objects.
    Caller must provide the genuine capture time and exact expected window.
    """
    duration, expected = _check_window(
        interval=interval, start_open_ms=start_open_ms,
        end_open_ms=end_open_ms, max_candles=max_candles,
    )
    if (not isinstance(symbol, str) or not symbol.startswith("PF_")
            or len(symbol) > 48 or not symbol[3:].isalnum()
            or not symbol.isascii() or not symbol.isupper()):
        raise DataValidationError("invalid Kraken linear perpetual symbol")
    if type(observed_at_ms) is not int or observed_at_ms <= 0:
        raise DataValidationError("observed_at_ms must be a positive UTC-ms integer")
    if type(close_safety_ms) is not int or close_safety_ms < 0:
        raise ValueError("close_safety_ms must be nonnegative")
    if not isinstance(payload, Mapping):
        raise DataValidationError("Kraken candle response must be a JSON object")
    rows, more = payload.get("candles"), payload.get("more_candles")
    if not isinstance(rows, list) or type(more) is not bool:
        raise DataValidationError("Kraken candle response requires candles list and more_candles boolean")
    if len(rows) != expected:
        raise DataGapError("Kraken candle window has missing or extra rows")

    result: list[KrakenTradeCandleStaging] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise DataValidationError("Kraken candle row must be an object")
        open_time = row.get("time")
        if type(open_time) is not int or open_time < 0:
            raise DataValidationError("Kraken candle time must be UTC milliseconds")
        intended_open_time = start_open_ms + index * duration
        if open_time != intended_open_time:
            raise DataGapError("Kraken candle timestamps are not a contiguous ascending UTC window")
        close_time = open_time + duration - 1
        if close_time + close_safety_ms > observed_at_ms:
            raise DataValidationError("Kraken candle is not confirmed closed at capture time")
        open_price = _decimal_price(row.get("open"), "open")
        high = _decimal_price(row.get("high"), "high")
        low = _decimal_price(row.get("low"), "low")
        close = _decimal_price(row.get("close"), "close")
        if high < max(open_price, close, low) or low > min(open_price, close, high):
            raise DataValidationError("inconsistent Kraken OHLC extrema")
        result.append(KrakenTradeCandleStaging(
            symbol=symbol, interval=interval, open_time_ms=open_time,
            close_time_ms=close_time, open=open_price, high=high,
            low=low, close=close,
            raw_trade_volume_unverified=_raw_trade_volume(row.get("volume")),
        ))
    return KrakenStagedCandlePage(
        symbol=symbol, interval=interval,
        start_open_ms=start_open_ms, end_open_ms=end_open_ms,
        candles=tuple(result), provider_reports_more_candles=more,
    )
