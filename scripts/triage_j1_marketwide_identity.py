"""D257: owner-only offline ranking/identity gap triage on private J1 census.

Reports which portion of the COMPLETE 24h-volume leaderboard has an identity
reference in the archived registry. Archived references do not approve a
current crypto-only universe or justify excluding the unresolved contracts.
No HTTP, writes, trading or promotion to canonical history.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

try:
    import fcntl
except ImportError:  # Windows tests may import; owner-only execution off.
    fcntl = None

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, load_registry_json,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.audit_bybit_marketwide_closed24h import (
    _MATH, _dec, _digest, _strict_owner, _stable_json, MAX_DB_BYTES,
)
from scripts.audit_j1_marketwide_checkpoint import (
    _replay, _DB, _LOCK, AuditRejected,
)

MAX_REGISTRY_AGE_MS = 7 * 86_400_000
REGISTRY_FILE = (
    Path(__file__).resolve().parent.parent /
    "registries" / "crypto-bases-52-20261029-v4.json"
)


def _empty() -> dict[str, Any]:
    return {
        "schema_version": "j1-marketwide-identity-triage-v1",
        "status": "abstain",
        "requests_attempted": 0, "network_accessed": False,
        "database_modified": False, "orders_sent": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "continuous_collector_verified": False,
        "live_identity_approved": False,
        "source_authentication_verified": False,
        "full_basic_contract_24h_ranking_complete": False,
        "historical_registry_temporally_usable": False,
        "closed_24h_rank_promoted": False,
    }


def _rank_with_registry(db: sqlite3.Connection, registry_bytes: bytes) -> dict[str, Any]:
    # Reuse D256's full SQLite replay before accessing turnover aggregates.
    proof = _replay(db)
    if proof["remaining_contracts"] != 0:
        raise AuditRejected("survey_not_fully_inspected")
    if proof["completed_contracts"] < 50:
        raise AuditRejected("not_enough_complete_contracts")
    snapshot = load_registry_json(registry_bytes)
    end = proof["capture_window_end_ms"]
    known_at_window = snapshot.observed_at_ms <= end
    temporally_usable = False
    if known_at_window:
        try:
            CryptoRegistryHistory((snapshot,)).as_of(
                end, max_age_ms=MAX_REGISTRY_AGE_MS
            )
            temporally_usable = True
        except DataValidationError:
            pass

    groups: dict[str, list[str]] = {}
    for symbol, turnover in db.execute(
        "SELECT symbol,quote_turnover FROM candles ORDER BY symbol,open_ms"
    ):
        if type(symbol) is not str or type(turnover) is not str:
            raise AuditRejected("turnover_storage_invalid")
        groups.setdefault(symbol, []).append(turnover)
    totals: dict[str, Decimal] = {}
    with localcontext(_MATH):
        for symbol, amounts in groups.items():
            if len(amounts) != 24:
                raise AuditRejected("turnover_storage_invalid")
            totals[symbol] = sum((_dec(x) for x in amounts), Decimal(0))
    ordered = sorted(totals, key=lambda s: (-totals[s], s))
    digest = _digest([[s, str(totals[s])] for s in ordered[:50]])
    if digest != proof["top50_complete_subset_digest_sha256"]:
        raise AuditRejected("ranking_digest_mismatch")

    known_bases = snapshot.verified_crypto_bases
    def referenced(symbol: str) -> bool:
        return symbol.endswith("USDT") and symbol[:-4] in known_bases

    reviewed_complete = sum(referenced(s) for s in ordered)
    reviewed_top50 = sum(referenced(s) for s in ordered[:50])
    # The archived corpus may help select the next identities to REVIEW,
    # but we neither label them "verified" at this timestamp nor trade them.
    candidates = [s for s in ordered if not referenced(s)]
    shorts = [
        s for (s,) in db.execute("SELECT symbol FROM incomplete ORDER BY symbol")
    ]
    report = _empty()
    report.update({
        "status": (
            "identity_review_queue_stale_registry_no_go" if not temporally_usable
            else "identity_review_queue_registry_pit_recheck_required"
        ),
        "capture_window_end_ms": end,
        "basic_eligible_contracts": proof["basic_eligible_contracts"],
        "inspected_contracts": proof["inspected_contracts"],
        "complete_24h_contracts": len(ordered),
        "incomplete_24h_contracts": len(shorts),
        "incomplete_24h_rows": proof["incomplete_24h_rows"],
        "historical_registry_assets": len(snapshot.assets),
        "historical_registry_digest_sha256": snapshot.sha256_digest,
        "historical_registry_observed_at_ms": snapshot.observed_at_ms,
        "historical_registry_age_ms": end - snapshot.observed_at_ms,
        "historical_registry_known_at_window": known_at_window,
        "historical_registry_temporally_usable": temporally_usable,
        "historical_registry_overlap_complete_count": reviewed_complete,
        "historical_registry_overlap_top50_subset_count": reviewed_top50,
        "historical_registry_overlap_incomplete_count": sum(
            referenced(s) for s in shorts
        ),
        "historical_registry_unmatched_complete_count": len(candidates),
        "closed_top50_subset_unmatched_registry_count": 50 - reviewed_top50,
        "closed_top50_subset_digest_sha256": digest,
        "identity_review_priority_count": len(candidates),
        "identity_review_priority_digest_sha256": _digest([
            [s, str(totals[s])] for s in candidates
        ]),
        # Current eligibility requires independent fresh source checks.
        "current_eligible_contracts_verified": 0,
        "full_basic_contract_24h_ranking_complete": False
            if shorts else proof["full_basic_contract_24h_ranking_complete"],
    })
    return report


def triage_checkpoint(
    directory: Path, *, owner_ok: bool | None = None,
    registry_path: Path = REGISTRY_FILE,
) -> dict[str, Any]:
    report = _empty()
    stage = "owner_gate"
    allowed = (
        os.name == "posix" and fcntl is not None
        and os.getuid() == os.geteuid() and os.geteuid() != 0
    ) if owner_ok is None else owner_ok
    if not allowed:
        report.update(failure_stage=stage, failure_code="owner_gate_required")
        return report
    if not isinstance(directory, Path) or not directory.is_absolute():
        report.update(failure_stage=stage, failure_code="audit_configuration_invalid")
        return report
    try:
        stage = "private_files"
        _strict_owner(directory.parent, directory=True)
        _strict_owner(directory, directory=True)
        db_path, lock_path = directory / _DB, directory / _LOCK
        _strict_owner(db_path, directory=False)
        _strict_owner(lock_path, directory=False)
        if not 0 < db_path.stat().st_size <= MAX_DB_BYTES:
            raise AuditRejected("database_size_invalid")
        stage = "registry"
        # Test injection is restricted to local fixtures; no HTTP is possible.
        registry = load_registry_json(registry_path.read_bytes())
        registry_bytes = registry_path.read_bytes()
        if load_registry_json(registry_bytes) != registry:
            raise AuditRejected("registry_changed_during_read")
        stage = "sqlite_replay"
        fd = os.open(lock_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                raise AuditRejected("writer_active") from None
            with closing(sqlite3.connect(
                db_path.as_uri() + "?mode=ro", uri=True, timeout=0.1
            )) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise AuditRejected("sqlite_integrity_invalid")
                report = _rank_with_registry(db, registry_bytes)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except AuditRejected as e:
        report.update(status="abstain", failure_stage=stage, failure_code=str(e))
    except (DataValidationError, OSError, sqlite3.Error, ValueError,
            TypeError, OverflowError, ArithmeticError):
        report.update(
            status="abstain", failure_stage=stage,
            failure_code="registry_or_storage_validation_invalid",
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    report = triage_checkpoint(args.directory)
    print(_stable_json(report))
    return 2 if report["status"] == "abstain" else 0


if __name__ == "__main__":
    raise SystemExit(main())
