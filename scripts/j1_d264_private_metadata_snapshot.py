"""J1/D264: owner-private immutable *contemporary negative-only* overlay.

This file is NOT a crypto registry, historical PIT snapshot or eligibility
source. It stores minimal Bybit symbol indicator membership from one new,
explicitly opted-in catalog GET. The original D256 SQLite stays read-only.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None

from crypto_intelligence_agent.bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE
from crypto_intelligence_agent.bybit_identity_crosswalk_research import research_category
from crypto_intelligence_agent.j1_top50_frontier_worklist import frontier_review_worklist
from crypto_intelligence_agent.crypto_asset_registry import load_registry_json
from scripts.audit_bybit_marketwide_closed24h import (
    _MATH, _dec, _digest, _strict_owner, MAX_DB_BYTES,
)
from scripts.audit_j1_marketwide_checkpoint import _DB, _LOCK, _replay, AuditRejected
from scripts.triage_j1_marketwide_identity import REGISTRY_FILE

FILE_NAME = "d264-bybit-current-metadata-negative-v1.json"
SCHEMA = "j1-d264-current-negative-private-v1"
MAX_FILE_BYTES = 200_000
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _validate_symbols(value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if (type(value) is not list or len(value) > 1000 or
            (not allow_empty and not value)
            or any(type(x) is not str or _SYMBOL.fullmatch(x) is None
                   for x in value)
            or value != sorted(set(value))):
        raise AuditRejected("d264_symbols_invalid")
    return tuple(value)


def build_snapshot(payload: dict, *, frozen_members: frozenset[str],
                   frozen_end_ms: int, captured_at_ms: int,
                   received_at_ms: int) -> dict[str, Any]:
    """Use D263 schema/clock validation; store only indicator *presence*."""
    from scripts.audit_j1_bybit_current_metadata_negative import _classify
    metrics = _classify(payload, frozen_members=frozen_members,
                        captured_at_ms=captured_at_ms,
                        received_at_ms=received_at_ms)
    if (metrics["current_frozen_contract_overlap_count"] != len(frozen_members)
            or metrics["current_not_in_frozen_count"]
            or metrics["frozen_missing_from_current_count"]):
        raise AuditRejected("d264_scope_drift_no_snapshot")
    if (type(frozen_end_ms) is not int or frozen_end_ms <= 0
            or captured_at_ms <= frozen_end_ms):
        raise AuditRejected("d264_not_a_contemporary_snapshot")
    negative: list[str] = []
    missing: list[str] = []
    for row in payload["result"]["list"]:
        if row.get("symbol") not in frozen_members:
            continue
        # D263 validated all rows, types, uniqueness and clock *before* here.
        region, underlying = row.get("marketRegion"), row.get("underlyingTicker")
        if region is None or underlying is None:
            missing.append(row["symbol"])
        elif region or underlying:
            negative.append(row["symbol"])
    negative.sort()
    missing.sort()
    record = {
        "schema_version": SCHEMA,
        "frozen_window_end_ms": frozen_end_ms,
        "captured_at_ms": captured_at_ms,
        "received_at_ms": received_at_ms,
        "frozen_basic_contract_count": len(frozen_members),
        "current_basic_contract_count": metrics["current_basic_contract_count"],
        "catalog_rows": metrics["catalog_rows"],
        "frozen_scope_members_digest_sha256": _digest(sorted(frozen_members)),
        "current_provider_negative_symbols": negative,
        "current_metadata_missing_fields_symbols": missing,
        "negative_only_not_crypto_approval": True,
        "frozen_pit_authenticated": False,
        "marketwide_top50_verified": False,
        "orders_sent": False,
    }
    result = dict(record)
    result["sha256"] = sha256(_canonical(record)).hexdigest()
    validate_snapshot(result, frozen_members=frozen_members,
                      frozen_end_ms=frozen_end_ms)
    return result


def validate_snapshot(value: Any, *, frozen_members: frozenset[str],
                      frozen_end_ms: int) -> dict[str, Any]:
    if type(value) is not dict:
        raise AuditRejected("d264_snapshot_invalid")
    required = {
        "schema_version", "frozen_window_end_ms", "captured_at_ms",
        "received_at_ms", "frozen_basic_contract_count",
        "current_basic_contract_count", "catalog_rows",
        "frozen_scope_members_digest_sha256",
        "current_provider_negative_symbols",
        "current_metadata_missing_fields_symbols",
        "negative_only_not_crypto_approval", "frozen_pit_authenticated",
        "marketwide_top50_verified", "orders_sent", "sha256",
    }
    if set(value) != required:
        raise AuditRejected("d264_fields_invalid")
    neg = _validate_symbols(value["current_provider_negative_symbols"], allow_empty=True)
    missing = _validate_symbols(value["current_metadata_missing_fields_symbols"], allow_empty=True)
    if (set(neg) & set(missing)
            or not set(neg).issubset(frozen_members)
            or not set(missing).issubset(frozen_members)):
        raise AuditRejected("d264_membership_invalid")
    times = (value["frozen_window_end_ms"],
             value["captured_at_ms"], value["received_at_ms"])
    if (any(type(t) is not int or t <= 0 for t in times)
            or times[0] != frozen_end_ms
            or not times[0] < times[1] <= times[2]
            or times[2] - times[1] > 120_000
            or type(value["frozen_basic_contract_count"]) is not int
            or value["frozen_basic_contract_count"] != len(frozen_members)
            or type(value["current_basic_contract_count"]) is not int
            or value["current_basic_contract_count"] != len(frozen_members)
            or type(value["catalog_rows"]) is not int
            or not len(frozen_members) <= value["catalog_rows"] <= 1000
            or value["schema_version"] != SCHEMA
            or value["frozen_scope_members_digest_sha256"] != _digest(sorted(frozen_members))
            or value["negative_only_not_crypto_approval"] is not True
            or value["frozen_pit_authenticated"] is not False
            or value["marketwide_top50_verified"] is not False
            or value["orders_sent"] is not False):
        raise AuditRejected("d264_provenance_invalid")
    h = value["sha256"]
    rest = {k: v for k, v in value.items() if k != "sha256"}
    if type(h) is not str or h != sha256(_canonical(rest)).hexdigest():
        raise AuditRejected("d264_hash_invalid")
    return value


def private_path(directory: Path) -> Path:
    if not isinstance(directory, Path) or not directory.is_absolute():
        raise AuditRejected("d264_path_invalid")
    _strict_owner(directory.parent, directory=True)
    _strict_owner(directory, directory=True)
    return directory / FILE_NAME


def save_new_snapshot(directory: Path, value: dict) -> None:
    """Atomic no-clobber publish. Crash leaves no usable partial final file."""
    target = private_path(directory)
    if target.exists() or target.is_symlink():
        raise AuditRejected("d264_snapshot_already_exists")
    payload = _canonical(value)
    if not 0 < len(payload) <= MAX_FILE_BYTES:
        raise AuditRejected("d264_size_invalid")
    temp = directory / (".d264-stage-" + secrets.token_hex(10))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, target, follow_symlinks=False)
        dir_fd = os.open(directory, os.O_RDONLY |
                         getattr(os, "O_DIRECTORY", 0) |
                         getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        temp.unlink(missing_ok=True)


def _load_private(directory: Path, members: frozenset[str], frozen_end: int) -> dict:
    target = private_path(directory)
    _strict_owner(target, directory=False)
    if target.stat().st_size > MAX_FILE_BYTES:
        raise AuditRejected("d264_size_invalid")
    raw = target.read_bytes()
    if len(raw) != target.stat().st_size:
        raise AuditRejected("d264_size_changed")
    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise AuditRejected("d264_duplicate_json_key")
            result[key] = item
        return result
    try:
        obj = json.loads(raw, object_pairs_hook=reject_duplicates,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise AuditRejected("d264_invalid_json") from None
    return validate_snapshot(obj, frozen_members=members,
                             frozen_end_ms=frozen_end)


def _default() -> dict:
    return {
        "schema_version": SCHEMA,
        "status": "abstain",
        "requests_attempted": 0,
        "network_accessed": False,
        "database_modified": False,
        "orders_sent": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "metadata_pit_valid_for_frozen_window": False,
        "current_eligible_contracts_verified": 0,
        "continuous_collector_verified": False,
    }


def replay_private_snapshot(directory: Path, *,
                            owner_ok: bool | None = None,
                            include_private_symbols: bool = False) -> dict:
    """No GET. A contemporary veto yields only an exploratory ranking."""
    out = _default()
    allowed = (os.name == "posix" and fcntl is not None
               and os.getuid() == os.geteuid() and os.geteuid() != 0
               ) if owner_ok is None else owner_ok
    if not allowed or type(include_private_symbols) is not bool:
        out["failure_code"] = "d264_owner_or_optin_invalid"
        return out
    try:
        private_path(directory)
        db_path, lock_path = directory / _DB, directory / _LOCK
        _strict_owner(db_path, directory=False)
        _strict_owner(lock_path, directory=False)
        if not 0 < db_path.stat().st_size <= MAX_DB_BYTES:
            raise AuditRejected("d264_db_size_invalid")
        with open(lock_path, "rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro",
                                         uri=True, timeout=0.1)) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise AuditRejected("d264_db_integrity_invalid")
                proof = _replay(db)
                if proof["remaining_contracts"]:
                    raise AuditRejected("d264_frozen_scope_incomplete")
                members = frozenset(json.loads(db.execute(
                    "SELECT members_json FROM scope WHERE id=1"
                ).fetchone()[0]))
                snap = _load_private(directory, members,
                                     proof["capture_window_end_ms"])
                totals: dict[str, Decimal] = {}
                with localcontext(_MATH):
                    for symbol, amount in db.execute(
                        "SELECT symbol,quote_turnover FROM candles "
                        "ORDER BY symbol,open_ms"
                    ):
                        if type(symbol) is not str or type(amount) is not str:
                            raise AuditRejected("d264_turnover_storage_invalid")
                        totals[symbol] = totals.get(symbol, Decimal(0)) + _dec(amount)
                ordered = sorted(totals, key=lambda s: (-totals[s], s))
                if (len(ordered) != proof["completed_contracts"]
                        or _digest([[s, str(totals[s])] for s in ordered[:50]]) !=
                        proof["top50_complete_subset_digest_sha256"]):
                    raise AuditRejected("d264_rank_digest_invalid")
                negatives_current = frozenset(
                    snap["current_provider_negative_symbols"]
                )
                exclusions = negatives_current | frozenset(NEGATIVE_EVIDENCE)
                frontier = tuple(s for s in ordered if s not in exclusions)[:50]
                if len(frontier) != 50:
                    raise AuditRejected("d264_too_few_research_candidates")
                archive = load_registry_json(REGISTRY_FILE.read_bytes())
                refs = archive.verified_crypto_bases
                def category(symbol):
                    return research_category(symbol, symbol[:-4] in refs)
                categories = [category(s) for s in frontier]
                archived = categories.count("archived_crypto_reference_only")
                hypotheses = sum(c in (
                    "crypto_token_candidate_unverified",
                    "ticker_collision_unresolved",
                    "tokenized_gold_policy_gate",
                ) for c in categories)
                out.update({
                    "status": "retrospective_negative_overlay_research_only",
                    "frozen_capture_window_end_ms": proof["capture_window_end_ms"],
                    "current_metadata_observed_at_ms": snap["received_at_ms"],
                    "frozen_complete_contracts": len(ordered),
                    "current_provider_negative_count": len(negatives_current),
                    "documented_negative_count": len(NEGATIVE_EVIDENCE),
                    "excluded_complete_contracts_current_or_documented_count":
                        len(set(ordered) & exclusions),
                    "research_frontier_count": len(frontier),
                    "research_frontier_archived_reference_count": archived,
                    "research_frontier_candidate_hypothesis_count": hypotheses,
                    "research_frontier_unresolved_count":
                        len(frontier) - archived - hypotheses,
                    "research_frontier_digest_sha256": _digest([
                        [s, str(totals[s])] for s in frontier
                    ]),
                    "frozen_raw_top50_digest_sha256":
                        proof["top50_complete_subset_digest_sha256"],
                    "private_snapshot_sha256": snap["sha256"],
                    "current_provider_negative_exclusions_not_pit": True,
                    "research_frontier_not_eligible_top50": True,
                })
                out["frontier_identity_review_worklist"] = frontier_review_worklist(
                    frontier,
                    frozen_market_window_end_ms=proof["capture_window_end_ms"],
                    archived_crypto_bases=frozenset(refs),
                    include_private_symbols=include_private_symbols,
                )
                if include_private_symbols:
                    out["private_research_symbols_only"] = [
                        {"position": i, "symbol": s,
                         "category_unverified": category(s)}
                        for i, s in enumerate(frontier, 1)
                    ]
    except AuditRejected as ex:
        out["failure_code"] = str(ex)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        out["failure_code"] = "d264_storage_or_validation_invalid"
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--include-private-symbols", action="store_true")
    args = parser.parse_args(argv)
    result = replay_private_snapshot(
        args.directory, include_private_symbols=args.include_private_symbols,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "retrospective_negative_overlay_research_only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
