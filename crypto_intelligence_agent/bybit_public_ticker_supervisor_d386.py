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
# A burst across 50+ topics can exceed 128 frames before the SUBSCRIBE ACK.
# Drop (never cache, ingest or dispatch) each pre-ACK market frame; use a
# bounded count proportional to the subscribed topics, capped at 4096.
MAX_PREACK_FRAMES = 128
MAX_PREACK_PER_TOPIC = 64
MAX_PREACK_TOTAL = 4096
# Each per-connection pre-ACK payload is quarantined in RAM, never forwarded
# to PAPER or exposed to callers. Only a matching successful ACK permits
# validation/replay of the bounded bootstrap; otherwise it is discarded.
MAX_PREACK_BOOTSTRAP_BYTES = 8 * 1024 * 1024
MAX_SUBSCRIBE_ARG_CHARS = 21_000
PING_EVERY_SECONDS = 20.0
PONG_DEADLINE_SECONDS = 45.0
RECEIVE_TIMEOUT_SECONDS = 5.0
RECONNECT_WAIT_SECONDS = 5.0

# Fixed categories from our own code only, never include provider payloads.
_FAILURE_CLASSES = {
    "ticker_subscription_not_acknowledged": "subscription_not_acknowledged",
    "ticker_ws_preack_budget_exceeded": "preack_limit_reached_before_ack",
    "ticker_ws_bad_subscription_ack": "invalid_subscription_ack",
    "ticker_ws_preack_bootstrap_memory_exceeded": "preack_bootstrap_memory_limit",
    "ticker_envelope_fields_invalid": "bad_envelope",
    "ticker_topic_invalid": "bad_topic",
    "ticker_outside_reviewed_membership": "scope_mismatch",
    "ticker_payload_symbol_invalid": "payload_symbol_mismatch",
    "ticker_retrograde_sequence_or_time": "sequence_regression",
    "ticker_same_sequence_conflicting_payload": "conflicting_replay",
    "ticker_delta_without_snapshot": "snapshot_required",
    "ticker_transport_clock_stale_or_future": "stale_or_future",
    "ticker_future_universe_at_receive": "scope_clock_invalid",
    "ticker_event_type_invalid": "bad_event_type",
    "ticker_cross_sequence_invalid": "bad_cross_sequence",
    "ticker_payload_value_shape_invalid": "invalid_payload_shape",
    "ticker_snapshot_price_fields_missing": "incomplete_snapshot",
    "ticker_funding_rate_invalid": "invalid_funding",
    "ticker_exchange_utc_ms_invalid": "invalid_exchange_time",
    "ticker_received_utc_ms_invalid": "invalid_receipt_time",
    "ticker_crossed_best_bid_ask": "bad_best_quotes",
    "paper_held_quote_silence_exceeded": "held_paper_feed_silent",
    "ticker_universe_rotation_invalid": "scope_clock_invalid",
    "duplicate market JSON keys are forbidden": "duplicate_json_keys",
}


# D473: known gaps in a market STATE can be recovered only after destroying
# all quotes and obtaining a new ACK plus a fresh snapshot on a new socket.
# Invalid prices, malformed frames, unexpected topics, ACKs and consumer
# failures remain fail-closed. Nothing can reuse a pre-fault quote as a fill.
_RESNAPSHOT_GAPS = frozenset((
    "ticker_retrograde_sequence_or_time",
    "ticker_same_sequence_conflicting_payload",
    "ticker_delta_without_snapshot",
    "ticker_transport_clock_stale_or_future",
    "ticker_crossed_best_bid_ask",
))


class _ResnapshotRequired(Exception):
    """A local control signal, never raw provider content."""


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
    preack_frames_bootstrapped_after_ack: int
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
            "preack_frames_bootstrapped_after_ack":
                self.preack_frames_bootstrapped_after_ack,
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


_PAPER_STAGED_FAILURES = {
    "D450 PAPER risk callback failed": "paper_risk_callback_failed",
    "D450 PAPER cycle callback failed": "paper_execution_callback_failed",
}


def _callback_failure(error: Exception) -> str:
    """Keep existing read-only coverage/held-feed contracts intact.

    In a shared WS supervisor callbacks also serve N50 coverage and held
    monitoring: their known DataGap categories must NOT be overwritten with
    an invented financial-consumer label. D449/D452/D463 callbacks are the
    PAPER chain we need to distinguish from a Bybit parser rejection.
    """
    if isinstance(error, (DataGapError, DataValidationError)):
        stage = _PAPER_STAGED_FAILURES.get(str(error))
        if stage is not None:
            return stage
        if str(error).startswith((
            "D449 ", "D452 ", "D463 ", "D447 ", "D448 ",
            "D425 ", "D391 ", "D394 ", "D453 ",
        )):
            return "paper_cycle_callback_failed"
        return _safe_failure(error)
    return "paper_cycle_callback_failed"


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
    on_session_reset: Callable[[], None] | None = None,
    on_acked_poll: Callable[[], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> TickerLeaseReport:
    """Receive real-time ticker data from injected sessions for a finite lease.

    ONE subscribe request per connection. The Bybit linear subscribe ACK may
    omit req_id or return an empty ID; a single request avoids false ACK
    correlation. Bybit has been observed (VPS 2026-11-17) sending initial
    ticker messages BEFORE the matching subscribe ACK (7 frames for BTC and
    263 for N50), then a delta needing the earlier initial snapshot. D414
    quarantines a strictly bounded sequence of pre-ACK packets in RAM.
    ONLY AFTER a matching successful ACK are these validated into the book
    in original causal order, with actual receive timestamps. They are
    NEVER forwarded to on_quote/PAPER, NEVER counted as post-ACK ticker
    callbacks, and are discarded if ACK fails or the connection closes.
    An invalid staged message fails the entire lease closed. Reconnect resets
    both staged state and the book; no prior session seed is carried over.
    Transport errors and a fixed list of recoverable post-ACK sequence/state
    gaps trigger bounded reconnect; malformed payloads/ACKs never do.
    Consumer PAPER failures are separately classified and never disguised as
    a bad Bybit frame, or retried as a new market connection.

    The optional callback is strictly a caller-supplied PAPER/monitoring hook,
    not an order/exchange adapter. It runs synchronously with no buffered queue.
    Optional on_session_reset is called BEFORE every socket attempt, including
    the first. It must reset ephemeral consumer sequence state while retaining
    causal timestamp watermarks. Exceptions abort before any socket is opened.
    D429: opt-in on_acked_poll runs during the receive loop after ACK, also
    after a timeout. It can stop a PAPER-only lease if its HELD contracts have
    fallen silent even while unrelated tickers continue to stream. No source
    data or callbacks escape to an untrusted network.
    """
    if (not callable(session_factory) or not callable(clock)
            or not callable(wall_ms) or not callable(sleeper)
            or type(book) is not BybitPublicTickerBook
            or type(budget) is not TickerLeaseBudget
            or (on_quote is not None and not callable(on_quote))
            or (on_session_reset is not None and not callable(on_session_reset))
            or (on_acked_poll is not None and not callable(on_acked_poll))
            or (stop_requested is not None and not callable(stop_requested))):
        raise DataValidationError("ticker_ws_injected_dependencies_invalid")
    topics = _topic_args(book)
    allowed = frozenset(topics)
    preack_limit = min(
        MAX_PREACK_TOTAL, max(MAX_PREACK_FRAMES, len(allowed) * MAX_PREACK_PER_TOPIC),
    )
    sessions = sends = acks = frames = accepted = preack = pings = pongs = 0
    bootstrap_validated = 0
    last_resync_category: str | None = None
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
            preack_frames_discarded=preack,
            preack_frames_bootstrapped_after_ack=bootstrap_validated,
            pong_frames=pongs,
            ping_frames=pings, last_fresh_quote_count=freshness,
            latency_0_to_100ms=bins[0],
            latency_101_to_1000ms=bins[1],
            latency_1001_to_5000ms=bins[2],
            latency_over_5000ms=bins[3],
        )

    for attempt in range(budget.max_sessions):
        if stop_requested is not None and stop_requested():
            book.mark_disconnected()
            return report("lease_abstained", "paired_public_stream_stopped")
        if attempt:
            delay = min(RECONNECT_WAIT_SECONDS * 2 ** (attempt - 1), 20.0)
            if _monotonic(clock) + delay >= started + budget.max_seconds:
                return report("lease_abstained",
                              last_resync_category or "reconnect_deferred")
            sleeper(delay)
            if stop_requested is not None and stop_requested():
                book.mark_disconnected()
                return report("lease_abstained", "paired_public_stream_stopped")
        if _monotonic(clock) - started >= budget.max_seconds:
            return report("lease_abstained", "time_budget_exceeded")
        if frames >= budget.max_frames:
            book.mark_disconnected()
            return report("lease_abstained", "frame_budget_exceeded")
        book.mark_disconnected()
        # Session-scoped cross-sequence numbers may restart on reconnect.
        # Reject a failed reset before constructing any new transport.
        if on_session_reset is not None:
            on_session_reset()
        sessions += 1
        try:
            with closing(session_factory()) as session:
                session.send(json.dumps({
                    "op": "subscribe", "req_id": "cia-ticker-1", "args": list(topics),
                }, separators=(",", ":")))
                sends += 1
                acknowledged = False
                preack_session = 0
                preack_staged: list[tuple[str | bytes, int]] = []
                preack_staged_bytes = 0
                last_ping = _monotonic(clock)
                pending_ping: float | None = None
                attempts = 0

                while True:
                    if stop_requested is not None and stop_requested():
                        book.mark_disconnected()
                        return report("lease_abstained", "paired_public_stream_stopped")
                    now = _monotonic(clock)
                    remaining = started + budget.max_seconds - now
                    if acknowledged and on_acked_poll is not None:
                        # This is a PAPER consumer gate, NOT a Bybit parser.
                        # Do not mislabel an internal callback failure as
                        # invalid_market_data or silently retry it.
                        try:
                            on_acked_poll()
                        except Exception as error:
                            book.mark_disconnected()
                            return report("lease_abstained",
                                          _callback_failure(error))
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
                        # The server has now explicitly acknowledged this
                        # exact subscription. Validate all quarantined ticker
                        # frames, in receive order, to reconstruct snapshot
                        # state for subsequent post-ACK deltas. Do not emit
                        # callback/decisions for any pre-ACK frame.
                        # ACK validity is independent of any subsequent
                        # bootstrap error. Report it even if replay fails.
                        acknowledged = True
                        acks += 1
                        for staged_raw, staged_at_ms in preack_staged:
                            book.ingest(staged_raw, received_at_ms=staged_at_ms)
                        # Count as bootstrapped only when the entire set is
                        # valid. On any error the book is invalidated and
                        # no partial state can reach the caller.
                        bootstrap_validated += len(preack_staged)
                        preack_staged.clear()
                        preack_staged_bytes = 0
                        continue
                    if payload.get("op") is not None:
                        raise DataValidationError("ticker_ws_unexpected_control")
                    if (type(payload.get("topic")) is not str
                            or payload["topic"] not in allowed):
                        raise DataGapError("ticker_ws_outside_scope")
                    if not acknowledged:
                        preack += 1
                        preack_session += 1
                        if preack_session > preack_limit:
                            raise DataGapError("ticker_ws_preack_budget_exceeded")
                        # Bound both the count and bytes independently. The
                        # payload parser already enforces per-frame size and
                        # exact JSON. Nothing escapes this session before ACK.
                        packet_bytes = (len(raw) if type(raw) is bytes
                                        else len(raw.encode("utf-8")))
                        if (preack_staged_bytes + packet_bytes >
                                MAX_PREACK_BOOTSTRAP_BYTES):
                            raise DataGapError(
                                "ticker_ws_preack_bootstrap_memory_exceeded")
                        preack_staged.append((raw, wall_ms()))
                        preack_staged_bytes += packet_bytes
                        continue
                    received = wall_ms()
                    try:
                        quote = book.ingest(raw, received_at_ms=received)
                    except DataGapError as error:
                        # Only AFTER ACK, with a fresh new socket available.
                        # The book has already erased every quote on failure.
                        # Pre-ACK staged frames and malformed JSON are NEVER
                        # eligible for this recovery.
                        if (str(error) in _RESNAPSHOT_GAPS
                                and attempt + 1 < budget.max_sessions):
                            raise _ResnapshotRequired(
                                _safe_failure(error)) from None
                        raise
                    accepted += 1
                    latency = max(0, received - quote.exchange_at_ms)
                    index = (0 if latency <= 100 else 1 if latency <= 1000
                             else 2 if latency <= 5000 else 3)
                    bins[index] += 1
                    if on_quote is not None:
                        try:
                            on_quote(quote)
                        except Exception as error:
                            book.mark_disconnected()
                            return report("lease_abstained",
                                          _callback_failure(error))
        except _ResnapshotRequired as error:
            # This session has lost causal continuity. No old data crosses
            # into another ACKed connection or the next PAPER fill.
            last_resync_category = str(error)
            book.mark_disconnected()
            continue
        except (DataGapError, DataValidationError, ValueError, TypeError) as error:
            book.mark_disconnected()
            return report("lease_abstained", _safe_failure(error))
        except (OSError, RuntimeError):
            book.mark_disconnected()
            continue
    book.mark_disconnected()
    return report("lease_abstained", "reconnect_budget_exhausted")
