"""J1/OPS21: offline-only comparison; a match NEVER approves WS ingestion.

Caller supplies one untrusted WS snapshot and one previously schema-validated
REST research page. Neither side is authenticated by this comparison.
No sockets, HTTP, disk writes, orders, or secret/raw-value reports.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from .bybit_linear_candle_research import (
    BybitLinearCandlePageResearch, BybitLinearCandleResearch,
    SOURCE, UNIT_BASIS, _strict_decimal,
)
from .bybit_public_ws_once import _validate_one_kline_row
from .market_data import DataValidationError

HOUR_MS = 3_600_000
MAX_UTC_MS = 4_102_444_800_000
MAX_REST_DELAY_MS = 86_400_000
_SYMBOL = re.compile(r"[A-Z0-9]{2,30}USDT\Z")
_FIELDS = ("open", "high", "low", "close", "volume", "turnover")


@dataclass(frozen=True)
class OfflineCloseCorroboration:
    """Diagnostic only. No candle, symbol, price or raw timestamp is exposed."""

    status: str
    fields_compared: int
    fields_equal: int

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "fields_compared": self.fields_compared,
            "fields_equal": self.fields_equal,
            "ws_candle_approved": False,
            "historical_reference_authenticated": False,
            "canonical_ohlcv_approved": False,
            "marketwide_top50_verified": False,
            "storage_writes": 0,
            "network_requests": 0,
            "orders_sent": False,
            "live_trading_authorized": False,
        }


def corroborate_anomalous_close_offline(
    *, frame: dict, received_at_ms: int,
    reference: BybitLinearCandlePageResearch,
) -> OfflineCloseCorroboration:
    """Compare six exact decimal fields without normalizing a post-end stamp.

    Raises DataValidationError for malformed or temporally incompatible inputs.
    For a structurally valid anomalous frame, reports equality *only*:
    equality does not prove provenance, correct hour assignment, or permission
    to accept a candle. This function never returns data usable by the journal.
    """
    if (type(frame) is not dict
            or set(frame) != {"topic", "type", "ts", "data"}
            or frame.get("type") != "snapshot"
            or type(frame.get("topic")) is not str
            or not frame["topic"].startswith("kline.60.")
            or type(frame.get("data")) is not list
            or len(frame["data"]) != 1
            or type(frame.get("ts")) is not int
            or type(received_at_ms) is not int
            or not 0 < received_at_ms < MAX_UTC_MS):
        raise DataValidationError("offline corroboration WS envelope invalid")
    symbol = frame["topic"][len("kline.60."):]
    if _SYMBOL.fullmatch(symbol) is None:
        raise DataValidationError("offline corroboration WS topic invalid")
    row = frame["data"][0]
    if type(row) is not dict:
        raise DataValidationError("offline corroboration WS row invalid")
    start, end, stamp = row.get("start"), row.get("end"), row.get("timestamp")
    server = frame["ts"]
    if (any(type(x) is not int for x in (start, end, stamp))
            or not 0 < start < end < MAX_UTC_MS
            or end != start + HOUR_MS - 1 or start % HOUR_MS
            or stamp <= end or stamp > server
            or not end + 1 <= server <= received_at_ms
            or received_at_ms - server > 30_000
            or not 1000 <= received_at_ms - (end + 1) <= 120_000
            or row.get("confirm") is not True):
        raise DataValidationError("offline corroboration WS close chronology invalid")
    # All other WS validation still runs, with only the already-known invalid
    # trade-stamp predicate bypassed for isolated diagnostic inspection.
    if not _validate_one_kline_row(
        row, server, received_at_ms, diagnostic_ignore_trade_stamp=True
    ):
        raise DataValidationError("offline corroboration unconfirmed WS candle")
    if (type(reference) is not BybitLinearCandlePageResearch
            or reference.source != SOURCE
            or reference.symbol != symbol or reference.quote_currency != "USDT"
            or reference.interval != "1h"
            or reference.start_open_ms != start
            or reference.end_open_ms != start + HOUR_MS
            or type(reference.observed_at_ms) is not int
            or not received_at_ms <= reference.observed_at_ms
            or reference.observed_at_ms - received_at_ms > MAX_REST_DELAY_MS
            or len(reference.candles) != 1):
        raise DataValidationError("offline corroboration REST page identity or chronology invalid")
    candle = reference.candles[0]
    if (type(candle) is not BybitLinearCandleResearch
            or candle.source != SOURCE or candle.unit_basis != UNIT_BASIS
            or candle.symbol != symbol or candle.quote_currency != "USDT"
            or candle.interval != "1h"
            or candle.open_time_ms != start or candle.close_time_ms != end):
        raise DataValidationError("offline corroboration REST candle mismatch")
    reference_values = (
        candle.open, candle.high, candle.low, candle.close,
        candle.documented_base_volume, candle.documented_quote_turnover,
    )
    if (any(type(v) is not Decimal or not v.is_finite() or v < 0
            for v in reference_values)
            or any(v == 0 for v in reference_values[:4])
            or reference_values[1] < max(reference_values[:4])
            or reference_values[2] > min(reference_values[:4])):
        raise DataValidationError("offline corroboration REST financial values invalid")
    ws_values = tuple(
        _strict_decimal(row[k], label=k, may_be_zero=k in ("volume", "turnover"))
        for k in _FIELDS
    )
    equal = sum(a == b for a, b in zip(ws_values, reference_values))
    return OfflineCloseCorroboration(
        "offline_values_match_unverified" if equal == 6
        else "offline_values_diverge_abstain",
        6, equal,
    )
