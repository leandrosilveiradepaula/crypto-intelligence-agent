"""J1/OPS3: bounded WebSocket supervisor for reviewed research fixtures.

All connections are supplied by the caller.  NO network connector, REST,
private database, scheduler, credential, trade, or deployment is enabled here.
A session may be backed by a test fake or a separately gated public socket.
Research data still has unverified provider origin and is NOT marketwide Top50.

The per-frame ingester is the existing strict offline WS pipeline and journal.
This orchestrator owns only connection lifecycle, topic ACK, heartbeat, bounded
reconnection, and sanitized operational counters. It never fills gaps itself.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import math
import time
from typing import Callable

from .bybit_closed_stream_cache import (
    OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    _scope_contract_fingerprint,
)
from .bybit_public_ws_once import (
    StreamSession, _bounded_json, _subscription_ack, _is_public_pong,
)
from .bybit_ws_offline_pipeline import ingest_offline_ws_batch
from .market_data import DataGapError, DataValidationError

TOPICS_PER_REQUEST = 10  # Conservative until real Linear subscription validated.
MAX_STREAM_TOPICS = 52
MAX_EARLY_FRAMES = 128
MAX_SESSIONS = 4
MAX_FRAMES = 20_000
MAX_SECONDS = 3_600
PING_EVERY_SECONDS = 20.0
PONG_DEADLINE_SECONDS = 45.0
RECEIVE_TIMEOUT_SECONDS = 5.0
RECONNECT_WAIT_SECONDS = 5.0


@dataclass(frozen=True)
class WSRunBudget:
    """Finely bounded demonstration lease; no infinite daemon is authorized."""

    max_sessions: int = 3
    max_frames: int = 4_096
    max_seconds: int = 180

    def __post_init__(self) -> None:
        if (type(self.max_sessions) is not int
                or not 1 <= self.max_sessions <= MAX_SESSIONS
                or type(self.max_frames) is not int
                or not 1 <= self.max_frames <= MAX_FRAMES
                or type(self.max_seconds) is not int
                or not 1 <= self.max_seconds <= MAX_SECONDS):
            raise DataValidationError("invalid bounded WS research budget")


@dataclass(frozen=True)
class WSRunReport:
    status: str
    failure_category: str | None
    sessions_attempted: int
    sessions_fully_acknowledged: int
    reconnects: int
    subscriptions_sent: int
    subscriptions_acknowledged: int
    frames_seen: int
    open_updates: int
    closed_events_appended: int
    identical_replays: int
    early_frames_buffered: int
    heartbeat_pings: int
    heartbeat_pongs: int

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "failure_category": self.failure_category,
            "sessions_attempted": self.sessions_attempted,
            "sessions_fully_acknowledged": self.sessions_fully_acknowledged,
            "reconnects": self.reconnects,
            "subscriptions_sent": self.subscriptions_sent,
            "subscriptions_acknowledged": self.subscriptions_acknowledged,
            "frames_seen": self.frames_seen,
            "open_updates": self.open_updates,
            "closed_events_appended": self.closed_events_appended,
            "identical_replays": self.identical_replays,
            "early_frames_buffered": self.early_frames_buffered,
            "heartbeat_pings": self.heartbeat_pings,
            "heartbeat_pongs": self.heartbeat_pongs,
            "http_gets": 0,
            "marketwide_top50_verified": False,
            "source_authenticated": False,
            "canonical_ohlcv_approved": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }


def _topic_batches(scope: OfflineReviewedStreamScope) -> tuple[tuple[str, ...], ...]:
    """A complete reviewed scope, not the current top 50, must be subscribed."""
    if type(scope) is not OfflineReviewedStreamScope:
        raise DataValidationError("offline reviewed WS scope required")
    _scope_contract_fingerprint(scope)
    if not 1 <= len(scope.contracts) <= MAX_STREAM_TOPICS:
        raise DataValidationError("WS stream scope exceeds independently reviewed budget")
    topics = tuple(sorted("kline.60." + x.symbol for x in scope.contracts))
    if len(set(topics)) != len(topics):
        raise DataValidationError("duplicate WS topic in reviewed scope")
    return tuple(tuple(topics[i:i + TOPICS_PER_REQUEST])
                 for i in range(0, len(topics), TOPICS_PER_REQUEST))


def supervise_ws_research(
    *, session_factory: Callable[[], StreamSession],
    scope: OfflineReviewedStreamScope,
    journal: SQLiteOfflineClosedStreamJournal,
    budget: WSRunBudget = WSRunBudget(),
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> WSRunReport:
    """Collect confirmed hourly WS events for a finite, *injected* lease.

    One subscribe request is outstanding at a time. The exchange may omit
    req_id on ACK: this remains unambiguous because there is one in flight.
    Market frames arriving before the related ACK are bounded and quarantined;
    they reach the existing strict ingester only after ALL ACKs were accepted.
    Recoverable transport exceptions reconnect at most max_sessions times.
    Corrupt frames, gap, malformed ACK, or stale candle fail CLOSED immediately.
    """
    if (not callable(session_factory) or not callable(clock)
            or not callable(wall_ms) or not callable(sleeper)
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(budget) is not WSRunBudget):
        raise DataValidationError("injected WS research capabilities required")
    groups = _topic_batches(scope)
    all_topics = frozenset(topic for batch in groups for topic in batch)
    frames = opened = appended = replayed = early_count = 0
    sessions = complete_sessions = sends = acks = pings = pongs = 0
    started = clock()
    if type(started) not in (int, float) or not math.isfinite(started):
        raise DataValidationError("WS monotonic clock invalid")

    def report(status: str, failure: str | None = None) -> WSRunReport:
        return WSRunReport(status, failure, sessions, complete_sessions,
                           max(0, sessions - 1), sends, acks, frames, opened,
                           appended, replayed, early_count, pings, pongs)

    for attempt in range(budget.max_sessions):
        if attempt:
            wait = RECONNECT_WAIT_SECONDS * (2 ** (attempt - 1))
            now = clock()
            if now + wait >= started + budget.max_seconds:
                return report("ws_budget_ended_abstain", "reconnection_deferred")
            sleeper(wait)
        if clock() - started >= budget.max_seconds or frames >= budget.max_frames:
            return report("ws_budget_ended_research_only")
        sessions += 1
        try:
            with closing(session_factory()) as session:
                pending_index = 0
                acknowledged_topics: set[str] = set()
                early: list[tuple[str | bytes, int]] = []
                last_ping = clock()
                pending_ping: float | None = None
                received_attempts = 0

                def subscribe(index: int) -> None:
                    nonlocal sends
                    args = groups[index]
                    payload = {"op": "subscribe", "req_id": f"cia-ws-{index + 1}",
                               "args": list(args)}
                    session.send(json.dumps(payload, separators=(",", ":")))
                    sends += 1

                def ingest(frame: str | bytes, at_ms: int) -> None:
                    nonlocal opened, appended, replayed
                    batch = ingest_offline_ws_batch(
                        frames=((frame, at_ms),), scope=scope,
                        journal=journal, require_ack=False,
                    )
                    opened += batch.open_updates
                    appended += batch.appended
                    replayed += batch.identical_replays

                subscribe(0)
                while True:
                    now = clock()
                    remaining = started + budget.max_seconds - now
                    if remaining <= 0 or frames >= budget.max_frames:
                        return report("ws_budget_ended_research_only" if
                                      len(acknowledged_topics) == sum(map(len, groups))
                                      else "ws_budget_ended_abstain")
                    if (pending_ping is not None
                            and now - pending_ping >= PONG_DEADLINE_SECONDS):
                        raise OSError("pong missing")
                    if now - last_ping >= PING_EVERY_SECONDS:
                        session.send('{"op":"ping"}')
                        pings += 1
                        last_ping = now
                        if pending_ping is None:
                            pending_ping = now
                    received_attempts += 1
                    # Bound even broken fake clocks and timeout-only sessions.
                    if received_attempts > (budget.max_frames * 4 + MAX_SECONDS):
                        return report("ws_budget_ended_abstain", "receive_budget")
                    try:
                        raw = session.recv(min(RECEIVE_TIMEOUT_SECONDS, remaining))
                    except TimeoutError:
                        continue
                    frames += 1
                    payload = _bounded_json(raw)
                    if type(payload) is not dict:
                        raise DataValidationError("WS object envelope required")
                    at_ms = wall_ms()
                    if type(at_ms) is not int or at_ms <= 0:
                        raise DataValidationError("WS wall clock must be positive UTC ms")
                    if _is_public_pong(payload):
                        pongs += 1
                        pending_ping = None
                        continue
                    if payload.get("op") == "subscribe":
                        if pending_index >= len(groups) or not _subscription_ack(payload):
                            raise DataValidationError("WS malformed or extra subscription ACK")
                        # When several subscription chunks share one socket,
                        # a missing req_id can misattribute a duplicated ACK
                        # to the *next* chunk. Fail closed until a bounded
                        # venue probe proves a stronger correlation contract.
                        expected_req = f"cia-ws-{pending_index + 1}"
                        if (payload.get("req_id") != expected_req
                                if len(groups) > 1 else
                                ("req_id" in payload
                                 and payload["req_id"] != expected_req)):
                            raise DataValidationError("WS subscribe ACK correlation mismatch")
                        acknowledged_topics.update(groups[pending_index])
                        pending_index += 1
                        acks += 1
                        if pending_index < len(groups):
                            subscribe(pending_index)
                        else:
                            complete_sessions += 1
                            for buffered, buffered_ms in early:
                                ingest(buffered, buffered_ms)
                            early.clear()
                        continue
                    if payload.get("op") is not None:
                        raise DataValidationError("unexpected WS control frame")
                    if (type(payload.get("topic")) is not str
                            or payload["topic"] not in all_topics):
                        raise DataValidationError("unexpected WS market topic")
                    if pending_index < len(groups):
                        if len(early) >= MAX_EARLY_FRAMES:
                            raise DataValidationError("WS early frame budget exceeded")
                        early.append((raw, at_ms))
                        early_count += 1
                        continue
                    ingest(raw, at_ms)
        except (DataGapError, DataValidationError, ValueError, TypeError):
            return report("ws_fail_closed_abstain", "invalid_or_gapped_market_data")
        except (OSError, RuntimeError):
            # No special 10006 recovery: this path only handles WS connection
            # disruption. Missing CLOSED hours remain missing in the journal.
            continue
    return report("ws_reconnect_budget_exhausted_abstain", "transport_disconnected")