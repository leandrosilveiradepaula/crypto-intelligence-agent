"""J1/OPS30: one finite public WS shadow session; zero journal or REST writes.

The network transport is injected. Every reported metric is aggregate and
non-authorizing. A post-end trade timestamp is counted for research only:
the strict persistent kline parser is neither imported nor changed here.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
import json
import math
import re
import time
from typing import Callable

from .bybit_public_ws_once import (
    StreamSession, _bounded_json, _is_public_pong, _subscription_ack,
    _validate_one_kline_row,
)
from .bybit_closed_stream_cache import HOUR_MS
from .j1_ws_close_causal_gate import _band
from .market_data import DataValidationError

_TOPIC = re.compile(r"kline\.60\.[A-Z0-9]{2,30}USDT\Z")
MAX_TOPICS = 52
MAX_SECONDS = 3600
MAX_FRAMES = 200_000
MAX_PREACK = 128
_BANDS = (
    "within_interval", "overrun_1ms", "overrun_2_to_1000ms",
    "overrun_1001_to_5000ms", "overrun_over_5000ms",
)


@dataclass(frozen=True)
class ShadowWSReport:
    status: str
    frames_seen: int = 0
    postack_market_frames: int = 0
    preack_discarded: int = 0
    topics_observed: int = 0
    unique_closed: int = 0
    duplicate_closes: int = 0
    open_rows: int = 0
    closed_bands: tuple[int, ...] = field(default_factory=lambda: (0,) * 5)
    open_bands: tuple[int, ...] = field(default_factory=lambda: (0,) * 5)
    pong_frames: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "frames_seen": self.frames_seen,
            "postack_market_frames": self.postack_market_frames,
            "preack_discarded": self.preack_discarded,
            "topics_observed": self.topics_observed,
            "unique_closed": self.unique_closed,
            "duplicate_closes": self.duplicate_closes,
            "open_rows": self.open_rows,
            "closed_timestamp_bands": dict(zip(_BANDS, self.closed_bands)),
            "open_timestamp_bands": dict(zip(_BANDS, self.open_bands)),
            "pong_frames": self.pong_frames,
            "public_ws_connections": 1 if self.frames_seen else 0,
            "rest_gets": 0, "storage_writes": 0, "orders_sent": False,
            "source_authenticated": False,
            "canonical_ohlcv_approved": False,
            "marketwide_top50_verified": False,
            "continuous_collector_authorized": False,
            "live_trading_authorized": False,
        }


def observe_shadow_once(
    *, session_factory: Callable[[], StreamSession], topics: tuple[str, ...],
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    max_seconds: int = 90, max_frames: int = 256,
) -> ShadowWSReport:
    """Bounded, no reconnect, no retro-preACK data and no persistence.

    For each frame, all rows are validated before any counter is committed.
    An invalid/ambiguous frame ends the observation fail-closed, without
    claiming the successfully observed prefix certifies the full window.
    """
    abstain = ShadowWSReport("shadow_configuration_abstain")
    if (type(topics) is not tuple or not 1 <= len(topics) <= MAX_TOPICS
            or len(topics) != len(set(topics))
            or any(type(t) is not str or _TOPIC.fullmatch(t) is None for t in topics)
            or type(max_seconds) is not int or not 1 <= max_seconds <= MAX_SECONDS
            or type(max_frames) is not int or not 2 <= max_frames <= MAX_FRAMES
            or not callable(session_factory) or not callable(clock) or not callable(wall_ms)):
        return abstain
    if len(json.dumps(topics, separators=(",", ":"))) > 21_000:
        return abstain

    started = clock()
    if type(started) not in (int, float) or not math.isfinite(started):
        return ShadowWSReport("shadow_clock_abstain")
    frames = market = preack = dup = opens = pong = 0
    seen_topics: set[str] = set()
    seen_closed: set[tuple[str, int]] = set()
    closed_bands = [0] * 5
    open_bands = [0] * 5
    ack = False
    last_ping = started
    pending_ping = None
    status = "shadow_no_ack_abstain"
    try:
        with closing(session_factory()) as session:
            session.send(json.dumps({
                "op": "subscribe", "req_id": "cia-ops30-shadow",
                "args": list(topics),
            }, separators=(",", ":")))
            while frames < max_frames:
                now_mono = clock()
                remaining = max_seconds - (now_mono - started)
                if remaining <= 0:
                    break
                if pending_ping is not None and now_mono - pending_ping >= 45:
                    status = "shadow_pong_timeout_abstain"
                    break
                if now_mono - last_ping >= 20:
                    session.send('{"op":"ping"}')
                    last_ping = now_mono
                    pending_ping = now_mono
                try:
                    raw = session.recv(min(remaining, 5))
                except TimeoutError:
                    continue
                frames += 1
                payload = _bounded_json(raw)
                if type(payload) is not dict:
                    status = "shadow_envelope_abstain"
                    break
                if _is_public_pong(payload):
                    pong += 1
                    pending_ping = None
                    continue
                if payload.get("op") == "subscribe":
                    if (ack or not _subscription_ack(payload)
                            or payload.get("req_id", "") not in ("", "cia-ops30-shadow")):
                        status = "shadow_ack_invalid_abstain"
                        break
                    ack = True
                    status = "shadow_no_closed_candle_unverified"
                    continue
                if "op" in payload:
                    status = "shadow_control_abstain"
                    break
                if (set(payload) != {"topic", "type", "ts", "data"}
                        or payload.get("topic") not in topics
                        or payload.get("type") != "snapshot"
                        or type(payload.get("ts")) is not int
                        or type(payload.get("data")) is not list
                        or not 1 <= len(payload["data"]) <= 8
                        or any(type(r) is not dict for r in payload["data"])):
                    status = "shadow_envelope_abstain"
                    break
                if not ack:
                    preack += 1
                    if preack > MAX_PREACK:
                        status = "shadow_preack_budget_abstain"
                        break
                    continue
                receipt = wall_ms()
                server = payload["ts"]
                if (type(receipt) is not int or receipt <= 0
                        or server <= 0 or server > receipt
                        or receipt - server > 30_000):
                    status = "shadow_clock_abstain"
                    break
                current = receipt // HOUR_MS * HOUR_MS
                staged_closed = []
                staged_open = []
                malformed = False
                for row in payload["data"]:
                    start, end, stamp = row.get("start"), row.get("end"), row.get("timestamp")
                    if (any(type(v) is not int for v in (start, end, stamp))
                            or type(row.get("confirm")) is not bool
                            or stamp < start or stamp > server):
                        malformed = True
                        break
                    try:
                        _validate_one_kline_row(
                            row, server, receipt,
                            diagnostic_ignore_trade_stamp=True)
                    except DataValidationError:
                        malformed = True
                        break
                    band = _band(stamp, end)
                    if row["confirm"]:
                        if (start != current - HOUR_MS
                                or not end + 1 <= receipt <= end + 120_001):
                            malformed = True
                            break
                        staged_closed.append((payload["topic"], start, band))
                    else:
                        if start not in (current, current - HOUR_MS):
                            malformed = True
                            break
                        staged_open.append(band)
                if malformed or len(staged_closed) > 1:
                    status = "shadow_row_abstain"
                    break
                # Frames validated atomically. No WS message survives in state:
                # only topic membership and bounded per-hour keys are retained.
                market += 1
                seen_topics.add(payload["topic"])
                for _, _, band in staged_closed:
                    key = (payload["topic"], staged_closed[0][1])
                    if key in seen_closed:
                        dup += 1
                    else:
                        seen_closed.add(key)
                        closed_bands[band] += 1
                for band in staged_open:
                    open_bands[band] += 1
                    opens += 1
            if ack and status in ("shadow_no_closed_candle_unverified", "shadow_no_ack_abstain"):
                status = ("shadow_closes_observed_quarantined"
                          if seen_closed else "shadow_no_closed_candle_unverified")
            if frames >= max_frames and ack:
                # Saturation is not a successful complete observation.
                status = "shadow_frame_budget_abstain"
    except (DataValidationError, OSError, RuntimeError, ValueError, TypeError, ImportError):
        status = "shadow_transport_or_validation_abstain"
    except Exception:
        status = "shadow_unexpected_abstain"

    return ShadowWSReport(
        status, frames, market, preack, len(seen_topics),
        len(seen_closed), dup, opens, tuple(closed_bands),
        tuple(open_bands), pong)
