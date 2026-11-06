"""OPS1: owner-only read-only observation of the existing WS research journal.

A valid local 24h research window is NOT an authenticated feed, a running
collector, a marketwide Top50, or an authorization to trade. Reuse the existing
PIT scope-chain validator and SQLite journal audit; never create/repair files.
"""
from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from .bybit_closed_stream_cache import HOUR_MS, SQLiteOfflineClosedStreamJournal
from .bybit_ws_owner_lock import _safe_stat
from .bybit_ws_owner_pilot import _read_epoch_chain, _audit_epoch_chain, MAX_PILOT_SCOPE_AGE_MS
from .market_data import DataGapError, DataValidationError

MAX_UTC_MS = 4_102_444_800_000
MAX_OBSERVATION_DELAY_MS = 60_000
_STATUS = frozenset({
    "owner_gate_required", "owner_directory_unavailable",
    "scope_missing_or_invalid", "scope_not_yet_known",
    "scope_stale", "journal_missing_or_invalid",
    "journal_audit_abstain", "reviewed_ws_sample_incomplete",
    "reviewed_ws_sample_complete_unverified",
})


def _base(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1_ws_owner_readonly_v1",
        "status": status,
        "reviewed_scope_members": 0,
        "scope_epochs": 0,
        "scope_age_ms": None,
        "persisted_rows": 0,
        "complete_24h_members": 0,
        "missing_24h_members": 0,
        "rank_digest_sha256": None,
        "journal_digest_sha256": None,
        "declared_gap_markers": 0,
        "network_requests_by_observer": 0,
        "database_mutation_statements": 0,
        "worker_running_verified": False,
        "marketwide_top50_verified": False,
        "source_authenticated": False,
        "canonical_ohlcv_approved": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def audit_owner_ws_journal(*, directory: str | Path,
    decision_at_ms: int, observed_at_ms: int,
    allow_private_readonly_audit: bool = False,
) -> dict[str, Any]:
    """Audit a finished UTC hour with one existing private journal/scope chain.

    No retry, sleep, HTTP, websocket, local file creation or writer lock. The
    journal audit itself verifies every stored event, including digests, OHLC,
    timestamp and PIT membership, in a single read-only SQLite transaction.
    """
    if allow_private_readonly_audit is not True:
        return _base("owner_gate_required")
    if (os.name != "posix" or not hasattr(os, "getuid") or
            os.geteuid() == 0 or os.getuid() != os.geteuid()):
        return _base("owner_gate_required")
    if (type(decision_at_ms) is not int or
            not 25 * HOUR_MS <= decision_at_ms < MAX_UTC_MS or
            decision_at_ms % HOUR_MS or type(observed_at_ms) is not int or
            not decision_at_ms + 1000 <= observed_at_ms <=
                decision_at_ms + MAX_OBSERVATION_DELAY_MS):
        return _base("owner_gate_required")
    try:
        parent = Path(directory)
        if not parent.is_absolute():
            return _base("owner_directory_unavailable")
        _safe_stat(parent, directory=True)
    except (OSError, DataValidationError, ValueError, TypeError):
        return _base("owner_directory_unavailable")

    try:
        epochs = _read_epoch_chain(parent, now_ms=observed_at_ms)
    except (OSError, DataGapError, DataValidationError, ValueError, TypeError):
        return _base("scope_missing_or_invalid")
    # The caller may supply any decision within the available history, but
    # future registry reviews must not be backdated to authorize old candles.
    visible = tuple(s for s in epochs if s.observed_at_ms <= decision_at_ms)
    if not visible:
        return _base("scope_not_yet_known")
    scope = visible[-1]
    if observed_at_ms - scope.observed_at_ms > MAX_PILOT_SCOPE_AGE_MS:
        return _base("scope_stale")

    path = parent / "ws-confirmed.sqlite"
    try:
        _safe_stat(path, directory=False)
    except (OSError, DataValidationError):
        return _base("journal_missing_or_invalid")
    try:
        audit = _audit_epoch_chain(
            journal=SQLiteOfflineClosedStreamJournal(path),
            epochs=visible, decision=decision_at_ms, now=observed_at_ms,
        )
        n = len(scope.contracts)
        if (audit.missing_24h_symbols + audit.complete_24h_symbols != n
                or audit.persisted_rows < 0):
            return _base("journal_audit_abstain")
        complete = (
            audit.status == "offline_reviewed_24h_complete_not_top50"
            and audit.missing_24h_symbols == 0
            and audit.complete_24h_symbols == n
            and audit.rank_digest_sha256 is not None
        )
        status = ("reviewed_ws_sample_complete_unverified" if complete
                  else "reviewed_ws_sample_incomplete")
        report = _base(status)
        report.update({
            "reviewed_scope_members": n,
            "scope_epochs": len(visible),
            "scope_age_ms": observed_at_ms - scope.observed_at_ms,
            "persisted_rows": audit.persisted_rows,
            "complete_24h_members": audit.complete_24h_symbols,
            "missing_24h_members": audit.missing_24h_symbols,
            "rank_digest_sha256": audit.rank_digest_sha256 if complete else None,
            "journal_digest_sha256": audit.journal_digest_sha256,
            "declared_gap_markers": audit.declared_gap_markers,
        })
        return report
    except (DataGapError, DataValidationError, OSError, ValueError, TypeError):
        return _base("journal_audit_abstain")
