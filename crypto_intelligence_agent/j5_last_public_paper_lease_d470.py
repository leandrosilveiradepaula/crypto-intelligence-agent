"""D470: read the LAST finished public J2/J4 PAPER lease for the J5 Console.

This is a bounded, owner-only summary (D459/D469), not a live exchange
connection, position health, journal certification, current N50 or a signal.
Never returns paths, symbols, raw provider frames, prices or arbitrary errors.
Works with the archived D466 D459 schema and the extended D469 schema.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from .bybit_public_ticker_supervisor_d386 import _FAILURE_CLASSES as _TICKER_CLASSES
from .bybit_ws_supervisor import _SAFE_REJECTION_CLASSES as _KLINE_CLASSES
from .j4_private_paper_ws_operator_d425 import _private_directory, _owner_file
from .market_data import DataValidationError

_FILENAME = "paper-last-public-lease-d459.json"
_BASE = frozenset((
    "schema_version", "observed_at_ms", "primary_result", "primary_status",
    "kline_lease_status", "ticker_lease_status",
    "kline_subscription_acks", "ticker_subscription_acks",
    "accepted_confirmed_close_callbacks", "accepted_public_ticker_callbacks",
    "kline_failure_category", "kline_confirmed_events_appended",
    "kline_postclose_trade_clock_accepted", "kline_temporal_discard_count",
    "historical_rest_validated_closed_candles",
    "paper_contract_public_gets", "paper_contract_rules_unchanged",
    "paper_contract_rule_changes_denied", "real_orders_sent",
    "protected_positions_at_venue",
))
_D469 = frozenset((
    "ticker_failure_category", "ticker_frames_seen",
    "ticker_sessions_attempted", "ticker_reconnects",
    "paper_research_cohort_contracts", "paper_research_cohort_complete",
    "paper_relative_btc_hypotheses", "paper_pending_open_count",
    "paper_cohort_researched_count",
))
_KLINE_STATES = frozenset((
    "not_reported", "ws_budget_ended_research_only", "ws_budget_ended_abstain",
    "ws_fail_closed_abstain", "ws_frame_budget_exhausted_abstain",
    "ws_reconnect_budget_exhausted_abstain",
))
_TICKER_STATES = frozenset((
    "not_reported", "lease_completed", "lease_degraded", "lease_abstained",
    "ticker_fail_closed_abstain", "ticker_reconnect_budget_exhausted_abstain",
))
_KLINE_FAILURES = frozenset(_KLINE_CLASSES.values()) | frozenset((
    "none_or_unknown", "transport_disconnected", "frame_budget_exhausted",
    "reconnection_deferred", "receive_budget",
    "invalid_or_gapped_market_data", "paired_public_stream_stopped",
))
_TICKER_FAILURES = frozenset(_TICKER_CLASSES.values()) | frozenset((
    "none_or_unknown", "reconnect_budget_exhausted", "reconnect_deferred",
    "frame_budget_exceeded", "receive_loop_budget_exceeded",
    "no_subscription_ack", "time_budget_exceeded",
    "paired_public_stream_stopped", "internal_validation_failure",
    "invalid_market_data", "paper_cycle_callback_failed",
    "paper_risk_callback_failed", "paper_execution_callback_failed",
))
_MAX_BYTES = 4096
_MAX_HISTORY_MS = 7 * 86_400_000
_RECENT_MS = 180_000
_COUNT_CAP = 5_000_000


class LastPaperLeaseUnavailable(Exception):
    """No safe historical public lease report is available for localhost."""


def _unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise DataValidationError("D470 duplicate field in owner-only lease")
        value[key] = item
    return value


def _bounded_count(value, *, maximum=_COUNT_CAP):
    if value is not None and (type(value) is not int or not 0 <= value <= maximum):
        raise DataValidationError("D470 malformed local lease counter")
    return value


def read_last_paper_lease(*, directory: Path, now_ms: int) -> dict:
    """Read and strictly project the last completed lease, not a running feed.

    A report may remain historical for up to seven days, but even a fresh
    successful lease never represents current price coverage or a venue stop.
    """
    if (type(now_ms) is not int
            or not 1_600_000_000_000 <= now_ms <= 4_102_444_800_000):
        raise LastPaperLeaseUnavailable("last_public_paper_lease_unavailable")
    try:
        home = _private_directory(directory)
        fd = _owner_file(home, _FILENAME)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_nlink != 1
                    or not 2 <= before.st_size <= _MAX_BYTES):
                raise DataValidationError("D470 unsafe owner diagnostic")
            with os.fdopen(fd, "rb", closefd=False) as source:
                raw = source.read(_MAX_BYTES + 1)
            after = os.fstat(fd)
            current = (home / _FILENAME).lstat()
            if (len(raw) != before.st_size
                    or (before.st_dev, before.st_ino, before.st_size,
                        before.st_mtime_ns) !=
                       (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns)
                    or current.st_dev != before.st_dev
                    or current.st_ino != before.st_ino
                    or not stat.S_ISREG(current.st_mode)
                    or (home / _FILENAME).is_symlink()):
                raise DataValidationError("D470 changed owner diagnostic")
        finally:
            os.close(fd)
        value = json.loads(
            raw.decode("ascii"), object_pairs_hook=_unique_fields,
            parse_float=lambda _: (_ for _ in ()).throw(
                DataValidationError("D470 float not allowed")),
            parse_constant=lambda _: (_ for _ in ()).throw(
                DataValidationError("D470 nonfinite number")),
        )
        if type(value) is not dict or set(value) not in (_BASE, _BASE | _D469):
            raise DataValidationError("D470 unexpected local diagnostic schema")
        v = value
        ts = v["observed_at_ms"]
        if (v["schema_version"] != "d459-operator-public-lease-diagnostic-v1"
                or type(ts) is not int
                or not 1_600_000_000_000 <= ts <= 4_102_444_800_000
                or not -5000 <= now_ms - ts <= _MAX_HISTORY_MS
                or v["primary_result"] not in ("returned", "raised_exception")
                or v["primary_status"] not in (
                    "not_reported", "finite_public_paper_research_closed",
                    "finite_public_paper_research_degraded",
                )
                or v["kline_lease_status"] not in _KLINE_STATES
                or v["ticker_lease_status"] not in _TICKER_STATES
                or v["kline_failure_category"] not in _KLINE_FAILURES
                or v["real_orders_sent"] is not False
                or v["protected_positions_at_venue"] is not False):
            raise DataValidationError("D470 untrusted lease provenance or time")
        if v["primary_result"] == "raised_exception" and (
                v["primary_status"] != "not_reported"
                or v["kline_lease_status"] != "not_reported"
                or v["ticker_lease_status"] != "not_reported"):
            raise DataValidationError("D470 conflicting exception summary")
        if "ticker_failure_category" in v and (
                v["ticker_failure_category"] not in _TICKER_FAILURES):
            raise DataValidationError("D470 unapproved ticker failure code")
        names = (
            "kline_subscription_acks", "ticker_subscription_acks",
            "accepted_confirmed_close_callbacks",
            "accepted_public_ticker_callbacks",
            "kline_confirmed_events_appended",
            "kline_postclose_trade_clock_accepted",
            "kline_temporal_discard_count",
            "historical_rest_validated_closed_candles",
            "paper_contract_public_gets", "paper_contract_rules_unchanged",
            "paper_contract_rule_changes_denied",
        )
        for name in names:
            _bounded_count(v[name])
        for name in _D469 - {"ticker_failure_category",
                             "paper_research_cohort_complete"}:
            if name in v:
                _bounded_count(v[name])
        if "paper_research_cohort_complete" in v and (
                v["paper_research_cohort_complete"] is not None
                and type(v["paper_research_cohort_complete"]) is not bool):
            raise DataValidationError("D470 invalid cohort boolean")
        for name in ("kline_subscription_acks", "ticker_subscription_acks"):
            _bounded_count(v[name], maximum=1)
        _bounded_count(v["historical_rest_validated_closed_candles"], maximum=1200)
        if "paper_research_cohort_contracts" in v:
            _bounded_count(v["paper_research_cohort_contracts"], maximum=50)
        a = v["accepted_confirmed_close_callbacks"]
        b = v["kline_confirmed_events_appended"]
        if (a is not None and b is not None and a > b):
            raise DataValidationError("D470 impossible callback count")
        if (v["primary_status"] == "finite_public_paper_research_closed"
                and (v["kline_lease_status"] != "ws_budget_ended_research_only"
                     or v["ticker_lease_status"] != "lease_completed")):
            raise DataValidationError("D470 false completed dual stream")
        return {
            "schema_version": "j5-last-public-paper-lease-d470-v1",
            "status": v["primary_status"],
            "primary_returned": v["primary_result"] == "returned",
            "sampled_at_ms": now_ms,
            "last_lease_observed_at_ms": ts,
            "last_lease_recent": now_ms - ts <= _RECENT_MS,
            "historical_rest_candles_reported":
                v["historical_rest_validated_closed_candles"],
            "confirmed_ws_closes_reported": b,
            "paper_close_callbacks_reported": a,
            "public_ticker_callbacks_reported":
                v["accepted_public_ticker_callbacks"],
            "kline_lease_status": v["kline_lease_status"],
            "ticker_lease_status": v["ticker_lease_status"],
            "kline_failure_category": v["kline_failure_category"],
            "ticker_failure_category":
                v.get("ticker_failure_category", "none_or_unknown"),
            "paper_research_cohort_complete":
                v.get("paper_research_cohort_complete"),
            "paper_relative_btc_hypotheses":
                v.get("paper_relative_btc_hypotheses"),
            "paper_pending_open_count": v.get("paper_pending_open_count"),
            "paper_cohort_researched_count":
                v.get("paper_cohort_researched_count"),
            "is_historical_lease_report": True,
            "same_hour_ws_cohort_integrity_independently_verified": False,
            "current_ticker_coverage_verified": False,
            "current_kline_coverage_verified": False,
            "native_stop_verified": False,
            "real_fills_verified": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
    except (OSError, DataValidationError, ValueError, TypeError, UnicodeError,
            AttributeError, OverflowError):
        raise LastPaperLeaseUnavailable("last_public_paper_lease_unavailable") from None
