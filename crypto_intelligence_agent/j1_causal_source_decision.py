"""OPS32: offline, fail-closed source decision for one *completed* UTC candle.

This module NEVER makes network calls, opens storage or authorizes ingestion.
It compares venue-specific temporal semantics without changing any provider
trade timestamp.  All payloads are caller-provided research fixtures and do
not attest transport provenance; a claim that a WS ACK was observed is not
itself proof of a real subscription.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any

HOUR_MS = 3_600_000
MAX_UTC_MS = 4_102_444_800_000  # 2100-01-01 UTC, finite time boundary
WS_LAG_MS = 30_000
REST_SETTLE_MS = 60_000  # REST has no explicit finality flag
MAX_RECEIPT_AFTER_CLOSE_MS = 600_000
_SYMBOL = re.compile(r"[A-Z0-9]{2,30}USDT\Z")
_VENUES = ("bybit_v5_linear", "binance_usdm")
_WS_FIELDS = frozenset((
    "start", "end", "interval", "open", "high", "low", "close",
    "volume", "turnover", "confirm", "timestamp",
))
_BINANCE_FIELDS = frozenset((
    "t", "T", "s", "i", "f", "L", "o", "c", "h", "l", "v",
    "n", "x", "q", "V", "Q", "B",
))


@dataclass(frozen=True)
class SourceEvidence:
    """One caller-supplied envelope; transport metadata is NOT authentication."""

    venue: str
    transport: str  # ws or rest
    symbol: str
    interval: str
    payload: Any
    received_at_ms: int
    requested_at_ms: int | None = None
    ack_verified: bool = False


@dataclass(frozen=True)
class CausalSourceDecision:
    status: str
    selected_transport: str | None = None
    sources_checked: int = 0
    values_corrob_same_venue: bool = False

    def sanitized_report(self) -> dict:
        """Do not export symbol, timestamps, OHLCV, provider payloads or paths."""
        return {
            "status": self.status,
            "selected_transport": self.selected_transport,
            "sources_checked": self.sources_checked,
            "values_corrob_same_venue": self.values_corrob_same_venue,
            "network_requests": 0,
            "storage_writes": 0,
            "ws_candle_approved": False,
            "canonical_ohlcv_approved": False,
            "source_authenticated": False,
            "marketwide_top50_verified": False,
            "continuous_collector_authorized": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }


class _Veto(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _veto(reason: str) -> None:
    raise _Veto(reason)


def _integer(value: Any) -> int:
    if type(value) is not int or not 0 < value < MAX_UTC_MS:
        _veto("source_clock_abstain")
    return value


def _decimal(value: Any, *, positive: bool) -> Decimal:
    if type(value) is not str or len(value) > 80 or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value
    ):
        _veto("source_value_abstain")
    try:
        n = Decimal(value)
    except InvalidOperation:
        _veto("source_value_abstain")
    if not n.is_finite() or (n <= 0 if positive else n < 0):
        _veto("source_value_abstain")
    return n


def _ohlcv(values: tuple[Any, ...]) -> tuple[Decimal, ...]:
    if len(values) != 6:
        _veto("source_schema_abstain")
    o, h, l, c = (_decimal(v, positive=True) for v in values[:4])
    volume, turnover = (_decimal(v, positive=False) for v in values[4:])
    if not l <= min(o, c) <= max(o, c) <= h or l > h:
        _veto("source_value_abstain")
    # Turnover and base volume are different dimensions, never convert units.
    if (volume == 0) != (turnover == 0):
        _veto("source_value_abstain")
    return o, h, l, c, volume, turnover


def _one_closed_utc_hour(start: Any, end: Any, receipt: int) -> int:
    start, end = _integer(start), _integer(end)
    if (start % HOUR_MS or end != start + HOUR_MS - 1
            or not end < receipt <= end + MAX_RECEIPT_AFTER_CLOSE_MS):
        _veto("source_window_abstain")
    # Only the most recently completed hour at receipt: no stale replay.
    if start != (receipt // HOUR_MS - 1) * HOUR_MS:
        _veto("source_window_abstain")
    return end


def _ws_clock(server: Any, receipt: int, end: int) -> None:
    ts = _integer(server)
    if not end < ts <= receipt or receipt - ts > WS_LAG_MS:
        _veto("source_clock_abstain")


def _rest_clock(e: SourceEvidence, end: int) -> None:
    requested = _integer(e.requested_at_ms)
    if (e.ack_verified is not False or requested < end + 1 + REST_SETTLE_MS
            or requested > e.received_at_ms
            or e.received_at_ms - requested > WS_LAG_MS):
        _veto("source_window_abstain")


def _bybit_ws(e: SourceEvidence) -> tuple[int, tuple[Decimal, ...]]:
    p = e.payload
    if e.ack_verified is not True or e.requested_at_ms is not None:
        _veto("source_ack_abstain")
    if (type(p) is not dict or set(p) != {"topic", "type", "ts", "data"}
            or p["topic"] != "kline.60." + e.symbol
            or p["type"] != "snapshot" or type(p["data"]) is not list
            or len(p["data"]) != 1 or type(p["data"][0]) is not dict):
        _veto("source_schema_abstain")
    row = p["data"][0]
    if set(row) != _WS_FIELDS or row["interval"] != "60":
        _veto("source_schema_abstain")
    end = _one_closed_utc_hour(row["start"], row["end"], e.received_at_ms)
    _ws_clock(p["ts"], e.received_at_ms, end)
    if row["confirm"] is not True:
        _veto("source_open_candle_abstain")
    stamp = _integer(row["timestamp"])
    if stamp < row["start"] or stamp > p["ts"]:
        _veto("source_clock_abstain")
    values = _ohlcv(tuple(row[k] for k in (
        "open", "high", "low", "close", "volume", "turnover"
    )))
    if stamp > end:
        # This is exactly the OPS31 observed condition. No correction or REST
        # fallback is permitted to conceal a contradictory WS observation.
        _veto("bybit_ws_stamp_overrun_quarantine")
    return row["start"], values


def _bybit_rest(e: SourceEvidence) -> tuple[int, tuple[Decimal, ...]]:
    p = e.payload
    if (type(p) is not dict or type(p.get("retCode")) is not int or p["retCode"] != 0
            or type(p.get("result")) is not dict):
        _veto("source_schema_abstain")
    result = p["result"]
    if (result.get("category") != "linear" or result.get("symbol") != e.symbol
            or type(result.get("list")) is not list
            or len(result["list"]) != 1):
        _veto("source_schema_abstain")
    row = result["list"][0]
    if type(row) is not list or len(row) != 7:
        _veto("source_schema_abstain")
    if type(row[0]) is not str or not re.fullmatch(r"[0-9]{13}", row[0]):
        _veto("source_schema_abstain")
    start = int(row[0])
    end = _one_closed_utc_hour(start, start + HOUR_MS - 1, e.received_at_ms)
    _rest_clock(e, end)
    return start, _ohlcv(tuple(row[1:]))


def _binance_ws(e: SourceEvidence) -> tuple[int, tuple[Decimal, ...]]:
    p = e.payload
    if e.ack_verified is not True or e.requested_at_ms is not None:
        _veto("source_ack_abstain")
    if (type(p) is not dict or set(p) != {"e", "E", "s", "k"}
            or p["e"] != "kline" or p["s"] != e.symbol
            or type(p["k"]) is not dict or set(p["k"]) != _BINANCE_FIELDS):
        _veto("source_schema_abstain")
    k = p["k"]
    if k["s"] != e.symbol or k["i"] != "1h" or k["x"] is not True:
        _veto("source_open_candle_abstain")
    end = _one_closed_utc_hour(k["t"], k["T"], e.received_at_ms)
    _ws_clock(p["E"], e.received_at_ms, end)
    for key in ("f", "L", "n"):
        if type(k[key]) is not int or k[key] < 0:
            _veto("source_schema_abstain")
    if k["L"] < k["f"] and k["n"] > 0:
        _veto("source_schema_abstain")
    # Auxiliary values validate too; no dropping malformed fields silently.
    _decimal(k["V"], positive=False)
    _decimal(k["Q"], positive=False)
    if type(k["B"]) not in (str, int):
        _veto("source_schema_abstain")
    return k["t"], _ohlcv(tuple(k[x] for x in ("o", "h", "l", "c", "v", "q")))


def _binance_rest(e: SourceEvidence) -> tuple[int, tuple[Decimal, ...]]:
    rows = e.payload
    if type(rows) is not list or len(rows) != 1:
        _veto("source_schema_abstain")
    row = rows[0]
    if type(row) is not list or len(row) != 12:
        _veto("source_schema_abstain")
    end = _one_closed_utc_hour(row[0], row[6], e.received_at_ms)
    _rest_clock(e, end)
    for key in (8,):
        if type(row[key]) is not int or row[key] < 0:
            _veto("source_schema_abstain")
    for key in (9, 10):
        _decimal(row[key], positive=False)
    # Raw Binance REST has no symbol/interval: caller's request metadata is
    # asserted and remains unverified; never treat a row as authenticated.
    return row[0], _ohlcv((row[1], row[2], row[3], row[4], row[5], row[7]))


def decide_causal_source(
    *, expected_venue: str, expected_symbol: str,
    evidence: tuple[SourceEvidence, ...],
) -> CausalSourceDecision:
    """Select a research-only closed candidate; fail closed on any mismatch.

    An anomalous WS observation is a veto even if same-venue REST agrees. All
    provided source observations must agree on exact 6 Decimal fields; neither
    same-venue concordance nor a caller assertion authenticates a source.
    """
    if (type(expected_venue) is not str or expected_venue not in _VENUES
            or type(expected_symbol) is not str
            or _SYMBOL.fullmatch(expected_symbol) is None
            or type(evidence) is not tuple or not 1 <= len(evidence) <= 2
            or any(type(e) is not SourceEvidence for e in evidence)):
        return CausalSourceDecision("source_config_abstain")
    if (any(e.venue != expected_venue or e.symbol != expected_symbol
            or e.interval != "1h" for e in evidence)):
        return CausalSourceDecision("source_venue_or_scope_abstain")
    transports = tuple(e.transport for e in evidence)
    if (any(t not in ("ws", "rest") for t in transports)
            or len(transports) != len(set(transports))):
        return CausalSourceDecision("source_duplicate_or_transport_abstain")
    parsed: list[tuple[str, tuple[int, tuple[Decimal, ...]]]] = []
    try:
        for e in evidence:
            _integer(e.received_at_ms)
            parser = {
                ("bybit_v5_linear", "ws"): _bybit_ws,
                ("bybit_v5_linear", "rest"): _bybit_rest,
                ("binance_usdm", "ws"): _binance_ws,
                ("binance_usdm", "rest"): _binance_rest,
            }[(e.venue, e.transport)]
            parsed.append((e.transport, parser(e)))
    except _Veto as exc:
        return CausalSourceDecision(exc.reason, sources_checked=len(parsed) + 1)
    except (TypeError, ValueError, KeyError, OverflowError, InvalidOperation):
        return CausalSourceDecision("source_schema_abstain", sources_checked=len(parsed) + 1)
    if len(parsed) == 2 and parsed[0][1][0] != parsed[1][1][0]:
        return CausalSourceDecision("source_hours_diverge_abstain", sources_checked=2)
    if len(parsed) == 2 and parsed[0][1][1] != parsed[1][1][1]:
        return CausalSourceDecision("source_values_diverge_abstain", sources_checked=2)
    selected = "ws" if "ws" in transports else "rest"
    return CausalSourceDecision(
        "source_closed_research_unverified", selected,
        len(parsed), len(parsed) == 2,
    )
