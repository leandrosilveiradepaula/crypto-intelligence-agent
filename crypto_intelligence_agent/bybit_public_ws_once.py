"""Finite, opt-in, read-only Bybit public WebSocket observer (J1 #328).

No account, order, historical backfill, marketwide proof or persistent data.
The network connector is injected in offline tests; production connector is
lazy-imported only after the owner opt-in gate. No reconnect/retry/fallback.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import os
import time
from typing import Callable, Protocol

from .decimal_json import decode_public_market_json_exact
from .market_data import DataValidationError

ENDPOINT = "wss://stream.bybit.com/v5/public/linear"
TOPIC = "kline.60.BTCUSDT"
MAX_FRAME_BYTES = 16384
MAX_FRAMES = 64
MAX_SECONDS = 90
HOUR_MS = 3_600_000


class StreamSession(Protocol):
    def send(self, payload: str) -> None: ...
    def recv(self, timeout: float) -> str | bytes: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class WSOnceResult:
    status: str
    frames_seen: int
    confirmed_closed_events: int
    acknowledged: bool

    def sanitized_report(self) -> dict:
        return {"status": self.status, "frames_seen": self.frames_seen,
                "confirmed_closed_events": self.confirmed_closed_events,
                "subscription_acknowledged": self.acknowledged,
                "network_source_authenticated": False,
                "marketwide_top50_verified": False,
                "data_stored": False, "orders_sent": False,
                "live_trading_authorized": False}


def _bounded_json(frame: str | bytes) -> dict:
    if type(frame) not in (str, bytes):
        raise DataValidationError("ws_frame_type_invalid")
    value = decode_public_market_json_exact(frame, max_bytes=MAX_FRAME_BYTES)
    return value


def _check_closed(frame: dict, *, received_ms: int) -> bool:
    if set(frame) != {"topic", "type", "ts", "data"} or frame.get("topic") != TOPIC or frame.get("type") != "snapshot":
        raise DataValidationError("ws_topic_or_envelope_invalid")
    rows = frame.get("data")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        raise DataValidationError("ws_kline_shape_invalid")
    row = rows[0]
    expected = {"start", "end", "interval", "open", "high", "low", "close", "volume", "turnover", "confirm", "timestamp"}
    if set(row) != expected:
        raise DataValidationError("ws_kline_fields_invalid")
    start, end, stamp, server = row["start"], row["end"], row["timestamp"], frame["ts"]
    if any(type(v) is not int for v in (start, end, stamp, server, received_ms)):
        raise DataValidationError("ws_time_type_invalid")
    if (row["interval"] != "60" or start <= 0 or start % HOUR_MS or end != start + HOUR_MS - 1
            or not start <= stamp <= end or server > received_ms or received_ms - server > 30000):
        raise DataValidationError("ws_clock_invalid")
    from .bybit_linear_candle_research import _strict_decimal
    prices = {k: _strict_decimal(row[k], label=k, may_be_zero=False) for k in ("open", "high", "low", "close")}
    _strict_decimal(row["volume"], label="volume", may_be_zero=True)
    _strict_decimal(row["turnover"], label="turnover", may_be_zero=True)
    if prices["high"] < max(prices.values()) or prices["low"] > min(prices.values()):
        raise DataValidationError("ws_ohlc_invalid")
    if type(row["confirm"]) is not bool:
        raise DataValidationError("ws_confirm_type_invalid")
    if not row["confirm"]:
        return False
    if server < end + 1 or received_ms < end + 1000 or received_ms - (end + 1) > 120000:
        raise DataValidationError("ws_close_clock_invalid")
    return True


def observe_once(*, session_factory: Callable[[], StreamSession], clock: Callable[[], float] = time.monotonic,
                 wall_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 max_frames: int = MAX_FRAMES, max_seconds: int = MAX_SECONDS) -> WSOnceResult:
    if (type(max_frames) is not int or not 1 <= max_frames <= MAX_FRAMES or type(max_seconds) is not int
            or not 1 <= max_seconds <= MAX_SECONDS):
        raise DataValidationError("ws_budget_invalid")
    frames = 0
    acknowledged = False
    started = clock()
    try:
        with closing(session_factory()) as session:
            session.send(json.dumps({"op": "subscribe", "args": [TOPIC]}, separators=(",", ":")))
            while frames < max_frames:
                remaining = max_seconds - (clock() - started)
                if remaining <= 0:
                    return WSOnceResult("ws_observation_timeout", frames, 0, acknowledged)
                try:
                    raw = session.recv(min(remaining, 5.0))
                except TimeoutError:
                    continue
                frames += 1
                payload = _bounded_json(raw)
                if not acknowledged:
                    if (set(payload) != {"success", "ret_msg", "conn_id", "op"}
                            or payload["op"] != "subscribe" or payload["success"] is not True
                            or type(payload["ret_msg"]) is not str or type(payload["conn_id"]) is not str):
                        return WSOnceResult("ws_subscription_not_acknowledged", frames, 0, False)
                    acknowledged = True
                    continue
                if _check_closed(payload, received_ms=wall_ms()):
                    return WSOnceResult("ws_one_closed_hour_observed_only", frames, 1, True)
    except (OSError, ValueError, TypeError, RuntimeError, DataValidationError, ImportError):
        return WSOnceResult("ws_failed_closed", frames, 0, acknowledged)
    return WSOnceResult("ws_frame_budget_exhausted", frames, 0, acknowledged)


def _real_session_factory():
    from websockets.sync.client import connect
    from websockets.exceptions import ConnectionClosed
    connection = connect(ENDPOINT, open_timeout=5, close_timeout=2, compression=None,
                         max_size=MAX_FRAME_BYTES, proxy=None, ping_interval=None)
    class Adapter:
        def send(self, payload): connection.send(payload)
        def recv(self, timeout):
            try: return connection.recv(timeout=timeout)
            except TimeoutError: raise
            except ConnectionClosed as exc: raise OSError("closed") from None
        def close(self): connection.close()
    return Adapter()


def owner_probe(*, allow_public_websocket: bool, confirm_region_and_personal_research: bool) -> dict:
    if (allow_public_websocket is not True or confirm_region_and_personal_research is not True
            or os.name != "posix"):
        return WSOnceResult("ws_owner_opt_in_or_posix_required", 0, 0, False).sanitized_report()
    return observe_once(session_factory=_real_session_factory).sanitized_report()
