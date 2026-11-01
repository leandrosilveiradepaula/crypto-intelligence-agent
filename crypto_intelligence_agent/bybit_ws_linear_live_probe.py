"""J1/OPS8: one-shot, no-persistence, personal public LINEAR WS proof.

This is deliberately distinct from the full collector: a successful subscribe
ACK does not certify delivery of all 52 topics, all eligible contracts, a
closed 1h candle, provider identity or trading availability. No REST, SQLite,
credentials, orders, reconnects, or background tasks exist in this module.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import math
import os
import re
import time
from typing import Callable

from .bybit_public_ws_once import (
    StreamSession, _bounded_json, _is_public_pong,
    _subscription_ack, _validate_one_kline_row,
)
from .market_data import DataValidationError
from .research_registry_catalog import load_reviewed_registry

MAX_TOPICS = 52
MAX_ARGS_CHARS = 21_000
MAX_FRAMES = 1_024
MAX_SECONDS = 90
MAX_EARLY_FRAMES = 128
PONG_SECONDS = 45
PING_SECONDS = 20
RECEIVE_SECONDS = 5
_REQUEST_ID = "cia-probe-52"
_TOPIC = re.compile(r"kline\.60\.[A-Z0-9]{2,30}USDT\Z")


@dataclass(frozen=True)
class LinearWSProof:
    status: str
    failure_category: str | None
    topics_requested: int
    subscription_acks: int = 0
    frames_received: int = 0
    pre_ack_market_frames: int = 0
    valid_market_frames: int = 0
    distinct_topics_seen: int = 0
    validated_closed_events: int = 0
    distinct_closed_topics: int = 0
    heartbeat_pongs: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status, "failure_category": self.failure_category,
            "topics_requested": self.topics_requested,
            "subscription_acks": self.subscription_acks,
            "frames_received": self.frames_received,
            "pre_ack_market_frames": self.pre_ack_market_frames,
            "valid_market_frames": self.valid_market_frames,
            "distinct_topics_seen": self.distinct_topics_seen,
            "validated_closed_events": self.validated_closed_events,
            "distinct_closed_topics": self.distinct_closed_topics,
            "all_topics_delivered_verified": False,
            "closed_24h_complete": False,
            "marketwide_top50_verified": False,
            "network_source_authenticated": False,
            "data_stored": False, "http_gets": 0,
            "credentials_used": False, "orders_sent": False,
            "live_trading_authorized": False,
        }


def reviewed_candidate_topics(*, at_ms: int) -> tuple[str, ...]:
    """Only topic *candidates*: not a verification of live venue instruments."""
    registry = load_reviewed_registry("expanded-52", as_of_ms=at_ms)
    topics = tuple(sorted("kline.60." + a.base + "USDT" for a in registry.assets))
    _validate_topics(topics)
    if len(topics) != MAX_TOPICS:
        raise DataValidationError("reviewed candidate registry has wrong size")
    return topics


def _validate_topics(topics: tuple[str, ...]) -> None:
    if (type(topics) is not tuple or not 1 <= len(topics) <= MAX_TOPICS
            or any(type(t) is not str or not _TOPIC.fullmatch(t) for t in topics)
            or len(set(topics)) != len(topics)
            or tuple(sorted(topics)) != topics
            or len(json.dumps(topics, separators=(",", ":"))) > MAX_ARGS_CHARS):
        raise DataValidationError("invalid bounded single-request LINEAR topics")


def probe_linear_topics_once(
    *, session_factory: Callable[[], StreamSession],
    topics: tuple[str, ...],
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    max_seconds: int = 35,
    max_frames: int = 512,
) -> LinearWSProof:
    """Single socket, single subscribe; count only strict post-ACK data frames."""
    _validate_topics(topics)
    if (not callable(session_factory) or not callable(clock)
            or not callable(wall_ms) or type(max_seconds) is not int
            or not 1 <= max_seconds <= MAX_SECONDS or type(max_frames) is not int
            or not 1 <= max_frames <= MAX_FRAMES):
        raise DataValidationError("invalid LINEAR proof capabilities or budget")
    started = clock()
    if type(started) not in (int, float) or not math.isfinite(started):
        raise DataValidationError("LINEAR proof monotonic clock invalid")
    frames = preack = valid = closed = pongs = ack = 0
    topics_seen: set[str] = set()
    closed_seen: set[str] = set()
    failure: str | None = None
    status = "ws_ack_missing_abstain"
    last_ping = started
    pending_ping: float | None = None
    no_progress = 0
    stage = "connect"

    def result() -> LinearWSProof:
        return LinearWSProof(status, failure, len(topics), ack, frames,
                             preack, valid, len(topics_seen), closed,
                             len(closed_seen), pongs)

    try:
        with closing(session_factory()) as session:
            stage = "subscribe"
            request = {"op": "subscribe", "req_id": _REQUEST_ID, "args": list(topics)}
            session.send(json.dumps(request, separators=(",", ":")))
            while frames < max_frames:
                now = clock()
                remaining = started + max_seconds - now
                if remaining <= 0:
                    status = ("ws_ack_with_market_frames_unverified" if valid else
                              "ws_ack_only_unverified" if ack else "ws_ack_missing_abstain")
                    return result()
                if pending_ping is not None and now - pending_ping >= PONG_SECONDS:
                    status, failure = "ws_transport_abstain", "pong_timeout"
                    return result()
                if now - last_ping >= PING_SECONDS:
                    session.send('{"op":"ping"}')
                    last_ping = now
                    if pending_ping is None:
                        pending_ping = now
                no_progress += 1
                if no_progress > max_frames * 4 + MAX_SECONDS:
                    status, failure = "ws_budget_abstain", "receive_budget"
                    return result()
                stage = "receive"
                try:
                    raw = session.recv(min(RECEIVE_SECONDS, remaining))
                except TimeoutError:
                    continue
                frames += 1
                stage = "validate"
                obj = _bounded_json(raw)
                if type(obj) is not dict:
                    raise DataValidationError("LINEAR proof frame envelope invalid")
                if _is_public_pong(obj):
                    pongs += 1
                    pending_ping = None
                    continue
                if obj.get("op") == "subscribe":
                    if ack or not _subscription_ack(obj):
                        status, failure = "ws_ack_rejected_abstain", "malformed_or_duplicate_ack"
                        return result()
                    if ("req_id" in obj and obj["req_id"] not in ("", _REQUEST_ID)):
                        status, failure = "ws_ack_rejected_abstain", "wrong_request_id"
                        return result()
                    ack += 1
                    continue
                if obj.get("op") is not None:
                    status, failure = "ws_frame_invalid_abstain", "unexpected_control"
                    return result()
                topic = obj.get("topic")
                if type(topic) is not str or topic not in topics:
                    status, failure = "ws_frame_invalid_abstain", "unexpected_topic"
                    return result()
                # Market data before ACK never count as accepted proof and
                # are never buffered, printed or saved.
                if not ack:
                    preack += 1
                    if preack > MAX_EARLY_FRAMES:
                        status, failure = "ws_ack_missing_abstain", "preack_budget"
                        return result()
                    continue
                received = wall_ms()
                server = obj.get("ts")
                rows = obj.get("data")
                if (set(obj) != {"topic", "type", "ts", "data"}
                        or obj.get("type") != "snapshot"
                        or type(server) is not int or type(received) is not int
                        or received <= 0 or server > received + 5000
                        or received - server > 30_000
                        or type(rows) is not list or not 1 <= len(rows) <= 8):
                    raise DataValidationError("LINEAR proof market envelope invalid")
                has_close = False
                for row in rows:
                    if type(row) is not dict:
                        raise DataValidationError("LINEAR proof market row invalid")
                    has_close |= _validate_one_kline_row(row, server, received)
                    closed += int(row["confirm"] is True)
                valid += 1
                topics_seen.add(topic)
                if has_close:
                    closed_seen.add(topic)
            status = ("ws_ack_with_market_frames_unverified" if valid else
                      "ws_ack_only_unverified" if ack else "ws_ack_missing_abstain")
            return result()
    except (OSError, TimeoutError, RuntimeError, ImportError):
        status, failure = "ws_transport_abstain", stage
    except (DataValidationError, ValueError, TypeError):
        status, failure = "ws_frame_invalid_abstain", stage
    except Exception:
        # Unknown dependency/provider exceptions must not disclose payloads.
        status, failure = "ws_unexpected_failure_abstain", stage
    return result()


def owner_probe_linear_topics_once(*, allow_public_network: bool = False,
                                   allow_public_websocket: bool = False,
                                   confirm_region_and_personal_research: bool = False,
                                   seconds: int = 35,
                                   max_frames: int = 512,
                                   session_factory=None,
                                   clock: Callable[[], float] = time.monotonic,
                                   wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
                                   owner_check: Callable[[], bool] | None = None) -> LinearWSProof:
    """Explicit permission gate *before* importing or opening a real socket."""
    if (allow_public_network is not True or allow_public_websocket is not True
            or confirm_region_and_personal_research is not True):
        return LinearWSProof("ws_owner_opt_in_required", None, 0)
    if owner_check is None:
        owner_check = lambda: os.name == "posix" and os.geteuid() != 0
    if not owner_check():
        return LinearWSProof("ws_owner_posix_unprivileged_required", None, 0)
    if (type(seconds) is not int or not 1 <= seconds <= MAX_SECONDS
            or type(max_frames) is not int or not 1 <= max_frames <= MAX_FRAMES):
        return LinearWSProof("ws_budget_invalid_abstain", None, 0)
    try:
        topics = reviewed_candidate_topics(at_ms=wall_ms())
    except (ValueError, DataValidationError, OSError, TypeError):
        return LinearWSProof("ws_candidate_registry_invalid_abstain", None, 0)
    if session_factory is None:
        from .bybit_public_ws_once import _real_session_factory
        session_factory = _real_session_factory
    return probe_linear_topics_once(
        session_factory=session_factory, topics=topics, clock=clock,
        wall_ms=wall_ms, max_seconds=seconds, max_frames=max_frames)