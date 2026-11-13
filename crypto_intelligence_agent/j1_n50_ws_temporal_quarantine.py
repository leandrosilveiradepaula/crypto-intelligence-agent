"""D328: classify non-evidentiary Bybit WS CLOSED snapshots, without IO.

This is a narrowly scoped, pre-parser discard decision. It may NEVER label a
temporal candidate valid. All candle admission still goes through the strict
D313/D326 parse_offline_confirmed_kline and immutable SQLite journal.

Return only a fixed small integer bucket; never expose member names,
timestamps, price fields, raw frames, or free-form exception strings.
"""
from __future__ import annotations

from decimal import Decimal

from .bybit_closed_stream_cache import (
    HOUR_MS, MAX_UTC_MS, MAX_WS_LAG_MS, MAX_SERVER_SKEW_MS,
    MAX_SCOPE_AGE_MS, _ROW_FIELDS, OfflineReviewedStreamScope,
)
from .bybit_linear_candle_research import _strict_decimal
from .market_data import DataGapError, DataValidationError

# Indices are fixed across batch, supervisor, owner, CLI and sanitized logs.
TRADE_OUT_OF_HOUR = 0
PREMATURE_CLOSE = 1
STALE_PREVIOUS_CLOSE = 2


def classify_non_evidence_closed_frame(
    message: object, *, scope: OfflineReviewedStreamScope,
    received_at_ms: int,
) -> int | None:
    """Return a discard bucket only for an otherwise sound CLOSED snapshot.

    We quarantine (discard, do not write) three temporal non-evidence cases:
    prior-hour snapshot already older than the WS 120s replay window;
    premature confirm before the UTC close; last-trade timestamp outside
    its declared hour. All other corruption and stale scope is fatal under
    the original parser. Never interpret a discard as a confirmed bar.
    """
    if (type(message) is not dict or type(scope) is not OfflineReviewedStreamScope
            or type(received_at_ms) is not int
            or not 0 < received_at_ms < MAX_UTC_MS
            or set(message) != {"topic", "type", "ts", "data"}
            or message.get("type") != "snapshot"
            or type(message.get("topic")) is not str
            or not message["topic"].startswith("kline.60.")
            or type(message.get("ts")) is not int
            or type(message.get("data")) is not list
            or len(message["data"]) != 1
            or type(message["data"][0]) is not dict
            or set(message["data"][0]) != _ROW_FIELDS):
        return None
    row = message["data"][0]
    start, end, trade, server = (
        row["start"], row["end"], row["timestamp"], message["ts"],
    )
    if (row["interval"] != "60" or row["confirm"] is not True
            or any(type(v) is not int for v in (start, end, trade))
            or start <= 0 or start % HOUR_MS
            or end != start + HOUR_MS - 1 or end >= MAX_UTC_MS
            or server <= 0 or server > received_at_ms
            or received_at_ms - server > MAX_SERVER_SKEW_MS
            or scope.observed_at_ms > server
            or server - scope.observed_at_ms > MAX_SCOPE_AGE_MS):
        return None
    try:
        member = scope.member(message["topic"].removeprefix("kline.60."))
        if member.launch_time_ms > start:
            return None
        # Do not silently mask malformed numeric fields/structural OHLC.
        if any(type(row[k]) is not str for k in
               ("open", "high", "low", "close", "volume", "turnover")):
            return None
        prices = {
            k: _strict_decimal(row[k], label=k, may_be_zero=False)
            for k in ("open", "high", "low", "close")
        }
        for k in ("volume", "turnover"):
            _strict_decimal(row[k], label=k, may_be_zero=True)
        if (prices["high"] < max(prices.values())
                or prices["low"] > min(prices.values())):
            return None
    except (ValueError, TypeError, OverflowError, DataGapError, DataValidationError):
        return None

    if not start <= trade <= end:
        return TRADE_OUT_OF_HOUR
    if server < end + 1 or received_at_ms < end + 1:
        return PREMATURE_CLOSE
    if received_at_ms - (end + 1) > MAX_WS_LAG_MS:
        return STALE_PREVIOUS_CLOSE
    return None
