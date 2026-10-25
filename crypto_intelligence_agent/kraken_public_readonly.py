"""Bounded, opt-in, PUBLIC-GET-ONLY Kraken Futures research client (J1/WU16).

The client has no key, signature, POST or order capability. It never stores
responses and never emits canonical ClosedCandle because chart trade volume
has no independently verified base/quote unit. All online access requires an
explicit allow_public_network=True; tests inject fake openers and clocks.

An HTTP200 snapshot is not a historical universe or permission to trade.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import time
from types import MappingProxyType
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .decimal_json import MAX_PUBLIC_JSON_BYTES, decode_public_market_json_exact
from .kraken_candle_validation import (
    KrakenStagedCandlePage, KRAKEN_RESOLUTIONS,
    epoch_ms_window_to_kraken_seconds, stage_kraken_trade_candles,
)
from .market_data import (
    DataTimeoutError, DataValidationError, ExchangeAccessError,
    HttpResponseError,
)


SOURCE = "kraken_futures_public_readonly_research"
_HOST = "https://futures.kraken.com"
_INSTRUMENTS_PATH = "/derivatives/api/v3/instruments"
_TICKERS_PATH = "/derivatives/api/v3/tickers"
_INSTRUMENT_FIELDS = frozenset({
    "symbol", "base", "quote", "pair", "category", "tradfi",
    "type", "tradeable", "suspended", "isExpired",
    "contractSize", "tickSize",
})
_TICKER_FIELDS = frozenset({
    "symbol", "tag", "pair", "suspended", "postOnly",
    "volumeQuote", "vol24h",
})
_MAX_TIMEOUT_S = 10.0
_MAX_SNAPSHOT_SPAN_MS = 30_000


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never follow redirects, including to other hosts or regions.
        return None


def _default_public_open(request: Request, *, timeout: float):
    return build_opener(_RejectRedirects()).open(request, timeout=timeout)


def _utc_millis() -> int:
    return int(time() * 1_000)


@dataclass(frozen=True)
class KrakenCurrentResearchSnapshot:
    """Sanitized contemporary instrument/ticker rows, NOT historical eligibility."""

    captured_start_ms: int
    captured_end_ms: int
    instruments: tuple[Mapping[str, Any], ...]
    tickers: tuple[Mapping[str, Any], ...]
    source: str = SOURCE

    @property
    def observed_at_ms(self) -> int:
        return self.captured_end_ms


@dataclass(frozen=True)
class KrakenCapturedCandleResearchPage:
    """Price-staging page with local response-capture time and unknown volume unit."""

    observed_at_ms: int
    staged: KrakenStagedCandlePage
    source: str = SOURCE


def _rows_for_research(payload: dict[str, Any], collection: str,
                       fields: frozenset[str]) -> tuple[Mapping[str, Any], ...]:
    if payload.get("result") != "success" or not isinstance(payload.get(collection), list):
        raise DataValidationError("Kraken public metadata response has invalid schema")
    by_symbol: dict[str, Mapping[str, Any]] = {}
    for row in payload[collection]:
        if not isinstance(row, dict):
            raise DataValidationError("Kraken public metadata row must be object")
        symbol = row.get("symbol")
        if (not isinstance(symbol, str) or not symbol.isascii()
                or len(symbol) > 80 or not symbol):
            raise DataValidationError("Kraken public row has invalid symbol")
        allowed = MappingProxyType({
            field: row[field] for field in fields if field in row
        })
        original = by_symbol.get(symbol)
        if original is not None and original != allowed:
            raise DataValidationError("Kraken public response has conflicting duplicate symbol")
        by_symbol[symbol] = allowed
    if not by_symbol:
        raise DataValidationError("Kraken public response has no rows")
    # Sorting ensures stable replay independent of REST response row order.
    return tuple(by_symbol[key] for key in sorted(by_symbol))


class KrakenPublicReadOnlyResearch:
    """Opt-in GET-only Kraken data for staging and risk research, never trading."""

    def __init__(
        self,
        *,
        allow_public_network: bool = False,
        opener: Callable[..., Any] | None = None,
        clock_ms: Callable[[], int] | None = None,
        timeout_seconds: float = 8.0,
        max_response_bytes: int = MAX_PUBLIC_JSON_BYTES,
        max_snapshot_span_ms: int = _MAX_SNAPSHOT_SPAN_MS,
        close_safety_ms: int = 1_000,
    ) -> None:
        if type(allow_public_network) is not bool:
            raise ValueError("allow_public_network must be explicit boolean")
        if (type(timeout_seconds) not in (float, int)
                or not 0 < timeout_seconds <= _MAX_TIMEOUT_S):
            raise ValueError("public GET timeout exceeds bounded budget")
        if (type(max_response_bytes) is not int
                or not 1 <= max_response_bytes <= MAX_PUBLIC_JSON_BYTES):
            raise ValueError("public GET response-size limit is invalid")
        if (type(max_snapshot_span_ms) is not int
                or not 1 <= max_snapshot_span_ms <= _MAX_SNAPSHOT_SPAN_MS):
            raise ValueError("public snapshot span limit is invalid")
        if type(close_safety_ms) is not int or close_safety_ms < 0:
            raise ValueError("candle close safety must be nonnegative milliseconds")
        self._allowed = allow_public_network
        self._opener = opener or _default_public_open
        self._clock = clock_ms or _utc_millis
        self._timeout = float(timeout_seconds)
        self._max_bytes = max_response_bytes
        self._max_span_ms = max_snapshot_span_ms
        self._close_safety_ms = close_safety_ms

    def _read_public(self, url: str) -> dict[str, Any]:
        if not self._allowed:
            raise ExchangeAccessError("Kraken public network is disabled by default")
        # Routes are fixed by our own methods; do not allow a URL from payload
        # or a caller to become an arbitrary outbound network request.
        if (not url.startswith(_HOST + "/")
                or not (url == _HOST + _INSTRUMENTS_PATH
                        or url == _HOST + _TICKERS_PATH
                        or url.startswith(_HOST + "/api/charts/v1/trade/PF_"))):
            raise ExchangeAccessError("unapproved Kraken public URL")
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with self._opener(request, timeout=self._timeout) as response:
                code = response.getcode()
                if code != 200:
                    raise HttpResponseError(f"Kraken public GET returned HTTP {code}")
                data = response.read(self._max_bytes + 1)
                if len(data) > self._max_bytes:
                    raise DataValidationError("Kraken public payload exceeds bounded GET size")
        except HTTPError as error:
            if error.code in (403, 418, 451):
                raise ExchangeAccessError(
                    f"Kraken public GET restricted (HTTP {error.code}); no retry"
                ) from None
            raise HttpResponseError(
                f"Kraken public GET refused (HTTP {error.code}); no retry"
            ) from None
        except (URLError, TimeoutError, OSError) as error:
            raise DataTimeoutError("Kraken public GET network failure; no retry") from None
        return decode_public_market_json_exact(data, max_bytes=self._max_bytes)

    def _now_ms(self) -> int:
        value = self._clock()
        if type(value) is not int or value <= 0:
            raise DataValidationError("local clock must provide positive UTC milliseconds")
        return value

    def current_market_snapshot(self) -> KrakenCurrentResearchSnapshot:
        """Two current public GETs; one local collection window, no backdated tags."""
        if not self._allowed:
            raise ExchangeAccessError("Kraken public network is disabled by default")
        start = self._now_ms()
        instruments = _rows_for_research(
            self._read_public(_HOST + _INSTRUMENTS_PATH),
            "instruments", _INSTRUMENT_FIELDS,
        )
        tickers = _rows_for_research(
            self._read_public(_HOST + _TICKERS_PATH),
            "tickers", _TICKER_FIELDS,
        )
        end = self._now_ms()
        if end < start or end - start > self._max_span_ms:
            raise DataValidationError("Kraken public snapshot clock regressed or collection span expired")
        return KrakenCurrentResearchSnapshot(
            captured_start_ms=start, captured_end_ms=end,
            instruments=instruments, tickers=tickers,
        )

    def staged_closed_candles(
        self, *,
        symbol: str, interval: str, start_open_ms: int, end_open_ms: int,
    ) -> KrakenCapturedCandleResearchPage:
        """Return closed OHLC staging ONLY; raw trade volume has no proven unit."""
        if not self._allowed:
            raise ExchangeAccessError("Kraken public network is disabled by default")
        if (not isinstance(symbol, str) or not symbol.isascii()
                or not symbol.startswith("PF_") or len(symbol) > 48
                or not symbol.isupper() or not symbol[3:].isalnum()):
            raise DataValidationError("invalid Kraken perpetual chart symbol")
        if interval not in KRAKEN_RESOLUTIONS:
            raise DataValidationError("unsupported Kraken chart resolution")
        from_seconds, to_seconds = epoch_ms_window_to_kraken_seconds(
            interval=interval, start_open_ms=start_open_ms,
            end_open_ms=end_open_ms,
        )
        url = (_HOST + f"/api/charts/v1/trade/{symbol}/{interval}"
               + f"?from={from_seconds}&to={to_seconds}")
        chart = self._read_public(url)
        observed = self._now_ms()
        staging = stage_kraken_trade_candles(
            chart, symbol=symbol, interval=interval,
            start_open_ms=start_open_ms, end_open_ms=end_open_ms,
            observed_at_ms=observed,
            close_safety_ms=self._close_safety_ms,
        )
        return KrakenCapturedCandleResearchPage(
            observed_at_ms=observed, staged=staging,
        )
