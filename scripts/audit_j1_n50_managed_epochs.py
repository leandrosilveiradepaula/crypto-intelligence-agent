"""J1/D299: read-only, owner-only telemetry across immutable managed N50 epochs.

This never invokes the exchange, changes a timer, creates a DB, revises PIT,
fills a missing closed hour, grants trading, or writes files. A complete
per-epoch owner replay (D290/D292) is mandatory before counting checkpoints.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from crypto_intelligence_agent.j1_auto_research_epoch import (
    FILE_NAME, HOUR_MS, MAX_SCOPE_AGE_MS, validate_ranked_research_scope,
)
from crypto_intelligence_agent.j1_n50_managed_cycle import (
    ACTIVE_FILE, EPOCH_RE, _pointer_read,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import _DB_NAME
from crypto_intelligence_agent.j1_rest_resume_readiness import (
    audit_existing_rest_resume, MAX_PUBLISHED, MAX_DB_BYTES,
)
from scripts.audit_bybit_marketwide_closed24h import (
    CensusAbstain, _strict_owner,
)
from scripts.run_j1_current_ranked_epoch_once import (
    MAX_MANIFEST_BYTES, _decode_private_file,
)

ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")
MAX_EPOCHS = 96
MAX_TOTAL_CANDLES = 500_000


def _result(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-managed-owner-health-v1",
        "status": status,
        "active_epoch_id": None,
        "epoch_count": 0,
        "audited_journals": 0,
        "archived_halted_epochs": 0,
        "archived_partial_unpublished_contracts": 0,
        "stored_candles": 0,
        "published_checkpoints": 0,
        "unique_published_utc_hours": 0,
        "missing_hours_between_publications": None,
        "latest_published_end_ms": None,
        "latest_published_age_hours": None,
        "published_last_24_closed_hours": 0,
        "expected_last_24_closed_hours": 24,
        "active_epoch_age_hours": None,
        "owner_integrity_verified": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def _verified_directory(path: Path) -> None:
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise ValueError("managed_owner_directory_alias")
    _strict_owner(path, directory=True)


def _capture_candidate_pending(path: Path, *, now: int) -> bool:
    """An unpromoted epoch is expected only during its current capture hour.

    No manifest content is trusted, and no new SQLITE checkpoint is implied.
    """
    decision = now // HOUR_MS * HOUR_MS
    if (path.name != f"epoch-{decision:013d}"
            or not 60_000 <= now % HOUR_MS <= 900_000):
        return False
    _verified_directory(path)
    scope = path / "scope"
    journal = path / "journal"
    _verified_directory(scope)
    _verified_directory(journal)
    if next(journal.iterdir(), None) is not None:
        return False
    contents = list(scope.iterdir())
    if len(contents) > 1:
        return False
    if contents:
        if contents[0].name != FILE_NAME or contents[0].is_symlink():
            return False
        _strict_owner(contents[0], directory=False)
    return True


def _published_ends(path: Path, *, expected: int, last: int) -> list[int]:
    _strict_owner(path, directory=False)
    if path.is_symlink() or path.stat().st_size > MAX_DB_BYTES:
        raise ValueError("private_sqlite_invalid")
    with closing(sqlite3.connect(
        path.as_uri() + "?mode=ro", uri=True, timeout=2,
    )) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            "SELECT end_ms FROM published_hour ORDER BY end_ms LIMIT ?",
            (MAX_PUBLISHED + 1,),
        ).fetchall()
    ends = [x[0] for x in rows]
    if (len(ends) != expected or not ends or ends[-1] != last
            or any(type(v) is not int or v % HOUR_MS for v in ends)
            or any(b <= a for a,b in zip(ends, ends[1:]))):
        raise ValueError("published_hour_count_or_clock_drift")
    return ends


def audit_managed_n50_epochs(
    *, root_directory: Path = ROOT,
    allow_private_readonly_audit: bool = False,
    owner_ok: bool | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Aggregate verified actual PIT checkpoints, never backfilled fake hours."""
    out = _result("optin_required")
    if allow_private_readonly_audit is not True:
        return out
    out["status"] = "blocked"
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if (owner is not True or not isinstance(root_directory, Path)
            or not root_directory.is_absolute()
            or not isinstance(now_ms, (int, type(None)))
            or type(now_ms) is bool):
        return out
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if type(now) is not int or not 1_600_000_000_000 <= now < 4_102_444_800_000:
        return out
    try:
        _verified_directory(root_directory)
        epochs = root_directory / "epochs"
        _verified_directory(epochs)
        _verified_directory(root_directory / "lease")
        folders = list(epochs.iterdir())
        if (len(folders) > MAX_EPOCHS
                or any(not EPOCH_RE.fullmatch(p.name) for p in folders)):
            return out
        folders.sort(key=lambda x: x.name)
        pointer = _pointer_read(root_directory)
        if pointer is None:
            if not folders:
                return _result("awaiting_first_epoch")
            if (len(folders) == 1
                    and _capture_candidate_pending(folders[0], now=now)):
                out["status"] = "capture_in_progress_unverified"
                out["epoch_count"] = 1
            return out
        active = pointer["epoch_id"]
        if active not in {p.name for p in folders}:
            return out
        out["active_epoch_id"] = active
        out["epoch_count"] = len(folders)
        pending = [p for p in folders if p.name > active]
        if pending:
            if (len(pending) == 1
                    and _capture_candidate_pending(pending[0], now=now)):
                out["status"] = "rotation_in_progress_unverified"
            return out
        all_ends: list[int] = []
        for folder in folders:
            _verified_directory(folder)
            scope_dir = folder / "scope"
            journal_dir = folder / "journal"
            _verified_directory(scope_dir)
            _verified_directory(journal_dir)
            manifest = _decode_private_file(
                scope_dir / FILE_NAME, max_bytes=MAX_MANIFEST_BYTES,
            )
            observed = manifest.get("catalog_post_observed_at_ms")
            if type(observed) is not int or observed > now:
                return _result("blocked")
            members, digest = validate_ranked_research_scope(
                manifest, now_ms=min(now, observed + MAX_SCOPE_AGE_MS),
                max_assets=50,
            )
            if (len(members) != 50
                    or folder.name != f"epoch-{manifest['closed_hour_end_ms']:013d}"):
                return _result("blocked")
            if folder.name == active:
                if (digest != pointer["scope_digest_sha256"]
                        or observed != pointer["catalog_post_observed_at_ms"]):
                    return _result("blocked")
                out["active_epoch_age_hours"] = (now - observed) // HOUR_MS
            db_path = journal_dir / _DB_NAME
            if not db_path.exists() and not db_path.is_symlink():
                if folder.name == active:
                    out["status"] = "awaiting_first_writer"
                    return out
                return _result("blocked")
            if db_path.is_symlink():
                return _result("blocked")
            audit = audit_existing_rest_resume(
                output_directory=journal_dir, now_ms=now,
                allow_private_readonly_audit=True, expected_members=50,
                allow_unpublished_partial_hour=True,
                owner_ok=owner,
            )
            if audit.get("journal_integrity_verified") is not True:
                if folder.name != active:
                    # After D306's authorized new-epoch recovery the old M1
                    # journal remains deliberately HALTED and unmodified.
                    # Replay it independently using D304, not the active
                    # D290 resume policy. Its six unpublished candles are
                    # NEVER promoted to historical PIT checkpoints.
                    from crypto_intelligence_agent.j1_n50_halted_forensic import (
                        audit_halted_n50_epoch,
                    )
                    forensic = audit_halted_n50_epoch(
                        scope_directory=scope_dir, journal_directory=journal_dir,
                        allow_private_readonly_audit=True, owner_ok=owner,
                        now_ms=now,
                    )
                    if (forensic.get("status") != "halted_owner_review_verified"
                            or forensic.get("saved_rows_integrity_verified") is not True
                            or forensic.get("scope_digest_sha256") != digest
                            or forensic.get("historical_missing_publication_hours") != 0
                            or forensic.get("resume_authorized") is not False
                            or forensic.get("orders_sent") is not False
                            or forensic.get("network_requests") != 0
                            or forensic.get("database_mutation_statements") != 0
                            or type(forensic.get("published_hours")) is not int
                            or type(forensic.get("stored_candles")) is not int
                            or type(forensic.get("partial_contracts_at_next_hour")) is not int):
                        return _result("blocked")
                    out["archived_halted_epochs"] += 1
                    out["archived_partial_unpublished_contracts"] += (
                        forensic["partial_contracts_at_next_hour"])
                    # Only the already-published rows, not the six partial
                    # candles, are counted below as published checkpoints.
                    audit = {
                        "journal_scope_digest_sha256": digest,
                        "reviewed_research_contracts":50,
                        "orders_sent":False,
                        "live_trading_authorized":False,
                        "marketwide_top50_verified":False,
                        "stored_candles":forensic["stored_candles"],
                        "published_hours":forensic["published_hours"],
                        "last_published_end_ms":forensic["last_published_end_ms"],
                    }
                else:
                    # First owner writer may be mid-transaction in HH:01–15;
                    # never label it healthy or corrupt prematurely.
                    if 60_000 <= now % HOUR_MS <= 900_000:
                        out["status"] = "in_progress_unverified"
                        return out
                    return _result("blocked")
            if (audit.get("journal_scope_digest_sha256") != digest
                    or audit.get("reviewed_research_contracts") != 50
                    or audit.get("orders_sent") is not False
                    or audit.get("live_trading_authorized") is not False
                    or audit.get("marketwide_top50_verified") is not False
                    or type(audit.get("stored_candles")) is not int
                    or type(audit.get("published_hours")) is not int):
                return _result("blocked")
            if audit["published_hours"] == 0:
                if (folder.name == active
                        and audit.get("status") ==
                            "unpublished_bootstrap_resume_ready"):
                    out["status"] = "partial_first_writer"
                    out["stored_candles"] += audit["stored_candles"]
                    return out
                return _result("blocked")
            if audit["published_hours"] < 0:
                return _result("blocked")
            ends = _published_ends(
                db_path, expected=audit["published_hours"],
                last=audit["last_published_end_ms"],
            )
            all_ends.extend(ends)
            out["audited_journals"] += 1
            out["stored_candles"] += audit["stored_candles"]
            out["published_checkpoints"] += len(ends)
            if out["stored_candles"] > MAX_TOTAL_CANDLES:
                return _result("blocked")
        if not all_ends:
            return _result("blocked")
        all_ends.sort()
        if len(set(all_ends)) != len(all_ends):
            return _result("blocked")
        skipped = 0
        for a,b in zip(all_ends,all_ends[1:]):
            if (b - a) % HOUR_MS:
                return _result("blocked")
            skipped += (b - a) // HOUR_MS - 1
        out["unique_published_utc_hours"] = len(all_ends)
        out["missing_hours_between_publications"] = skipped
        out["latest_published_end_ms"] = all_ends[-1]
        out["latest_published_age_hours"] = (now - all_ends[-1]) // HOUR_MS
        phase = now % HOUR_MS
        last_eligible = now // HOUR_MS * HOUR_MS
        if phase < 60_000:
            last_eligible -= HOUR_MS
        low = last_eligible - 23 * HOUR_MS
        out["published_last_24_closed_hours"] = sum(
            low <= x <= last_eligible for x in all_ends
        )
        out["owner_integrity_verified"] = True
        # 'pass' is replay quality, never a blanket 24/7 guarantee.
        out["status"] = ("stale_active_publication" if
                         now - all_ends[-1] > 2 * HOUR_MS
                         else "verified_with_missing_pit" if skipped
                         else "verified_epoch_history")
        return out
    except (CensusAbstain, OSError, ValueError, TypeError, OverflowError,
            sqlite3.Error, json.JSONDecodeError, UnicodeError):
        return _result("blocked")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # The operational CLI has a pinned path; no caller-selected SQLite/SQL.
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    args = parser.parse_args(argv)
    report = audit_managed_n50_epochs(**vars(args))
    print(json.dumps(report, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True))
    return 0 if report["status"] in (
        "awaiting_first_epoch", "awaiting_first_writer",
        "in_progress_unverified", "partial_first_writer",
        "capture_in_progress_unverified", "rotation_in_progress_unverified",
        "verified_epoch_history", "verified_with_missing_pit",
        "stale_active_publication",
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
