"""J1/OPS27: bounded, read-only causal audit for anomalous Bybit WS closes.

This is *not* an ingestion adapter, a feed authenticator or a service gate
which can authorize writes. Caller supplies already-received frames, receipt
clocks and an independently staged *schema-valid* same-venue research page.
No socket, disk, database, credentials, timer or API client is used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .bybit_closed_stream_cache import HOUR_MS, MAX_UTC_MS
from .bybit_public_ws_once import _validate_one_kline_row
from .bybit_ws_rest_offline_corroboration import (
    corroborate_anomalous_close_offline,
)
from .market_data import DataValidationError

MAX_AUDIT_FRAMES = 64
MAX_FRAME_ROWS = 8
_TOPIC = re.compile(r"kline\.60\.[A-Z0-9]{2,30}USDT\Z")
_BAND_NAMES = (
    "closed_stamp_within_interval",
    "closed_stamp_after_1ms",
    "closed_stamp_after_2_to_1000ms",
    "closed_stamp_after_1001_to_5000ms",
    "closed_stamp_after_over_5000ms",
    "open_stamp_within_interval",
    "open_stamp_after_1ms",
    "open_stamp_after_2_to_1000ms",
    "open_stamp_after_1001_to_5000ms",
    "open_stamp_after_over_5000ms",
)


@dataclass(frozen=True)
class CausalCloseAudit:
    """Aggregates only: no symbol, absolute time, OHLCV, path or raw frame."""

    status: str
    frames_seen: int = 0
    rows_validated: int = 0
    bands: tuple[int, ...] = field(default_factory=lambda: (0,) * 10)
    fields_compared: int = 0
    fields_equal: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "frames_seen": self.frames_seen,
            "rows_validated": self.rows_validated,
            **dict(zip(_BAND_NAMES, self.bands)),
            "fields_compared": self.fields_compared,
            "fields_equal": self.fields_equal,
            "ws_candle_approved": False,
            "canonical_ohlcv_approved": False,
            "source_authenticated": False,
            "historical_reference_authenticated": False,
            "marketwide_top50_verified": False,
            "continuous_collector_authorized": False,
            "live_trading_authorized": False,
            "network_requests": 0,
            "storage_writes": 0,
            "orders_sent": False,
        }


def _band(stamp: int, end: int) -> int:
    """Disjoint, fixed overrun buckets; source timestamps never escape."""
    delta = stamp - end
    if delta <= 0:
        return 0
    if delta == 1:
        return 1
    if delta <= 1_000:
        return 2
    if delta <= 5_000:
        return 3
    return 4


def audit_causal_rollover_offline(
    *, events: tuple[tuple[dict, int], ...], expected_topic: str,
    ack_verified: bool = False, reference=None,
) -> CausalCloseAudit:
    """Audit one topical, post-ACK window without approving ANY candle.

    Only a caller-provided ACK assertion is checked; this function does not
    itself attest the WS subscription. Every row of every frame must validate
    before any same-venue corroboration. A closed candle must belong to the
    most recently completed UTC hour at receipt. A second closed candle,
    including an identical replay, is ambiguous and fails closed.
    """
    def reject(reason: str) -> CausalCloseAudit:
        # Incomplete windows return no partial measurements that could be
        # mistaken for a successfully validated subset.
        return CausalCloseAudit(reason)

    if (ack_verified is not True or type(expected_topic) is not str
            or _TOPIC.fullmatch(expected_topic) is None):
        return reject("causal_gate_ack_or_topic_abstain")
    if (type(events) is not tuple
            or not 1 <= len(events) <= MAX_AUDIT_FRAMES):
        return reject("causal_gate_input_abstain")

    counts = [0] * len(_BAND_NAMES)
    count_rows = 0
    last_receipt = 0
    selected = None
    try:
        for item in events:
            if (type(item) is not tuple or len(item) != 2
                    or type(item[1]) is not int
                    or not 0 < item[1] < MAX_UTC_MS):
                return reject("causal_gate_input_abstain")
            frame, received = item
            if received < last_receipt:
                return reject("causal_gate_clock_abstain")
            last_receipt = received
            if (type(frame) is not dict
                    or set(frame) != {"topic", "type", "ts", "data"}
                    or frame.get("topic") != expected_topic
                    or frame.get("type") != "snapshot"
                    or type(frame.get("ts")) is not int):
                return reject("causal_gate_envelope_abstain")
            server = frame["ts"]
            if (server <= 0 or server > received
                    or received - server > 30_000):
                return reject("causal_gate_clock_abstain")
            rows = frame["data"]
            if (type(rows) is not list
                    or not 1 <= len(rows) <= MAX_FRAME_ROWS
                    or any(type(row) is not dict for row in rows)):
                return reject("causal_gate_envelope_abstain")
            closed_hour = (received // HOUR_MS - 1) * HOUR_MS
            current_hour = closed_hour + HOUR_MS
            for row in rows:
                start = row.get("start")
                end = row.get("end")
                stamp = row.get("timestamp")
                confirmed = row.get("confirm")
                if (any(type(v) is not int for v in (start, end, stamp))
                        or type(confirmed) is not bool):
                    return reject("causal_gate_row_abstain")
                if (stamp < start or stamp > server
                        or start not in (closed_hour, current_hour)):
                    return reject("causal_gate_chronology_abstain")
                try:
                    # Only the trade-stamp interval predicate is bypassed for
                    # diagnosis. All other UTC, Decimal, OHLC, server, receipt
                    # and close predicates remain checked.
                    _validate_one_kline_row(
                        row, server, received,
                        diagnostic_ignore_trade_stamp=True)
                except DataValidationError:
                    return reject("causal_gate_row_abstain")
                if confirmed:
                    if (start != closed_hour or
                            not end + 1 <= received <= end + 120_001
                            or server < end + 1):
                        return reject("causal_gate_chronology_abstain")
                    if selected is not None:
                        return reject("causal_gate_duplicate_close_abstain")
                    selected = (
                        {**frame, "data": [row]}, received, stamp > end
                    )
                counts[(0 if confirmed else 5) + _band(stamp, end)] += 1
                count_rows += 1
    except (TypeError, ValueError, KeyError, OverflowError):
        return reject("causal_gate_row_abstain")

    if selected is None:
        return CausalCloseAudit(
            "causal_gate_no_closed_candle_abstain",
            len(events), count_rows, tuple(counts))
    candidate, received_at, anomalous = selected
    if not anomalous:
        return CausalCloseAudit(
            "causal_gate_strict_stamp_observed_unverified",
            len(events), count_rows, tuple(counts))
    if reference is None:
        return CausalCloseAudit(
            "causal_gate_stamp_overrun_quarantined",
            len(events), count_rows, tuple(counts))

    try:
        corroboration = corroborate_anomalous_close_offline(
            frame=candidate, received_at_ms=received_at,
            reference=reference, diagnostic_early_receipt=True)
    except (DataValidationError, TypeError, ValueError, AttributeError):
        return reject("causal_gate_reference_abstain")
    return CausalCloseAudit(
        "causal_gate_same_venue_match_quarantined"
        if corroboration.fields_equal == 6
        else "causal_gate_same_venue_diverge_abstain",
        len(events), count_rows, tuple(counts),
        corroboration.fields_compared, corroboration.fields_equal)
