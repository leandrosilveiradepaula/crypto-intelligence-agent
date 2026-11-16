"""D386 / #677: bounded Bybit V5 public ticker WS lease; pure injected transport.

The caller supplies a socket/session factory and independently admitted N50
membership. No credentials, network connector, REST, order, position journal,
systemd installer, or live-account operation is imported or invoked here.
The lease is FINITE; a deployment/scheduler for 24x7 is a separate gate.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import math
import time
from typing import Callable

from .bybit_public_ticker_state_d385 import BybitPublicTickerBook, BybitTickerQuote
from .bybit_public_ws_once import (
    StreamSession, _bounded_json, _is_public_pong, _subscription_ack,
)
from .market_data import DataGapError, DataValidationError

MAX_SECONDS = 3600
MAX_FRAMES = 5_000_000
MAX_SESSIONS = 4
MAX_PREACK_FRAMES = 128
MAX_SUBSCRIBE_ARG_CHARS = 21_000
PING_EVERY_SECONDS = 20.0
PONG_DEADLINE_SECONDS = 45.0
RECEIVE_TIMEOUT_SECONDS = 5.0
RECONNECT_WAIT_SECONDS = 5.0

# Fixed categories from our own code only, never include provider payloads.
_FAILURE_CLASSES = {
    "ticker_subscription_not_acknowledged": "subscription_not_acknowledged",
    "ticker_envelope_fields_invalid": "bad_envelope",
    "ticker_topic_invalid": "bad_topic",
    "ticker_outside_reviewed_membership": "scope_mismatch",
    "ticker_payload_symbol_invalid": "payload_symbol_mismatch",
    "ticker_retrograde_sequence_or_time": "sequence_regression",
    "ticker_same_sequence_conflicting_payload": "conflicting_replay",
    "ticker_delta_without_snapshot": "snapshot_required",
    "ticker_transport_clock_stale_or_future": "stale_or_future",
    "ticker_crossed_best_bid_ask": "bad_best_quotes",
    "ticker_universe_rotation_invalid": "scope_clock_invalid",
    "duplicate market JSON keys are forbidden": "duplicate_json_keys",
}


@dataclass(frozen=True)
class TickerLeaseBudget:
    max_sessions: int = 3
    max_frames: int = 50_000
    max_seconds: int = 180

    def __post_init__(self) -> None:
        if (type(self.max_sessions) is not int
                or not 1 <= self.max_sessions <= MAX_SESSIONS
                or type(self.max_frames) is not int
                or not 1 <= self.max_frames <= MAX_FRAMES
                or type(self.max_seconds) is not int
                or not 1 <= self.max_seconds <= MAX_SECONDS):
            raise DataValidationError("ticker_ws_lease_budget_invalid")


@dataclass(frozen=True)
class TickerLeaseReport:
    status: str
    failure_category: str | None
    sessions_attempted: int
    subscriptions_sent: int
    subscriptions_acknowledged: int
    reconnects: int
    frames_seen: int
    ticker_frames_accepted: int
    preack_frames_discarded: int
    pong_frames: int
    ping_frames: int
    last_fresh_quote_count: int
    latency_0_to_100ms: int
    latency_101_to_1000ms: int
    latency_1001_to_5000ms: int
    latency_over_5000ms: int

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "bybit-public-ticker-lease-d386-v1",
            "status": self.status,
            "failure_category": self.failure_category,
            "sessions_attempted": self.sessions_attempted,
            "subscriptions_sent": self.subscriptions_sent,
            "subscriptions_acknowledged": self.subscriptions_acknowledged,
            "reconnects": self.reconnects,
            "frames_seen": self.frames_seen,
            "ticker_frames_accepted": self.ticker_frames_accepted,
            "preack_frames_discarded": self.preack_frames_discarded,
            "heartbeat_pings": self.ping_frames,
            "heartbeat_pongs": self.pong_frames,
            "last_fresh_quote_count": self.last_fresh_quote_count,
            "latency_0_to_100ms": self.latency_0_to_100ms,
            "latency_101_to_1000ms": self.latency_101_to_1000ms,
            "latency_1001_to_5000ms": self.latency_1001_to_5000ms,
            "latency_over_5000ms": self.latency_over_5000ms,
            "no_unbounded_queue": True,
            "source_authenticated": False,
            "marketwide_top50_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def _safe_failure(error: Exception) -> str:
    if isinstance(error, (DataGapError, DataValidationError)):
        return _FAILURE_CLASSES.get(str(error), "invalid_market_data")
    return "internal_validation_failure"


def _monotonic(clock: Callable[[], float]) -> float:
    result = clock()
    if type(result) not in (int, float) or not math.isfinite(result):
        raise DataValidationError("ticker_ws_monotonic_clock_invalid")
    return float(result)


def _topic_args(book: BybitPublicTickerBook) -> tuple[str, ...]:
    if type(book) is not BybitPublicTickerBook:
        raise DataValidationError("ticker_ws_requires_reviewed_state")
    topics = book.topics
    if (not topics or
            len(json.dumps(topics, separators=(",", ":"))) > MAX_SUBSCRIBE_ARG_CHARS):
        raise DataValidationError("ticker_ws_linear_args_budget_invalid")
    return topics


def supervise_public_tickers(
    *, session_factory: Callable[[], StreamSession],
    book: BybitPublicTickerBook,
    budget: TickerLeaseBudget = TickerLeaseBudget(),
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
    on_quote: Callable[[BybitTickerQuote], None] | None = None,
) -> TickerLeaseReport:
    """Receive real-time ticker data from injected sessions for a finite lease.

    ONE subscribe request per connection. The Bybit linear subscribe ACK may
    omit req_id or return an empty ID; a single request avoids false ACK
    correlation. Pre-ACK ticker messages are discarded without ingestion.
    Restart/reconnect invalidates ALL snapshots and later deltas require a new
    snapshot; transport errors alone trigger bounded reconnect. A broken WS
    frame is a terminal fail-closed error, never silently skipped.

    The optional callback is strictly a caller-supplied PAPER/monitoring hook,
    not an order/exchange adapter. It runs synchronously with no buffered queue.
    """
    if (not callable(session_factory) or not callable(clock)
            or not callable(wall_ms) or not callable(sleeper)
            or type(book) is not BybitPublicTickerBook
            or type(budget) is not TickerLeaseBudget
            or (on_quote is not None and not callable(on_quote))):
        raise DataValidationError("ticker_ws_injected_dependencies_invalid")
    topics = _topic_args(book)
    allowed = frozenset(topics)
    sessions = sends = acks = frames = accepted = preack = pings = pongs = 0
    bins = [0, 0, 0, 0]
    started = _monotonic(clock)
    book.mark_disconnected()

    def report(status: str, failure: str | None = None) -> TickerLeaseReport:
        try:
            freshness = book.sanitized_report(at_ms=wall_ms())["fresh_quotes"]
        except (ValueError, TypeError, DataValidationError):
            freshness = 0
        return TickerLeaseReport(
            status=status, failure_category=failure,
            sessions_attempted=sessions, subscriptions_sent=sends,
            subscriptions_acknowledged=acks,
            reconnects=max(0, sessions - 1),
            frames_seen=frames, ticker_frames_accepted=accepted,
            preack_frames_discarded=preack, pong_frames=pongs,
            ping_frames=pings, last_fresh_quote_count=freshness,
            latency_0_to_100ms=bins[0],
            latency_101_to_1000ms=bins[1],
            latency_1001_to_5000ms=bins[2],
            latency_over_5000ms=bins[3],
        )

    for attempt in range(budget.max_sessions):
        if attempt:
            delay = min(RECONNECT_WAIT_SECONDS * 2 ** (attempt - 1), 20.0)
            if _monotonic(clock) + delay >= started + budget.max_seconds:
                return report("lease_abstained", "reconnect_deferred")
            sleeper(delay)
        if _monotonic(clock) - started >= budget.max_seconds:
            return report("lease_abstained", "time_budget_exceeded")
        if frames >= budget.max_frames:
            book.mark_disconnected()
            return report("lease_abstained", "frame_budget_exceeded")
        sessions += 1
        book.mark_disconnected()
        try:
            with closing(session_factory()) as session:
                session.send(json.dumps({
                    "op": "subscribe", "req_id": "cia-ticker-1", "args": list(topics),
                }, separators=(",", ":")))
                sends += 1
                acknowledged = False
                preack_session = 0
                last_ping = _monotonic(clock)
                pending_ping: float | None = None
                attempts = 0

                while True:
                    now = _monotonic(clock)
                    remaining = started + budget.max_seconds - now
                    if remaining <= 0:
                        return report("lease_completed" if acknowledged
                                      else "lease_abstained",
                                      None if acknowledged else "no_subscription_ack")
                    if frames >= budget.max_frames:
                        book.mark_disconnected()
                        return report("lease_abstained", "frame_budget_exceeded")
                    if pending_ping is not None and now - pending_ping >= PONG_DEADLINE_SECONDS:
                        raise OSError("heartbeat_timeout")
                    if now - last_ping >= PING_EVERY_SECONDS:
                        session.send('{"op":"ping"}')
                        pings += 1
                        last_ping = now
                        if pending_ping is None:
                            pending_ping = now
                    attempts += 1
                    if attempts > budget.max_frames * 4 + budget.max_seconds:
                        book.mark_disconnected()
                        return report("lease_abstained", "receive_loop_budget_exceeded")
                    try:
                        raw = session.recv(min(RECEIVE_TIMEOUT_SECONDS, remaining))
                    except TimeoutError:
                        continue
                    frames += 1
                    payload = _bounded_json(raw)
                    if _is_public_pong(payload):
                        pongs += 1
                        pending_ping = None
                        continue
                    if payload.get("op") == "subscribe":
                        if acknowledged or not _subscription_ack(payload):
                            raise DataValidationError("ticker_ws_bad_subscription_ack")
                        req_id = payload.get("req_id", "")
                        if req_id not in ("", "cia-ticker-1"):
                            raise DataValidationError("ticker_ws_bad_subscription_ack")
                        book.begin_acknowledged_session()
                        acknowledged = True
                        acks += 1
                        continue
                    if payload.get("op") is not None:
                        raise DataValidationError("ticker_ws_unexpected_control")
                    if (type(payload.get("topic")) is not str
                            or payload["topic"] not in allowed):
                        raise DataGapError("ticker_ws_outside_scope")
                    if not acknowledged:
                        preack += 1
                        preack_session += 1
                        if preack_session > MAX_PREACK_FRAMES:
                            raise DataGapError("ticker_ws_preack_budget_exceeded")
                        continue
                    received = wall_ms()
                    quote = book.ingest(raw, received_at_ms=received)
                    accepted += 1
                    latency = max(0, received - quote.exchange_at_ms)
                    index = (0 if latency <= 100 else 1 if latency <= 1000
                             else 2 if latency <= 5000 else 3)
                    bins[index] += 1
                    if on_quote is not None:
                        on_quote(quote)
        except (DataGapError, DataValidationError, ValueError, TypeError) as error:
            book.mark_disconnected()
            return report("lease_abstained", _safe_failure(error))
        except (OSError, RuntimeError):
            book.mark_disconnected()
            continue
    book.mark_disconnected()
    return report("lease_abstained", "reconnect_budget_exhausted")
