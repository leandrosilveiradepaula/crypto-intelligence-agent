"""J1/D317: one bounded owner N50 WS window from immutable D287/D316 files.

No HTTP GET, no built-in socket connector, no systemd, no orders. A caller
must explicitly inject a reviewed socket factory. This is a research lease
orchestrator, NOT a service launcher or a production cutover.
"""
from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Callable, Any

from .bybit_closed_stream_cache import HOUR_MS, SQLiteOfflineClosedStreamJournal
from .bybit_ws_owner_lock import _safe_stat
from .bybit_ws_supervisor import WSRunBudget
from .j1_n50_ws_owner_hour import run_n50_ws_owner_hour_once
from .j1_n50_ws_private_cache import load_n50_ws_dynamic_admission
from .market_data import DataGapError, DataValidationError
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

WS_SQLITE_NAME = "ws-confirmed.sqlite"
# Production halted REST journal root: never use it as a WS output directory.
_HALT_REST_ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")
_MIN_PRE_CLOSE_MS = 10_000
_MAX_PRE_CLOSE_MS = 60_000


def _report(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-ws-cached-owner-window-v1",
        "status": status,
        "failure_category": None,
        "expected_contracts": 50,
        "confirmed_contracts": 0,
        "missing_contracts": 50,
        "utc_closed_hour_end_ms": None,
        "hour_evidence_sha256": None,
        "ranked_scope_sha256": None,
        "ws_metadata_sha256": None,
        "source_provenance": None,
        "private_ws_journal_created": False,
        "closed_events_appended_to_ws_journal": 0,
        "ws_sessions_attempted": 0,
        "frames_seen": 0,
        "preack_frames_discarded": 0,
        "ignored_open_trade_clock": 0,
        "discarded_closed_trade_clock": 0,
        "discarded_closed_preclose": 0,
        "discarded_closed_stale": 0,
        "subscription_acks": 0,
        "owner_lock_acquired": False,
        "rest_gap_reconciliation_required": False,
        "declared_ws_gap_append_enabled": False,
        "http_gets": 0,
        "rest_database_modified": False,
        "systemd_modified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "continuous_collector_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def run_cached_n50_ws_owner_window(
    *, manifest_directory: Path,
    ws_directory: Path,
    session_factory: Callable | None = None,
    allow_private_manifest_read: bool = False,
    allow_private_ws_scope_read: bool = False,
    allow_private_ws_writer: bool = False,
    allow_injected_public_ws: bool = False,
    allow_create_ws_journal: bool = False,
    allow_declared_ws_gap: bool = False,
    allow_temporal_discard: bool = False,
    budget: WSRunBudget = WSRunBudget(max_sessions=2, max_frames=16_000, max_seconds=150),
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Read owner manifest/cache, lock isolated journal, consume one WS close.

    This opt-in API must be started within 10..60 seconds BEFORE the next
    hour boundary. An actual service would call it per hour under a root gate.
    The caller provides all WS transport capability. The cache and current
    manifest must match; REST data cannot be repackaged as WS.
    """
    out = _report("ws_owner_window_optin_required")
    if not all((
        allow_private_manifest_read is True,
        allow_private_ws_scope_read is True,
        allow_private_ws_writer is True,
        allow_injected_public_ws is True,
    )):
        return out
    out["status"] = "ws_owner_window_preflight_abstain"
    if (os.name != "posix" or os.getuid() != os.geteuid()
            or os.geteuid() == 0
            or not isinstance(manifest_directory, Path)
            or not isinstance(ws_directory, Path)
            or not manifest_directory.is_absolute()
            or not ws_directory.is_absolute()
            or ".." in manifest_directory.parts or ".." in ws_directory.parts
            or ws_directory == manifest_directory
            or ws_directory in manifest_directory.parents
            or manifest_directory in ws_directory.parents
            or ws_directory == _HALT_REST_ROOT
            or _HALT_REST_ROOT in ws_directory.parents
            or ws_directory in _HALT_REST_ROOT.parents
            or type(budget) is not WSRunBudget
            or not callable(session_factory)
            or not callable(clock) or not callable(wall_ms)
            or not callable(sleeper)
            or type(allow_create_ws_journal) is not bool
            or type(allow_declared_ws_gap) is not bool
            or type(allow_temporal_discard) is not bool):
        return out
    try:
        # Reject symlinked ancestors as well as direct symlinks: textual
        # path comparisons alone cannot protect the existing REST HALT root.
        if (manifest_directory.resolve(strict=True) != manifest_directory
                or ws_directory.resolve(strict=True) != ws_directory):
            return out
        now = wall_ms()
        if type(now) is not int or now <= 0:
            return out
        next_close = ((now // HOUR_MS) + 1) * HOUR_MS
        remaining = next_close - now
        if not _MIN_PRE_CLOSE_MS <= remaining <= _MAX_PRE_CLOSE_MS:
            return out
        # Both dirs must be private before opening any file or session.
        _safe_stat(manifest_directory, directory=True)
        _safe_stat(ws_directory, directory=True)
        current = load_private_ranked_scope(
            manifest_directory, now_ms=now,
        )
        # Cache was validated on initial save by D314 and is replayed again
        # here. It must match the CURRENT owner manifest digest, not a previous
        # or future epoch with a similar set of 50 ticker strings.
        admission = load_n50_ws_dynamic_admission(
            directory=ws_directory,
            current_at_ms=now,
            expected_ranked_scope_sha256=current["scope_digest_sha256"],
            allow_private_scope_read=True,
        )
        if (admission.status != "private_n50_ws_admission_loaded_revalidated"
                or admission.admission is None
                or admission.ranked_scope != current):
            out["status"] = "ws_owner_window_scope_abstain"
            return out

        journal_path = ws_directory / WS_SQLITE_NAME
        if journal_path.is_symlink():
            return out
        if journal_path.exists():
            _safe_stat(journal_path, directory=False)
            journal = SQLiteOfflineClosedStreamJournal(journal_path)
        else:
            if not allow_create_ws_journal:
                out["status"] = "ws_owner_window_journal_missing"
                return out
            journal = SQLiteOfflineClosedStreamJournal.create(journal_path)
            _safe_stat(journal_path, directory=False)
            out["private_ws_journal_created"] = True
        # D313 accepts receipt no later than 120s after close. Clamp the
        # finite WS lease to <=119s post-close, even when started only 10s
        # before the boundary. Otherwise a healthy 50/50 could become stale
        # solely because the default 150-second budget ran too long.
        max_safe_seconds = (remaining + 119_000) // 1000
        bounded = WSRunBudget(
            max_sessions=budget.max_sessions, max_frames=budget.max_frames,
            max_seconds=min(budget.max_seconds, max_safe_seconds),
        )
        # D315 checks the live wall clock again, obtains the owner POSIX lock
        # BEFORE calling injected session_factory, and independently audits
        # exact 50-of-50 in a read-only SQLite transaction.
        detail = run_n50_ws_owner_hour_once(
            ranked_scope=current, admission=admission.admission,
            journal=journal, decision_at_ms=next_close,
            started_at_ms=now, session_factory=session_factory,
            allow_private_ws_writer=True, allow_injected_public_ws=True,
            budget=bounded, clock=clock, wall_ms=wall_ms, sleeper=sleeper,
            allow_declared_ws_gap=allow_declared_ws_gap,
            allow_temporal_discard=allow_temporal_discard,
        )
        out["status"] = detail["status"]
        out["declared_ws_gap_append_enabled"] = allow_declared_ws_gap
        out["failure_category"] = detail["failure_category"]
        out["confirmed_contracts"] = detail["confirmed_contracts"]
        out["missing_contracts"] = detail["missing_contracts"]
        out["utc_closed_hour_end_ms"] = detail["utc_closed_hour_end_ms"]
        out["hour_evidence_sha256"] = detail["hour_evidence_sha256"]
        out["ranked_scope_sha256"] = detail["ranked_scope_sha256"]
        out["ws_metadata_sha256"] = detail["ws_scope_sha256"]
        out["source_provenance"] = detail["source_provenance"]
        out["closed_events_appended_to_ws_journal"] = detail[
            "closed_events_appended_to_ws_journal"]
        out["ws_sessions_attempted"] = detail["websocket_sessions_attempted"]
        out["frames_seen"] = detail["frames_seen"]
        out["preack_frames_discarded"] = detail["preack_frames_discarded"]
        out["ignored_open_trade_clock"] = detail["ignored_open_trade_clock"]
        out["discarded_closed_trade_clock"] = detail["discarded_closed_trade_clock"]
        out["discarded_closed_preclose"] = detail["discarded_closed_preclose"]
        out["discarded_closed_stale"] = detail["discarded_closed_stale"]
        out["subscription_acks"] = detail["subscriptions_acknowledged"]
        out["owner_lock_acquired"] = detail["owner_lock_acquired"]
        out["rest_gap_reconciliation_required"] = detail[
            "rest_gap_reconciliation_required"]
        return out
    except (OSError, ValueError, TypeError, RuntimeError, DataGapError,
            DataValidationError, OverflowError, KeyError, UnicodeError):
        out["status"] = "ws_owner_window_integrity_abstain"
        return out
