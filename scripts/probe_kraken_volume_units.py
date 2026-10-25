"""One-shot Kraken Futures *volume unit diagnostic*, never an adapter.

Public GET only, no redirects, no retries, no secrets, no orders. Output is
sanitized aggregates, not raw data and not proof of base/quote volume units.
Default CLI makes ZERO network requests unless two opt-in flags are supplied.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from time import monotonic, time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request

from scripts.probe_public_kraken import (
    MAX_RESPONSE_BYTES, MAX_TIMEOUT_SECONDS, _default_open,
)
from crypto_intelligence_agent.kraken_candle_validation import _raw_trade_volume
from crypto_intelligence_agent.decimal_json import (
    decode_public_market_json_exact, positive_market_decimal,
)
from crypto_intelligence_agent.market_data import DataValidationError


CANDLES_URL = "https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/1h?count=27"
TICKERS_URL = "https://futures.kraken.com/derivatives/api/v3/tickers"
SYMBOL = "PF_XBTUSD"
HOUR_MS = 3_600_000
WINDOW_HOURS = 24
CLOSE_SAFETY_MS = 1_000
MAX_ROWS = 27


def _safe_positive_decimal(value: Any) -> str | None:
    try:
        # From exact JSON Decimal/int/string only; reject native binary float.
        return str(positive_market_decimal(value, "Kraken public ticker volume"))
    except DataValidationError:
        return None


def _get_json(
    *, route: str, url: str, opener: Callable[..., Any],
) -> tuple[dict[str, object], dict[str, Any] | None]:
    started = monotonic()
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=MAX_TIMEOUT_SECONDS) as response:
            status = response.getcode()
            if status != 200:
                return {"route": route, "http_status": status, "status": "http_error"}, None
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                return {"route": route, "http_status": 200, "status": "response_too_large"}, None
            try:
                payload = decode_public_market_json_exact(data, max_bytes=MAX_RESPONSE_BYTES)
            except (DataValidationError, ValueError, UnicodeDecodeError):
                return {"route": route, "http_status": 200, "status": "invalid_json"}, None
            if not isinstance(payload, dict):
                return {"route": route, "http_status": 200, "status": "invalid_schema"}, None
            return {
                "route": route, "http_status": 200, "status": "ok",
                "elapsed_ms": int((monotonic() - started) * 1000),
            }, payload
    except HTTPError as error:
        return {
            "route": route, "http_status": error.code,
            "status": "access_or_policy_restriction"
            if error.code in (403, 418, 451) else "http_error",
        }, None
    except (URLError, TimeoutError, OSError):
        return {"route": route, "status": "network_or_dns_failure"}, None


def describe_chart_structure(
    payload: Mapping[str, Any], *, observed_at_ms: int,
) -> dict[str, object]:
    """Only count/timestamp/type metadata; never expose raw price/volume rows.

    Diagnostics intentionally do NOT relax validation or produce financial
    volume units. Used when an HTTP 200 response fails the strict chart gate.
    """
    rows = payload.get("candles")
    if not isinstance(rows, list):
        return {"candles_shape": "not_list", "more_candles_is_boolean":
                type(payload.get("more_candles")) is bool}
    type_counts: dict[str, int] = {
        "integer": 0, "decimal_string": 0, "other_string": 0,
        "float": 0, "boolean": 0, "missing_or_other": 0,
    }
    valid_opens: list[int] = []
    invalid_grid_times = 0
    for row in rows[:MAX_ROWS + 1]:
        if not isinstance(row, dict):
            type_counts["missing_or_other"] += 1
            continue
        volume = row.get("volume")
        if type(volume) is int:
            type_counts["integer"] += 1
        elif type(volume) is str:
            # Only classify, never emit the string itself.
            try:
                parsed = Decimal(volume) if len(volume) <= 90 else None
            except InvalidOperation:
                parsed = None
            key = ("decimal_string" if parsed is not None and parsed.is_finite()
                   else "other_string")
            type_counts[key] += 1
        elif type(volume) is float:
            type_counts["float"] += 1
        elif type(volume) is bool:
            type_counts["boolean"] += 1
        else:
            type_counts["missing_or_other"] += 1
        timestamp = row.get("time")
        if type(timestamp) is int and timestamp >= 0 and timestamp % HOUR_MS == 0:
            valid_opens.append(timestamp)
        else:
            invalid_grid_times += 1
    closed = sum(
        t + HOUR_MS - 1 + CLOSE_SAFETY_MS <= observed_at_ms
        for t in valid_opens
    )
    return {
        "chart_row_count": len(rows),
        "inspected_row_limit": MAX_ROWS + 1,
        "more_candles_is_boolean": type(payload.get("more_candles")) is bool,
        "more_candles_value": payload.get("more_candles")
        if type(payload.get("more_candles")) is bool else None,
        "raw_volume_field_types": type_counts,
        "valid_utc_hour_grid_count_in_sample": len(valid_opens),
        "invalid_hour_grid_count_in_sample": invalid_grid_times,
        "closed_hour_grid_count_in_sample": closed,
        "first_valid_hour_open_ms": valid_opens[0] if valid_opens else None,
        "last_valid_hour_open_ms": valid_opens[-1] if valid_opens else None,
        "unit_proof": False,
    }


def summarize_closed_chart(
    payload: Mapping[str, Any], *,
    observed_at_ms: int,
) -> dict[str, object]:
    """Return opaque integer volume sum for 24 consecutive closed hourly bars.

    No base/quote unit conversion and no inference about 24h rolling windows.
    """
    if type(observed_at_ms) is not int or observed_at_ms <= 0:
        raise ValueError("observed_at_ms must be positive UTC-ms integer")
    rows = payload.get("candles")
    if (not isinstance(rows, list) or not 24 <= len(rows) <= MAX_ROWS
            or type(payload.get("more_candles")) is not bool):
        raise ValueError("chart does not contain 24-27 candles and a pagination flag")
    validated: list[tuple[int, Decimal]] = []
    previous_time = -1
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("chart candle must be an object")
        timestamp = row.get("time")
        if (type(timestamp) is not int or timestamp < 0
                or timestamp % HOUR_MS != 0 or timestamp <= previous_time):
            raise ValueError("invalid chart timestamp, order or UTC hour grid")
        previous_time = timestamp
        try:
            # Share WU11 strict parser: the actual chart returned bounded
            # decimal-string values, not the documented int64 field type.
            raw_volume = _raw_trade_volume(row.get("volume"))
        except DataValidationError as exc:
            raise ValueError("invalid unverified raw volume type or value") from exc
        if timestamp + HOUR_MS - 1 + CLOSE_SAFETY_MS <= observed_at_ms:
            validated.append((timestamp, raw_volume))
    if len(validated) < WINDOW_HOURS:
        raise ValueError("not enough closed hourly candles")
    sample = validated[-WINDOW_HOURS:]
    for (before, _), (after, _) in zip(sample, sample[1:]):
        if after - before != HOUR_MS:
            raise ValueError("closed volume comparison has gaps or duplicates")
    return {
        "closed_candles_used": WINDOW_HOURS,
        "window_start_open_time_ms": sample[0][0],
        "window_end_open_exclusive_ms": sample[-1][0] + HOUR_MS,
        "sum_24_closed_hours_raw_volume_unverified": str(
            sum((v for _, v in sample), Decimal(0))
        ),
        "raw_volume_unit": "unverified",
        "chart_count_received": len(rows),
        "pagination_flag_present": True,
        "rolling_24h_alignment": "not_exact; full UTC hours vs rolling 24h",
    }


def summarize_public_ticker(payload: Mapping[str, Any]) -> dict[str, object]:
    if not isinstance(payload.get("tickers"), list):
        raise ValueError("tickers response is not a list")
    rows = [r for r in payload["tickers"]
            if isinstance(r, dict) and r.get("symbol") == SYMBOL]
    if len(rows) != 1 or rows[0].get("tag") != "perpetual":
        raise ValueError("no unique perpetual BTC ticker")
    ticker = rows[0]
    volume_base_24h = _safe_positive_decimal(ticker.get("vol24h"))
    volume_quote_24h = _safe_positive_decimal(ticker.get("volumeQuote"))
    if volume_base_24h is None or volume_quote_24h is None:
        raise ValueError("ticker missing positive volume fields")
    return {
        "ticker_symbol": SYMBOL,
        "ticker_tag": "perpetual",
        "ticker_vol24h_as_reported": volume_base_24h,
        "ticker_volumeQuote_as_reported": volume_quote_24h,
        "ticker_volume_unit_validation": "not_established",
    }


def make_report(
    *, opener: Callable[..., Any] | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> dict[str, object]:
    """At most two fixed public GETs, with normalized non-sensitive summary."""
    call = opener or _default_open
    now = clock_ms or (lambda: int(time() * 1000))
    observed_at_ms = now()
    if type(observed_at_ms) is not int or observed_at_ms <= 0:
        raise ValueError("invalid runner clock for public diagnostic")
    report: dict[str, object] = {
        "source": "kraken_futures_public", "symbol": SYMBOL,
        "observed_at_utc": datetime.fromtimestamp(
            observed_at_ms / 1000, tz=timezone.utc
        ).isoformat(timespec="seconds"),
        "clock_source": "runner_local_utc_not_exchange_verified",
        "auth_used": False, "orders_enabled": False,
        "raw_response_persisted": False, "max_requests": 2,
        "unit_proof": False,
    }
    first, chart = _get_json(route="trade_hourly_chart", url=CANDLES_URL, opener=call)
    routes = [first]
    if chart is None:
        return {**report, "status": "blocked", "routes": routes, "requests_attempted": 1}
    try:
        chart_summary = summarize_closed_chart(chart, observed_at_ms=observed_at_ms)
    except (ValueError, TypeError) as error:
        # Static parser error labels only; do not log provider payloads.
        return {**report, "status": "invalid_chart_or_insufficient_data",
                "chart_rejection_reason": str(error),
                "chart_structure": describe_chart_structure(
                    chart, observed_at_ms=observed_at_ms,
                ),
                "routes": routes, "requests_attempted": 1}
    second, ticker = _get_json(route="public_tickers", url=TICKERS_URL, opener=call)
    routes.append(second)
    if ticker is None:
        return {**report, "status": "partial", "routes": routes,
                "chart": chart_summary, "requests_attempted": 2}
    try:
        ticker_summary = summarize_public_ticker(ticker)
    except (ValueError, TypeError):
        return {**report, "status": "invalid_ticker", "routes": routes,
                "chart": chart_summary, "requests_attempted": 2}
    return {
        **report, "status": "observed_aggregates_not_unit_proof",
        "routes": routes, "chart": chart_summary, "ticker": ticker_summary,
        "requests_attempted": 2,
        "warning": (
            "Rolling ticker 24h does NOT align to complete UTC hours. "
            "Numerical similarity cannot establish contract units or exact "
            "candle quote/base volumes. No canonical ClosedCandle conversion."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Two public Kraken GETs for opaque volume diagnostics only."
    )
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-volume-diagnostic", action="store_true")
    args = parser.parse_args(argv)
    if not (args.allow_public_network and args.allow_volume_diagnostic):
        parser.error("both explicit public-network and volume-diagnostic permissions are required")
    report = make_report()
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "observed_aggregates_not_unit_proof" else 2


if __name__ == "__main__":
    raise SystemExit(main())
