"""CandleFeed Free research: documented BASE BTC + reported USD volume.

The aggregator docs describe volume as base units (BTC) and quote_volume
as *normalized/reported USD*, even when the underlying exchange instrument
is BTCUSDT, quoted in USDT. These units MUST NOT be conflated: a candle
from CandleFeed is NOT an authenticated Binance venue candle, its USD metric
is NOT venue-native USDT notional, and neither grants raw-data publishing.
Research-only until provider identity, upstream rights, fees, funding and
real sample quality are confirmed. No ClosedCandle/SQLite/trades here.

Sources:
https://candlefeed.ai/docs/
https://candlefeed.ai/terms/ (version 2026-10-18, sections 5.3 and 6)
"""
from __future__ import annotations

from calendar import timegm
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any, Mapping

from .decimal_json import positive_market_decimal
from .market_data import DataGapError, DataValidationError
from .research_registry_catalog import load_reviewed_registry

SOURCE = "candlefeed_binance_aggregated_private_research"
ORIGIN = "binance"
SYMBOL = "BTCUSDT"
BASE = "BTC"
ORIGIN_QUOTE = "USDT"
REPORTED_QUOTE_UNIT = "USD"
INTERVAL = "1h"
HOUR_MS = 3_600_000
WINDOW_HOURS = 24
_MAX_AGE_MS = 30_000
_UTC = re.compile(
    r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d"
    r"(?:\.\d{1,6})?(?:Z|\+00:00)"
)


@dataclass(frozen=True)
class CandleFeedResearchCandle:
    symbol: str
    origin_exchange: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    reported_base_volume_btc: Decimal
    reported_quote_volume_usd: Decimal
    source: str = SOURCE

    @property
    def canonical_ohlcv(self) -> bool:
        return False

    @property
    def verified_live_exchange_origin(self) -> bool:
        return False


@dataclass(frozen=True)
class CandleFeedResearchPage:
    source: str
    origin_exchange: str
    symbol: str
    origin_quote_currency: str
    reported_quote_currency: str
    start_open_ms: int
    end_open_ms: int
    observed_at_ms: int
    registry_sha256: str
    candles: tuple[CandleFeedResearchCandle, ...]

    @property
    def canonical_ohlcv(self) -> bool:
        return False

    @property
    def public_or_commercial_redistribution_authorized(self) -> bool:
        return False

    @property
    def live_exchange_origin_verified(self) -> bool:
        return False


def _open_ms(value: Any) -> int:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        raise DataValidationError("CandleFeed timestamps require ISO UTC Z or +00:00")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise DataValidationError("CandleFeed malformed calendar UTC timestamp") from None
    if parsed.utcoffset() != timedelta(0) or parsed.microsecond % 1000:
        raise DataValidationError("CandleFeed time must be exact UTC milliseconds")
    # Avoid binary float roundoff in datetime.timestamp() * 1000.
    result = timegm(parsed.utctimetuple()) * 1000 + parsed.microsecond // 1000
    if result <= 0:
        raise DataValidationError("CandleFeed UTC timestamp invalid")
    return result


def _nonnegative(value: Any, *, label: str) -> Decimal:
    # The JSON boundary preserves precise Decimal/int tokens; zero must not
    # inadvertently admit float(0) or bool(False) by Python equality.
    if type(value) is int and value == 0:
        return Decimal(0)
    if type(value) is Decimal and value.is_finite() and value == 0:
        return Decimal(0)
    if type(value) is str and (value == "0" or (value.startswith("0.") and 1 <= len(value[2:]) <= 24 and set(value[2:]) == {"0"})):
        return Decimal(0)
    return positive_market_decimal(value, label)


def stage_candlefeed_btc_24h(
    payload: Mapping[str, Any], *,
    start_open_ms: int, end_open_ms: int,
    observed_at_ms: int, requested_at_ms: int,
    registry_variant: str = "btc-eth",
) -> CandleFeedResearchPage:
    """Validate exactly 24 contiguous fully CLOSED BTCUSDT 1h bars.

    The source payload must have been decoded via exact JSON parser. No
    source/network authenticity can be proven from caller-supplied fixtures.
    """
    if (type(start_open_ms) is not int or type(end_open_ms) is not int
            or type(observed_at_ms) is not int or type(requested_at_ms) is not int
            or start_open_ms <= 0
            or end_open_ms - start_open_ms != WINDOW_HOURS * HOUR_MS
            or start_open_ms % HOUR_MS or end_open_ms % HOUR_MS
            or requested_at_ms <= 0 or observed_at_ms < requested_at_ms
            or observed_at_ms - requested_at_ms > _MAX_AGE_MS
            or end_open_ms + 1000 > observed_at_ms):
        raise DataValidationError("CandleFeed window/capture timing invalid")
    registry = load_reviewed_registry(registry_variant, as_of_ms=requested_at_ms)
    if BASE not in registry.verified_crypto_bases:
        raise DataValidationError("CandleFeed BTC is not reviewed at request time")
    if (not isinstance(payload, Mapping)
            or payload.get("status") != "ok"
            or payload.get("symbol") != SYMBOL
            or payload.get("exchange") != ORIGIN
            or type(payload.get("count")) is not int
            or payload["count"] != WINDOW_HOURS
            or type(payload.get("has_more")) is not bool
            or payload["has_more"] is not False
            or payload.get("next_cursor") is not None
            or type(payload.get("data")) is not list
            or len(payload["data"]) != WINDOW_HOURS):
        raise DataValidationError("CandleFeed wrong origin/status/coverage/pagination")
    candles: dict[int, CandleFeedResearchCandle] = {}
    for row in payload["data"]:
        if type(row) is not dict:
            raise DataValidationError("CandleFeed row must be a mapping")
        t = _open_ms(row.get("time"))
        if t < start_open_ms or t >= end_open_ms or t % HOUR_MS != 0:
            raise DataGapError("CandleFeed row outside exact closed UTC hours")
        if t in candles:
            raise DataGapError("CandleFeed duplicate hourly timestamp")
        if t + HOUR_MS > observed_at_ms - 1000:
            raise DataValidationError("CandleFeed row is not completely closed")
        o = positive_market_decimal(row.get("open"), "open")
        h = positive_market_decimal(row.get("high"), "high")
        l = positive_market_decimal(row.get("low"), "low")
        c = positive_market_decimal(row.get("close"), "close")
        if l > min(o, h, c) or h < max(o, l, c):
            raise DataValidationError("CandleFeed impossible OHLC range")
        base = _nonnegative(row.get("volume"), label="base volume BTC")
        usd = _nonnegative(row.get("quote_volume"), label="reported quote volume USD")
        if (base == 0) != (usd == 0):
            raise DataValidationError("CandleFeed base/USD volume zero mismatch")
        candles[t] = CandleFeedResearchCandle(
            symbol=SYMBOL, origin_exchange=ORIGIN, interval=INTERVAL,
            open_time_ms=t, close_time_ms=t + HOUR_MS - 1,
            open=o, high=h, low=l, close=c,
            reported_base_volume_btc=base, reported_quote_volume_usd=usd,
        )
    expected = tuple(range(start_open_ms, end_open_ms, HOUR_MS))
    if tuple(sorted(candles)) != expected:
        raise DataGapError("CandleFeed exact 24-hour coverage incomplete")
    return CandleFeedResearchPage(
        SOURCE, ORIGIN, SYMBOL, ORIGIN_QUOTE, REPORTED_QUOTE_UNIT,
        start_open_ms, end_open_ms, observed_at_ms, registry.sha256_digest,
        tuple(candles[t] for t in expected),
    )
