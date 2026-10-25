"""Bybit V5 linear kline schema: offline-only, documented volume units.

Bybit's official V5 docs explicitly state:
- USDT/USDC linear contracts: volume is in BASE coin.
- turnover is in QUOTE coin (USDT/USDC).
- kline list arrives newest-first; close of a live candle is not final.

This parser is NOT an API client, trading adapter, actual venue approval or
licensing grant. Contract metadata is asserted by the caller and is not
independently verified here. No network, storage, ClosedCandle or orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any, Mapping

from .market_data import (
    DataGapError, DataValidationError, interval_duration_ms, interval_open_aligned,
)


SOURCE = "bybit_v5_linear_kline_synthetic_research"
UNIT_BASIS = "documented_bybit_linear_kline_schema_not_live_verified"
MAX_PAGE = 1_000
_INTERVALS = frozenset({
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h",
    "6h", "12h", "1d", "1w",
})
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?")
_TIMESTAMP = re.compile(r"(?:0|[1-9][0-9]{0,15})")
_SYMBOL = re.compile(r"^[A-Z0-9]{2,30}(?:USDT|USDC)$")


@dataclass(frozen=True)
class BybitLinearCandleResearch:
    symbol: str
    quote_currency: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    documented_base_volume: Decimal
    documented_quote_turnover: Decimal
    unit_basis: str = UNIT_BASIS
    source: str = SOURCE


@dataclass(frozen=True)
class BybitLinearCandlePageResearch:
    """Only a synthetic conformance sample; NOT a canonical storage write."""

    symbol: str
    quote_currency: str
    interval: str
    start_open_ms: int
    end_open_ms: int
    observed_at_ms: int
    candles: tuple[BybitLinearCandleResearch, ...]
    source: str = SOURCE


def _strict_decimal(value: Any, *, label: str, may_be_zero: bool) -> Decimal:
    if type(value) is not str or len(value) > 80 or _DECIMAL.fullmatch(value) is None:
        raise DataValidationError(f"Bybit {label} must be bounded exact decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite() or parsed < 0 or (not may_be_zero and parsed == 0):
        raise DataValidationError(f"Bybit {label} must be {'nonnegative' if may_be_zero else 'positive'}")
    return parsed


def stage_bybit_linear_kline(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    quote_currency: str,
    contract_type: str,
    contract_status: str,
    contract_observed_at_ms: int,
    observed_at_ms: int,
    max_contract_age_ms: int,
    interval: str,
    start_open_ms: int,
    end_open_ms: int,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_PAGE,
) -> BybitLinearCandlePageResearch:
    """Require a contemporaneous, caller-asserted linear perpetual contract.

    The contract metadata here is UNVERIFIED outside synthetic fixtures.
    Its provenance must be established separately before a real adapter.
    """
    if (not isinstance(symbol, str) or not symbol.isascii()
            or _SYMBOL.fullmatch(symbol) is None
            or quote_currency not in ("USDT", "USDC")
            or not symbol.endswith(quote_currency)):
        raise DataValidationError("Bybit symbol and quote currency mismatch")
    if contract_type != "LinearPerpetual" or contract_status != "Trading":
        raise DataValidationError("Bybit contract is not a trading linear perpetual")
    if (type(contract_observed_at_ms) is not int or contract_observed_at_ms <= 0
            or type(observed_at_ms) is not int or observed_at_ms <= 0
            or contract_observed_at_ms > observed_at_ms):
        raise DataValidationError("Bybit contract observation is absent or from the future")
    if type(max_contract_age_ms) is not int or max_contract_age_ms < 0:
        raise ValueError("Bybit maximum contract age must be nonnegative integer")
    if observed_at_ms - contract_observed_at_ms > max_contract_age_ms:
        raise DataValidationError("Bybit contract metadata is stale at chart capture")
    if interval not in _INTERVALS:
        raise DataValidationError("unsupported Bybit fixed-UTC research interval")
    if (type(start_open_ms) is not int or type(end_open_ms) is not int
            or start_open_ms < 0 or end_open_ms <= start_open_ms
            or not interval_open_aligned(interval, start_open_ms)
            or not interval_open_aligned(interval, end_open_ms)):
        raise DataValidationError("Bybit chart window must be ascending and UTC grid aligned")
    duration = interval_duration_ms(interval)
    if (type(max_candles) is not int or not 1 <= max_candles <= MAX_PAGE
            or (end_open_ms - start_open_ms) % duration != 0
            or (end_open_ms - start_open_ms) // duration > max_candles):
        raise DataValidationError("invalid Bybit kline page size or grid duration")
    if type(close_safety_ms) is not int or close_safety_ms < 0:
        raise ValueError("Bybit close_safety_ms must be nonnegative integer")
    if not isinstance(payload, Mapping) or type(payload.get("retCode")) is not int or payload.get("retCode") != 0:
        raise DataValidationError("Bybit kline response status is not successful")
    result = payload.get("result")
    if (not isinstance(result, Mapping) or result.get("category") != "linear"
            or result.get("symbol") != symbol or not isinstance(result.get("list"), list)):
        raise DataValidationError("Bybit kline category, symbol or list invalid")
    rows = result["list"]
    expected = (end_open_ms - start_open_ms) // duration
    if len(rows) != expected:
        raise DataGapError("Bybit research page is incomplete or has extra candles")
    normalized: list[BybitLinearCandleResearch] = []
    for index, row in enumerate(rows):
        if (not isinstance(row, (tuple, list)) or len(row) != 7
                or not all(type(x) is str for x in row)):
            raise DataValidationError("Bybit kline row must contain exactly seven strings")
        open_text = row[0]
        if len(open_text) > 16 or _TIMESTAMP.fullmatch(open_text) is None:
            raise DataValidationError("Bybit UTC millisecond timestamp must be decimal string")
        opened = int(open_text)
        # API returns newest-first, and sorting silently would hide malformed
        # order/duplicate provider rows; enforce exact reverse sequence.
        expected_open = end_open_ms - (index + 1) * duration
        if opened != expected_open:
            raise DataGapError("Bybit kline timestamps are not a contiguous descending UTC window")
        closed = opened + duration - 1
        if closed + close_safety_ms > observed_at_ms:
            raise DataValidationError("Bybit latest candle was not confirmed closed")
        opening = _strict_decimal(row[1], label="openPrice", may_be_zero=False)
        high = _strict_decimal(row[2], label="highPrice", may_be_zero=False)
        low = _strict_decimal(row[3], label="lowPrice", may_be_zero=False)
        closing = _strict_decimal(row[4], label="closePrice", may_be_zero=False)
        if high < max(opening, closing, low) or low > min(opening, closing, high):
            raise DataValidationError("Bybit kline OHLC extrema are inconsistent")
        base = _strict_decimal(row[5], label="base-volume", may_be_zero=True)
        quote = _strict_decimal(row[6], label="quote-turnover", may_be_zero=True)
        normalized.append(BybitLinearCandleResearch(
            symbol=symbol, quote_currency=quote_currency, interval=interval,
            open_time_ms=opened, close_time_ms=closed,
            open=opening, high=high, low=low, close=closing,
            documented_base_volume=base, documented_quote_turnover=quote,
        ))
    return BybitLinearCandlePageResearch(
        symbol=symbol, quote_currency=quote_currency, interval=interval,
        start_open_ms=start_open_ms, end_open_ms=end_open_ms,
        observed_at_ms=observed_at_ms,
        candles=tuple(reversed(normalized)),
    )
