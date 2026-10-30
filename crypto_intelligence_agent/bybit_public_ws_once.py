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
    failure_category: str | None = None

    def sanitized_report(self) -> dict:
        return {"status": self.status, "frames_seen": self.frames_seen,
                "confirmed_closed_events": self.confirmed_closed_events,
                "subscription_acknowledged": self.acknowledged,
                "network_source_authenticated": False,
                "marketwide_top50_verified": False,
                "data_stored": False, "orders_sent": False,
                "live_trading_authorized": False,
                "failure_category": self.failure_category}


def _bounded_json(frame: str | bytes) -> dict:
    if type(frame) not in (str, bytes):
        raise DataValidationError("ws_frame_type_invalid")
    value = decode_public_market_json_exact(frame, max_bytes=MAX_FRAME_BYTES)
    return value


def _subscription_ack(payload: dict) -> bool:
    """Only supported Bybit public subscribe ACK fields, never echo IDs."""
    required = {"success", "ret_msg", "conn_id", "op"}
    if (not isinstance(payload, dict) or not required <= set(payload)
            or set(payload) - required - {"req_id"}
            or payload.get("op") != "subscribe"
            or type(payload.get("success")) is not bool
            or type(payload.get("ret_msg")) is not str
            or len(payload["ret_msg"]) > 128
            or type(payload.get("conn_id")) is not str
            or len(payload["conn_id"]) > 128
            or ("req_id" in payload and
                (type(payload["req_id"]) is not str or len(payload["req_id"]) > 128))):
        return False
    return payload["success"] is True



def _classify_first_frame(payload: dict) -> str:
    """Allowlisted reason only; never echo provider strings or identifiers."""
    if payload.get("op") == "subscribe":
        if payload.get("success") is False:
            return "ws_subscription_explicitly_rejected"
        required = {"success", "ret_msg", "conn_id", "op"}
        if not required <= set(payload):
            return "ws_subscription_fields_missing"
        if set(payload) - required - {"req_id"}:
            return "ws_subscription_fields_unexpected"
        return "ws_subscription_fields_invalid"
    if payload.get("topic") is not None or "data" in payload:
        return "ws_market_data_before_ack"
    if payload.get("op") is not None:
        return "ws_unexpected_control_before_ack"
    return "ws_unexpected_first_frame"


def _public_pong(payload: dict) -> bool:
    """Recognize only a bounded heartbeat reply; not a market data frame."""
    if (not isinstance(payload, dict) or payload.get("op") != "ping"
            or not {"op", "ret_msg"} <= set(payload)
            or set(payload) - {"op", "ret_msg", "conn_id", "req_id", "success", "args"}
            or payload.get("ret_msg") != "pong"):
        return False
    for key in ("conn_id", "req_id"):
        if key in payload and (type(payload[key]) is not str or len(payload[key]) > 128):
            return False
    if "success" in payload and payload["success"] is not True:
        return False
    if "args" in payload and (type(payload["args"]) is not list
                              or len(payload["args"]) > 1):
        return False
    return True


def _public_pong_v2(payload: dict) -> bool:
    """Bybit V5 alternative public pong; reject all undocumented fields."""
    if (type(payload) is not dict or set(payload) != {"op", "args"}
            or payload.get("op") != "pong"):
        return False
    args = payload.get("args")
    return (type(args) is list and len(args) == 1
            and type(args[0]) is str and 1 <= len(args[0]) <= 16
            and args[0].isascii() and args[0].isdecimal())


def _is_public_pong(payload: dict) -> bool:
    return _public_pong(payload) or _public_pong_v2(payload)


def seconds_to_closed_hour_probe(now_ms: int) -> int:
    """UTC scheduling: connect at most 20s before a boundary, at most once."""
    if type(now_ms) is not int or now_ms <= 0:
        raise DataValidationError("ws_owner_clock_invalid")
    until_boundary_ms = HOUR_MS - now_ms % HOUR_MS
    return max(0, (until_boundary_ms - 20_000 + 999) // 1000)



def _safe_failure_category(error: Exception, stage: str) -> str:
    """Only fixed categories; never serialize exception text or provider bytes."""
    if stage == "transport":
        return "transport"
    if stage == "json":
        return "json"
    if not isinstance(error, DataValidationError):
        return "processing"
    # The error text is inspected locally, never emitted or logged.
    reason = str(error)
    mapping = {
        "ws_kline_root_keys_invalid": "kline_root_keys",
        "ws_kline_topic_invalid": "kline_topic",
        "ws_kline_type_invalid": "kline_type",
        "ws_kline_rows_type_invalid": "kline_rows_type",
        "ws_kline_rows_nonobject_invalid": "kline_rows_nonobject",
        "ws_kline_rows_overflow_invalid": "kline_rows_overflow",
        "ws_kline_fields_invalid": "kline_fields",
    }
    for prefix, category in mapping.items():
        if reason.startswith(prefix):
            return category
    if reason.startswith("ws_clock") or reason.startswith("ws_time") or reason.startswith("ws_close_clock"):
        return "kline_clock"
    if reason.startswith("ws_confirm"):
        return "kline_confirmation"
    if reason.startswith("ws_ohlc"):
        return "kline_ohlc"
    if reason.startswith("Bybit "):
        return "kline_decimal"
    return "kline_invalid"


def _check_closed(frame: dict, *, received_ms: int) -> bool:
    if set(frame) != {"topic", "type", "ts", "data"}:
        raise DataValidationError("ws_kline_root_keys_invalid")
    if frame.get("topic") != TOPIC:
        raise DataValidationError("ws_kline_topic_invalid")
    if frame.get("type") != "snapshot":
        raise DataValidationError("ws_kline_type_invalid")
    rows = frame.get("data")
    if type(rows) is not list:
        raise DataValidationError("ws_kline_rows_type_invalid")
    if len(rows) > 8:
        raise DataValidationError("ws_kline_rows_overflow_invalid")
    if any(type(row) is not dict for row in rows):
        raise DataValidationError("ws_kline_rows_nonobject_invalid")
    # Validate every row before approving any closed candle.
    return any_closed_after_full_validation(rows, frame["ts"], received_ms)


def any_closed_after_full_validation(rows: list, server: int, received_ms: int) -> bool:
    any_closed = False
    for row in rows:
        any_closed = _validate_one_kline_row(row, server, received_ms) or any_closed
    return any_closed


def _validate_one_kline_row(row: dict, server: int, received_ms: int) -> bool:
    expected = {"start", "end", "interval", "open", "high", "low", "close", "volume", "turnover", "confirm", "timestamp"}
    if set(row) != expected:
        raise DataValidationError("ws_kline_fields_invalid")
    start, end, stamp = row["start"], row["end"], row["timestamp"]
    if any(type(v) is not int for v in (start, end, stamp, server, received_ms)):
        raise DataValidationError("ws_time_type_invalid")
    if (row["interval"] != "60" or start <= 0 or start % HOUR_MS or end != start + HOUR_MS - 1
            or not start <= stamp <= end or server > received_ms + 5000 or received_ms - server > 30000):
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
    if server < end + 1 or received_ms + 5000 < end + 1 or received_ms - (end + 1) > 120000:
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
    last_ping = started
    preack_frames = 0
    preack_closed = False
    stage = "transport"
    try:
        with closing(session_factory()) as session:
            session.send(json.dumps({"op": "subscribe", "args": [TOPIC]}, separators=(",", ":")))
            while frames < max_frames:
                remaining = max_seconds - (clock() - started)
                if remaining <= 0:
                    return WSOnceResult("ws_unacknowledged_market_data" if preack_frames and not acknowledged else "ws_observation_timeout", frames, 0, acknowledged)
                now = clock()
                if acknowledged and now - last_ping >= 20:
                    session.send('{"op":"ping"}')
                    last_ping = now
                try:
                    raw = session.recv(min(remaining, 5.0))
                except TimeoutError:
                    continue
                frames += 1
                stage = "json"
                payload = _bounded_json(raw)
                stage = "envelope"
                if not acknowledged:
                    if payload.get("topic") is not None or "data" in payload:
                        # A pre-ACK frame is never accepted without a later valid ACK.
                        # Do not retain the payload or any market value.
                        stage = "kline"
                        closed = _check_closed(payload, received_ms=wall_ms())
                        preack_frames += 1
                        if preack_frames > 8:
                            return WSOnceResult("ws_preack_frame_limit", frames, 0, False)
                        preack_closed = preack_closed or closed
                        continue
                    if not _subscription_ack(payload):
                        return WSOnceResult(_classify_first_frame(payload), frames, 0, False)
                    acknowledged = True
                    if preack_closed:
                        return WSOnceResult("ws_one_closed_hour_observed_only", frames, 1, True)
                    continue
                if _is_public_pong(payload):
                    continue
                if "op" in payload and "topic" not in payload and "data" not in payload:
                    return WSOnceResult("ws_failed_closed", frames, 0, acknowledged, "unexpected_control")
                stage = "kline"
                if _check_closed(payload, received_ms=wall_ms()):
                    return WSOnceResult("ws_one_closed_hour_observed_only", frames, 1, True)
    except (OSError, ValueError, TypeError, RuntimeError, DataValidationError, ImportError) as error:
        category = _safe_failure_category(error, stage)
        return WSOnceResult("ws_failed_closed", frames, 0, acknowledged, category)
    return WSOnceResult("ws_unacknowledged_market_data" if preack_frames and not acknowledged else "ws_frame_budget_exhausted", frames, 0, acknowledged)


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


def owner_probe(*, allow_public_websocket: bool, confirm_region_and_personal_research: bool,
                schedule_closed_utc_hour: bool = False,
                clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                sleeper: Callable[[float], None] = time.sleep) -> dict:
    if (allow_public_websocket is not True or confirm_region_and_personal_research is not True
            or os.name != "posix"):
        return WSOnceResult("ws_owner_opt_in_or_posix_required", 0, 0, False).sanitized_report()
    if schedule_closed_utc_hour is not True:
        return WSOnceResult("ws_closed_hour_schedule_required", 0, 0, False).sanitized_report()
    try:
        seconds = seconds_to_closed_hour_probe(clock_ms())
        if seconds > 3580:
            return WSOnceResult("ws_owner_clock_invalid", 0, 0, False).sanitized_report()
        if seconds:
            sleeper(seconds)
    except (OSError, ValueError, TypeError, RuntimeError):
        return WSOnceResult("ws_owner_clock_invalid", 0, 0, False).sanitized_report()
    return observe_once(session_factory=_real_session_factory).sanitized_report()
