"""dYdX Chain v4: documented BASE + USD volume, only research staging.

Unlike Kraken trade-candle volume, the dYdX indexer exposes separate
baseTokenVolume and usdVolume fields. USD here is a reported USD measurement,
NOT a proof of collateral/settlement denomination in USDC or USD. Provider
access, rights, historical coverage, candle finality and source authenticity
are not established by this pure parser. Never produce canonical ClosedCandle.
Official indexer: https://indexer.dydx.trade/docs/
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any, Mapping

from .market_data import DataGapError, DataValidationError
from .research_registry_catalog import load_reviewed_registry

SOURCE = "dydx_v4_indexer_documented_private_research"
TICKER = "BTC-USD"
INTERVAL = "1HOUR"
HOUR_MS = 3_600_000
MAX_ROWS = 6
_MAX_CAPTURE_AGE_MS = 30_000
_FIXED = re.compile(r"(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?")
_UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z")


@dataclass(frozen=True)
class DydxV4PerpCandleResearch:
    ticker: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_token_volume: Decimal
    usd_volume: Decimal
    trade_count: int
    source: str = SOURCE

    @property
    def canonical_ohlcv(self) -> bool:
        return False


@dataclass(frozen=True)
class DydxV4CandlePageResearch:
    ticker: str
    interval: str
    open_time_ms: int
    end_open_ms: int
    market_observed_at_ms: int
    observed_at_ms: int
    candles: tuple[DydxV4PerpCandleResearch, ...]
    registry_sha256: str
    source: str = SOURCE

    @property
    def canonical_ohlcv(self) -> bool:
        return False

    @property
    def public_or_commercial_rights_authorized(self) -> bool:
        return False

    @property
    def live_provider_authenticated(self) -> bool:
        return False


def _number(raw: Any, field: str, *, zero: bool = False) -> Decimal:
    if type(raw) is not str or len(raw) > 80 or _FIXED.fullmatch(raw) is None:
        raise DataValidationError(f"dYdX {field} must be exact bounded decimal string")
    value = Decimal(raw)
    if not value.is_finite() or value < 0 or (value == 0 and not zero):
        raise DataValidationError(f"dYdX {field} has invalid nonnegative value")
    return value


def _timestamp(raw: Any) -> int:
    if type(raw) is not str or _UTC.fullmatch(raw) is None:
        raise DataValidationError("dYdX candle timestamp requires explicit UTC Z")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
        value = int(parsed.timestamp() * 1000)
    except (ValueError, OverflowError, OSError):
        raise DataValidationError("dYdX candle timestamp is not valid UTC") from None
    if datetime.fromtimestamp(value / 1000, timezone.utc).year < 2000:
        raise DataValidationError("dYdX candle timestamp out of allowed epoch")
    return value


def _trade_count(raw: Any) -> int:
    if type(raw) is int and 0 <= raw <= 10_000_000:
        return raw
    if (type(raw) is str and 1 <= len(raw) <= 8
            and raw.isascii() and raw.isdecimal()
            and (raw == "0" or not raw.startswith("0"))):
        return int(raw)
    raise DataValidationError("dYdX trade count is not bounded exact integer")


def stage_dydx_v4_btc_hourly(
    market_payload: Mapping[str, Any],
    candles_payload: Mapping[str, Any],
    *,
    market_observed_at_ms: int,
    observed_at_ms: int,
    start_open_ms: int,
    end_open_ms: int,
    registry_variant: str = "btc-eth",
) -> DydxV4CandlePageResearch:
    """Fail closed on market identity and exactly three fully closed 1H candles.

    Callers MUST independently verify HTTP source, TLS/host and capture times.
    6 newest indexer rows are allowed: only the requested three closed hours
    are consumed; an incomplete newest hour can appear and is not promoted.
    """
    if (type(market_observed_at_ms) is not int
            or type(observed_at_ms) is not int
            or market_observed_at_ms <= 0
            or observed_at_ms < market_observed_at_ms
            or observed_at_ms - market_observed_at_ms > _MAX_CAPTURE_AGE_MS
            or type(start_open_ms) is not int
            or type(end_open_ms) is not int
            or start_open_ms <= 0 or end_open_ms - start_open_ms != 3 * HOUR_MS
            or start_open_ms % HOUR_MS != 0
            or end_open_ms % HOUR_MS != 0
            or end_open_ms + 999 > observed_at_ms):
        raise DataValidationError("dYdX UTC window or metadata age invalid")
    registry = load_reviewed_registry(registry_variant, as_of_ms=market_observed_at_ms)
    if "BTC" not in registry.verified_crypto_bases:
        raise DataValidationError("BTC not verified in point-in-time crypto registry")
    if not isinstance(market_payload, Mapping):
        raise DataValidationError("dYdX perpetual market response must be object")
    markets = market_payload.get("markets")
    if not isinstance(markets, Mapping) or TICKER not in markets:
        raise DataValidationError("dYdX BTC perpetual market missing")
    market = markets[TICKER]
    if (not isinstance(market, Mapping)
            or market.get("status") != "ACTIVE"
            or market.get("ticker", TICKER) != TICKER
            or market.get("marketType") not in (None, "CROSS", "ISOLATED")):
        raise DataValidationError("dYdX market is not a known active BTC perpetual")
    if (not isinstance(candles_payload, Mapping)
            or type(candles_payload.get("candles")) is not list
            or not 3 <= len(candles_payload["candles"]) <= MAX_ROWS):
        raise DataValidationError("dYdX candle response must be a bounded list")
    accepted: dict[int, DydxV4PerpCandleResearch] = {}
    for row in candles_payload["candles"]:
        if type(row) is not dict:
            raise DataValidationError("dYdX candle row must be object")
        if (row.get("ticker") != TICKER or row.get("resolution") != INTERVAL):
            raise DataValidationError("dYdX candle market or resolution mismatch")
        t = _timestamp(row.get("startedAt"))
        # Newest / oldest rows are not in the conservative chosen window.
        # They do not prove coverage and cannot fill in missing selected rows.
        if t < start_open_ms or t >= end_open_ms:
            continue
        if t in accepted:
            raise DataGapError("dYdX duplicate selected candle timestamp")
        if t % HOUR_MS != 0 or t + HOUR_MS > observed_at_ms - 1000:
            raise DataValidationError("dYdX candle not aligned and fully closed")
        o = _number(row.get("open"), "open")
        h = _number(row.get("high"), "high")
        l = _number(row.get("low"), "low")
        c = _number(row.get("close"), "close")
        if l > min(o, h, c) or h < max(o, l, c):
            raise DataValidationError("dYdX candle inconsistent OHLC range")
        base = _number(row.get("baseTokenVolume"), "baseTokenVolume", zero=True)
        usd = _number(row.get("usdVolume"), "usdVolume", zero=True)
        trades = _trade_count(row.get("trades"))
        if (trades == 0) != (base == 0 and usd == 0):
            raise DataValidationError("dYdX trade count and volume zeros disagree")
        if (trades > 0 and (base == 0 or usd == 0)):
            raise DataValidationError("dYdX nonzero trades require positive unit volumes")
        accepted[t] = DydxV4PerpCandleResearch(
            TICKER, INTERVAL, t, t + HOUR_MS - 1,
            o, h, l, c, base, usd, trades,
        )
    required = tuple(range(start_open_ms, end_open_ms, HOUR_MS))
    if tuple(sorted(accepted)) != required:
        raise DataGapError("dYdX selected historical UTC window incomplete")
    return DydxV4CandlePageResearch(
        TICKER, INTERVAL, start_open_ms, end_open_ms,
        market_observed_at_ms, observed_at_ms,
        tuple(accepted[t] for t in required), registry.sha256_digest,
    )
