"""D323: read-only owner witness of 24 consecutive N50 WebSocket hours.

Replays D321 private epoch and the D313 SQLite journal, then checks current
systemd isolation. Local 50x24 does not prove venue authentication, 36h
rotation, global crypto Top50, 24/7 uptime, or a tradable strategy.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import time
from typing import Any

from .bybit_closed_stream_cache import HOUR_MS, OfflineStreamAudit, SQLiteOfflineClosedStreamJournal
from .bybit_ws_owner_lock import _safe_stat
from .j1_auto_research_epoch import validate_ranked_research_scope
from .j1_n50_ws_epoch_rotation import _OWNER_ROOT, load_active_n50_ws_epoch
from .j1_n50_ws_private_cache import load_n50_ws_dynamic_admission
from .market_data import DataGapError, DataValidationError
from scripts.release_j1_n50_ws_owner_once import N2_TIMER, OLD_N50_TIMER, WS_SERVICE, WS_TIMER, _show
from scripts.release_j1_n50_ws_rotating_once import ROT_TIMER
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

STATE_DIRECTORY = _OWNER_ROOT / "active"
_UNITS = {
    "ws_timer": WS_TIMER,
    "ws_service": WS_SERVICE,
    "rotation_timer": ROT_TIMER,
    "n2_timer": N2_TIMER,
    "old_n50_timer": OLD_N50_TIMER,
}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED = {
    "ws_timer": ("loaded", "active", "enabled"),
    "rotation_timer": ("loaded", "active", "enabled"),
    "n2_timer": ("loaded", "inactive", "disabled"),
    "old_n50_timer": ("loaded", "inactive", "disabled"),
}


def _result(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-ws-closed24h-owner-witness-v1",
        "status": status,
        "latest_eligible_closed_end_ms": None,
        "verified_closed_hours": 0,
        "expected_closed_hours": 24,
        "verified_contracts_per_hour": 0,
        "expected_contracts_per_hour": 50,
        "persisted_ws_rows": 0,
        "ranked_scope_sha256": None,
        "ws_metadata_sha256": None,
        "ws_journal_sha256": None,
        "last_hour_sha256": None,
        "ws_timer_active_enabled": False,
        "rotation_timer_active_enabled": False,
        "n2_quiesced": False,
        "old_rest_n50_quiesced": False,
        "ws_service_not_failed": False,
        "ws_journal_integrity_verified": False,
        "ws_closed_24h_local_verified": False,
        "rotation_36h_live_verified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _systemd_state() -> dict[str, dict[str, str]]:
    """Only hardcoded unit names, bounded by existing D320 strict reader."""
    return {key: _show(name) for key, name in _UNITS.items()}


def evaluate_n50_ws_24h(
    audit: object, units: object, *, now_ms: int,
    ranked_scope_sha256: str | None = None,
    ws_metadata_sha256: str | None = None,
) -> dict[str, Any]:
    """Pure conservative gate; no actions, symbols, or prices."""
    out = _result("invalid_or_untrusted_witness_input")
    if (type(now_ms) is not int
            or not 1_600_000_000_000 <= now_ms < 4_102_444_800_000
            or type(units) is not dict or set(units) != set(_UNITS)):
        return out
    for state in units.values():
        if (type(state) is not dict
                or set(state) != {"LoadState", "ActiveState", "UnitFileState"}
                or any(type(v) is not str or len(v) > 32 for v in state.values())
                or state["LoadState"] not in ("loaded", "not-found")
                or state["ActiveState"] not in ("active", "inactive", "failed", "activating")
                or state["UnitFileState"] not in ("enabled", "disabled", "static")):
            return out
    phase = now_ms % HOUR_MS
    if not 180_000 <= phase < HOUR_MS - 60_000:
        out["status"] = "awaiting_safe_closed_hour_audit_window"
        return out
    out["latest_eligible_closed_end_ms"] = now_ms - phase
    for key, attr in (
        ("ws_timer", "ws_timer_active_enabled"),
        ("rotation_timer", "rotation_timer_active_enabled"),
        ("n2_timer", "n2_quiesced"),
        ("old_n50_timer", "old_rest_n50_quiesced"),
    ):
        out[attr] = tuple(units[key][field] for field in
                          ("LoadState", "ActiveState", "UnitFileState")) == _REQUIRED[key]
    service = units["ws_service"]
    out["ws_service_not_failed"] = (
        service == {"LoadState": "loaded", "ActiveState": "inactive",
                    "UnitFileState": "static"}
    )
    if units["n2_timer"]["ActiveState"] == "active" and not out["ws_timer_active_enabled"]:
        out["status"] = "n2_failback_observed"
        return out
    if not all(out[key] for key in (
        "ws_timer_active_enabled", "rotation_timer_active_enabled",
        "n2_quiesced", "old_rest_n50_quiesced", "ws_service_not_failed",
    )):
        out["status"] = "ws_systemd_isolation_or_service_not_ready"
        return out
    out["status"] = "awaiting_owner_ws_journal_audit"
    if audit is None:
        return out
    if (type(audit) is not OfflineStreamAudit
            or audit.status not in ("offline_reviewed_24h_complete_not_top50",
                                     "offline_closed_stream_incomplete_abstain")
            or type(audit.persisted_rows) is not int
            or not 0 <= audit.persisted_rows <= 1_000_000
            or type(audit.complete_24h_symbols) is not int
            or type(audit.missing_24h_symbols) is not int
            or not 0 <= audit.complete_24h_symbols <= 50
            or audit.complete_24h_symbols + audit.missing_24h_symbols != 50
            or type(audit.hour_evidence_expected) is not int
            or audit.hour_evidence_expected != 50
            or type(audit.hour_evidence_confirmed) is not int
            or not 0 <= audit.hour_evidence_confirmed <= 50
            or type(audit.journal_digest_sha256) is not str
            or _SHA.fullmatch(audit.journal_digest_sha256) is None
            or type(ranked_scope_sha256) is not str
            or _SHA.fullmatch(ranked_scope_sha256) is None
            or type(ws_metadata_sha256) is not str
            or _SHA.fullmatch(ws_metadata_sha256) is None):
        out["status"] = "owner_ws_journal_integrity_abstain"
        return out
    out.update(
        persisted_ws_rows=audit.persisted_rows,
        ws_journal_integrity_verified=True,
        ranked_scope_sha256=ranked_scope_sha256,
        ws_metadata_sha256=ws_metadata_sha256,
        ws_journal_sha256=audit.journal_digest_sha256,
    )
    if (audit.status != "offline_reviewed_24h_complete_not_top50"
            or audit.complete_24h_symbols != 50
            or audit.missing_24h_symbols != 0
            or audit.hour_evidence_confirmed != 50
            or type(audit.rank_digest_sha256) is not str
            or _SHA.fullmatch(audit.rank_digest_sha256) is None
            or type(audit.hour_evidence_sha256) is not str
            or _SHA.fullmatch(audit.hour_evidence_sha256) is None
            or audit.persisted_rows < 1200):
        out["status"] = "accumulating_or_incomplete_ws_24h"
        return out
    # audit() independently replays every row and gap marker in ONE SQLite
    # read-only BEGIN snapshot; the last 24h means [end-24h, end).
    out.update(
        status="ws_24h_local_evidence_verified",
        verified_closed_hours=24, verified_contracts_per_hour=50,
        last_hour_sha256=audit.hour_evidence_sha256,
        ws_closed_24h_local_verified=True,
    )
    return out


def observe_n50_ws_24h(
    *, state_directory: Path = STATE_DIRECTORY,
    allow_private_readonly_audit: bool = False,
    enable_ws_24h_witness: bool = False,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Owner-only entrypoint; never writes or opens a network session."""
    if not (allow_private_readonly_audit is True and enable_ws_24h_witness is True):
        return _result("owner_optin_required")
    if (os.name != "posix" or os.getuid() != os.geteuid()
            or os.geteuid() == 0 or not isinstance(state_directory, Path)
            or state_directory != STATE_DIRECTORY
            or (now_ms is not None and type(now_ms) is not int)):
        return _result("owner_environment_abstain")
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    try:
        units = _systemd_state()
        preliminary = evaluate_n50_ws_24h(None, units, now_ms=now)
        if preliminary["status"] != "awaiting_owner_ws_journal_audit":
            return preliminary
        active = load_active_n50_ws_epoch(
            state_directory=state_directory, current_at_ms=now,
            allow_private_pointer_read=True,
        )
        if (active.status != "active_n50_ws_epoch_revalidated"
                or active.manifest_directory is None
                or active.ws_directory is None
                or active.ranked_scope_sha256 is None
                or active.ws_metadata_sha256 is None):
            preliminary["status"] = "owner_active_ws_epoch_unavailable"
            return preliminary
        ranked = load_private_ranked_scope(active.manifest_directory, now_ms=now)
        members, digest = validate_ranked_research_scope(
            ranked, now_ms=now, max_assets=50,
        )
        cache = load_n50_ws_dynamic_admission(
            directory=active.ws_directory, current_at_ms=now,
            expected_ranked_scope_sha256=digest, allow_private_scope_read=True,
        )
        if (len(members) != 50 or digest != active.ranked_scope_sha256
                or cache.status != "private_n50_ws_admission_loaded_revalidated"
                or cache.admission is None or cache.ranked_scope != ranked
                or cache.admission.selected_contracts != 50
                or cache.admission.metadata_sha256 != active.ws_metadata_sha256
                or len(cache.admission.ws_scope.contracts) != 50):
            preliminary["status"] = "owner_ws_scope_integrity_abstain"
            return preliminary
        journal_path = active.ws_directory / "ws-confirmed.sqlite"
        if journal_path.is_symlink():
            preliminary["status"] = "owner_ws_journal_integrity_abstain"
            return preliminary
        _safe_stat(journal_path, directory=False)
        audited = SQLiteOfflineClosedStreamJournal(journal_path).audit(
            scope=cache.admission.ws_scope,
            decision_at_ms=preliminary["latest_eligible_closed_end_ms"],
            as_of_ms=now,
            hour_evidence_symbols=tuple(sorted(members)),
        )
        return evaluate_n50_ws_24h(
            audited, units, now_ms=now,
            ranked_scope_sha256=digest,
            ws_metadata_sha256=cache.admission.metadata_sha256,
        )
    except (OSError, ValueError, TypeError, RuntimeError, KeyError,
            OverflowError, UnicodeError, DataGapError, DataValidationError):
        return _result("owner_ws_readonly_audit_abstain")
