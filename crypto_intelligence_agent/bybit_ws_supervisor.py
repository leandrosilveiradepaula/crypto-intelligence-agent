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


# Exact literals from our own validators only: never echo an exception's
# provider-supplied values, symbols, URLs, paths, or raw frame to journalctl.
_SAFE_REJECTION_CLASSES = {
    "offline WS unsubscribed or malformed topic": "ws_envelope_invalid",
    "offline WS batch row count or type invalid": "ws_row_count_or_type_invalid",
    "offline WS batch server clock invalid": "ws_server_clock_invalid",
    "offline WS batch row fields invalid": "ws_row_fields_invalid",
    "offline WS duplicate or malformed hour": "ws_row_duplicate_hour_invalid",
    "offline WS multiple closed rows require atomic batch": "ws_multiple_closed_rows_invalid",
    "offline WS open candle clock invalid": "ws_open_candle_clock_invalid",
    "offline WS open candle OHLC invalid": "ws_open_candle_ohlc_invalid",
    "offline WS confirm must be boolean": "ws_confirm_flag_invalid",
    "unsupported WS snapshot envelope": "ws_closed_envelope_invalid",
    "WS confirmation, UTC clock or scope chronology invalid": "ws_closed_temporal_invalid",
    "WS values must be exact decimal strings": "ws_closed_value_type_invalid",
    "Bybit latest candle was not confirmed closed": "ws_closed_staging_clock_invalid",
    "offline journal write failed closed": "ws_journal_write_invalid",
    "unexpected WS market topic": "ws_unexpected_topic_invalid",
    "invalid pre-ACK WS envelope": "ws_preack_envelope_invalid",
    "WS temporal discard budget exceeded": "ws_closed_temporal_discard_limit",

    # D331: exact LOCAL validator literals, never raw exception text. The
    # actual 42-row D329 halt is still unknown until a new sanitized run.
    # This taxonomy does NOT change which frames/journal writes are accepted.
    "conflicting replay of closed hour": "ws_journal_closed_replay_conflict",
    "offline kline backfill or registry drift: abstain": "ws_journal_backfill_or_registry_drift",
    "offline kline gap exceeds declared budget: abstain": "ws_journal_gap_limit",
    "offline predecessor was corrupted": "ws_journal_predecessor_corrupt",
    "offline journal row budget exhausted": "ws_journal_row_limit",
    "offline event metadata mismatch": "ws_journal_event_metadata_mismatch",
    "offline journal schema mismatch": "ws_journal_schema_invalid",
    "offline journal schema unreadable": "ws_journal_schema_invalid",
    "offline journal file not present or not regular": "ws_journal_file_invalid",
    "offline candle record digest invalid": "ws_journal_payload_integrity_invalid",
    "offline candle record JSON invalid": "ws_journal_payload_integrity_invalid",
    "offline candle record structure invalid": "ws_journal_payload_integrity_invalid",
    "offline candle record clock invalid": "ws_journal_payload_integrity_invalid",
    "offline candle record temporal tamper": "ws_journal_payload_integrity_invalid",
    "offline candle record decimals invalid": "ws_journal_payload_integrity_invalid",
    "offline candle record price range invalid": "ws_journal_payload_integrity_invalid",
    "only parsed confirmed offline kline may be appended": "ws_journal_event_type_invalid",
    "WS symbol not present in reviewed scan": "ws_scope_member_invalid",
    "offline WS frame too large": "ws_frame_size_invalid",
    "offline WS frame is not bounded JSON": "ws_frame_json_invalid",
    "only 1h Bybit public kline stream is supported": "ws_interval_invalid",
    "unexpected Bybit WS kline fields": "ws_closed_fields_invalid",
    "Bybit kline OHLC extrema are inconsistent": "ws_closed_ohlcv_invalid",
    "Bybit kline row must contain exactly seven strings": "ws_closed_ohlcv_type_invalid",
    "Bybit research page is incomplete or has extra candles": "ws_closed_source_page_invalid",
    "Bybit kline timestamps are not a contiguous descending UTC window": "ws_closed_source_page_invalid",
    "Bybit contract metadata is stale at chart capture": "ws_scope_metadata_stale",
    "Bybit contract observation is absent or from the future": "ws_scope_metadata_invalid",
    "Bybit symbol and quote currency mismatch": "ws_scope_member_invalid",
    "Bybit contract is not a trading linear perpetual": "ws_scope_member_invalid",
    "Bybit chart window must be ascending and UTC grid aligned": "ws_closed_window_invalid",
    "Bybit UTC millisecond timestamp must be decimal string": "ws_closed_window_invalid",
    "Bybit kline category, symbol or list invalid": "ws_closed_source_page_invalid",

    # The real path also receives exact JSON decoder/WS control exceptions.
    "ws_frame_type_invalid": "ws_json_frame_type_invalid",
    "public market JSON must be UTF-8 text or bytes": "ws_json_frame_type_invalid",
    "invalid UTF-8 market JSON": "ws_json_utf8_invalid",
    "market JSON body is empty or oversized": "ws_json_size_invalid",
    "malformed public market JSON": "ws_json_format_invalid",
    "public market JSON root must be an object": "ws_json_format_invalid",
    "duplicate market JSON keys are forbidden": "ws_json_duplicate_keys",
    "nonstandard NaN/Infinity constants are forbidden": "ws_json_numeric_invalid",
    "JSON integer has too many digits": "ws_json_numeric_invalid",
    "JSON fractional number token is too long": "ws_json_numeric_invalid",
    "JSON fractional number is malformed": "ws_json_numeric_invalid",
    "JSON fractional number is not finite": "ws_json_numeric_invalid",
    "JSON fractional number exceeds supported exact JSON numeric bounds": "ws_json_numeric_invalid",
    "offline WS scope, journal or ACK policy invalid": "ws_ingest_contract_invalid",
    "offline WS frame budget exceeded": "ws_frame_budget_exhausted",
    "offline WS receive clock invalid": "ws_receive_clock_invalid",
    "offline WS subscription not acknowledged": "ws_ack_invalid",
    "offline WS ACK missing": "ws_ack_invalid",
    "offline WS journal outcome invalid": "ws_journal_outcome_invalid",
    "WS malformed or extra subscription ACK": "ws_ack_invalid",
    "WS subscribe ACK correlation mismatch": "ws_ack_invalid",
    "WS pre-ACK frame budget exceeded": "ws_preack_frame_limit",
    "WS object envelope required": "ws_envelope_invalid",
    "WS wall clock must be positive UTC ms": "ws_receive_clock_invalid",
    "unexpected WS control frame": "ws_control_frame_unexpected",
}


# Only these six fixed WS -> REST-fixture numeric labels are constructed
# by the existing Bybit validator. No prefix/wildcard from untrusted data.
for _label, _nonnegative in (
    ("openPrice", False), ("highPrice", False), ("lowPrice", False),
    ("closePrice", False), ("base-volume", True),
    ("quote-turnover", True),
    ("open", False), ("high", False), ("low", False),
    ("close", False), ("volume", True), ("turnover", True),
):
    _SAFE_REJECTION_CLASSES[
        f"Bybit {_label} must be bounded exact decimal string"
    ] = ("ws_closed_ohlcv_type_invalid" if _label.endswith("Price")
         or _label in ("base-volume", "quote-turnover") else "ws_open_ohlcv_type_invalid")
    _SAFE_REJECTION_CLASSES[
        f"Bybit {_label} must be {'nonnegative' if _nonnegative else 'positive'}"
    ] = ("ws_closed_ohlcv_invalid" if _label.endswith("Price")
         or _label in ("base-volume", "quote-turnover") else "ws_open_ohlcv_invalid")
del _label, _nonnegative


def _safe_ws_failure_class(error: BaseException) -> str:
    """Whitelist reasons for owner ops; never serialize raw exception text."""
    if isinstance(error, (DataGapError, DataValidationError)):
        return _SAFE_REJECTION_CLASSES.get(
            str(error), "invalid_or_gapped_market_data",
        )
    return "invalid_or_gapped_market_data"

# Bybit's public LINEAR connection supports multiple subscribed topics, with
# an args JSON budget of 21,000 characters. A SINGLE request is intentional:
# the documented linear ACK may omit req_id or return req_id="" even when
# the request supplied one. Multiple sequential requests with empty IDs
# cannot be safely correlated to the requested chunk.
TOPICS_PER_REQUEST = 52
MAX_STREAM_TOPICS = 52
MAX_LINEAR_ARGS_JSON_CHARS = 21_000
MAX_EARLY_FRAMES = 128
MAX_SESSIONS = 4
# The small default pilot budget (4,096 frames) is unchanged. An explicitly
# authorized 52-topic SERVICE lease can see one update per topic per second;
# 52 * 3,590 = 186,680 frames before heartbeat/control overhead.
# Keep a separate hard upper bound instead of ending a 55-minute lease early.
MAX_FRAMES = 200_000
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
    preack_frames_discarded: int = 0
    ignored_open_trade_clock: int = 0
    discarded_closed_temporal: tuple[int, int, int] = (0, 0, 0)
    accepted_postclose_trade_clock: int = 0
    discarded_trade_before_start: int = 0
    discarded_trade_after_end_unbounded: int = 0

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
            "ignored_open_trade_clock": self.ignored_open_trade_clock,
            "discarded_closed_trade_clock": self.discarded_closed_temporal[0],
            "discarded_closed_preclose": self.discarded_closed_temporal[1],
            "discarded_closed_stale": self.discarded_closed_temporal[2],
            "accepted_postclose_trade_clock": self.accepted_postclose_trade_clock,
            "discarded_trade_before_start": self.discarded_trade_before_start,
            "discarded_trade_after_end_unbounded": self.discarded_trade_after_end_unbounded,
            "closed_events_appended": self.closed_events_appended,
            "identical_replays": self.identical_replays,
            "early_frames_buffered": self.early_frames_buffered,
            "preack_frames_discarded": self.preack_frames_discarded,
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
    # No multi-chunk fallback: a request split would reintroduce ambiguous
    # ACK correlation on real Bybit LINEAR connections.
    if (len(topics) > TOPICS_PER_REQUEST
            or len(json.dumps(topics, separators=(",", ":"),
                              ensure_ascii=True)) > MAX_LINEAR_ARGS_JSON_CHARS):
        raise DataValidationError("linear subscribe args exceed bounded single request")
    return (topics,)


def supervise_ws_research(
    *, session_factory: Callable[[], StreamSession],
    scope: OfflineReviewedStreamScope,
    journal: SQLiteOfflineClosedStreamJournal,
    budget: WSRunBudget = WSRunBudget(),
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
    allow_declared_gaps: bool = False,
    allow_temporal_discard: bool = False,
    allow_server_bounded_trade_clock: bool = False,
) -> WSRunReport:
    """Collect confirmed hourly WS events for a finite, *injected* lease.

    A single 1..52-topic subscribe request is sent per socket. Bybit's
    documented LINEAR ACK may have a missing or blank req_id; this is
    unambiguous only for ONE request per connection. Never split into multiple
    chunks while accepting uncorrelated acknowledgements.
    Market frames arriving before the ACK are bounded and discarded;
    no pre-ACK market frame is ever replayed or promoted into the journal.
    Recoverable transport exceptions reconnect at most max_sessions times.
    Corrupt frames, gap, malformed ACK, or stale candle fail CLOSED immediately.
    """
    if (not callable(session_factory) or not callable(clock)
            or not callable(wall_ms) or not callable(sleeper)
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(budget) is not WSRunBudget
            or type(allow_declared_gaps) is not bool
            or type(allow_temporal_discard) is not bool
            or type(allow_server_bounded_trade_clock) is not bool
            or (allow_server_bounded_trade_clock and not allow_temporal_discard)):
        raise DataValidationError("injected WS research capabilities required")
    groups = _topic_batches(scope)
    all_topics = frozenset(topic for batch in groups for topic in batch)
    frames = opened = appended = replayed = preack_discarded = ignored_open = 0
    discarded_closed = [0, 0, 0]
    accepted_postclose = discarded_before = discarded_after = 0
    sessions = complete_sessions = sends = acks = pings = pongs = 0
    started = clock()
    if type(started) not in (int, float) or not math.isfinite(started):
        raise DataValidationError("WS monotonic clock invalid")

    def report(status: str, failure: str | None = None) -> WSRunReport:
        return WSRunReport(status, failure, sessions, complete_sessions,
                           max(0, sessions - 1), sends, acks, frames, opened,
                           appended, replayed, 0, pings, pongs,
                           preack_discarded, ignored_open,
                           tuple(discarded_closed), accepted_postclose,
                           discarded_before, discarded_after)

    for attempt in range(budget.max_sessions):
        if attempt:
            wait = RECONNECT_WAIT_SECONDS * (2 ** (attempt - 1))
            now = clock()
            if now + wait >= started + budget.max_seconds:
                return report("ws_budget_ended_abstain", "reconnection_deferred")
            sleeper(wait)
        if clock() - started >= budget.max_seconds:
            return report("ws_budget_ended_research_only")
        if frames >= budget.max_frames:
            return report("ws_frame_budget_exhausted_abstain", "frame_budget_exhausted")
        sessions += 1
        try:
            with closing(session_factory()) as session:
                pending_index = 0
                acknowledged_topics: set[str] = set()
                preack_session_frames = 0
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
                    nonlocal opened, appended, replayed, ignored_open
                    nonlocal accepted_postclose, discarded_before, discarded_after
                    batch = ingest_offline_ws_batch(
                        frames=((frame, at_ms),), scope=scope,
                        journal=journal, require_ack=False,
                        allow_declared_gap=allow_declared_gaps,
                        allow_temporal_discard=allow_temporal_discard,
                        allow_server_bounded_trade_clock=allow_server_bounded_trade_clock,
                    )
                    opened += batch.open_updates
                    ignored_open += batch.ignored_open_trade_clock
                    accepted_postclose += batch.accepted_postclose_trade_clock
                    discarded_before += batch.discarded_trade_before_start
                    discarded_after += batch.discarded_trade_after_end_unbounded
                    for i, n in enumerate(batch.discarded_closed_temporal):
                        discarded_closed[i] += n
                    # At most three discarded closed candidates per member
                    # in one finite lease. Systemic bad data still trips N2.
                    if sum(discarded_closed) > 3 * len(scope.contracts):
                        raise DataValidationError("WS temporal discard budget exceeded")
                    appended += batch.appended
                    replayed += batch.identical_replays

                subscribe(0)
                while True:
                    now = clock()
                    remaining = started + budget.max_seconds - now
                    if frames >= budget.max_frames:
                        # A frame cap hit BEFORE the lease deadline is a loss
                        # of continuity, never a successful hourly completion.
                        return report("ws_frame_budget_exhausted_abstain",
                                      "frame_budget_exhausted")
                    if remaining <= 0:
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
                        # The documented Bybit LINEAR ACK may omit req_id
                        # or send an empty string, even for an explicit request.
                        # Safe because _topic_batches only returns ONE batch.
                        expected_req = "cia-ws-1"
                        if (len(groups) != 1 or
                                ("req_id" in payload and
                                 payload["req_id"] not in ("", expected_req))):
                            raise DataValidationError("WS subscribe ACK correlation mismatch")
                        acknowledged_topics.update(groups[pending_index])
                        pending_index += 1
                        acks += 1
                        if pending_index < len(groups):
                            subscribe(pending_index)
                        else:
                            complete_sessions += 1
                        continue
                    if payload.get("op") is not None:
                        raise DataValidationError("unexpected WS control frame")
                    if (type(payload.get("topic")) is not str
                            or payload["topic"] not in all_topics):
                        raise DataValidationError("unexpected WS market topic")
                    if pending_index < len(groups):
                        # Provider messages can race their subscribe ACK. A
                        # recognized topic does NOT establish subscription
                        # acknowledgement: discard structurally sane pre-ACK
                        # frames without retaining data, prices, or receipt.
                        if (set(payload) != {"topic", "type", "ts", "data"}
                                or payload.get("type") != "snapshot"
                                or type(payload.get("ts")) is not int
                                or type(payload.get("data")) is not list
                                or not 1 <= len(payload["data"]) <= 8
                                or any(type(row) is not dict
                                       for row in payload["data"])):
                            raise DataValidationError("invalid pre-ACK WS envelope")
                        preack_session_frames += 1
                        preack_discarded += 1
                        if preack_session_frames > MAX_EARLY_FRAMES:
                            raise DataValidationError("WS pre-ACK frame budget exceeded")
                        continue
                    ingest(raw, at_ms)
        except (DataGapError, DataValidationError, ValueError, TypeError) as error:
            return report("ws_fail_closed_abstain", _safe_ws_failure_class(error))
        except (OSError, RuntimeError):
            # No special 10006 recovery: this path only handles WS connection
            # disruption. Missing CLOSED hours remain missing in the journal.
            continue
    return report("ws_reconnect_budget_exhausted_abstain", "transport_disconnected")