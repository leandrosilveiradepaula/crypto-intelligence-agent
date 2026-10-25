"""J1/WU39: documented Bybit V5 *offline* linear instrument + kline contract.

Bybit official schema: https://bybit-exchange.github.io/docs/v5/market/kline
USDT/USDC linear kline volume is in BASE coin, turnover in QUOTE coin.
Instrument structure: https://bybit-exchange.github.io/docs/v5/market/instrument

This module DOES NOT authenticate a live response, issue requests, approve
Bybit market-data usage, create ClosedCandle or write to SQLite. Its inputs
may be synthetic. Provider rights and regional eligibility remain gated.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any, Mapping

from .bybit_linear_candle_research import (
    BybitLinearCandlePageResearch, stage_bybit_linear_kline,
)
from .market_data import DataValidationError
from .research_registry_catalog import load_reviewed_registry

_SOURCE = "bybit_v5_linear_instrument_offline_schema"
_BASE = re.compile(r"^[A-Z0-9]{2,24}$")
_DIGITS = re.compile(r"^(0|[1-9][0-9]{0,15})$")
_POSITIVE = re.compile(r"^(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?$")
_QUOTE = frozenset({"USDT", "USDC"})


@dataclass(frozen=True)
class BybitLinearInstrumentResearch:
    """Validated V5 metadata SHAPE + local reviewed base, not a live listing."""

    symbol: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    observed_at_ms: int
    launch_time_ms: int
    max_leverage: Decimal
    tick_size: Decimal
    quantity_step: Decimal
    registry_sha256: str
    source: str = _SOURCE

    @property
    def live_metadata_authenticated(self) -> bool:
        return False

    @property
    def public_or_commercial_use_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class BybitLinearDocumentedPageResearch:
    """Only offline documented unit conformance, NEVER canonical OHLCV."""

    instrument: BybitLinearInstrumentResearch
    page: BybitLinearCandlePageResearch

    @property
    def base_volume_unit(self) -> str:
        return self.instrument.base_coin

    @property
    def quote_turnover_unit(self) -> str:
        return self.instrument.quote_coin

    @property
    def canonical_ohlcv(self) -> bool:
        return False

    @property
    def live_provider_verified(self) -> bool:
        return False

    @property
    def public_or_commercial_use_authorized(self) -> bool:
        return False


def _epoch_millis(value: Any, *, label: str, zero: bool = False) -> int:
    if type(value) is not str or _DIGITS.fullmatch(value) is None:
        raise DataValidationError(f"Bybit instrument {label} must be UTC-ms decimal string")
    parsed = int(value)
    if not zero and parsed <= 0:
        raise DataValidationError(f"Bybit instrument {label} must be positive")
    return parsed


def _positive_decimal(value: Any, *, label: str) -> Decimal:
    if type(value) is not str or _POSITIVE.fullmatch(value) is None:
        raise DataValidationError(f"Bybit instrument {label} must be exact decimal string")
    parsed = Decimal(value)
    if not parsed.is_finite() or parsed <= 0:
        raise DataValidationError(f"Bybit instrument {label} must be positive")
    return parsed


def validate_bybit_linear_instrument(
    payload: Mapping[str, Any],
    *, symbol: str, observed_at_ms: int,
    registry_variant: str = "btc-eth",
    max_server_skew_ms: int = 30_000,
) -> BybitLinearInstrumentResearch:
    """Validate one unambiguous, crypto-only, active linear perpetual row.

    Input is merely caller-provided structured data; no network source can be
    authenticated by this pure function. The real venue still requires an
    independently verified fetch and rights review.
    """
    if (type(symbol) is not str or not symbol.isascii()
            or len(symbol) > 30 or not symbol.isupper()):
        raise DataValidationError("Bybit instrument requested symbol malformed")
    suffix = "USDT" if symbol.endswith("USDT") else ("USDC" if symbol.endswith("USDC") else None)
    if suffix is None:
        raise DataValidationError("Bybit only USDT or USDC linear quotes are permitted")
    base = symbol[:-len(suffix)]
    if _BASE.fullmatch(base) is None:
        raise DataValidationError("Bybit linear symbol needs exact crypto base and quote")
    if (type(observed_at_ms) is not int or observed_at_ms <= 0
            or type(max_server_skew_ms) is not int or max_server_skew_ms < 0
            or max_server_skew_ms > 30_000):
        raise DataValidationError("Bybit instrument observation/skew invalid")
    registry = load_reviewed_registry(registry_variant, as_of_ms=observed_at_ms)
    if base not in registry.verified_crypto_bases:
        raise DataValidationError("Bybit base not in reviewed point-in-time crypto identity register")
    if (not isinstance(payload, Mapping) or type(payload.get("retCode")) is not int
            or payload.get("retCode") != 0):
        raise DataValidationError("Bybit instrument response status untrusted")
    result = payload.get("result")
    if (not isinstance(result, Mapping) or result.get("category") != "linear"
            or result.get("nextPageCursor") != ""
            or type(result.get("list")) is not list
            or len(result["list"]) != 1
            or type(payload.get("time")) is not int):
        raise DataValidationError("Bybit must return exact unpaginated single linear instrument")
    server_time = payload["time"]
    if (server_time <= 0 or server_time > observed_at_ms
            or observed_at_ms - server_time > max_server_skew_ms):
        raise DataValidationError("Bybit instrument server time missing, future or stale")
    row = result["list"][0]
    if not isinstance(row, Mapping):
        raise DataValidationError("Bybit instrument row missing")
    if (row.get("symbol") != symbol or row.get("baseCoin") != base
            or row.get("quoteCoin") != suffix or row.get("settleCoin") != suffix
            or row.get("contractType") != "LinearPerpetual"
            or row.get("status") != "Trading"):
        raise DataValidationError("Bybit is not exact trading linear crypto perpetual")
    # Official V5 now also carries TradFi perps. Empty region/underlying are
    # mandatory positive checks, NOT absence-of-evidence passed as crypto.
    if (row.get("symbolType") != "" or row.get("marketRegion") != ""
            or row.get("underlyingTicker") != ""
            or row.get("tags") != []
            or row.get("isPreListing") is not False
            or row.get("preListingInfo") is not None
            or row.get("deliveryTime") != "0"):
        raise DataValidationError("Bybit non-crypto, prelisting or expiring contract")
    launch_time = _epoch_millis(row.get("launchTime"), label="launchTime")
    if launch_time > server_time:
        raise DataValidationError("Bybit instrument listed after captured metadata")
    leverage = row.get("leverageFilter")
    price_filter = row.get("priceFilter")
    lot_filter = row.get("lotSizeFilter")
    if (not isinstance(leverage, Mapping)
            or not isinstance(price_filter, Mapping)
            or not isinstance(lot_filter, Mapping)):
        raise DataValidationError("Bybit financial contract limits missing")
    min_lev = _positive_decimal(leverage.get("minLeverage"), label="minLeverage")
    max_lev = _positive_decimal(leverage.get("maxLeverage"), label="maxLeverage")
    if min_lev > max_lev:
        raise DataValidationError("Bybit financial leverage bounds inverted")
    tick = _positive_decimal(price_filter.get("tickSize"), label="tickSize")
    step = _positive_decimal(lot_filter.get("qtyStep"), label="qtyStep")
    return BybitLinearInstrumentResearch(
        symbol=symbol, base_coin=base, quote_coin=suffix, settle_coin=suffix,
        observed_at_ms=observed_at_ms, launch_time_ms=launch_time,
        max_leverage=max_lev, tick_size=tick, quantity_step=step,
        registry_sha256=registry.sha256_digest,
    )


def stage_bybit_documented_linear_pair(
    *, instrument_payload: Mapping[str, Any], kline_payload: Mapping[str, Any],
    symbol: str, instrument_observed_at_ms: int, kline_observed_at_ms: int,
    interval: str, start_open_ms: int, end_open_ms: int,
    registry_variant: str = "btc-eth",
    max_contract_age_ms: int = 30_000,
    close_safety_ms: int = 1_000,
) -> BybitLinearDocumentedPageResearch:
    """Use ONE existing kline parser, with provider metadata no longer asserted.

    Quality is research-only. A fixture passing these checks is not evidence
    of exchange access and cannot be promoted to canonical data or a release.
    """
    instrument = validate_bybit_linear_instrument(
        instrument_payload, symbol=symbol,
        observed_at_ms=instrument_observed_at_ms,
        registry_variant=registry_variant,
    )
    if (type(max_contract_age_ms) is not int
            or not 0 <= max_contract_age_ms <= 30_000
            or type(kline_observed_at_ms) is not int
            or kline_observed_at_ms < instrument_observed_at_ms
            or kline_observed_at_ms - instrument_observed_at_ms > max_contract_age_ms):
        raise DataValidationError("Bybit document-only chart lacks recent contract metadata")
    page = stage_bybit_linear_kline(
        kline_payload, symbol=instrument.symbol,
        quote_currency=instrument.quote_coin,
        contract_type="LinearPerpetual", contract_status="Trading",
        contract_observed_at_ms=instrument.observed_at_ms,
        observed_at_ms=kline_observed_at_ms,
        max_contract_age_ms=max_contract_age_ms,
        interval=interval, start_open_ms=start_open_ms,
        end_open_ms=end_open_ms, close_safety_ms=close_safety_ms,
    )
    if (page.symbol != instrument.symbol or page.quote_currency != instrument.quote_coin
            or page.observed_at_ms != kline_observed_at_ms):
        raise DataValidationError("Bybit documented page and exact instrument identity mismatch")
    return BybitLinearDocumentedPageResearch(instrument, page)
