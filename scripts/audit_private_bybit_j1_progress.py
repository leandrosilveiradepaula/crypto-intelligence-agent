"""J1 #310: strictly read-only private Bybit SQLite recovery audit.

No market requests, secrets, filenames, symbols, prices, redistributions,
migration or DB writes. Intended to inspect a finished/aborted owner run.
SQLite is opened with mode=ro&immutable=1 only after owner-only POSIX checks.
Never run concurrently with a writer. Printed output is a bounded safe summary.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from stat import S_IMODE, S_ISREG

from crypto_intelligence_agent.bybit_research_storage import (
    INPUT_ORIGIN, SCHEMA_VERSION, SQLiteBybitResearchStore, _ALLOWED_TABLES,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.private_kraken_research import _private_db_path

HOUR_MS = 3_600_000
MAX_AUDIT_BYTES = 128 * 1024 * 1024
MAX_AUDIT_PAGES = 1000
MAX_AUDIT_SNAPSHOTS = 50


class BybitProgressAuditError(ValueError):
    """Only fixed error codes. No private values may leave this boundary."""


def _base_report(status: str, *, exists: bool) -> dict:
    return {
        "status": status,
        "database_exists": exists,
        "network_requests": 0,
        "data_stored_by_this_audit": False,
        "orders_sent": False,
        "marketwide_top50_verified": False,
        "rights_for_live_authorized": False,
    }


def audit_private_bybit_j1_progress(
    *, database: str | Path, allow_private_readonly_audit: bool = False,
) -> dict:
    """Validate existing private DB's page digests, clocks, continuity and PIT.

    Missing DB is a valid finding, not an instruction to fetch it. An existing
    database is NEVER opened for write or recreated by this function.
    """
    if allow_private_readonly_audit is not True or os.name != "posix":
        raise BybitProgressAuditError("private_readonly_audit_opt_in_or_posix_required")
    try:
        path = _private_db_path(database)
    except Exception:
        raise BybitProgressAuditError("private_database_path_rejected") from None
    if not path.exists():
        if path.is_symlink():
            raise BybitProgressAuditError("private_database_path_rejected")
        return _base_report("private_bybit_db_absent", exists=False)
    try:
        directory, file_stat = path.parent.stat(), path.lstat()
        if (not S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1
                or file_stat.st_uid != os.getuid()
                or S_IMODE(file_stat.st_mode) != 0o600
                or directory.st_uid != os.getuid()
                or S_IMODE(directory.st_mode) != 0o700
                or not 0 < file_stat.st_size <= MAX_AUDIT_BYTES
                or any(Path(str(path) + suffix).exists()
                       for suffix in ("-wal", "-shm", "-journal"))):
            raise BybitProgressAuditError("private_sqlite_file_not_safe_for_audit")
        # Read-only immutable avoids creation of lock/shm/journal files. Only
        # safe after the writer has terminated (owner operator requirement).
        source = path.resolve(strict=True)
        db = sqlite3.connect(
            source.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0,
        )
    except BybitProgressAuditError:
        raise
    except (OSError, RuntimeError, sqlite3.Error):
        raise BybitProgressAuditError("private_sqlite_readonly_open_rejected") from None
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("BEGIN")
        objects = db.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE type IN ('table', 'trigger', 'view') "
            "AND name NOT LIKE 'sqlite_%'",
        ).fetchall()
        if (any(row["type"] != "table" for row in objects)
                or {row["name"] for row in objects} != _ALLOWED_TABLES):
            raise BybitProgressAuditError("unrecognized_private_research_schema")
        meta = db.execute(
            "SELECT id, schema_version, input_origin FROM bybit_research_meta",
        ).fetchall()
        if (len(meta) != 1 or meta[0]["id"] != 1
                or meta[0]["schema_version"] != SCHEMA_VERSION
                or meta[0]["input_origin"] != INPUT_ORIGIN):
            raise BybitProgressAuditError("unrecognized_research_origin")
        integrity = db.execute("PRAGMA integrity_check").fetchall()
        if (len(integrity) != 1 or integrity[0][0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchone() is not None):
            raise BybitProgressAuditError("private_sqlite_integrity_rejected")
        pages = db.execute(
            "SELECT * FROM bybit_research_pages "
            "ORDER BY symbol, start_open_ms",
        ).fetchmany(MAX_AUDIT_PAGES + 1)
        if len(pages) > MAX_AUDIT_PAGES:
            raise BybitProgressAuditError("research_page_budget_exceeded")
        windows = {}
        volumes = defaultdict(int)
        registry = set()
        closed_candle_rows = 0
        for page in pages:
            symbol = page["symbol"]
            if (type(symbol) is not str or not symbol.isascii()
                    or not symbol.endswith("USDT") or not symbol.isupper()
                    or page["interval"] != "1h"
                    or page["quote_unit"] != "USDT"
                    or page["capture_environment"] != "private_local_unverified"):
                raise BybitProgressAuditError("unrecognized_research_page_type")
            try:
                reviewed = SQLiteBybitResearchStore._validate_page_in_snapshot(
                    db, page, symbol=symbol, interval="1h",
                )
            except (DataGapError, DataValidationError):
                raise BybitProgressAuditError("private_research_page_replay_rejected") from None
            if symbol not in windows:
                windows[symbol] = [reviewed.start_open_ms, reviewed.end_open_ms]
            elif windows[symbol][1] != reviewed.start_open_ms:
                raise BybitProgressAuditError("private_research_page_gap_or_overlap")
            else:
                windows[symbol][1] = reviewed.end_open_ms
            registry.add(reviewed.registry_sha256)
            volumes[symbol] += len(reviewed.candles)
            closed_candle_rows += len(reviewed.candles)
        if len(registry) != 1 or len(windows) > 50:
            raise BybitProgressAuditError("private_research_registry_or_scope_mixed")
        pit_rows = db.execute(
            "SELECT observed_at_ms,decision_at_ms,content_json,content_sha256 "
            "FROM bybit_research_pit_snapshots ORDER BY observed_at_ms",
        ).fetchmany(MAX_AUDIT_SNAPSHOTS + 1)
        if len(pit_rows) > MAX_AUDIT_SNAPSHOTS:
            raise BybitProgressAuditError("private_snapshot_budget_exceeded")
        prior_observed, prior_decision = None, None
        pit_digests = []
        decisions = []
        first_pit_members = set()
        for i, pit in enumerate(pit_rows):
            payload, digest = pit["content_json"], pit["content_sha256"]
            if (type(payload) is not str or type(digest) is not str
                    or sha256(payload.encode("utf-8")).hexdigest() != digest):
                raise BybitProgressAuditError("private_pit_digest_invalid")
            try:
                decoded = json.loads(payload)
                members = decoded["ranked"]
                symbols = {m["symbol"] for m in members}
                ok = (decoded["observed_at_ms"] == pit["observed_at_ms"]
                    and decoded["decision_at_ms"] == pit["decision_at_ms"]
                    and decoded["market_wide_top50_verified"] is False
                    and decoded["source_authenticated"] is False
                    and decoded["rights_for_live_authorized"] is False
                    and len(symbols) == len(members)
                    and symbols <= set(windows)
                    and decoded["registry_sha256"] in registry
                    and pit["decision_at_ms"] % HOUR_MS == 0
                    and pit["observed_at_ms"] > pit["decision_at_ms"]
                    and (prior_observed is None
                         or pit["observed_at_ms"] > prior_observed)
                    and (prior_decision is None
                         or pit["decision_at_ms"] > prior_decision))
            except (KeyError, TypeError, ValueError):
                ok = False
            if not ok:
                raise BybitProgressAuditError("private_pit_replay_rejected")
            if i == 0:
                first_pit_members = symbols
                if not all(
                    windows[s][0] <= pit["decision_at_ms"] - 720 * HOUR_MS
                    and windows[s][1] >= pit["decision_at_ms"]
                    for s in symbols
                ):
                    raise BybitProgressAuditError("first_snapshot_lacks_720h_coverage")
            prior_observed, prior_decision = pit["observed_at_ms"], pit["decision_at_ms"]
            decisions.append(pit["decision_at_ms"])
            pit_digests.append(digest)
        if len(windows) > 13:
            # Only the checked-in independently reviewed expanded-52
            # identity registry may authorize this larger research scope.
            # Compare hashes without applying a CURRENT registry age gate
            # to old immutable point-in-time observations.
            from crypto_intelligence_agent.crypto_asset_registry import load_registry_json
            from crypto_intelligence_agent.research_registry_catalog import _FILES
            verified_registry = load_registry_json(
                _FILES["expanded-52"].read_bytes()).sha256_digest
            if (registry != {verified_registry}
                    or not first_pit_members
                    or first_pit_members != set(windows)):
                raise BybitProgressAuditError("private_research_registry_or_scope_mixed")
        if any(
            set(item["symbol"] for item in json.loads(pit["content_json"])["ranked"])
                != first_pit_members
            for pit in pit_rows[1:]
        ):
            raise BybitProgressAuditError("private_research_pit_membership_changed")
        extensions = 0
        for current, earlier in zip(reversed(decisions[1:]), reversed(decisions[:-1])):
            if current - earlier != HOUR_MS:
                break
            extensions += 1
        result = _base_report("private_bybit_progress_readonly_verified", exists=True)
        result.update({
            "sqlite_integrity_passed": True,
            "private_page_replay_passed": True,
            "sample_asset_count": len(windows),
            "stored_page_count": len(pages),
            "stored_closed_candle_rows": closed_candle_rows,
            "immutable_pit_snapshots": len(pit_rows),
            "first_pit_720h_coverage": bool(first_pit_members),
            "consecutive_snapshots_at_end": extensions,
            "first_pit_decision_ms": decisions[0] if decisions else None,
            "last_pit_decision_ms": decisions[-1] if decisions else None,
            "min_stored_open_ms": min((x[0] for x in windows.values()), default=None),
            "max_stored_end_ms": max((x[1] for x in windows.values()), default=None),
            "min_hours_per_asset": min(volumes.values(), default=0),
            "data_stored_locally": closed_candle_rows > 0,
            "initial_snapshot_digest_sha256": pit_digests[0] if pit_digests else None,
        })
        return result
    except BybitProgressAuditError:
        raise
    except (sqlite3.Error, KeyError, TypeError, ValueError, OverflowError):
        raise BybitProgressAuditError("private_sqlite_readonly_audit_rejected") from None
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit_private_bybit_j1_progress(
            database=args.database,
            allow_private_readonly_audit=args.allow_private_readonly_audit,
        )
    except Exception as exc:
        result = _base_report(
            str(exc) if type(exc) is BybitProgressAuditError
            else "private_sqlite_audit_failed_sanitized",
            exists=False,
        )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return int(result["status"] not in (
        "private_bybit_progress_readonly_verified", "private_bybit_db_absent",
    ))


if __name__ == "__main__":
    raise SystemExit(main())
