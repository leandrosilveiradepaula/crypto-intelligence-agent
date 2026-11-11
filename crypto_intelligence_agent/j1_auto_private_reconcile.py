"""J1 D281: reconcile today's automatic USDT screen against frozen private census.

Strict owner-only READ-ONLY integrity replay of the existing D256 marketwide
SQLite plus immutable D264 negative overlay. No network, database writes or
historical PIT crypto-identity promotion. The caller separately obtains a
current complete-catalog candidate pool via D280 and supplies it in memory.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from decimal import Decimal
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None

from .j1_auto_usdt_perp import (
    AutomaticPerpResearchPool, rank_auto_candidates_closed24h_offline,
)
from .market_data import DataValidationError
from scripts.audit_bybit_marketwide_closed24h import (
    HOUR_MS, MAX_DB_BYTES, _strict_owner, _dec, _digest,
)
from scripts.audit_j1_marketwide_checkpoint import (
    _DB, _LOCK, _replay, AuditRejected,
)
from scripts.j1_d264_private_metadata_snapshot import _load_private


def _blank(code: str = "abstain") -> dict[str, Any]:
    return {
        "schema_version": "j1-automatic-research-private-d256-d264-join-v1",
        "status": code,
        "network_requests": 0,
        "database_modified": False,
        "orders_sent": False,
        "marketwide_top50_verified": False,
        "historical_pit_crypto_identity_verified": False,
        "current_candidates_are_research_only": True,
    }


def reconcile_auto_pool_with_private_census(
    pool: AutomaticPerpResearchPool, directory: Path, *,
    allow_private_readonly_audit: bool = False,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    """Crosscheck 24 closed hours without recapturing 819 market rows.

    The fresh 2026 catalog is observed AFTER the D256 historic window and
    must never retroactively certify the historic crypto membership.
    Explicit D264 retrospective TradFi negatives are vetoed regardless of
    new optional metadata being empty.
    """
    if allow_private_readonly_audit is not True:
        return _blank("owner_optin_required")
    if (type(pool) is not AutomaticPerpResearchPool
            or not isinstance(directory, Path)
            or not directory.is_absolute()):
        return _blank("invalid_configuration")
    owner = (os.name == "posix" and fcntl is not None
             and os.getuid() == os.geteuid() and os.geteuid() != 0
             ) if owner_ok is None else owner_ok
    if not owner or fcntl is None:
        return _blank("owner_required")
    out = _blank()
    stage = "private_files"
    try:
        _strict_owner(directory.parent, directory=True)
        _strict_owner(directory, directory=True)
        path, lock = directory / _DB, directory / _LOCK
        _strict_owner(path, directory=False)
        _strict_owner(lock, directory=False)
        if not 0 < path.stat().st_size <= MAX_DB_BYTES:
            raise AuditRejected("private_database_size_invalid")
        fd = os.open(lock, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                raise AuditRejected("private_census_writer_active") from None
            stage = "integrity_replay"
            with closing(sqlite3.connect(
                path.as_uri() + "?mode=ro", uri=True, timeout=0.1
            )) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise AuditRejected("private_database_integrity_invalid")
                proof = _replay(db)
                if proof["remaining_contracts"]:
                    raise AuditRejected("private_census_incomplete")
                end = proof["capture_window_end_ms"]
                if pool.observed_at_ms < end + 1000:
                    raise AuditRejected("today_catalog_not_later_than_frozen_window")
                scope = db.execute(
                    "SELECT members_json FROM scope WHERE id=1"
                ).fetchone()
                if scope is None:
                    raise AuditRejected("private_scope_missing")
                members = frozenset(json.loads(scope[0]))
                if len(members) != proof["basic_eligible_contracts"]:
                    raise AuditRejected("private_scope_count_mismatch")
                stage = "overlay_replay"
                snap = _load_private(directory, members, end)
                if pool.observed_at_ms <= snap["received_at_ms"]:
                    raise AuditRejected("current_catalog_predates_overlay")
                retrospective_negatives = frozenset(
                    snap["current_provider_negative_symbols"]
                )
                visible_candidates = frozenset(pool.candidate_symbols)
                vetoed = visible_candidates & retrospective_negatives
                screened = tuple(sorted(visible_candidates - vetoed))
                filtered_pool = replace(pool, candidate_symbols=screened)
                stage = "closed_hour_join"
                mapping: dict[str, list[tuple[int, Decimal]]] = {}
                # Only the frozen members can have historic D256 candles.
                for sym, opened, amount in db.execute(
                    "SELECT symbol,open_ms,quote_turnover FROM candles "
                    "ORDER BY symbol,open_ms"
                ):
                    if sym in visible_candidates and sym not in vetoed:
                        mapping.setdefault(sym, []).append(
                            (opened, _dec(amount, field="quote_turnover"))
                        )
                # _replay validated each stored short series and its hash.
                # Do not synthesize missing bars or assign turnover zero.
                rank = rank_auto_candidates_closed24h_offline(
                    filtered_pool,
                    closed_hour_end_ms=end,
                    closed_candle_turnovers={
                        key: tuple(value) for key, value in mapping.items()
                    },
                )
                raw_covered = frozenset(mapping)
                raw_catalog_overlap = members & visible_candidates
                frozen_unmatched = members - visible_candidates
                today_without_frozen = visible_candidates - members
                # Ranking reproducibility proof: recompute hash from already
                # verified D256 source and compare to D281's published digest.
                rank_payload = [[s, format(total, "f")]
                                for s, total in rank.ranked]
                rank_hash = sha256(json.dumps(
                    rank_payload, ensure_ascii=True, separators=(",", ":")
                ).encode("ascii")).hexdigest()
                if rank.sanitized_report()["rank_digest_sha256"] != rank_hash:
                    raise AuditRejected("automatic_research_rank_digest_mismatch")
                if (len(raw_covered) > proof["completed_contracts"]
                        or len(screened) !=
                        len(visible_candidates) - len(vetoed)
                        or len(frozen_unmatched) + len(raw_catalog_overlap)
                        != len(members)
                        or len(rank.ranked) > 50):
                    raise AuditRejected("automatic_research_overlap_inconsistent")
                out.update({
                    "status": "retrospective_auto_crypto_usdt_overlap_research_only",
                    "frozen_window_end_ms": end,
                    "today_catalog_observed_at_ms": pool.observed_at_ms,
                    "d264_metadata_observed_at_ms": snap["received_at_ms"],
                    "d256_sqlite_completed_contracts": proof["completed_contracts"],
                    "d256_sqlite_incomplete_contracts":
                        proof["incomplete_24h_contracts"],
                    "d256_catalog_contracts": len(members),
                    "today_provisional_pool_contracts": len(visible_candidates),
                    "d264_persisted_tradfi_negative_vetoes_applied": len(vetoed),
                    "retrospective_candidates_after_veto": len(screened),
                    "frozen_overlap_candidates": len(raw_catalog_overlap),
                    "frozen_contracts_not_in_today_provisional_pool":
                        len(frozen_unmatched),
                    "today_candidates_not_in_frozen_catalog":
                        len(today_without_frozen),
                    "complete_24h_positive_turnover_overlap":
                        rank.covered_count,
                    "incomplete_or_unavailable_24h_candidates":
                        rank.insufficient_count,
                    "zero_24h_turnover_candidates":
                        rank.zero_turnover_count,
                    "retrospective_top50_research_size": len(rank.ranked),
                    "retrospective_top50_research_digest_sha256": rank_hash,
                    "current_catalog_candidate_digest_sha256":
                        pool.sanitized_report()["candidate_digest_sha256"],
                    "d264_snapshot_digest_sha256": snap["sha256"],
                    "frozen_census_raw_top50_digest_sha256":
                        proof["top50_complete_subset_digest_sha256"],
                    "today_metadata_not_historical_pit_proof": True,
                    "full_current_market_top50_not_proven": True,
                })
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except (AuditRejected, DataValidationError, OSError, sqlite3.Error,
            ValueError, TypeError, OverflowError):
        out = _blank()
        out["failure_stage"] = stage
        out["failure_code"] = "private_reconciliation_" + stage + "_rejected"
    return out
