"""Hyperliquid-native perpetual metadata and candle conformance: OFFLINE only.

The public Hyperliquid /info endpoint is an HTTP POST, but its info messages
are read-only. This module DOES NOT SEND it: responses/observation times are
caller-asserted synthetic research fixtures, never verified live data.
Neither a public endpoint nor a numeric quote implies redistribution rights,
crypto-only identity, verified units, historical coverage or tradability.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any, Mapping, Sequence

from .market_data import (
    DataGapError, DataValidationError, interval_duration_ms, interval_open_aligned,
)

SOURCE = "hyperliquid_native_info_synthetic_research"
MAX_RESEARCH_PAGE = 500
DOCUMENTED_RECENT_HISTORY_CANDLES = 5_000
MAX_INSTRUMENTS = 1_000
# Exclude week/month until Hyperliquid's exact UTC anchor is independently
# confirmed. Never interpret a calendar month as a fixed interval.
_INTERVALS = frozenset({
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d",
})
_SYMBOL = re.compile(r"(?:[A-Z0-9]{2,20}|k[A-Z0-9]{2,20})")
# Other members of the reported native universe are NOT research targets.
# Their exact trading-asset naming rules do not establish crypto identity.
# Validate only a bounded, inert name with no HIP-3/spot namespace markers.
_NON_TARGET_NATIVE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_METADATA_REASONS = frozenset({
    "target_symbol_invalid", "snapshot_shape", "universe_alignment",
    "universe_entry", "native_name_or_namespace", "duplicate_native_name",
    "target_missing", "target_delisted_or_context",
    "target_leverage_precision", "target_day_notional",
    "target_mark_price", "target_open_interest", "target_funding",
})


class NativeMetadataSchemaError(DataValidationError):
    """Fixed, non-sensitive diagnostic reason: never include external values."""

    def __init__(self, reason: str) -> None:
        if reason not in _METADATA_REASONS:
            raise ValueError("internal invalid metadata diagnostic reason")
        self.reason = reason
        super().__init__("native_metadata_" + reason)

_UNSIGNED = re.compile(r"(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?")
_SIGNED = re.compile(r"-?(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?")


@dataclass(frozen=True)
class NativePerpMetadataResearch:
    symbol: str
    max_leverage_reported: int
    size_decimals_reported: int
    day_notional_reported: Decimal
    mark_price_reported: Decimal
    open_interest_reported: Decimal
    funding_rate_reported: Decimal
    observed_at_ms: int
    source: str = SOURCE

    @property
    def crypto_identity_verified(self) -> bool:
        return False

    @property
    def venue_leverage_verified(self) -> bool:
        return False

    @property
    def rights_for_distribution(self) -> bool:
        return False


@dataclass(frozen=True)
class NativeCandleResearch:
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    raw_volume_unit_unverified: Decimal
    reported_trade_count: int
    source: str = SOURCE

    @property
    def base_volume_verified(self) -> bool:
        return False

    @property
    def quote_volume_verified(self) -> bool:
        return False


@dataclass(frozen=True)
class NativePerpCandlePageResearch:
    symbol: str
    interval: str
    start_open_ms: int
    end_open_ms: int
    observed_at_ms: int
    metadata: NativePerpMetadataResearch
    candles: tuple[NativeCandleResearch, ...]
    source: str = SOURCE

    @property
    def ready_for_canonical_ohlcv(self) -> bool:
        return False

    @property
    def ready_for_live_top50(self) -> bool:
        return False

    @property
    def rights_for_distribution(self) -> bool:
        return False


def _decimal_text(value: Any, field: str, *, positive: bool = False,
                  signed: bool = False) -> Decimal:
    pat = _SIGNED if signed else _UNSIGNED
    if type(value) is not str or len(value) > 80 or pat.fullmatch(value) is None:
        raise DataValidationError(f"Hyperliquid {field} needs exact bounded decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite() or (not signed and parsed < 0) or (positive and parsed <= 0):
        raise DataValidationError(f"Hyperliquid {field} has invalid decimal sign or value")
    return parsed


def _ms(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise DataValidationError(f"{label} must be positive UTC-ms integer")
    return value


def _native_perp_context(
    snapshot: Any, *, symbol: str, observed_at_ms: int,
) -> NativePerpMetadataResearch:
    """Validate one requested perp by exact position; other names are inert.

    The response may legitimately contain delisted, inactive or unusual
    unrelated native contracts. Those entries cannot approve the requested
    BTC instrument, and a malformed selected entry still fails closed.
    This is *not* a positive crypto-only/rights/venue identity check.
    """
    if type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None:
        raise NativeMetadataSchemaError("target_symbol_invalid")
    if type(snapshot) not in (list, tuple) or len(snapshot) != 2:
        raise NativeMetadataSchemaError("snapshot_shape")
    info, ctxs = snapshot
    if (type(info) is not dict or type(ctxs) is not list
            or type(info.get("universe")) is not list):
        raise NativeMetadataSchemaError("snapshot_shape")
    universe = info["universe"]
    if not 1 <= len(universe) <= MAX_INSTRUMENTS or len(universe) != len(ctxs):
        raise NativeMetadataSchemaError("universe_alignment")
    if "tokens" in info:
        raise NativeMetadataSchemaError("native_name_or_namespace")
    names: set[str] = set()
    found_index: int | None = None
    for i, item in enumerate(universe):
        if type(item) is not dict:
            raise NativeMetadataSchemaError("universe_entry")
        name = item.get("name")
        # This check is intentionally looser than the selected instrument
        # regex: an unrelated 1-letter/ticker-form native perp may exist.
        # Any spot (@, /) or HIP-3 (:) namespace still fails closed.
        if (type(name) is not str
                or _NON_TARGET_NATIVE_NAME.fullmatch(name) is None
                or "tokens" in item):
            raise NativeMetadataSchemaError("native_name_or_namespace")
        if name in names:
            raise NativeMetadataSchemaError("duplicate_native_name")
        names.add(name)
        flag = item.get("isDelisted", False)
        if type(flag) is not bool:
            raise NativeMetadataSchemaError("universe_entry")
        if name == symbol:
            found_index = i
    if found_index is None:
        raise NativeMetadataSchemaError("target_missing")
    item, context = universe[found_index], ctxs[found_index]
    if type(context) is not dict or item.get("isDelisted", False):
        raise NativeMetadataSchemaError("target_delisted_or_context")
    lev, decimals = item.get("maxLeverage"), item.get("szDecimals")
    if (type(lev) is not int or not 1 <= lev <= 200
            or type(decimals) is not int or not 0 <= decimals <= 18):
        raise NativeMetadataSchemaError("target_leverage_precision")

    def require_decimal(field: str, reason: str, *, positive: bool = False,
                        signed: bool = False) -> Decimal:
        try:
            return _decimal_text(context.get(field), field,
                                 positive=positive, signed=signed)
        except DataValidationError:
            raise NativeMetadataSchemaError(reason) from None

    return NativePerpMetadataResearch(
        symbol=symbol,
        max_leverage_reported=lev,
        size_decimals_reported=decimals,
        day_notional_reported=require_decimal("dayNtlVlm", "target_day_notional"),
        mark_price_reported=require_decimal("markPx", "target_mark_price", positive=True),
        open_interest_reported=require_decimal("openInterest", "target_open_interest"),
        funding_rate_reported=require_decimal("funding", "target_funding", signed=True),
        observed_at_ms=observed_at_ms,
    )

def stage_hyperliquid_native_perp_candles(
    meta_and_asset_ctxs: Any,
    candle_snapshot: Sequence[Mapping[str, Any]],
    *,
    symbol: str,
    dex_scope: str,
    interval: str,
    start_open_ms: int,
    end_open_ms: int,
    context_observed_at_ms: int,
    observed_at_ms: int,
    max_context_age_ms: int,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_RESEARCH_PAGE,
) -> NativePerpCandlePageResearch:
    """Validate one exact closed, contiguous, TRADED window from supplied JSON.

    No REST request, USD conversion, base/quote volume interpretation,
    point-in-time identity check or license attestation is made.
    """
    if type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None or type(dex_scope) is not str or dex_scope != "":
        raise DataValidationError("only explicitly named native perp dex symbols allowed")
    context_time = _ms(context_observed_at_ms, "context_observed_at_ms")
    capture_time = _ms(observed_at_ms, "observed_at_ms")
    if (type(max_context_age_ms) is not int or max_context_age_ms < 0
            or max_context_age_ms > 86_400_000
            or context_time > capture_time or capture_time - context_time > max_context_age_ms):
        raise DataValidationError("context is future, stale or invalid age")
    if type(interval) is not str or interval not in _INTERVALS:
        raise DataValidationError("unsupported/non-UTC Hyperliquid candle interval")
    duration = interval_duration_ms(interval)
    if (type(start_open_ms) is not int or type(end_open_ms) is not int
            or start_open_ms < 0 or end_open_ms <= start_open_ms
            or not interval_open_aligned(interval, start_open_ms)
            or not interval_open_aligned(interval, end_open_ms)
            or (end_open_ms - start_open_ms) % duration):
        raise DataValidationError("invalid aligned ascending UTC window")
    expected = (end_open_ms - start_open_ms) // duration
    if (type(max_candles) is not int or not 1 <= max_candles <= MAX_RESEARCH_PAGE
            or expected > max_candles):
        raise DataValidationError("research page outside bounded candle limit")
    if type(close_safety_ms) is not int or not 0 <= close_safety_ms <= duration:
        raise DataValidationError("invalid candle close safety milliseconds")
    meta = _native_perp_context(
        meta_and_asset_ctxs, symbol=symbol, observed_at_ms=context_time,
    )
    if type(candle_snapshot) not in (list, tuple) or len(candle_snapshot) != expected:
        raise DataGapError("candles absent, extra or incomplete; never fill gaps")
    rows: list[NativeCandleResearch] = []
    required = {"t", "T", "s", "i", "o", "h", "l", "c", "v", "n"}
    for i, item in enumerate(candle_snapshot):
        if type(item) is not dict or set(item) != required:
            raise DataValidationError("Hyperliquid candle must have exact schema")
        opened, closed, count = item["t"], item["T"], item["n"]
        if (type(opened) is not int or type(closed) is not int
                or opened != start_open_ms + i * duration
                or closed != opened + duration - 1):
            raise DataGapError("candle has invalid UTC time, gap or ordering")
        if item["s"] != symbol or item["i"] != interval:
            raise DataValidationError("candle symbol/interval inconsistent with native scope")
        if closed + close_safety_ms > capture_time:
            raise DataValidationError("future/unclosed candle cannot enter research")
        # n=0 with normal-looking OHLC can represent a provider padded price;
        # do not accept it as real traded liquidity or a usable bar.
        if type(count) is not int or count <= 0:
            raise DataValidationError("zero-trade or malformed candle must not be considered traded")
        opening = _decimal_text(item["o"], "open", positive=True)
        high = _decimal_text(item["h"], "high", positive=True)
        low = _decimal_text(item["l"], "low", positive=True)
        closing = _decimal_text(item["c"], "close", positive=True)
        volume = _decimal_text(item["v"], "raw volume", positive=True)
        if high < max(opening, closing, low) or low > min(opening, closing, high):
            raise DataValidationError("Hyperliquid OHLC extrema inconsistent")
        rows.append(NativeCandleResearch(
            symbol=symbol, interval=interval,
            open_time_ms=opened, close_time_ms=closed,
            open=opening, high=high, low=low, close=closing,
            raw_volume_unit_unverified=volume, reported_trade_count=count,
        ))
    return NativePerpCandlePageResearch(
        symbol=symbol, interval=interval,
        start_open_ms=start_open_ms, end_open_ms=end_open_ms,
        observed_at_ms=capture_time, metadata=meta, candles=tuple(rows),
    )
