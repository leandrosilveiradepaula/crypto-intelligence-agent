"""D304: bounded owner-only forensic replay of a HALTED N50 M1 journal.

A latched provider denial is never retried, cleared or reclassified as
healthy. Verify all *saved* candles/cursors and publication receipts, expose
only counts and fixed reasons, never symbols/prices/provider payloads.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from crypto_intelligence_agent.j1_auto_research_epoch import (
    HOUR_MS, validate_ranked_research_scope,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import (
    _DB_NAME, _SHA, _validate_cursor,
)
from crypto_intelligence_agent.j1_rest_resume_readiness import (
    MAX_DB_BYTES, SETTLE_MS, LATEST_START_MS,
)
from scripts.audit_bybit_marketwide_closed24h import CensusAbstain, _strict_owner
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

MAX_FORENSIC_HOURS = 72
_HALTS = frozenset(("provider_denied_owner_review",
                    "candle_or_storage_integrity"))


def _base(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-halted-owner-forensic-v1",
        "status": status,
        "halted_reason": None,
        "saved_rows_integrity_verified": False,
        "resume_authorized": False,
        "last_published_end_ms": None,
        "published_hours": 0,
        "partial_contracts_at_next_hour": 0,
        "stored_candles": 0,
        "historical_missing_publication_hours": None,
        "scope_digest_sha256": None,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def audit_halted_n50_epoch(
    *, scope_directory: Path, journal_directory: Path,
    allow_private_readonly_audit: bool = False,
    owner_ok: bool | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Independently replay a latched N50 epoch, never permit resumption."""
    if allow_private_readonly_audit is not True:
        return _base("optin_required")
    out = _base("blocked")
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if (owner is not True
            or not isinstance(scope_directory, Path)
            or not isinstance(journal_directory, Path)
            or not scope_directory.is_absolute()
            or not journal_directory.is_absolute()
            or scope_directory.name != "scope"
            or journal_directory.name != "journal"
            or scope_directory.parent != journal_directory.parent
            or scope_directory == journal_directory
            or type(now_ms) not in (int, type(None))):
        return out
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if type(now) is not int or not 1_600_000_000_000 <= now < 4_102_444_800_000:
        return out
    try:
        for path in (scope_directory.parent, scope_directory, journal_directory):
            if path.is_symlink() or path.resolve(strict=True) != path:
                return out
            _strict_owner(path, directory=True)
        # Forensics may replay an expired scope without proposing any
        # market action; revalidate at its last allowed read instant.
        snapshot = load_private_ranked_scope(scope_directory, now_ms=now)
        members, digest = validate_ranked_research_scope(
            snapshot, now_ms=now, max_assets=50,
        )
        if len(members) != 50:
            return out
        db_path = journal_directory / _DB_NAME
        if db_path.is_symlink() or not db_path.is_file():
            return out
        _strict_owner(db_path, directory=False)
        if not 0 < db_path.stat().st_size <= MAX_DB_BYTES:
            return out
        with closing(sqlite3.connect(
            db_path.as_uri() + "?mode=ro", uri=True, timeout=2,
        )) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                return out
            schema = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"scope", "cursor", "candles", "published_hour"} <= schema:
                return out
            scopes = db.execute(
                "SELECT id,scope_digest,members_json,initial_end_ms,halted_reason "
                "FROM scope ORDER BY id LIMIT 2",
            ).fetchall()
            if len(scopes) != 1:
                return out
            idx, got_digest, raw_members, initial, halted = scopes[0]
            if (idx != 1 or type(got_digest) is not str or got_digest != digest
                    or type(raw_members) is not str
                    or len(raw_members) > 50 * 40
                    or json.loads(raw_members) != list(members)
                    or type(initial) is not int or initial % HOUR_MS
                    or initial <= 24 * HOUR_MS or initial > now):
                return out
            if halted is None:
                return _base("not_halted")
            if type(halted) is not str or halted not in _HALTS:
                return out
            publications = db.execute(
                "SELECT end_ms,observed_at_ms,scope_digest,observed_contracts "
                "FROM published_hour ORDER BY end_ms LIMIT 75",
            ).fetchall()
            if not 1 <= len(publications) <= MAX_FORENSIC_HOURS:
                return out
            first = publications[0][0]
            if type(first) is not int or first not in (
                    initial, initial + HOUR_MS):
                return out
            previous = None
            missing = (first - initial) // HOUR_MS
            for end, observed, receipt_digest, count in publications:
                if (type(end) is not int or end % HOUR_MS
                        or type(observed) is not int
                        or not end + SETTLE_MS <= observed <= end + LATEST_START_MS
                        or observed > now or receipt_digest != digest
                        or type(count) is not int or count != 50):
                    return out
                if previous is not None:
                    delta = (end - previous) // HOUR_MS
                    if not 1 <= delta <= MAX_FORENSIC_HOURS:
                        return out
                    missing += delta - 1
                previous = end
            last = publications[-1][0]
            if last < initial or last > now or (
                    last - initial) // HOUR_MS > MAX_FORENSIC_HOURS:
                return out
            target = min(last + HOUR_MS, now // HOUR_MS * HOUR_MS)
            if target < last:
                return out
            cursors = [_validate_cursor(db, sym, initial, target)
                       for sym in members]
            if (len(cursors) != 50
                    or any(v not in (last, target) for v in cursors)
                    or db.execute("SELECT COUNT(*) FROM cursor").fetchone() != (50,)):
                return out
            partial = sum(v == target for v in cursors) if target > last else 0
            expected_rows = 50 * (24 + (last-initial)//HOUR_MS) + partial
            stored = db.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
            if type(stored) is not int or stored != expected_rows:
                return out
            out.update(
                status="halted_owner_review_verified",
                halted_reason=halted,
                saved_rows_integrity_verified=True,
                last_published_end_ms=last,
                published_hours=len(publications),
                partial_contracts_at_next_hour=partial,
                stored_candles=stored,
                historical_missing_publication_hours=missing,
                scope_digest_sha256=digest,
            )
            return out
    except (OSError, TypeError, ValueError, sqlite3.Error, CensusAbstain,
            UnicodeError, OverflowError, json.JSONDecodeError, KeyError):
        return _base("blocked")
