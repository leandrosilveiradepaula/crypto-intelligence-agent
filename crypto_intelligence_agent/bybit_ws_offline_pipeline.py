"""J1 #330: deterministic, strictly offline WS frames -> existing research journal.

Caller-provided frames only. No socket creation, REST, retry, account or orders.
A replayed complete 24-hour sample never authenticates a marketwide Top50.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .bybit_closed_stream_cache import (
    OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    parse_offline_confirmed_kline,
)
from .bybit_public_ws_once import _bounded_json, _subscription_ack, _is_public_pong
from .market_data import DataValidationError
from .j1_n50_ws_temporal_quarantine import classify_non_evidence_closed_frame

MAX_BATCH_FRAMES = 4096


@dataclass(frozen=True)
class OfflineWSBatch:
    frames: int
    open_updates: int
    appended: int
    identical_replays: int
    acknowledged: bool
    ignored_open_trade_clock: int = 0
    discarded_closed_temporal: tuple[int, int, int] = (0, 0, 0)

    def sanitized_report(self) -> dict:
        return {
            "status": "offline_ws_batch_completed_not_top50",
            "frames_seen": self.frames,
            "open_updates": self.open_updates,
            "ignored_open_trade_clock": self.ignored_open_trade_clock,
            "discarded_closed_trade_clock": self.discarded_closed_temporal[0],
            "discarded_closed_preclose": self.discarded_closed_temporal[1],
            "discarded_closed_stale": self.discarded_closed_temporal[2],
            "closed_events_appended": self.appended,
            "identical_replays": self.identical_replays,
            "subscription_acknowledged": self.acknowledged,
            "network_requests": 0,
            "orders_sent": False,
            "marketwide_top50_verified": False,
            "live_trading_authorized": False,
        }


def ingest_offline_ws_batch(*, frames: Iterable[tuple[str | bytes, int]],
                            scope: OfflineReviewedStreamScope,
                            journal: SQLiteOfflineClosedStreamJournal,
                            require_ack: bool = True,
                            allow_declared_gap: bool = False,
                            allow_temporal_discard: bool = False) -> OfflineWSBatch:
    """Consume a bounded pre-recorded batch, never making network calls.

    Each item carries its explicit receive timestamp, not process wall time.
    Fail-closed on gaps; already committed rows remain independently auditable.
    """
    if (type(scope) is not OfflineReviewedStreamScope
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(require_ack) is not bool
            or type(allow_declared_gap) is not bool
            or type(allow_temporal_discard) is not bool):
        raise DataValidationError("offline WS scope, journal or ACK policy invalid")
    count = opened = appended = replayed = ignored_open = 0
    temporal_discards = [0, 0, 0]
    ack = not require_ack
    subscribed = {"kline.60." + member.symbol for member in scope.contracts}
    for item in frames:
        count += 1
        if count > MAX_BATCH_FRAMES:
            raise DataValidationError("offline WS frame budget exceeded")
        if (type(item) is not tuple or len(item) != 2
                or type(item[1]) is not int or item[1] <= 0):
            raise DataValidationError("offline WS receive clock invalid")
        payload = _bounded_json(item[0])
        if not ack:
            if not _subscription_ack(payload):
                raise DataValidationError("offline WS subscription not acknowledged")
            ack = True
            continue
        if _is_public_pong(payload):
            # Heartbeats are neither market data nor additional ACKs.
            continue
        if (set(payload) != {"topic", "type", "ts", "data"}
                or payload.get("topic") not in subscribed
                or payload.get("type") != "snapshot"
                or type(payload.get("ts")) is not int
                or type(payload.get("data")) is not list):
            raise DataValidationError("offline WS unsubscribed or malformed topic")
        rows = payload["data"]
        if len(rows) > 8 or any(type(row) is not dict for row in rows):
            raise DataValidationError("offline WS batch row count or type invalid")
        if payload["ts"] > item[1] or item[1] - payload["ts"] > 30000:
            raise DataValidationError("offline WS batch server clock invalid")
        # Validate ALL rows before any SQLite write. A frame is indivisible.
        # The established single-candle parser remains the source of truth.
        pending_closed = []
        pending_open = 0
        seen_hours = set()
        for row in rows:
            from .bybit_closed_stream_cache import _ROW_FIELDS, HOUR_MS
            if set(row) != _ROW_FIELDS:
                raise DataValidationError("offline WS batch row fields invalid")
            start_ms = row["start"]
            if type(start_ms) is not int or start_ms in seen_hours:
                raise DataValidationError("offline WS duplicate or malformed hour")
            seen_hours.add(start_ms)
            if row["confirm"] is True:
                if pending_closed:
                    # Multiple closed candles require atomic journal batch support.
                    raise DataValidationError("offline WS multiple closed rows require atomic batch")
                one = dict(payload, data=[row])
                # Never accept a mismatched closed candle. A *validated*
                # envelope with an out-of-window temporal candidate, however,
                # carries NO evidence and must not kill 49 other topics.
                # All such candidates are discarded, NOT written or backfilled.
                reason = (classify_non_evidence_closed_frame(
                    one, scope=scope, received_at_ms=item[1],
                ) if allow_temporal_discard else None)
                if reason is not None:
                    temporal_discards[reason] += 1
                    continue
                pending_closed.append(parse_offline_confirmed_kline(
                    one, scope=scope, received_at_ms=item[1]))
            elif row["confirm"] is False:
                # An open update must be fully checked, but cannot be stored.
                from .bybit_linear_candle_research import _strict_decimal
                if (row["interval"] != "60"
                        or any(type(row[key]) is not int
                               for key in ("start", "end", "timestamp"))
                        or row["start"] <= 0 or row["start"] % HOUR_MS
                        or row["end"] != row["start"] + HOUR_MS - 1):
                    raise DataValidationError("offline WS open candle clock invalid")
                # A non-final update is never evidence: the provider's last
                # matched trade timestamp can lag behind the new candle at an
                # UTC rollover. Drop only this untrusted *open* update, do not
                # abort the owner lease or synthesize a matching candle.
                if not row["start"] <= row["timestamp"] <= row["end"]:
                    ignored_open += 1
                    continue
                values = {key: _strict_decimal(row[key], label=key, may_be_zero=False)
                          for key in ("open", "high", "low", "close")}
                for key in ("volume", "turnover"):
                    _strict_decimal(row[key], label=key, may_be_zero=True)
                if (values["high"] < max(values.values())
                        or values["low"] > min(values.values())):
                    raise DataValidationError("offline WS open candle OHLC invalid")
                pending_open += 1
            else:
                raise DataValidationError("offline WS confirm must be boolean")
        # No partially validated frame reaches the journal.
        if pending_closed:
            outcome = journal.append(pending_closed[0], allow_declared_gap=allow_declared_gap)
            if outcome == "appended":
                appended += 1
            elif outcome == "idempotent":
                replayed += 1
            else:
                raise DataValidationError("offline WS journal outcome invalid")
        opened += pending_open
    if not ack:
        raise DataValidationError("offline WS ACK missing")
    return OfflineWSBatch(count, opened, appended, replayed, ack, ignored_open,
                          tuple(temporal_discards))
