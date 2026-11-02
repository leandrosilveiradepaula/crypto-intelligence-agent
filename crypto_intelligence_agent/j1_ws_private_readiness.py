"""OPS13: owner-only read-only status of reviewed WS journal, never a live check."""
from __future__ import annotations

import os
from pathlib import Path
import time

from .bybit_closed_stream_cache import HOUR_MS, MAX_JOURNAL_ROWS, SQLiteOfflineClosedStreamJournal
from .bybit_ws_owner_lock import _safe_stat
from .bybit_ws_owner_pilot import _read_epoch_chain, _audit_epoch_chain, MAX_PILOT_SCOPE_AGE_MS
from .j1_ws_service_health import read_owner_ws_health
from .market_data import DataGapError, DataValidationError

LOW_CAPACITY_DAYS = 7


def _abstain(reason: str) -> dict:
    return {
        "status": "ws_private_readiness_abstain",
        "reason": reason,
        "worker_running_verified": False,
        "source_authenticated": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
    }


def read_private_ws_readiness(directory: str | Path, *,
                              now_ms: int | None = None) -> dict:
    """Re-audit closed hours in a private SQLite read-only snapshot.

    Never trust health JSON to establish live process or venue origin.
    This is not an operational soak certificate.
    """
    if now_ms is None:
        now_ms = time.time_ns() // 1_000_000
    if os.name != "posix" or type(now_ms) is not int or now_ms <= HOUR_MS:
        return _abstain("invalid_owner_or_clock")
    try:
        d = Path(directory)
        if d.is_symlink():
            raise DataValidationError("private directory symlink")
        _safe_stat(d, directory=True)
        p = d / "ws-confirmed.sqlite"
        _safe_stat(p, directory=False)
        decision = now_ms // HOUR_MS * HOUR_MS
        if now_ms - decision < 1000:
            return _abstain("utc_close_margin")
        epochs = _read_epoch_chain(d, now_ms=now_ms)
        latest = epochs[-1]
        if (latest.observed_at_ms > now_ms
                or now_ms - latest.observed_at_ms > MAX_PILOT_SCOPE_AGE_MS):
            return _abstain("scope_expired_or_future")
        audit = _audit_epoch_chain(
            journal=SQLiteOfflineClosedStreamJournal(p),
            epochs=epochs, decision=decision, now=now_ms,
        )
        count = len(latest.contracts)
        if (type(audit.persisted_rows) is not int
                or not 0 <= audit.persisted_rows <= MAX_JOURNAL_ROWS
                or type(audit.missing_24h_symbols) is not int
                or type(audit.complete_24h_symbols) is not int
                or audit.complete_24h_symbols + audit.missing_24h_symbols != count
                or audit.complete_24h_symbols < 0 or audit.missing_24h_symbols < 0
                or type(audit.declared_gap_markers) is not int
                or audit.declared_gap_markers < 0):
            raise DataValidationError("untrusted journal audit counts")
        free = MAX_JOURNAL_ROWS - audit.persisted_rows
        days = free // (count * 24)
        health = read_owner_ws_health(d, now_ms=now_ms)
        full = (audit.complete_24h_symbols == count
                and audit.rank_digest_sha256 is not None)
        return {
            "status": "ws_private_sample_complete_not_live" if full
                      else "ws_private_sample_incomplete_abstain",
            "decision_at_utc_ms": decision,
            "reviewed_contracts": count,
            "scope_epochs": len(epochs),
            "complete_24h_contracts": audit.complete_24h_symbols,
            "missing_24h_contracts": audit.missing_24h_symbols,
            "declared_gap_markers": audit.declared_gap_markers,
            "journal_rows": audit.persisted_rows,
            "journal_row_limit": MAX_JOURNAL_ROWS,
            "remaining_rows": free,
            "remaining_full_days_at_scope": days,
            "low_capacity_warning": days <= LOW_CAPACITY_DAYS,
            "last_health_status": health["status"],
            "worker_running_verified": False,
            "source_authenticated": False,
            "marketwide_top50_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
        }
    except (DataGapError, DataValidationError, OSError, ValueError,
            TypeError, OverflowError):
        return _abstain("private_journal_or_scope_invalid")
