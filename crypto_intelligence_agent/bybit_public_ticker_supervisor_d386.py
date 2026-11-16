"""D386: transport-injected Bybit linear ticker WS control plane (NO I/O).

This is a finite, offline-tested protocol supervisor, not a socket launcher.
The caller supplies public socket transport, monotonic polling and PIT universe.
No REST, credentials, account access, J1 journal, disk writes or orders exist.
One subscribe request per socket makes Bybit's empty/missing req_id ACK safe.
"""
from __future__ import annotations

import json
from typing import Optional

from .bybit_public_ticker_state_d385 import (
    BybitPublicTickerBook, BybitTickerQuote, MAX_FRAME_BYTES, _ms,
)
from .bybit_public_ws_once import _subscription_ack, _is_public_pong
from .decimal_json import decode_public_market_json_exact
from .market_data import DataGapError, DataValidationError

ENDPOINT = "wss://stream.bybit.com/v5/public/linear"  # reference only
SUBSCRIBE_BATCH_LIMIT = 50
MAX_SOCKETS = 2
MAX_TOTAL_FRAMES = 200_000
MAX_PENDING = 128
MAX_LAG_SAMPLES = 256
_PING = '{"op":"ping"}'


def _positive_int(value: int, low: int, high: int, reason: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise DataValidationError(reason)
    return value


class BybitPublicTickerSupervisor:
    """Fail-closed control plane for injected PUBLIC-only WS sessions.

    The external runner MUST open one separate socket per requested index,
    send its single subscription command, pass received frames with truthful
    receive timestamps and invoke poll regularly. Nothing here opens sockets.
    Never treat a subscribe ACK as financial or transport provenance proof.
    """

    def __init__(
        self, *, book: BybitPublicTickerBook,
        topics_per_socket: int = 50, max_frames: int = 50_000,
        max_attempts: int = 4, max_preack_frames: int = 32,
        max_pending_frames: int = 128, max_backlog: int = 256,
        ack_timeout_ms: int = 15_000, ping_every_ms: int = 20_000,
        pong_timeout_ms: int = 45_000, idle_timeout_ms: int = 30_000,
        retry_base_ms: int = 1_000,
    ) -> None:
        if type(book) is not BybitPublicTickerBook:
            raise DataValidationError("ticker_supervisor_book_required")
        self.book = book
        self.topics_per_socket = _positive_int(
            topics_per_socket, 1, SUBSCRIBE_BATCH_LIMIT, "ticker_shard_budget_invalid")
        self.max_frames = _positive_int(
            max_frames, 1, MAX_TOTAL_FRAMES, "ticker_frame_budget_invalid")
        self.max_attempts = _positive_int(
            max_attempts, 1, 8, "ticker_retry_budget_invalid")
        self.max_preack_frames = _positive_int(
            max_preack_frames, 1, MAX_PENDING, "ticker_preack_budget_invalid")
        self.max_pending_frames = _positive_int(
            max_pending_frames, 1, MAX_PENDING, "ticker_buffer_budget_invalid")
        self.max_backlog = _positive_int(
            max_backlog, 1, 8192, "ticker_backlog_budget_invalid")
        self.ack_timeout_ms = _positive_int(
            ack_timeout_ms, 100, 60_000, "ticker_ack_timeout_invalid")
        self.ping_every_ms = _positive_int(
            ping_every_ms, 1000, 60_000, "ticker_ping_interval_invalid")
        self.pong_timeout_ms = _positive_int(
            pong_timeout_ms, self.ping_every_ms, 120_000, "ticker_pong_timeout_invalid")
        self.idle_timeout_ms = _positive_int(
            idle_timeout_ms, 1000, 180_000, "ticker_idle_timeout_invalid")
        self.retry_base_ms = _positive_int(
            retry_base_ms, 100, 30_000, "ticker_retry_delay_invalid")
        self.phase = "idle"
        self.attempts = 0
        self.next_retry_at_ms: Optional[int] = None
        self._last_now: Optional[int] = None
        self._opened_at = 0
        self._last_market_at = 0
        self._shards: tuple[tuple[str, ...], ...] = ()
        self._acknowledged: set[int] = set()
        self._pending: list[tuple[int, str | bytes, int]] = []
        self._ping_at: dict[int, int] = {}
        self._last_ping_at: dict[int, int] = {}
        self._seen = 0
        self._accepted = 0
        self._discarded_preack = 0
        self._reconnects = 0
        self._pings = 0
        self._pongs = 0
        self._max_backlog_seen = 0
        self._lag_samples: list[int] = []
        self._last_failure: Optional[str] = None

    def _clock(self, at_ms: int) -> int:
        now = _ms(at_ms, "ticker_supervisor")
        if self._last_now is not None and now < self._last_now:
            self._fail("nonmonotonic_receive_clock", self._last_now)
            raise DataGapError("ticker_supervisor_nonmonotonic_receive_clock")
        self._last_now = now
        return now

    def _fail(self, reason: str, now: int) -> None:
        # Never emit provider-controlled exception strings or frame contents.
        self.book.mark_disconnected()
        self._pending.clear()
        self._acknowledged.clear()
        self._ping_at.clear()
        self._last_failure = reason
        if self.phase not in ("idle", "closed", "backoff", "exhausted"):
            self._reconnects += 1
        if self.attempts >= self.max_attempts:
            self.phase = "exhausted"
            self.next_retry_at_ms = None
        else:
            self.phase = "backoff"
            self.next_retry_at_ms = now + min(
                60_000, self.retry_base_ms * (2 ** max(0, self.attempts - 1)))

    def start_attempt(self, *, at_ms: int) -> tuple[tuple[int, str], ...]:
        """Return JSON subscription commands; the caller opens the sockets."""
        now = self._clock(at_ms)
        if self.phase not in ("idle", "backoff"):
            raise DataGapError("ticker_supervisor_attempt_not_permitted")
        if self.next_retry_at_ms is not None and now < self.next_retry_at_ms:
            raise DataGapError("ticker_supervisor_backoff_active")
        if self.attempts >= self.max_attempts:
            raise DataGapError("ticker_supervisor_retries_exhausted")
        topics = self.book.topics
        shards = tuple(
            tuple(topics[i:i + self.topics_per_socket])
            for i in range(0, len(topics), self.topics_per_socket))
        if not 1 <= len(shards) <= MAX_SOCKETS:
            raise DataValidationError("ticker_supervisor_socket_budget_exceeded")
        self.book.mark_disconnected()
        self.attempts += 1
        self._shards = shards
        self._acknowledged.clear()
        self._pending.clear()
        self._ping_at.clear()
        self._last_ping_at.clear()
        self._opened_at = now
        self._last_market_at = now
        self.phase = "awaiting_ack"
        self.next_retry_at_ms = None
        return tuple(
            (i, json.dumps({"op": "subscribe", "args": list(group)},
                           separators=(",", ":"), ensure_ascii=True))
            for i, group in enumerate(shards))

    def _market(self, index: int, raw: str | bytes, frame: dict,
                at_ms: int) -> BybitTickerQuote:
        if frame.get("topic") not in self._shards[index]:
            raise DataGapError("ticker_supervisor_wrong_socket_topic")
        if self._accepted >= self.max_frames:
            raise DataGapError("ticker_supervisor_frame_budget_exhausted")
        quote = self.book.ingest(raw, received_at_ms=at_ms)
        self._accepted += 1
        lag = max(0, at_ms - quote.exchange_at_ms)
        self._lag_samples.append(lag)
        if len(self._lag_samples) > MAX_LAG_SAMPLES:
            del self._lag_samples[0]
        self._last_market_at = at_ms
        return quote

    def receive(self, index: int, raw: str | bytes, *,
                received_at_ms: int) -> Optional[BybitTickerQuote]:
        """Process one frame on an independently tagged PUBLIC socket."""
        now = self._clock(received_at_ms)
        if self.phase not in ("awaiting_ack", "ready"):
            raise DataGapError("ticker_supervisor_not_connected")
        try:
            if type(index) is not int or not 0 <= index < len(self._shards):
                raise DataValidationError("ticker_supervisor_socket_index_invalid")
            frame = decode_public_market_json_exact(raw, max_bytes=MAX_FRAME_BYTES)
            self._seen += 1
            if self._seen > self.max_frames + self.max_preack_frames + self.max_pending_frames + 1000:
                raise DataGapError("ticker_supervisor_total_frame_budget_exhausted")
            if frame.get("op") == "subscribe":
                if (self.phase != "awaiting_ack" or index in self._acknowledged
                        or not _subscription_ack(frame)
                        or frame.get("req_id", "") != ""):
                    raise DataGapError("ticker_supervisor_subscribe_ack_invalid")
                self._acknowledged.add(index)
                if len(self._acknowledged) == len(self._shards):
                    self.book.begin_acknowledged_session()
                    self.phase = "ready"
                    for shard, pending_raw, received in self._pending:
                        decoded = decode_public_market_json_exact(
                            pending_raw, max_bytes=MAX_FRAME_BYTES)
                        self._market(shard, pending_raw, decoded, received)
                    self._pending.clear()
                return None
            if frame.get("op") is not None:
                if (self.phase != "ready" or index not in self._ping_at
                        or not _is_public_pong(frame)):
                    raise DataGapError("ticker_supervisor_control_frame_invalid")
                del self._ping_at[index]
                self._pongs += 1
                return None
            if index not in self._acknowledged:
                self._discarded_preack += 1
                if self._discarded_preack > self.max_preack_frames:
                    raise DataGapError("ticker_supervisor_preack_overflow")
                return None
            if self.phase == "awaiting_ack":
                if len(self._pending) >= self.max_pending_frames:
                    raise DataGapError("ticker_supervisor_pre_ready_backpressure")
                # Buffer only frames seen AFTER this socket's valid ACK.
                self._pending.append((index, raw, now))
                return None
            return self._market(index, raw, frame, now)
        except (DataGapError, DataValidationError, ValueError, TypeError):
            self._fail("market_or_protocol_invalid", now)
            raise DataGapError("ticker_supervisor_fail_closed") from None

    def poll(self, *, at_ms: int, queued_frames: int = 0) -> tuple[tuple[int, str], ...]:
        """Call on every driver tick; returns PUBLIC ping commands, never orders."""
        now = self._clock(at_ms)
        if type(queued_frames) is not int or queued_frames < 0:
            raise DataValidationError("ticker_supervisor_backlog_metric_invalid")
        self._max_backlog_seen = max(self._max_backlog_seen, queued_frames)
        if self.phase == "awaiting_ack":
            if queued_frames > self.max_backlog:
                self._fail("backpressure", now)
            elif now - self._opened_at > self.ack_timeout_ms:
                self._fail("ack_timeout", now)
            return ()
        if self.phase != "ready":
            return ()
        if queued_frames > self.max_backlog:
            self._fail("backpressure", now)
            return ()
        if now - self._last_market_at > self.idle_timeout_ms:
            self._fail("idle_stale", now)
            return ()
        if any(now - then > self.pong_timeout_ms for then in self._ping_at.values()):
            self._fail("pong_timeout", now)
            return ()
        to_send = []
        for index in range(len(self._shards)):
            if (index not in self._ping_at
                    and now - self._last_ping_at.get(index, self._opened_at) >= self.ping_every_ms):
                self._ping_at[index] = now
                self._last_ping_at[index] = now
                self._pings += 1
                to_send.append((index, _PING))
        return tuple(to_send)

    def transport_lost(self, *, at_ms: int) -> None:
        now = self._clock(at_ms)
        if self.phase in ("ready", "awaiting_ack"):
            self._fail("public_transport_lost", now)

    def rotate(self, *, ranked_symbols: tuple[str, ...],
               position_symbols: tuple[str, ...],
               universe_at_ms: int) -> None:
        """Close all old sockets at the transport layer; new ACK/snapshot required."""
        now = self._clock(universe_at_ms)
        self.book.rotate_membership(
            ranked_symbols=ranked_symbols,
            position_symbols=position_symbols, universe_at_ms=now)
        if self.phase in ("ready", "awaiting_ack"):
            self._fail("universe_rotated", now)

    def close(self) -> None:
        self.book.mark_disconnected()
        self.phase = "closed"
        self.next_retry_at_ms = None
        self._pending.clear()
        self._ping_at.clear()

    def sanitized_report(self, *, at_ms: int) -> dict:
        now = _ms(at_ms, "ticker_supervisor_report")
        lags = sorted(self._lag_samples)
        def pct(q: int) -> Optional[int]:
            return lags[(len(lags) * q + 99) // 100 - 1] if lags else None
        report = self.book.sanitized_report(at_ms=now)
        return {
            "schema_version": "bybit-public-ticker-control-d386-v1",
            "status": self.phase, "failure_category": self._last_failure,
            "connection_attempts": self.attempts,
            "socket_shards": len(self._shards),
            "acknowledged_shards": len(self._acknowledged),
            "received_frames": self._seen, "accepted_frames": self._accepted,
            "preack_dropped": self._discarded_preack,
            "pending_buffered": len(self._pending),
            "max_backlog_seen": self._max_backlog_seen,
            "heartbeat_pings": self._pings, "heartbeat_pongs": self._pongs,
            "reconnects": self._reconnects,
            "ingress_age_p95_ms": pct(95), "ingress_age_p99_ms": pct(99),
            "fresh_quotes": report["fresh_quotes"],
            "monitored_contracts": report["monitored_contracts"],
            "marketwide_top50_verified": False,
            "network_connector_installed": False,
            "order_submission_enabled": False, "orders_sent": False,
            "live_trading_authorized": False,
        }
