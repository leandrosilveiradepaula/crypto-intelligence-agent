"""One public Bybit REST ticker snapshot for the J5 read-only market panel.

Reuses J1's fixed-origin, bounded GET transport. Unlike an intrahour
WebSocket, this is ONE observation, never a live price source for a
position, stop, signal, fill, leverage or exchange order.
"""
from __future__ import annotations

import time
from typing import Callable

from .bybit_linear_candle_research import _strict_decimal
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, _SYMBOL, tickers_url,
)
from .market_data import DataGapError, DataValidationError

MAX_SYMBOLS = 50
MAX_ROWS = 3000
MIN_UTC_MS = 1_600_000_000_000
MAX_UTC_MS = 4_102_444_800_000
MAX_SERVER_AGE_MS = 45_000
MAX_FUTURE_SKEW_MS = 5_000

_FIELDS = ("lastPrice", "markPrice", "bid1Price", "ask1Price",
           "bid1Size", "ask1Size", "turnover24h")


def capture_public_rest_price_pulse(
    *, symbols: tuple[str, ...],
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> dict:
    """Get exactly one all-linear REST snapshot, keep only admitted symbols.

    Membership is supplied by a separate owner scope; not derived from a
    USDT suffix or re-ranked here. No persistence or account operations.
    """
    if (type(symbols) is not tuple or not 1 <= len(symbols) <= MAX_SYMBOLS
            or any(type(x) is not str or _SYMBOL.fullmatch(x) is None
                   for x in symbols)
            or len(set(symbols)) != len(symbols)
            or (client is not None and type(client) is not BoundedBybitPublicClient)
            or not callable(clock_ms)):
        raise DataValidationError("D403 reviewed USDT membership required")
    before = clock_ms()
    if type(before) is not int or not MIN_UTC_MS <= before < MAX_UTC_MS:
        raise DataValidationError("D403 clock invalid")
    source = client if client is not None else BoundedBybitPublicClient()
    _raw, payload = source.get(tickers_url())  # one fixed-origin public GET
    after = clock_ms()
    if (type(after) is not int or after < before
            or after - before > MAX_SERVER_AGE_MS
            or after >= MAX_UTC_MS):
        raise DataGapError("D403 network observation time invalid")
    server_at_ms = payload.get("time")
    if (type(server_at_ms) is not int
            or not MIN_UTC_MS <= server_at_ms < MAX_UTC_MS
            or server_at_ms > after + MAX_FUTURE_SKEW_MS
            or after - server_at_ms > MAX_SERVER_AGE_MS):
        raise DataGapError("D403 REST server time stale or future")
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("category") != "linear":
        raise DataValidationError("D403 Bybit linear category mismatch")
    rows = result.get("list")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise DataValidationError("D403 ticker response rows invalid")

    wanted = set(symbols)
    selected = {}
    for row in rows:
        if type(row) is not dict:
            raise DataValidationError("D403 nonobject ticker response")
        name = row.get("symbol")
        if name not in wanted:
            continue
        if name in selected:
            raise DataValidationError("D403 duplicate public ticker")
        selected[name] = row
    if set(selected) != wanted:
        raise DataGapError("D403 requested public ticker missing")

    quotes = []
    for symbol in sorted(wanted):
        row = selected[symbol]
        if any(type(row.get(k)) is not str for k in _FIELDS):
            raise DataValidationError("D403 required quote field missing")
        p = {
            k: _strict_decimal(row[k], label="D403_" + k,
                               may_be_zero=k == "turnover24h")
            for k in _FIELDS
        }
        if (p["bid1Price"] > p["ask1Price"]
                or p["bid1Size"] <= 0 or p["ask1Size"] <= 0):
            raise DataGapError("D403 public bid ask depth invalid")
        quotes.append({
            "symbol": symbol,
            "last_price": str(p["lastPrice"]),
            "mark_price": str(p["markPrice"]),
            "bid_price": str(p["bid1Price"]),
            "ask_price": str(p["ask1Price"]),
            "bid_size": str(p["bid1Size"]),
            "ask_size": str(p["ask1Size"]),
            "turnover_24h": str(p["turnover24h"]),
        })
    return {
        "schema_version": "bybit-public-rest-price-pulse-d403-v1",
        "status": "rest_snapshot_display_only",
        "source": "bybit_v5_public_linear_tickers",
        "server_at_ms": server_at_ms,
        "captured_at_ms": after,
        "observed_symbol_count": len(quotes),
        "quotes": quotes,
        "network_gets_in_this_capture": 1,
        "crypto_only_membership_verified": False,
        "continuous_websocket_verified": False,
        "imported_report_authenticated_by_browser": False,
        "paper_positions_linked": False,
        "orders_sent": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
    }
