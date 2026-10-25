"""Offline OKX V5 linear SWAP history-candle schema research (J1/WU22).

Official documentation distinguishes contract volume, base currency volume,
quote currency volume and a confirmed/unfinished candle flag. This validator
does NOT make network requests, authenticate caller-asserted instrument metadata,
confirm crypto-only identity or confer market-data redistribution rights.
It cannot write canonical ClosedCandle, storage, backtests or trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any, Mapping

from .market_data import (
    DataGapError, DataValidationError, interval_duration_ms, interval_open_aligned,
)


SOURCE = "okx_v5_swap_history_candle_synthetic_research"
UNIT_BASIS = "documented_okx_swap_history_schema_not_live_verified"
MAX_HISTORY_PAGE = 300
# Only timeframes whose opening UTC grid is represented by the domain model.
# OKX '1D' is UTC+8; '1Dutc' is the explicit UTC+0 equivalent.
_BAR_TO_INTERVAL = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1H": "1h", "2H": "2h", "4H": "4h",
    "1Dutc": "1d",
}
_SYMBOL = re.compile(r"[A-Z0-9]{2,30}-(?:USDT|USDC)-SWAP")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?")
_TIMESTAMP = re.compile(r"(?:0|[1-9][0-9]{0,15})")


@dataclass(frozen=True)
class OkxSwapHistoryCandleResearch:
    instrument_id: str
    quote_currency: str
    bar: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    documented_contract_volume: Decimal
    documented_base_volume: Decimal
    documented_quote_volume: Decimal
    unit_basis: str = UNIT_BASIS
    source: str = SOURCE
    @property
    def crypto_identity_verified(self) -> bool:
        """Research parsing can never authenticate a crypto-only identity."""
        return False

    @property
    def exchange_schema_verified_live(self) -> bool:
        """An offline fixture is not live exchange evidence."""
        return False


@dataclass(frozen=True)
class OkxSwapHistoryPageResearch:
    instrument_id: str
    quote_currency: str
    bar: str
    interval: str
    start_open_ms: int
    end_open_ms: int
    observed_at_ms: int
    instrument_observed_at_ms: int
    candles: tuple[OkxSwapHistoryCandleResearch, ...]
    source: str = SOURCE
    @property
    def rights_for_distribution(self) -> bool:
        """A JSON payload cannot confer a market-data distribution license."""
        return False


def _exact_decimal(value: Any, name: str, *, zero_allowed: bool) -> Decimal:
    if type(value) is not str or len(value) > 80 or _DECIMAL.fullmatch(value) is None:
        raise DataValidationError(f"OKX {name} must be an exact bounded decimal string")
    number = Decimal(value)
    if not number.is_finite() or number < 0 or (not zero_allowed and number == 0):
        raise DataValidationError(f"OKX {name} must be finite and nonnegative/positive")
    return number


def _utc_ms(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise DataValidationError(f"OKX {label} must be positive UTC milliseconds")
    return value


def stage_okx_linear_swap_history(
    payload: Mapping[str, Any],
    *,
    instrument_id: str,
    quote_currency: str,
    instrument_type: str,
    contract_type: str,
    instrument_status: str,
    settlement_currency: str,
    instrument_observed_at_ms: int,
    observed_at_ms: int,
    max_instrument_age_ms: int,
    bar: str,
    start_open_ms: int,
    end_open_ms: int,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_HISTORY_PAGE,
    price_adjustment: str = "unadjusted",
) -> OkxSwapHistoryPageResearch:
    """Stage one exact UTC window using synthetic OKX history-response fixtures.

    The caller asserts instrument metadata, request parameters and observation
    times. This function cannot prove those assertions correspond to a real
    historical contract and never promotes its output to canonical candles.
    """
    if (type(instrument_id) is not str or _SYMBOL.fullmatch(instrument_id) is None
            or quote_currency not in ("USDT", "USDC")
            or not instrument_id.endswith("-" + quote_currency + "-SWAP")):
        raise DataValidationError("OKX instrument and quote must match a linear SWAP symbol")
    if (instrument_type != "SWAP" or contract_type != "linear"
            or instrument_status != "live" or settlement_currency != quote_currency):
        raise DataValidationError("OKX instrument metadata must assert a live linear settled SWAP")
    instrument_time = _utc_ms(instrument_observed_at_ms, "instrument_observed_at_ms")
    decision_time = _utc_ms(observed_at_ms, "observed_at_ms")
    if instrument_time > decision_time:
        raise DataValidationError("OKX instrument evidence is in the future")
    if type(max_instrument_age_ms) is not int or max_instrument_age_ms < 0:
        raise DataValidationError("OKX instrument age must be a nonnegative integer")
    if decision_time - instrument_time > max_instrument_age_ms:
        raise DataValidationError("OKX instrument metadata is stale")

    if type(bar) is not str or bar not in _BAR_TO_INTERVAL:
        raise DataValidationError("unsupported or non-UTC OKX research bar")
    interval = _BAR_TO_INTERVAL[bar]
    duration = interval_duration_ms(interval)
    if (type(start_open_ms) is not int or type(end_open_ms) is not int
            or start_open_ms < 0 or end_open_ms <= start_open_ms
            or not interval_open_aligned(interval, start_open_ms)
            or not interval_open_aligned(interval, end_open_ms)
            or (end_open_ms - start_open_ms) % duration != 0):
        raise DataValidationError("OKX research window must be UTC aligned and ascending")
    if type(max_candles) is not int or not 1 <= max_candles <= MAX_HISTORY_PAGE:
        raise DataValidationError("OKX history page limit must be between 1 and 300")
    count = (end_open_ms - start_open_ms) // duration
    if count > max_candles:
        raise DataValidationError("OKX research window exceeds page limit")
    if type(close_safety_ms) is not int or close_safety_ms < 0:
        raise DataValidationError("OKX close safety must be nonnegative integer")
    if price_adjustment != "unadjusted":
        raise DataValidationError("OKX equity forward-adjusted history is not supported")
    if (not isinstance(payload, Mapping) or type(payload.get("code")) is not str
            or payload.get("code") != "0" or type(payload.get("msg")) is not str
            or not isinstance(payload.get("data"), list)):
        raise DataValidationError("OKX history response code, msg or data is invalid")
    rows = payload["data"]
    if len(rows) != count:
        raise DataGapError("OKX history response has missing or extra rows")

    candles: list[OkxSwapHistoryCandleResearch] = []
    for i, row in enumerate(rows):
        if (type(row) not in (list, tuple) or len(row) != 9
                or any(type(value) is not str for value in row)):
            raise DataValidationError("OKX history candle must contain exactly nine strings")
        if len(row[0]) > 16 or _TIMESTAMP.fullmatch(row[0]) is None:
            raise DataValidationError("OKX history timestamp must be decimal UTC-ms string")
        opened = int(row[0])
        if opened != end_open_ms - (i + 1) * duration:
            raise DataGapError("OKX history rows are not contiguous and newest-first")
        closed = opened + duration - 1
        if closed + close_safety_ms > decision_time:
            raise DataValidationError("OKX candle is open or too recent for capture time")
        if row[8] != "1":
            raise DataValidationError("OKX candle confirm=0 is not a finalized bar")
        opening = _exact_decimal(row[1], "open", zero_allowed=False)
        high = _exact_decimal(row[2], "high", zero_allowed=False)
        low = _exact_decimal(row[3], "low", zero_allowed=False)
        closing = _exact_decimal(row[4], "close", zero_allowed=False)
        if high < max(opening, closing, low) or low > min(opening, closing, high):
            raise DataValidationError("OKX high/low do not bracket OHLC prices")
        contracts = _exact_decimal(row[5], "vol contracts", zero_allowed=True)
        base = _exact_decimal(row[6], "volCcy base", zero_allowed=True)
        quote = _exact_decimal(row[7], "volCcyQuote", zero_allowed=True)
        candles.append(OkxSwapHistoryCandleResearch(
            instrument_id=instrument_id, quote_currency=quote_currency, bar=bar,
            open_time_ms=opened, close_time_ms=closed,
            open=opening, high=high, low=low, close=closing,
            documented_contract_volume=contracts,
            documented_base_volume=base, documented_quote_volume=quote,
        ))
    return OkxSwapHistoryPageResearch(
        instrument_id=instrument_id, quote_currency=quote_currency,
        bar=bar, interval=interval,
        start_open_ms=start_open_ms, end_open_ms=end_open_ms,
        observed_at_ms=decision_time, instrument_observed_at_ms=instrument_time,
        candles=tuple(reversed(candles)),
    )
