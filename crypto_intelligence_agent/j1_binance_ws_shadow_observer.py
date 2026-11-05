"""OPS33: finite Binance USD-M public WS kline observer; strictly in-memory.

Combined /market/stream frames only. No REST, journal, timers or orders.
A successful observation is NOT approval of a source, contract or candle.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import math
import time
from typing import Callable

from .bybit_public_ws_once import StreamSession, _bounded_json
from .j1_causal_source_decision import (
    HOUR_MS, _BINANCE_FIELDS, _decimal, _ohlcv,
    SourceEvidence, decide_causal_source,
)

STREAMS = ("btcusdt@kline_1h", "ethusdt@kline_1h")
SYMBOLS = ("BTCUSDT", "ETHUSDT")
URL = "wss://fstream.binance.com/market/stream"
SUBSCRIPTION_ID = 33
MAX_FRAMES = 1024
MAX_SECONDS = 180
MAX_PREACK = 128
MAX_EVENT_AGE_MS = 30_000
MAX_OPEN_POST_END_MS = 5_000


@dataclass(frozen=True)
class BinanceShadowReport:
    status: str
    frames_seen: int = 0
    subscription_acknowledged: bool = False
    preack_discarded: int = 0
    postack_market_frames: int = 0
    topics_observed: int = 0
    open_updates: int = 0
    unique_closed: int = 0
    duplicate_closes: int = 0
    closed_event_delay_over_1000ms: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "frames_seen": self.frames_seen,
            "subscription_acknowledged": self.subscription_acknowledged,
            "preack_discarded": self.preack_discarded,
            "postack_market_frames": self.postack_market_frames,
            "topics_observed": self.topics_observed,
            "open_updates": self.open_updates,
            "unique_closed": self.unique_closed,
            "duplicate_closes": self.duplicate_closes,
            "closed_event_delay_over_1000ms": self.closed_event_delay_over_1000ms,
            "rest_gets": 0,
            "storage_writes": 0,
            "orders_sent": False,
            "source_authenticated": False,
            "usdm_contract_verified": False,
            "canonical_ohlcv_approved": False,
            "marketwide_top50_verified": False,
            "continuous_collector_authorized": False,
            "live_trading_authorized": False,
        }


def _validate_open_event(event: dict, received_ms: int) -> None:
    """No open candle is silently exempted from schema/price/clock checks."""
    k = event["k"]
    start, end, server = k["t"], k["T"], event["E"]
    if (type(start) is not int or start <= 0 or start % HOUR_MS
            or type(end) is not int or end != start + HOUR_MS - 1
            or type(server) is not int or server < start
            or server > end or received_ms < server
            or received_ms - server > MAX_EVENT_AGE_MS):
        raise ValueError("open clock")
    current = (received_ms // HOUR_MS) * HOUR_MS
    # A final nonfinal update can arrive just after a boundary; it stays open.
    if start != current and not (
        start == current - HOUR_MS and received_ms - current <= MAX_OPEN_POST_END_MS
    ):
        raise ValueError("open stale or future")
    _ohlcv(tuple(k[x] for x in ("o", "h", "l", "c", "v", "q")))
    _decimal(k["V"], positive=False)
    _decimal(k["Q"], positive=False)


def observe_binance_shadow_once(
    *, session_factory: Callable[[], StreamSession],
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    max_seconds: int = MAX_SECONDS,
    max_frames: int = MAX_FRAMES,
) -> BinanceShadowReport:
    """Observe two post-ACK x=true closes, or abstain with an allowlisted status.

    Everything derived from market content lives only in this stack frame.
    The service and caller receive only counters. No reconnection or retry.
    """
    if (not callable(session_factory) or not callable(clock) or not callable(wall_ms)
            or type(max_seconds) is not int or not 1 <= max_seconds <= MAX_SECONDS
            or type(max_frames) is not int or not 2 <= max_frames <= MAX_FRAMES):
        return BinanceShadowReport("binance_configuration_abstain")

    try:
        started = clock()
    except (OSError, TypeError, ValueError, RuntimeError):
        return BinanceShadowReport("binance_clock_abstain")
    if type(started) not in (int, float) or not math.isfinite(started):
        return BinanceShadowReport("binance_clock_abstain")

    frames = preack = market = opened = duplicate = late = receives = 0
    acknowledged = False
    observed: set[str] = set()
    closes: dict[str, tuple] = {}
    status = "binance_no_ack_abstain"

    def report(result: str) -> BinanceShadowReport:
        return BinanceShadowReport(result, frames, acknowledged, preack,
                                   market, len(observed), opened,
                                   len(closes), duplicate, late)

    try:
        with closing(session_factory()) as session:
            session.send(json.dumps({
                "method": "SUBSCRIBE", "params": list(STREAMS),
                "id": SUBSCRIPTION_ID,
            }, separators=(",", ":")))
            while frames < max_frames:
                elapsed = clock() - started
                if (type(elapsed) not in (int, float) or not math.isfinite(elapsed)
                        or elapsed < 0):
                    return report("binance_clock_abstain")
                remaining = max_seconds - elapsed
                if remaining <= 0:
                    break
                receives += 1
                # A broken frozen monotonic clock cannot produce an infinite
                # loop of silent recv timeouts on the owner VPS.
                if receives > max_frames * 4 + max_seconds:
                    return report("binance_receive_budget_abstain")
                try:
                    raw = session.recv(min(remaining, 5.0))
                except TimeoutError:
                    continue
                frames += 1
                payload = _bounded_json(raw)
                if type(payload) is not dict:
                    return report("binance_envelope_abstain")
                if set(payload) == {"id", "result"}:
                    if (acknowledged or type(payload["id"]) is not int
                            or payload["id"] != SUBSCRIPTION_ID
                            or payload["result"] is not None):
                        return report("binance_ack_invalid_abstain")
                    acknowledged = True
                    status = "binance_no_close_abstain"
                    continue
                if set(payload) != {"stream", "data"}:
                    return report("binance_control_abstain")
                if (type(payload["stream"]) is not str
                        or payload["stream"] not in STREAMS
                        or type(payload["data"]) is not dict):
                    return report("binance_envelope_abstain")
                if not acknowledged:
                    preack += 1
                    if preack > MAX_PREACK:
                        return report("binance_preack_budget_abstain")
                    # Never inspect or retro-promote pre-ACK market data.
                    continue

                event = payload["data"]
                if (set(event) != {"e", "E", "s", "k"}
                        or event["e"] != "kline"
                        or type(event["s"]) is not str
                        or event["s"] not in SYMBOLS
                        or payload["stream"] != event["s"].lower() + "@kline_1h"
                        or type(event["k"]) is not dict
                        or set(event["k"]) != _BINANCE_FIELDS):
                    return report("binance_envelope_abstain")
                k = event["k"]
                if (k["s"] != event["s"] or k["i"] != "1h"
                        or type(k["x"]) is not bool
                        or any(type(k[v]) is not int or k[v] < 0 for v in ("f", "L", "n"))
                        or (k["n"] > 0 and k["L"] < k["f"])
                        or type(k["B"]) not in (str, int)):
                    return report("binance_row_abstain")
                received = wall_ms()
                if type(received) is not int or received <= 0:
                    return report("binance_clock_abstain")
                if (type(event["E"]) is not int or event["E"] <= 0
                        or event["E"] > received
                        or received - event["E"] > MAX_EVENT_AGE_MS):
                    return report("binance_clock_abstain")
                if k["x"] is True:
                    checked = decide_causal_source(
                        expected_venue="binance_usdm", expected_symbol=event["s"],
                        evidence=(SourceEvidence(
                            venue="binance_usdm", transport="ws",
                            symbol=event["s"], interval="1h", payload=event,
                            received_at_ms=received, ack_verified=True,
                        ),),
                    )
                    if checked.status != "source_closed_research_unverified":
                        return report("binance_closed_causal_abstain")
                    try:
                        values = _ohlcv(tuple(k[x] for x in (
                            "o", "h", "l", "c", "v", "q")))
                        _decimal(k["V"], positive=False)
                        _decimal(k["Q"], positive=False)
                    except Exception:
                        return report("binance_row_abstain")
                    if event["s"] in closes:
                        if closes[event["s"]] != values:
                            return report("binance_duplicate_conflict_abstain")
                        duplicate += 1
                    else:
                        closes[event["s"]] = values
                        late += int(event["E"] - (k["T"] + 1) > 1_000)
                else:
                    try:
                        _validate_open_event(event, received)
                    except Exception:
                        return report("binance_open_invalid_abstain")
                    opened += 1
                market += 1
                observed.add(event["s"])
                if len(closes) == len(SYMBOLS):
                    return report("binance_closes_observed_unverified")
            if frames >= max_frames:
                status = "binance_frame_budget_abstain"
            elif acknowledged and len(closes) == 1:
                status = "binance_partial_close_abstain"
    except (OSError, RuntimeError, ValueError, TypeError, ImportError, AttributeError):
        status = "binance_transport_or_validation_abstain"
    except Exception:
        status = "binance_unexpected_abstain"
    return report(status)
