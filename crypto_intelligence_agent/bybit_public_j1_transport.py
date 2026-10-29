"""Bounded public Bybit V5 GET transport for owner-operated J1 private research.

Only fixed-origin market-data GET. Never sends credentials, orders or POSTs.
The caller must still verify eligibility, schema, times and private use rights.
"""
from __future__ import annotations

import re
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from crypto_intelligence_agent.decimal_json import decode_public_market_json_exact
from crypto_intelligence_agent.market_data import DataValidationError

BASE_URL = "https://api.bybit.com"
MAX_GETS = 500
MAX_RESPONSE_BYTES = 1_500_000
TIMEOUT_SECONDS = 8
HOUR_MS = 3_600_000
_SYMBOL = re.compile(r"^[A-Z0-9]{2,24}USDT$")


class J1BybitCaptureError(ValueError):
    """Sanitized failure code; never includes URLs, symbols or raw API bodies."""


class _DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _network_get(url: str, limit: int) -> bytes:
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with build_opener(ProxyHandler({}), _DenyRedirect()).open(
            request, timeout=TIMEOUT_SECONDS,
        ) as response:
            if (response.getcode() != 200 or response.geturl() != url
                    or response.headers.get("Content-Type", "").split(";")[0]
                    .strip().lower() != "application/json"):
                raise J1BybitCaptureError("origin_or_media_type_rejected")
            raw = response.read(limit + 1)
            if not 1 <= len(raw) <= limit:
                raise J1BybitCaptureError("response_size_rejected")
            return raw
    except HTTPError as error:
        if error.code in (401, 403, 418, 429, 451):
            raise J1BybitCaptureError("access_region_or_rate_limit_no_retry") from None
        raise J1BybitCaptureError("provider_http_error_no_retry") from None
    except (URLError, TimeoutError, ConnectionError, OSError):
        raise J1BybitCaptureError("network_error_no_retry") from None


def instruments_url(*, cursor: str | None = None, symbol: str | None = None) -> str:
    parameters = [("category", "linear")]
    if symbol is not None:
        if type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None:
            raise J1BybitCaptureError("invalid_instrument_symbol")
        parameters.extend((("symbol", symbol), ("limit", "1")))
    else:
        parameters.append(("limit", "200"))
        if cursor:
            if (type(cursor) is not str or len(cursor) > 300
                    or any(ord(c) < 33 or ord(c) > 126 for c in cursor)):
                raise J1BybitCaptureError("unsafe_instrument_cursor")
            parameters.append(("cursor", cursor))
    return BASE_URL + "/v5/market/instruments-info?" + urlencode(parameters)


def kline_url(symbol: str, start: int, end: int) -> str:
    hours, remainder = divmod(end - start, HOUR_MS)
    if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(start) is not int or type(end) is not int
            or start <= 0 or start % HOUR_MS or end % HOUR_MS or remainder
            or hours not in (1, 24, 72)):
        raise J1BybitCaptureError("invalid_kline_window")
    parameters = (
        ("category", "linear"), ("symbol", symbol), ("interval", "60"),
        ("start", str(start)), ("end", str(end - 1)),
        ("limit", str(hours)),
    )
    return BASE_URL + "/v5/market/kline?" + urlencode(parameters)


class BoundedBybitPublicClient:
    def __init__(self, transport: Callable[[str, int], bytes] | None = None):
        self.transport = transport
        self.requests_attempted = 0
        self._last_request = 0.0

    def get(self, url: str) -> tuple[bytes, dict]:
        parsed = urlsplit(url)
        queries = parse_qs(parsed.query, keep_blank_values=True)
        if (parsed.scheme != "https" or parsed.netloc != "api.bybit.com"
                or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.fragment or len(url) > 700
                or self.requests_attempted >= MAX_GETS
                or queries.get("category") != ["linear"]):
            raise J1BybitCaptureError("origin_or_get_budget_rejected")
        if parsed.path == "/v5/market/instruments-info":
            if (set(queries) == {"category", "symbol", "limit"}
                    and queries.get("limit") == ["1"]
                    and _SYMBOL.fullmatch(queries["symbol"][0]) is not None):
                allowed = url == instruments_url(symbol=queries["symbol"][0])
            elif (set(queries) in (
                    {"category", "limit"},
                    {"category", "limit", "cursor"},
                ) and queries.get("limit") == ["200"]):
                cursor = queries.get("cursor", [None])[0]
                allowed = (
                    (cursor is None or (len(cursor) > 0 and len(cursor) <= 300))
                    and url == instruments_url(cursor=cursor)
                )
            else:
                allowed = False
        elif parsed.path == "/v5/market/kline":
            allowed = (set(queries) == {
                "category", "symbol", "interval", "start", "end", "limit"
            } and queries.get("interval") == ["60"]
                and queries.get("limit") in (["1"], ["24"], ["72"])
                and _SYMBOL.fullmatch(queries.get("symbol", [""])[0]) is not None)
            if allowed:
                try:
                    start, end = int(queries["start"][0]), int(queries["end"][0]) + 1
                    allowed = url == kline_url(queries["symbol"][0], start, end)
                except (ValueError, IndexError, TypeError, J1BybitCaptureError):
                    allowed = False
        else:
            allowed = False
        if not allowed:
            raise J1BybitCaptureError("unexpected_market_data_query_rejected")
        self.requests_attempted += 1
        if self.transport is None:
            remaining = 0.16 - (time.monotonic() - self._last_request)
            if remaining > 0:
                time.sleep(remaining)
            self._last_request = time.monotonic()
        limit = (MAX_RESPONSE_BYTES if queries.get("limit") == ["200"]
                 else 131_072)
        raw = (self.transport(url, limit) if self.transport is not None
               else _network_get(url, limit))
        if type(raw) is not bytes or not 1 <= len(raw) <= limit:
            raise J1BybitCaptureError("response_body_type_or_size_rejected")
        try:
            payload = decode_public_market_json_exact(raw, max_bytes=limit)
        except DataValidationError:
            raise J1BybitCaptureError("invalid_provider_json") from None
        if type(payload.get("retCode")) is not int or payload["retCode"] != 0:
            if payload.get("retCode") in (10009, 10024):
                raise J1BybitCaptureError("provider_region_restriction")
            raise J1BybitCaptureError("provider_ret_code_failure_no_retry")
        return raw, payload
