"""Bounded public Bybit V5 GET transport for owner-operated J1 private research.

Only fixed-origin market-data GET. Never sends credentials, orders or POSTs.
The caller must still verify eligibility, schema, times and private use rights.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
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
# Intentionally slower than the provider's nominal per-second/UID budget:
# public GET responses can share effective quotas with other activity.
# Bounded owner-only J1: 1 GET start every 2 seconds, no retry on 10006.
# Never treat a known public budget as a guarantee of available capacity.
MIN_PUBLIC_GET_INTERVAL_SECONDS = 2.0
HOUR_MS = 3_600_000
_SYMBOL = re.compile(r"^[A-Z0-9]{2,24}USDT$")
# Explicitly documented provider codes only. Do not print provider bodies or
# retMsg (which might contain a symbol or untrusted arbitrary text).
_KNOWN_PROVIDER_CODES = frozenset({
    -1, 429, 10000, 10001, 10003, 10004, 10005, 10006, 10007,
    10008, 10009, 10014, 10016, 10017, 10024, 10027, 10029,
})


def classify_provider_retcode(code: object) -> str:
    """Stable human-actionable class from official Bybit V5 retCodes."""
    if type(code) is not int:
        return "provider_retcode_invalid_no_retry"
    if code in (10009, 10024):
        return "provider_region_restriction"
    if code == 10006:
        return "provider_rate_limit_no_retry"
    if code == 10001:
        return "provider_request_parameters_rejected_no_retry"
    if code in (10000, 10016, 429):
        return "provider_server_unavailable_no_retry"
    if code in (10017, 10029):
        return "provider_route_or_symbol_unavailable_no_retry"
    if code in (10003, 10004, 10005, 10007, 10008, 10027):
        return "provider_access_or_permission_denied_no_retry"
    if code in (-1, 10014):
        return "provider_request_identity_rejected_no_retry"
    return "provider_unclassified_ret_code_no_retry"



class J1BybitCaptureError(ValueError):
    """Sanitized failure code; never includes URLs, symbols or raw API bodies."""


@dataclass(frozen=True)
class BybitQuotaObservation:
    """Bounded numerical HTTP metadata ONLY; never retain full headers."""

    headers_present: bool
    limit: int | None
    remaining: int | None
    reset_header_delta_ms: int | None

    def sanitized_fields(self) -> dict[str, bool | int]:
        out: dict[str, bool | int] = {
            "provider_quota_headers_present": self.headers_present,
        }
        if self.limit is not None:
            out["provider_endpoint_limit"] = self.limit
        if self.remaining is not None:
            out["provider_endpoint_remaining"] = self.remaining
        if self.reset_header_delta_ms is not None:
            out["provider_reset_header_delta_ms"] = self.reset_header_delta_ms
        return out


@dataclass(frozen=True)
class _NetworkGetWithQuota:
    raw: bytes
    quota: BybitQuotaObservation


def _bounded_nonnegative_http_int(headers, key: str, upper: int) -> int | None:
    """Treat HTTP response headers as UNTRUSTED strings, not instructions."""
    raw = headers.get(key)
    if (type(raw) is not str or not 1 <= len(raw) <= 13
            or not raw.isascii() or not raw.isdecimal()):
        return None
    value = int(raw)
    return value if 0 <= value <= upper else None


def _read_bybit_quota_headers(headers) -> BybitQuotaObservation:
    names = (
        "X-Bapi-Limit", "X-Bapi-Limit-Status", "X-Bapi-Limit-Reset-Timestamp",
    )
    present = any(headers.get(name) is not None for name in names)
    limit = _bounded_nonnegative_http_int(
        headers, names[0], 10_000,
    )
    remaining = _bounded_nonnegative_http_int(
        headers, names[1], 10_000,
    )
    reset_ms = _bounded_nonnegative_http_int(
        headers, names[2], 4_000_000_000_000,
    )
    if limit is not None and remaining is not None and remaining > limit:
        remaining = None
    wait_ms = None
    if reset_ms is not None:
        # On successful GET the documented header may be current server
        # time, NOT an actual cooldown. The output name deliberately says
        # 'header_delta', NEVER 'wait'. It is an observation only and cannot
        # trigger a sleep, retry, ban claim, or redirect.
        relative = reset_ms - int(time.time() * 1000)
        if 0 <= relative <= 600_000:
            wait_ms = relative
    return BybitQuotaObservation(
        headers_present=present, limit=limit, remaining=remaining,
        reset_header_delta_ms=wait_ms,
    )


class _DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _network_get(url: str, limit: int) -> _NetworkGetWithQuota:
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with build_opener(ProxyHandler({}), _DenyRedirect()).open(
            request, timeout=TIMEOUT_SECONDS,
        ) as response:
            if (response.getcode() != 200 or response.geturl() != url
                    or response.headers.get("Content-Type", "").split(";")[0]
                    .strip().lower() != "application/json"):
                raise J1BybitCaptureError("origin_or_media_type_rejected")
            quota = _read_bybit_quota_headers(response.headers)
            raw = response.read(limit + 1)
            if not 1 <= len(raw) <= limit:
                raise J1BybitCaptureError("response_size_rejected")
            return _NetworkGetWithQuota(raw=raw, quota=quota)
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
        parameters.append(("limit", "1000"))
        if cursor:
            if (type(cursor) is not str or len(cursor) > 300
                    or any(ord(c) < 33 or ord(c) > 126 for c in cursor)):
                raise J1BybitCaptureError("unsafe_instrument_cursor")
            parameters.append(("cursor", cursor))
    return BASE_URL + "/v5/market/instruments-info?" + urlencode(parameters)


def tickers_url() -> str:
    """Only the all-linear public ticker snapshot, never a trading endpoint."""
    return BASE_URL + "/v5/market/tickers?category=linear"


def kline_url(symbol: str, start: int, end: int) -> str:
    hours, remainder = divmod(end - start, HOUR_MS)
    if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(start) is not int or type(end) is not int
            or start <= 0 or start % HOUR_MS or end % HOUR_MS or remainder
            or hours not in (*range(1, 73), 720)):
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
        # None means the first request is not artificially delayed. A real
        # request always records its start *after* any required cooldown.
        self._last_request: float | None = None
        self.last_request_stage: str | None = None
        self.last_provider_retcode: int | None = None
        self.last_provider_quota: BybitQuotaObservation | None = None

    def sanitized_quota_fields(self) -> dict[str, bool | int]:
        """No headers, API responses, tokens, symbols, URLs or account data."""
        if self.last_provider_quota is None:
            return {"provider_quota_headers_present": False}
        return self.last_provider_quota.sanitized_fields()

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
                ) and queries.get("limit") == ["1000"]):
                cursor = queries.get("cursor", [None])[0]
                allowed = (
                    (cursor is None or (len(cursor) > 0 and len(cursor) <= 300))
                    and url == instruments_url(cursor=cursor)
                )
            else:
                allowed = False
        elif parsed.path == "/v5/market/tickers":
            # Only one public aggregate endpoint, no optional filter params.
            allowed = url == tickers_url()
        elif parsed.path == "/v5/market/kline":
            allowed = (set(queries) == {
                "category", "symbol", "interval", "start", "end", "limit"
            } and queries.get("interval") == ["60"]
                and queries.get("limit", [""])[0].isascii()
                and queries.get("limit", [""])[0].isdecimal()
                and int(queries["limit"][0]) in (*range(1, 73), 720)
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
        self.last_request_stage = (
            "instrument_metadata" if parsed.path.endswith("instruments-info")
            and "symbol" in queries else
            "instrument_universe" if parsed.path.endswith("instruments-info")
            else "ticker_review_proxy" if parsed.path.endswith("tickers")
            else "closed_kline_" + queries["limit"][0] + "h"
        )
        self.last_provider_retcode = None
        self.last_provider_quota = None
        self.requests_attempted += 1
        if self.transport is None:
            # The original 160ms spacing could submit >6 GET/s and offered
            # little headroom for other applications sharing a quota.
            # Do not retry a failing request: a 10006 always propagates and
            # leaves the already-committed SQLite research history intact.
            if self._last_request is not None:
                remaining = (MIN_PUBLIC_GET_INTERVAL_SECONDS
                             - (time.monotonic() - self._last_request))
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request = time.monotonic()
        limit = (
            MAX_RESPONSE_BYTES if (
                (parsed.path == "/v5/market/instruments-info"
                 and queries.get("limit") == ["1000"])
                or parsed.path == "/v5/market/tickers"
            ) else 131_072
        )
        wire = (self.transport(url, limit) if self.transport is not None
                else _network_get(url, limit))
        if type(wire) is _NetworkGetWithQuota:
            self.last_provider_quota = wire.quota
            raw = wire.raw
        else:
            # Keep the existing injected bytes transport (all offline tests)
            # unchanged. Never fabricate a provider rate-limit header.
            raw = wire
        if type(raw) is not bytes or not 1 <= len(raw) <= limit:
            raise J1BybitCaptureError("response_body_type_or_size_rejected")
        try:
            payload = decode_public_market_json_exact(raw, max_bytes=limit)
        except DataValidationError:
            raise J1BybitCaptureError("invalid_provider_json") from None
        ret_code = payload.get("retCode")
        if type(ret_code) is not int or ret_code != 0:
            # An unknown numeric code is deliberately not reflected, while
            # documented codes can be safely reported as a single integer.
            if type(ret_code) is int and ret_code in _KNOWN_PROVIDER_CODES:
                self.last_provider_retcode = ret_code
            raise J1BybitCaptureError(classify_provider_retcode(ret_code))
        return raw, payload
