"""D315: owner-locked dynamic N50 WebSocket -> SQLite -> exact-hour evidence.

This composes D287/D314/D313 with the existing WS supervisor and POSIX
writer lock. It never creates a socket, fetches REST, touches the halted N50
REST SQLite or installs a service: a separately gated owner supplies the
session factory and an already isolated WS journal.
"""
from __future__ import annotations

import os
import re
import time
from typing import Callable

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    _scope_contract_fingerprint,
)
from .bybit_ws_owner_lock import exclusive_owner_ws_writer
from .bybit_ws_supervisor import WSRunBudget, _topic_batches, supervise_ws_research
from .j1_auto_research_epoch import validate_ranked_research_scope
from .j1_n50_ws_dynamic_scope import DynamicN50WSAdmission
from .j1_n50_ws_hourly_attestation import attest_n50_ws_hour_once
from .market_data import DataGapError, DataValidationError

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _result(status: str) -> dict:
    """Only count/digest diagnostics; never symbols, prices or raw WS frames."""
    return {
        "schema_version": "j1-n50-ws-owner-hour-lease-v1",
        "status": status,
        "failure_category": None,
        "expected_contracts": 50,
        "confirmed_contracts": 0,
        "missing_contracts": 50,
        "utc_closed_hour_end_ms": None,
        "hour_evidence_sha256": None,
        "source_provenance": None,
        "ranked_scope_sha256": None,
        "ws_scope_sha256": None,
        "owner_lock_acquired": False,
        "subscriptions_acknowledged": 0,
        "websocket_sessions_attempted": 0,
        "frames_seen": 0,
        "closed_events_appended_to_ws_journal": 0,
        "identical_replays": 0,
        "preack_frames_discarded": 0,
        "ignored_open_trade_clock": 0,
        "discarded_closed_trade_clock": 0,
        "discarded_closed_preclose": 0,
        "discarded_closed_stale": 0,
        "accepted_postclose_trade_clock": 0,
        "discarded_trade_before_start": 0,
        "discarded_trade_after_end_unbounded": 0,
        "rest_gap_reconciliation_required": False,
        "http_gets": 0,
        "rest_database_modified": False,
        "published_rest_pit": False,
        "systemd_modified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def run_n50_ws_owner_hour_once(
    *, ranked_scope: dict, admission: DynamicN50WSAdmission,
    journal: SQLiteOfflineClosedStreamJournal,
    decision_at_ms: int, started_at_ms: int,
    session_factory: Callable | None = None,
    allow_private_ws_writer: bool = False,
    allow_injected_public_ws: bool = False,
    allow_declared_ws_gap: bool = False,
    allow_temporal_discard: bool = False,
    allow_server_bounded_trade_clock: bool = False,
    budget: WSRunBudget = WSRunBudget(max_sessions=1, max_frames=4096, max_seconds=60),
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """One bounded, explicit owner WS lease, never a 24/7 or marketwide claim.

    The admission must precede the observed hour and bind exactly the D287
    members. The caller owns the isolated 0700/0600 journal and socket gate.
    Only a clean, fully ACKed, budget-ended lease may obtain a D313 50/50
    evidence digest. Incomplete hours require separately gated REST *planning*,
    not an automatic GET or source substitution.
    """
    out = _result("owner_optin_required")
    if allow_private_ws_writer is not True or allow_injected_public_ws is not True:
        return out
    out["status"] = "ws_owner_preflight_abstain"
    if (os.name != "posix" or os.geteuid() == 0
            or os.getuid() != os.geteuid()
            or type(ranked_scope) is not dict
            or type(admission) is not DynamicN50WSAdmission
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(budget) is not WSRunBudget
            or type(allow_declared_ws_gap) is not bool
            or type(allow_temporal_discard) is not bool
            or type(allow_server_bounded_trade_clock) is not bool
            or (allow_server_bounded_trade_clock and not allow_temporal_discard)
            or not callable(session_factory)
            or not callable(clock) or not callable(wall_ms)
            or not callable(sleeper)
            or type(decision_at_ms) is not int
            or decision_at_ms <= HOUR_MS
            or decision_at_ms % HOUR_MS
            or type(started_at_ms) is not int
            or not decision_at_ms - HOUR_MS <= started_at_ms < decision_at_ms):
        return out
    phase = "preflight"
    try:
        # Do not trust a caller-supplied preclose start time without checking
        # the real/injected UTC clock before opening any socket or journal.
        observed_start = wall_ms()
        if (type(observed_start) is not int
                or abs(observed_start - started_at_ms) > 5000):
            return out
        members, ranked_sha = validate_ranked_research_scope(
            ranked_scope, now_ms=started_at_ms, max_assets=50,
        )
        scope = admission.ws_scope
        if (type(scope) is not OfflineReviewedStreamScope
                or admission.selected_contracts != 50
                or len(scope.contracts) != 50
                or admission.observed_at_ms != scope.observed_at_ms
                or admission.observed_at_ms > started_at_ms
                or admission.observed_at_ms >= decision_at_ms
                or ranked_scope["catalog_post_observed_at_ms"] >= decision_at_ms
                or admission.ranked_scope_sha256 != ranked_sha
                or type(admission.metadata_sha256) is not str
                or _DIGEST.fullmatch(admission.metadata_sha256) is None
                or admission.metadata_sha256 != scope.registry_sha256
                or {m.symbol for m in scope.contracts} != set(members)):
            return out
        _scope_contract_fingerprint(scope)
        topics = _topic_batches(scope)
        if len(topics) != 1 or len(topics[0]) != 50:
            return out

        # Check DAC, inode and one nonblocking flock BEFORE any WS factory call.
        phase = "owner_lock_or_lease"
        with exclusive_owner_ws_writer(
            journal=journal, allow_private_ws_writer=True,
        ):
            out["owner_lock_acquired"] = True
            out["ranked_scope_sha256"] = ranked_sha
            out["ws_scope_sha256"] = scope.registry_sha256
            run = supervise_ws_research(
                session_factory=session_factory, scope=scope, journal=journal,
                budget=budget, clock=clock, wall_ms=wall_ms, sleeper=sleeper,
                allow_declared_gaps=allow_declared_ws_gap,
                allow_temporal_discard=allow_temporal_discard,
                allow_server_bounded_trade_clock=allow_server_bounded_trade_clock,
            )
            out["websocket_sessions_attempted"] = run.sessions_attempted
            out["subscriptions_acknowledged"] = run.subscriptions_acknowledged
            out["frames_seen"] = run.frames_seen
            out["closed_events_appended_to_ws_journal"] = run.closed_events_appended
            out["identical_replays"] = run.identical_replays
            out["preack_frames_discarded"] = run.preack_frames_discarded
            out["ignored_open_trade_clock"] = run.ignored_open_trade_clock
            out["discarded_closed_trade_clock"] = run.discarded_closed_temporal[0]
            out["discarded_closed_preclose"] = run.discarded_closed_temporal[1]
            out["discarded_closed_stale"] = run.discarded_closed_temporal[2]
            out["accepted_postclose_trade_clock"] = run.accepted_postclose_trade_clock
            out["discarded_trade_before_start"] = run.discarded_trade_before_start
            out["discarded_trade_after_end_unbounded"] = run.discarded_trade_after_end_unbounded

            # A frame-cap or failed ACK may have saved partial legitimate rows,
            # but it cannot be promoted as a healthy complete hour.
            if (run.status != "ws_budget_ended_research_only"
                    or run.sessions_fully_acknowledged < 1
                    or run.subscriptions_acknowledged < 1):
                out["status"] = "ws_owner_lease_degraded_abstain"
                out["failure_category"] = run.failure_category
                return out
            observed = wall_ms()
            if type(observed) is not int:
                return out
            evidence = attest_n50_ws_hour_once(
                ranked_scope=ranked_scope, ws_scope=scope, journal=journal,
                decision_at_ms=decision_at_ms, observed_at_ms=observed,
            )
            out["confirmed_contracts"] = evidence["confirmed_contracts"]
            out["missing_contracts"] = evidence["missing_contracts"]
            out["utc_closed_hour_end_ms"] = evidence["utc_closed_hour_end_ms"]
            if evidence["status"] == "ws_hour_50_observed_local_only_not_marketwide":
                out["status"] = "ws_owner_hour_50_observed_local_only"
                out["hour_evidence_sha256"] = evidence["evidence_sha256"]
                out["source_provenance"] = "bybit_public_ws_confirmed"
            elif evidence["status"] == "ws_closed_hour_incomplete_no_pit":
                out["status"] = "ws_owner_hour_incomplete_no_pit"
                out["rest_gap_reconciliation_required"] = True
            else:
                out["status"] = "ws_owner_hour_audit_abstain"
            return out
    except (DataGapError, DataValidationError, OSError, RuntimeError, ValueError,
            TypeError, OverflowError, KeyError, UnicodeError):
        # The owner-only SQLite may hold independently auditable partial rows.
        # Never delete, retry the venue, silently change epoch or leak paths.
        out["status"] = ("ws_owner_preflight_abstain" if phase == "preflight"
                         else "ws_owner_integrity_or_lock_abstain")
        return out
