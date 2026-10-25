"""Typed, read-only access to public linear perpetual-futures market data.

The HTTP transport is deliberately injectable.  Production can use the small
``UrllibTransport`` implementation while CI uses recorded JSON fixtures and
never contacts an exchange.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
from time import sleep
from typing import Any, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


MARKET = "linear_perpetual"
SOURCE = "binance_usdm_public"
_INTERVAL_RE = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>[mhdw])$")


class MarketDataError(Exception):
    """Base class for explicit, recoverable market-data failures."""


class DataValidationError(MarketDataError):
    pass


class IneligibleSymbolError(MarketDataError):
    pass


class DataGapError(MarketDataError):
    pass


class DuplicateCandleError(MarketDataError):
    pass


class RateLimitError(MarketDataError):
    pass


class HttpResponseError(MarketDataError):
    pass


class DataTimeoutError(MarketDataError):
    pass


@dataclass(frozen=True)
class ContractSpec:
    exchange: str
    market: str
    symbol: str
    base_asset: str
    quote_asset: str
    contract_type: str
    status: str
    onboard_time_ms: int
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal | None
    observed_at_ms: int
    source: str


@dataclass(frozen=True)
class ClosedCandle:
    exchange: str
    market: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal
    quality: str

    @property
    def identity(self) -> tuple[str, str, str, str, int]:
        return (self.exchange, self.market, self.symbol, self.interval, self.open_time_ms)


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    rank: int
    quote_volume: Decimal


@dataclass(frozen=True)
class UniverseSnapshot:
    observed_at_ms: int
    selection_rule_version: str
    eligible: tuple[UniverseMember, ...]
    excluded: Mapping[str, str]
    source: str


@dataclass(frozen=True)
class MarketDataCheckpoint:
    """A reproducible boundary for a read-only collection or replay."""

    data_type: str
    exchange: str
    symbol: str
    interval: str | None
    confirmed_start_ms: int
    confirmed_end_ms: int
    source: str
    contract_version: str
    integrity: str


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str


class HttpTransport(Protocol):
    def get(self, url: str, timeout_seconds: float) -> HttpResponse: ...


class UrllibTransport:
    """Minimal public GET client; it has no trading authentication capability."""

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        try:
            with urlopen(url, timeout=timeout_seconds) as response:  # nosec B310 - public configured endpoint
                return HttpResponse(response.status, response.read().decode("utf-8"))
        except HTTPError as error:
            return HttpResponse(error.code, error.read().decode("utf-8", errors="replace"))
        except (TimeoutError, URLError) as error:
            raise DataTimeoutError(f"public market-data request timed out: {error}") from error


class BinanceFuturesPublicAdapter:
    """Adapter for Binance USD-M public endpoints, restricted to read-only data."""

    def __init__(
        self,
        transport: HttpTransport | None = None,
        *,
        base_url: str = "https://fapi.binance.com",
        timeout_seconds: float = 10.0,
        close_safety_ms: int = 1_000,
        max_rate_limit_retries: int = 2,
        initial_backoff_seconds: float = 0.25,
    ) -> None:
        if timeout_seconds <= 0 or close_safety_ms < 0 or max_rate_limit_retries < 0 or initial_backoff_seconds < 0:
            raise ValueError("invalid timeout, candle-safety, retry, or backoff configuration")
        self._transport = transport or UrllibTransport()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._close_safety_ms = close_safety_ms
        self._max_rate_limit_retries = max_rate_limit_retries
        self._initial_backoff_seconds = initial_backoff_seconds

    def contracts(self, *, observed_at_ms: int) -> tuple[ContractSpec, ...]:
        payload = self._get_json("/fapi/v1/exchangeInfo")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("symbols"), list):
            raise DataValidationError("exchangeInfo must contain a symbols list")
        contracts = [self._parse_contract(item, observed_at_ms) for item in payload["symbols"]]
        return tuple(sorted(contracts, key=lambda contract: contract.symbol))

    def universe(
        self,
        *,
        observed_at_ms: int,
        max_symbols: int = 50,
        min_onboard_age_ms: int = 0,
        selection_rule_version: str = "j1-wu1-v1",
    ) -> UniverseSnapshot:
        if max_symbols <= 0 or min_onboard_age_ms < 0:
            raise ValueError("max_symbols must be positive and min_onboard_age_ms cannot be negative")
        contracts = self.contracts(observed_at_ms=observed_at_ms)
        ticker_payload = self._get_json("/fapi/v1/ticker/24hr")
        if not isinstance(ticker_payload, list):
            raise DataValidationError("24hr ticker response must be a list")
        volumes = {str(row.get("symbol")): _decimal(row.get("quoteVolume"), "quoteVolume") for row in ticker_payload if isinstance(row, Mapping)}
        excluded: dict[str, str] = {}
        candidates: list[tuple[str, Decimal]] = []
        for contract in contracts:
            reason = _eligibility_reason(contract, observed_at_ms, min_onboard_age_ms)
            if reason:
                excluded[contract.symbol] = reason
            elif contract.symbol not in volumes:
                excluded[contract.symbol] = "missing_quote_volume"
            elif volumes[contract.symbol] <= 0:
                excluded[contract.symbol] = "non_positive_quote_volume"
            else:
                candidates.append((contract.symbol, volumes[contract.symbol]))
        candidates.sort(key=lambda item: (-item[1], item[0]))
        return UniverseSnapshot(
            observed_at_ms=observed_at_ms,
            selection_rule_version=selection_rule_version,
            eligible=tuple(UniverseMember(symbol, index, volume) for index, (symbol, volume) in enumerate(candidates[:max_symbols], start=1)),
            excluded=excluded,
            source=SOURCE,
        )

    def closed_candles(
        self,
        symbol: str,
        interval: str,
        *,
        observed_at_ms: int,
        eligible_symbols: set[str] | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int = 500,
    ) -> tuple[ClosedCandle, ...]:
        interval_ms = _interval_ms(interval)
        if eligible_symbols is not None and symbol not in eligible_symbols:
            raise IneligibleSymbolError(f"{symbol} is not in the supplied eligible universe")
        if limit < 1 or limit > 1_500:
            raise ValueError("limit must be between 1 and 1500")
        query: dict[str, int | str] = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time_ms is not None:
            query["startTime"] = start_time_ms
        if end_time_ms is not None:
            query["endTime"] = end_time_ms
        payload = self._get_json("/fapi/v1/klines", query)
        if not isinstance(payload, list):
            raise DataValidationError("kline response must be a list")
        candles = [self._parse_candle(symbol, interval, row) for row in payload]
        closed = [candle for candle in candles if candle.close_time_ms + self._close_safety_ms <= observed_at_ms]
        return _normalise_candles(closed, interval_ms)

    def _get_json(self, path: str, query: Mapping[str, int | str] | None = None) -> Any:
        suffix = f"?{urlencode(query)}" if query else ""
        url = f"{self._base_url}{path}{suffix}"
        for attempt in range(self._max_rate_limit_retries + 1):
            response = self._transport.get(url, self._timeout_seconds)
            if response.status != 429:
                break
            if attempt < self._max_rate_limit_retries:
                sleep(self._initial_backoff_seconds * (2 ** attempt))
        if response.status == 429:
            raise RateLimitError("public API throttled the request (HTTP 429) after bounded retries")
        if response.status >= 400:
            raise HttpResponseError(f"public API returned HTTP {response.status}")
        try:
            return json.loads(response.body)
        except json.JSONDecodeError as error:
            raise DataValidationError("public API returned invalid JSON") from error

    @staticmethod
    def _parse_contract(raw: Any, observed_at_ms: int) -> ContractSpec:
        if not isinstance(raw, Mapping):
            raise DataValidationError("contract entry must be an object")
        filters = {str(item.get("filterType")): item for item in raw.get("filters", []) if isinstance(item, Mapping)}
        price_filter, lot_filter = filters.get("PRICE_FILTER"), filters.get("LOT_SIZE")
        if price_filter is None or lot_filter is None:
            raise DataValidationError(f"{raw.get('symbol', '<unknown>')} lacks required trading filters")
        notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL")
        return ContractSpec(
            exchange="binance", market=MARKET, symbol=_string(raw, "symbol"), base_asset=_string(raw, "baseAsset"),
            quote_asset=_string(raw, "quoteAsset"), contract_type=_string(raw, "contractType"), status=_string(raw, "status"),
            onboard_time_ms=_integer(raw, "onboardDate"), tick_size=_decimal(price_filter.get("tickSize"), "tickSize"),
            step_size=_decimal(lot_filter.get("stepSize"), "stepSize"), min_qty=_decimal(lot_filter.get("minQty"), "minQty"),
            min_notional=_decimal(notional_filter.get("notional") or notional_filter.get("minNotional"), "minNotional") if notional_filter else None,
            observed_at_ms=observed_at_ms, source=SOURCE,
        )

    @staticmethod
    def _parse_candle(symbol: str, interval: str, raw: Any) -> ClosedCandle:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 8:
            raise DataValidationError("kline entry must have at least eight fields")
        candle = ClosedCandle(
            exchange="binance", market=MARKET, symbol=symbol, interval=interval,
            open_time_ms=_integer_at(raw, 0, "open_time_ms"), close_time_ms=_integer_at(raw, 6, "close_time_ms"),
            open=_decimal(raw[1], "open"), high=_decimal(raw[2], "high"), low=_decimal(raw[3], "low"), close=_decimal(raw[4], "close"),
            base_volume=_decimal(raw[5], "base_volume"), quote_volume=_decimal(raw[7], "quote_volume"), quality="source_closed",
        )
        if candle.close_time_ms <= candle.open_time_ms or candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
            raise DataValidationError(f"invalid OHLC chronology for {symbol} at {candle.open_time_ms}")
        return candle


def _normalise_candles(candles: Sequence[ClosedCandle], interval_ms: int) -> tuple[ClosedCandle, ...]:
    by_identity: dict[tuple[str, str, str, str, int], ClosedCandle] = {}
    for candle in candles:
        previous = by_identity.get(candle.identity)
        if previous is not None and previous != candle:
            raise DuplicateCandleError(f"conflicting duplicate candle at {candle.identity}")
        by_identity[candle.identity] = candle
    ordered = tuple(sorted(by_identity.values(), key=lambda candle: candle.open_time_ms))
    for previous, current in zip(ordered, ordered[1:]):
        if current.open_time_ms != previous.open_time_ms + interval_ms:
            raise DataGapError(f"gap between {previous.open_time_ms} and {current.open_time_ms}")
    return ordered


def _eligibility_reason(contract: ContractSpec, observed_at_ms: int, min_onboard_age_ms: int) -> str | None:
    if contract.market != MARKET or contract.contract_type != "PERPETUAL":
        return "not_linear_perpetual"
    if contract.quote_asset != "USDT":
        return "not_usdt_quoted"
    if contract.status != "TRADING":
        return "not_trading"
    if observed_at_ms - contract.onboard_time_ms < min_onboard_age_ms:
        return "below_minimum_onboard_age"
    return None


def _interval_ms(interval: str) -> int:
    match = _INTERVAL_RE.fullmatch(interval)
    if not match:
        raise DataValidationError(f"unsupported interval: {interval}")
    multiplier = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}[match["unit"]]
    return int(match["count"]) * multiplier


def _string(raw: Mapping[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise DataValidationError(f"{field} must be a non-empty string")
    return value


def _integer(raw: Mapping[str, Any], field: str) -> int:
    return _integer_value(raw.get(field), field)


def _integer_at(raw: Sequence[Any], index: int, field: str) -> int:
    return _integer_value(raw[index], field)


def _integer_value(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise DataValidationError(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise DataValidationError(f"{field} must be an integer") from error
    return parsed


def _decimal(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise DataValidationError(f"{field} must be a decimal") from error
    if not parsed.is_finite():
        raise DataValidationError(f"{field} must be finite")
    return parsed
