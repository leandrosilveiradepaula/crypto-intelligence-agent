"""One-shot OKX BTC-USDT-SWAP conformance for personal research (J1/WU32).

No credentials, orders, persistence, market prices in logs, retries or redirects.
Network disabled unless both opt-ins are explicitly passed. Not a live-data
license, crypto identity assertion or canonical ClosedCandle adapter.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from time import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.okx_swap_candle_research import stage_okx_linear_swap_history

HOST = "https://www.okx.com"
SYMBOL = "BTC-USDT-SWAP"
INSTRUMENTS_URL = HOST + "/api/v5/public/instruments?instType=SWAP&instId=" + SYMBOL
CANDLES_URL = HOST + "/api/v5/market/history-candles?instId=" + SYMBOL + "&bar=1H&limit=6"
HOUR_MS = 3_600_000
TIMEOUT_SECONDS = 8
MAX_BYTES = 131_072
MAX_SPAN_MS = 30_000


class ProbeError(ValueError):
    """Sanitized, finite diagnostic code, never remote response text."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(req: Request, *, timeout: int):
    return build_opener(ProxyHandler({}), _NoRedirects()).open(req, timeout=timeout)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ProbeError("duplicate_json_key")
        output[key] = value
    return output


def _no_nonfinite(value: str):
    raise ProbeError("nonfinite_json")


def _decode(raw: bytes) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_float=Decimal, parse_constant=_no_nonfinite)
    except ProbeError:
        raise
    except (ValueError, UnicodeDecodeError, RecursionError, OverflowError):
        raise ProbeError("invalid_json") from None


def _get(url: str, *, opened: Callable[..., Any],
         report: dict[str, Any], digest_field: str) -> Any:
    if url not in (INSTRUMENTS_URL, CANDLES_URL):
        raise ProbeError("unapproved_public_url")
    if report["requests_attempted"] >= 2:
        raise ProbeError("request_budget_exhausted")
    req = Request(url, method="GET", headers={"Accept": "application/json"})
    report["requests_attempted"] += 1
    try:
        with opened(req, timeout=TIMEOUT_SECONDS) as response:
            if response.getcode() != 200:
                raise ProbeError("unexpected_http_status")
            if response.geturl() != url:
                raise ProbeError("redirect_or_wrong_host")
            if response.headers.get("Content-Type", "").split(";")[0].lower() != "application/json":
                raise ProbeError("unexpected_content_type")
            raw = response.read(MAX_BYTES + 1)
            if not 1 <= len(raw) <= MAX_BYTES:
                raise ProbeError("invalid_response_size")
    except HTTPError as error:
        if error.code in (301, 302, 303, 307, 308):
            raise ProbeError("redirect_rejected") from None
        if error.code in (403, 418, 429, 451):
            raise ProbeError("access_or_rate_restricted") from None
        raise ProbeError("http_error") from None
    except (URLError, TimeoutError, ConnectionError, OSError):
        raise ProbeError("network_failure") from None
    report[digest_field] = sha256(raw).hexdigest()
    return _decode(raw)


def _now(clock_ms: Callable[[], int]) -> int:
    value = clock_ms()
    if type(value) is not int or not 10 * HOUR_MS < value < 253_402_300_799_999:
        raise ProbeError("invalid_utc_clock")
    return value


def _instrument_metadata(payload: Any) -> None:
    if (type(payload) is not dict or payload.get("code") != "0"
            or type(payload.get("msg")) is not str
            or type(payload.get("data")) is not list
            or len(payload["data"]) != 1):
        raise ProbeError("invalid_instrument_envelope")
    row = payload["data"][0]
    if (type(row) is not dict or row.get("instId") != SYMBOL
            or row.get("instType") != "SWAP" or row.get("ctType") != "linear"
            or row.get("state") != "live" or row.get("settleCcy") != "USDT"):
        raise ProbeError("invalid_instrument_schema")


def _fixed_closed_window(payload: Any, *, start_ms: int, end_ms: int) -> dict[str, Any]:
    if (type(payload) is not dict or payload.get("code") != "0"
            or type(payload.get("msg")) is not str
            or type(payload.get("data")) is not list
            or not 3 <= len(payload["data"]) <= 6):
        raise ProbeError("invalid_candles_envelope")
    selected = []
    for row in payload["data"]:
        if (type(row) is not list or len(row) != 9
                or type(row[0]) is not str or not row[0].isascii()
                or not row[0].isdigit() or len(row[0]) > 16):
            raise ProbeError("invalid_candle_row")
        timestamp = int(row[0])
        if start_ms <= timestamp < end_ms:
            selected.append(row)
    if len(selected) != 3:
        raise ProbeError("closed_window_incomplete")
    return {"code": payload["code"], "msg": payload["msg"], "data": selected}


def inspect_once(*, allow_public_network: bool, allow_okx_personal_probe: bool,
                 opened: Callable[..., Any] | None = None,
                 clock_ms: Callable[[], int] | None = None) -> dict[str, Any]:
    """At most two keyless GET requests; report only sanitized structural evidence."""
    if allow_public_network is not True or allow_okx_personal_probe is not True:
        raise ProbeError("double_opt_in_required")
    now = _now(clock_ms or (lambda: int(time() * 1000)))
    top = (now // HOUR_MS) * HOUR_MS
    # Previous fully closed bar is excluded as a conservative extra buffer.
    start, end = top - 4 * HOUR_MS, top - HOUR_MS
    report: dict[str, Any] = {
        "schema_version": "j1-okx-btc-private-conformance-v1",
        "provider": "okx_v5_swap",
        "instrument": SYMBOL, "interval": "1h",
        "observed_at_utc": datetime.fromtimestamp(now / 1000, timezone.utc).isoformat(timespec="seconds"),
        "window_start_ms": start, "window_end_ms_exclusive": end,
        "requests_attempted": 0, "credentials_used": False,
        "orders_sent": False, "raw_responses_persisted": False,
        "crypto_identity_verified": False, "canonical_ohlcv_approved": False,
        "commercial_or_public_rights_verified": False,
        "ready_for_live_top50": False, "ready_for_trading": False,
    }
    get = opened or _open
    clock = clock_ms or (lambda: int(time() * 1000))
    try:
        metadata = _get(INSTRUMENTS_URL, opened=get, report=report,
                        digest_field="instruments_response_sha256")
        _instrument_metadata(metadata)
        instrument_observed = _now(clock)
        report["instrument_schema_observed"] = True
        if instrument_observed < now or instrument_observed - now > MAX_SPAN_MS:
            raise ProbeError("capture_window_expired")
        raw_candles = _get(CANDLES_URL, opened=get, report=report,
                           digest_field="candles_response_sha256")
        captured = _now(clock)
        if captured < instrument_observed or captured - now > MAX_SPAN_MS:
            raise ProbeError("capture_window_expired")
        bounded = _fixed_closed_window(raw_candles, start_ms=start, end_ms=end)
        page = stage_okx_linear_swap_history(
            bounded, instrument_id=SYMBOL, quote_currency="USDT",
            instrument_type="SWAP", contract_type="linear",
            instrument_status="live", settlement_currency="USDT",
            instrument_observed_at_ms=instrument_observed,
            observed_at_ms=captured, max_instrument_age_ms=MAX_SPAN_MS,
            bar="1H", start_open_ms=start, end_open_ms=end,
            close_safety_ms=1_000, max_candles=3,
        )
        if not any(c.documented_quote_volume > 0 for c in page.candles):
            raise ProbeError("zero_observed_quote_volume")
        report["closed_candles_validated"] = len(page.candles)
        report["documented_quote_currency"] = "USDT"
        report["documented_volume_fields"] = ["vol_contracts", "volCcy_base", "volCcyQuote_quote"]
        report["status"] = "observed_private_schema_only"
    except ProbeError as error:
        report["status"] = error.args[0]
    except (DataValidationError, DataGapError):
        report["status"] = "staged_candle_contract_rejected"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-okx-personal-probe", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_once(allow_public_network=args.allow_public_network,
                              allow_okx_personal_probe=args.allow_okx_personal_probe)
    except ProbeError as error:
        result = {"status": error.args[0], "requests_attempted": 0,
                  "orders_sent": False, "raw_responses_persisted": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "observed_private_schema_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
