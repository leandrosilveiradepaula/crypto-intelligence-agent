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
from .bybit_public_ws_once import _bounded_json, _subscription_ack
from .market_data import DataValidationError

MAX_BATCH_FRAMES = 4096


@dataclass(frozen=True)
class OfflineWSBatch:
    frames: int
    open_updates: int
    appended: int
    identical_replays: int
    acknowledged: bool

    def sanitized_report(self) -> dict:
        return {
            "status": "offline_ws_batch_completed_not_top50",
            "frames_seen": self.frames,
            "open_updates": self.open_updates,
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
                            require_ack: bool = True) -> OfflineWSBatch:
    """Consume a bounded pre-recorded batch, never making network calls.

    Each item carries its explicit receive timestamp, not process wall time.
    Fail-closed on gaps; already committed rows remain independently auditable.
    """
    if (type(scope) is not OfflineReviewedStreamScope
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(require_ack) is not bool):
        raise DataValidationError("offline WS scope, journal or ACK policy invalid")
    count = opened = appended = replayed = 0
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
        if (payload.get("topic") not in subscribed or type(payload.get("data")) is not list
                or len(payload["data"]) != 1 or type(payload["data"][0]) is not dict):
            raise DataValidationError("offline WS unsubscribed or malformed topic")
        row = payload["data"][0]
        if row.get("confirm") is False:
            # Open events are never persisted. Require the exact known shape
            # and bounded numeric fields without pretending the candle closed.
            from .bybit_closed_stream_cache import _ROW_FIELDS, HOUR_MS
            from .bybit_linear_candle_research import _strict_decimal
            if (set(payload) != {"topic", "type", "ts", "data"}
                    or payload["type"] != "snapshot"
                    or set(row) != _ROW_FIELDS
                    or row["interval"] != "60"
                    or type(payload["ts"]) is not int
                    or any(type(row[key]) is not int for key in ("start", "end", "timestamp"))
                    or row["start"] <= 0 or row["start"] % HOUR_MS
                    or row["end"] != row["start"] + HOUR_MS - 1
                    or not row["start"] <= row["timestamp"] <= row["end"]
                    or payload["ts"] > item[1] or item[1] - payload["ts"] > 30000):
                raise DataValidationError("offline WS open candle envelope invalid")
            values = {key: _strict_decimal(row[key], label=key, may_be_zero=False)
                      for key in ("open", "high", "low", "close")}
            for key in ("volume", "turnover"):
                _strict_decimal(row[key], label=key, may_be_zero=True)
            if (values["high"] < max(values.values())
                    or values["low"] > min(values.values())):
                raise DataValidationError("offline WS open candle OHLC invalid")
            opened += 1
            continue
        event = parse_offline_confirmed_kline(payload, scope=scope,
                                             received_at_ms=item[1])
        outcome = journal.append(event)
        if outcome == "appended":
            appended += 1
        elif outcome == "idempotent":
            replayed += 1
        else:
            raise DataValidationError("offline WS journal outcome invalid")
    if not ack:
        raise DataValidationError("offline WS ACK missing")
    return OfflineWSBatch(count, opened, appended, replayed, ack)
