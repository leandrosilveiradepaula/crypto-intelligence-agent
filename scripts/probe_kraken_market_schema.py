"""Bounded no-auth conformance probe of an independent public Futures venue.

Only fixed Kraken Futures GET endpoints, at most three requests, no redirects,
no retries, no keys, no raw payload persistence, no trade functions.
Nothing accesses the network without TWO explicit CLI flags.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from time import monotonic
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request

from scripts.probe_public_kraken import (
    MAX_RESPONSE_BYTES, MAX_TIMEOUT_SECONDS, _default_open,
)

ROOT = "https://futures.kraken.com"
PATHS = {
    "instruments": "/derivatives/api/v3/instruments",
    "tickers": "/derivatives/api/v3/tickers",
    "candles": "/api/charts/v1/trade/PF_XBTUSD/1h?count=3",
}
MAX_CALLS = 3

SAFE_INSTRUMENT_FIELDS = (
    "symbol", "type", "contractType", "tradeable", "underlying",
    "underlyingSymbol", "pair", "contractSize", "tickSize",
    "marginCurrency", "currency", "lotSize", "contractValueTradePrecision",
)
SAFE_TICKER_FIELDS = ("symbol", "tag", "suspended", "postOnly", "volumeQuote", "vol24h")


def _scalar_safe(value: Any) -> bool:
    return (value is None or isinstance(value, (str, bool, int))
            or (isinstance(value, float) and math.isfinite(value)))


def _selected_fields(row: dict[str, Any], names: tuple[str, ...]) -> dict[str, object]:
    """Explicit allowlist of short public fields (no full payload printing)."""
    return {
        name: value
        for name in names
        if (name in row and _scalar_safe(value := row[name])
            and not (isinstance(value, str) and len(value) > 80))
    }


def _fetch(
    name: str, open_fn: Callable[..., Any],
) -> tuple[dict[str, object], dict[str, Any] | None]:
    url = ROOT + PATHS[name]
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    began = monotonic()
    try:
        with open_fn(request, timeout=MAX_TIMEOUT_SECONDS) as response:
            status = response.getcode()
            if status != 200:
                return ({"route": name, "http_status": status, "status": "http_error"}, None)
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                return ({"route": name, "http_status": 200, "status": "response_too_large"}, None)
            try:
                payload = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                return ({"route": name, "http_status": 200, "status": "invalid_json"}, None)
            if not isinstance(payload, dict):
                return ({"route": name, "http_status": 200, "status": "invalid_schema"}, None)
            return ({
                "route": name, "http_status": 200, "status": "ok",
                "elapsed_ms": int((monotonic() - began) * 1000),
            }, payload)
    except HTTPError as exc:
        return ({
            "route": name, "http_status": exc.code,
            "status": "policy_or_access_restriction"
            if exc.code in (403, 418, 451) else "http_error",
        }, None)
    except (URLError, TimeoutError, OSError):
        return ({"route": name, "status": "network_or_dns_failure"}, None)


def make_report(*, opener: Callable[..., Any] | None = None) -> dict[str, object]:
    """Perform at most 3 independent public GET calls, with bounded summaries."""
    call = opener or _default_open
    summary: dict[str, object] = {
        "provider": "kraken_futures",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "auth_used": False, "orders_enabled": False,
        "raw_response_persisted": False,
        "instrument_eligibility_validated": False,
        "request_limit": MAX_CALLS,
    }
    outcomes: list[dict[str, object]] = []
    instruments_result, instruments = _fetch("instruments", call)
    outcomes.append(instruments_result)
    if instruments is None:
        return {**summary, "status": "blocked", "routes": outcomes, "requests_attempted": len(outcomes)}
    rows = instruments.get("instruments")
    if instruments.get("result") != "success" or not isinstance(rows, list) or not rows:
        return {**summary, "status": "invalid_instruments", "routes": outcomes, "requests_attempted": len(outcomes)}
    by_symbol = {
        row["symbol"].upper(): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("symbol"), str)
    }
    summary["instrument_count"] = len(rows)
    btc = by_symbol.get("PF_XBTUSD")
    tokenized = by_symbol.get("PF_AAPLXUSD")
    summary["btc_metadata"] = {
        "found": btc is not None,
        "field_names": sorted(btc)[:50] if btc else [],
        "selected": _selected_fields(btc, SAFE_INSTRUMENT_FIELDS) if btc else {},
    }
    summary["tokenized_asset_metadata"] = {
        "found": tokenized is not None,
        "field_names": sorted(tokenized)[:50] if tokenized else [],
        "selected": _selected_fields(tokenized, SAFE_INSTRUMENT_FIELDS) if tokenized else {},
    }

    ticker_result, tickers = _fetch("tickers", call)
    outcomes.append(ticker_result)
    if tickers is None:
        return {**summary, "status": "partial", "routes": outcomes, "requests_attempted": len(outcomes)}
    ticker_rows = tickers.get("tickers")
    if not isinstance(ticker_rows, list):
        return {**summary, "status": "invalid_tickers", "routes": outcomes, "requests_attempted": len(outcomes)}
    match = next(
        (row for row in ticker_rows
         if isinstance(row, dict)
         and isinstance(row.get("symbol"), str)
         and row["symbol"].upper() == "PF_XBTUSD"), None,
    )
    summary["tickers_count"] = len(ticker_rows)
    summary["btc_ticker"] = {
        "found": match is not None,
        "field_names": sorted(match)[:50] if match else [],
        "selected": _selected_fields(match, SAFE_TICKER_FIELDS) if match else {},
    }

    if btc is None:
        return {**summary, "status": "missing_btc_instrument", "routes": outcomes,
                "requests_attempted": len(outcomes)}
    candles_result, candles_payload = _fetch("candles", call)
    outcomes.append(candles_result)
    if candles_payload is None:
        return {**summary, "status": "partial", "routes": outcomes, "requests_attempted": len(outcomes)}
    candles = candles_payload.get("candles")
    if not isinstance(candles, list):
        return {**summary, "status": "invalid_candles", "routes": outcomes, "requests_attempted": len(outcomes)}
    summary["candles"] = {
        "count": len(candles),
        "field_names": sorted(candles[0])[:30] if candles and isinstance(candles[0], dict) else [],
        "more_candles_flag_present": isinstance(candles_payload.get("more_candles"), bool),
        "first_time_ms": candles[0].get("time") if candles and isinstance(candles[0], dict)
        and isinstance(candles[0].get("time"), int) else None,
        "last_time_ms": candles[-1].get("time") if candles and isinstance(candles[-1], dict)
        and isinstance(candles[-1].get("time"), int) else None,
    }
    summary["status"] = "ok" if len(candles) > 0 else "empty_candles"
    summary["routes"] = outcomes
    summary["requests_attempted"] = len(outcomes)
    summary["conformance_note"] = (
        "Schema and one sample do not prove crypto-only classification, volume "
        "comparability, contract multipliers, true candle closure or historical coverage"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Three bounded public GETs, no credentials.")
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-kraken-schema-probe", action="store_true")
    args = parser.parse_args(argv)
    if not (args.allow_public_network and args.allow_kraken_schema_probe):
        parser.error("both explicit public-network and Kraken-schema-probe permissions required")
    report = make_report()
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
