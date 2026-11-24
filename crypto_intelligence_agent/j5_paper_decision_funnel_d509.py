"""D509: read-only decision funnel from the ACTUAL bounded PAPER lease.

The owner-only D459 receipt already exists after the lease. This module
projects only counters and fixed status classes; it never reads a Bybit account,
creates signals, places an order, or treats historical REST as WebSocket.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from .j4_private_paper_ws_operator_d425 import _private_directory, _owner_file
from .market_data import DataValidationError

_FILE = "paper-last-public-lease-d459.json"
_SCHEMA = "d459-operator-public-lease-diagnostic-v1"
_MAX_BYTES = 8192
_MAX_CLOCK_MS = 4_102_444_800_000
_MAX_AGE_MS = 24 * 60 * 60 * 1000
SAFE_PAPER_EVENT_COUNTS = frozenset((
    "confirmed_close_observed",
    "cohort_researched",
    "paper_open_pending_armed",
    "paper_position_created",
    "paper_open_expired_cancelled",
    "public_contract_refresh_pending",
    "configured_margin_does_not_fit_contract_lot",
    "paper_entry_replay_or_validation_blocked",
    "held_exit_quote_processed",
    "held_quote_noncausal_abstained",
))
_COUNT_FIELDS = frozenset((
    "kline_subscription_acks", "ticker_subscription_acks",
    "accepted_confirmed_close_callbacks", "accepted_public_ticker_callbacks",
    "ticker_frames_seen", "ticker_sessions_attempted", "ticker_reconnects",
    "paper_research_cohort_contracts", "paper_relative_btc_hypotheses",
    "paper_pending_open_count", "paper_cohort_researched_count",
    "kline_confirmed_events_appended", "kline_postclose_trade_clock_accepted",
    "kline_temporal_discard_count", "historical_rest_validated_closed_candles",
    "paper_contract_public_gets", "paper_contract_rules_unchanged",
    "paper_contract_rule_changes_denied",
))


class PaperDecisionUnavailable(Exception):
    """The private latest-lease receipt cannot be trusted or read."""


def _unique(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise DataValidationError("D509 duplicate lease report key")
        obj[k] = v
    return obj


def _reject_number(_):
    raise DataValidationError("D509 noninteger JSON number")


def read_paper_decision_funnel(*, directory: Path, now_ms: int) -> dict:
    """Summarize the last *completed* public lease, never current WS health."""
    try:
        if (type(now_ms) is not int
                or not 1_600_000_000_000 <= now_ms <= _MAX_CLOCK_MS):
            raise DataValidationError("D509 invalid observation time")
        home = _private_directory(directory)
        fd = _owner_file(home, _FILE)
        try:
            before = os.fstat(fd)
            if not 2 <= before.st_size <= _MAX_BYTES:
                raise DataValidationError("D509 lease size outside bound")
            raw = os.read(fd, _MAX_BYTES + 1)
            after = os.fstat(fd)
            path = home / _FILE
            current = path.lstat()
            if (len(raw) != before.st_size or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                    or (before.st_dev, before.st_ino) !=
                       (after.st_dev, after.st_ino)
                    or (current.st_dev, current.st_ino) !=
                       (before.st_dev, before.st_ino)
                    or not stat.S_ISREG(current.st_mode)
                    or path.is_symlink()):
                raise DataValidationError("D509 lease changed during read")
        finally:
            os.close(fd)
        value = json.loads(
            raw.decode("ascii"), object_pairs_hook=_unique,
            parse_float=_reject_number, parse_constant=_reject_number,
        )
        if (type(value) is not dict or value.get("schema_version") != _SCHEMA
                or value.get("primary_result") not in (
                    "returned", "raised_exception")
                or value.get("primary_status") not in (
                    "finite_public_paper_research_closed",
                    "finite_public_paper_research_degraded", "not_reported")
                or value.get("real_orders_sent") is not False
                or value.get("protected_positions_at_venue") is not False
                or type(value.get("observed_at_ms")) is not int):
            raise DataValidationError("D509 unexpected private lease schema")
        timestamp = value["observed_at_ms"]
        age = now_ms - timestamp
        if (not 1_600_000_000_000 <= timestamp <= _MAX_CLOCK_MS
                or age < -5000):
            raise DataValidationError("D509 impossible lease clock")

        counts = {}
        for key in _COUNT_FIELDS:
            number = value.get(key)
            if number is not None and (
                type(number) is not int or not 0 <= number <= 5_000_000
            ):
                raise DataValidationError("D509 unsafe funnel counter")
            counts[key] = number
        ready = value.get("paper_research_cohort_complete")
        if ready is not None and type(ready) is not bool:
            raise DataValidationError("D509 nonboolean complete cohort")
        raw_events = value.get("paper_event_counts", {})
        if (type(raw_events) is not dict or
                set(raw_events) - SAFE_PAPER_EVENT_COUNTS or
                any(type(v) is not int or not 0 <= v <= 5_000_000
                    for v in raw_events.values())):
            raise DataValidationError("D509 untrusted PAPER events")
        events = {name: raw_events.get(name) for name in
                  sorted(SAFE_PAPER_EVENT_COUNTS)}
        # D459 is the latest completed lease only. 'now' always comes
        # from the separate D456 heartbeat and never from this receipt.
        if age > _MAX_AGE_MS:
            state = "last_lease_stale"
        elif value["primary_result"] == "raised_exception":
            state = "last_lease_abstained"
        elif ready is not True:
            state = "confirmed_n50_cohort_not_proven"
        elif not counts["paper_cohort_researched_count"]:
            state = "confirmed_cohort_not_yet_researched"
        elif not counts["paper_relative_btc_hypotheses"]:
            state = "no_eligible_hypothesis_after_btc_filters"
        elif events["paper_position_created"]:
            state = "paper_position_recorded_in_lease"
        elif events["paper_open_pending_armed"]:
            state = "paper_open_pending_in_lease"
        else:
            state = "candidates_without_paper_fill"
        return {
            "schema_version": "d509-paper-decision-funnel-v1",
            "status": state,
            "last_lease_at_ms": timestamp,
            "sampled_at_ms": now_ms,
            "last_lease_age_ms": age,
            "primary_result": value["primary_result"],
            "research_cohort_complete": ready,
            "counters": dict(sorted(counts.items())),
            "paper_event_counts": events,
            "source": "previous_completed_public_lease_only",
            "websocket_live_health_verified": False,
            "exchange_orders_verified": False,
            "orders_sent": False,
        }
    except (OSError, DataValidationError, ValueError, UnicodeError,
            TypeError, OverflowError, AttributeError):
        raise PaperDecisionUnavailable(
            "paper_decision_funnel_not_available"
        ) from None
