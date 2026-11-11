"""J1/#319: read-only bridge from the preexisting owner-only marketwide SQLite.

No new collector, SQLite writes, provider HTTP, identity reclassification,
timer or orders. Reuse D256 replay before ranking. Unapproved identities are
*not* inserted as positive crypto by this bridge.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, localcontext
import os
from pathlib import Path
import sqlite3
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None

from scripts.audit_j1_marketwide_checkpoint import (
    AuditRejected, _DB, _LOCK, _replay,
)
from scripts.audit_bybit_marketwide_closed24h import (
    MAX_DB_BYTES, _MATH, _dec, _strict_owner,
)
from .j1_top50_rank_pressure import (
    Top50PressureRejected, pressure_from_closed_turnover,
)


def _empty(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-top50-private-pressure-bridge-v1",
        "status": status,
        "capture_window_end_ms": None,
        "catalog_members": 0,
        "completed_contracts": 0,
        "short_contracts": 0,
        "remaining_contracts": 0,
        "marketwide_top50_verified": False,
        "identity_pit_authenticated": False,
        "orders_sent": False,
        "trading_enabled": False,
        "database_modified": False,
        "network_requests": 0,
    }


def audit_private_top50_pressure(
    directory: Path, *, allow_private_readonly_audit: bool = False,
    include_public_symbols: bool = False,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    """Rank review pressure from private 24h candles; none is identity certified.

    All symbols start unresolved. Their order is useful for the review queue,
    not for marketwide eligibility. Do not use current retrospective TradFi
    markers to claim independently confirmed historical negatives.
    """
    if allow_private_readonly_audit is not True:
        return _empty("owner_optin_required")
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or type(include_public_symbols) is not bool):
        return _empty("invalid_configuration")
    allowed = (os.name == "posix" and fcntl is not None
               and os.getuid() == os.geteuid() and os.geteuid() != 0
               ) if owner_ok is None else owner_ok
    if not allowed or fcntl is None:
        return _empty("owner_required")
    out = _empty("abstain")
    try:
        _strict_owner(directory.parent, directory=True)
        _strict_owner(directory, directory=True)
        path = directory / _DB
        lock = directory / _LOCK
        _strict_owner(path, directory=False)
        _strict_owner(lock, directory=False)
        if not 0 < path.stat().st_size <= MAX_DB_BYTES:
            raise AuditRejected("database_size_invalid")
        fd = os.open(lock, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                raise AuditRejected("writer_active") from None
            with closing(sqlite3.connect(path.as_uri()+"?mode=ro",
                                         uri=True, timeout=0.1)) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise AuditRejected("sqlite_integrity_invalid")
                proof = _replay(db)
                if proof["remaining_contracts"]:
                    raise AuditRejected("census_not_finished")
                scope = db.execute("SELECT members_json FROM scope").fetchone()
                if scope is None:
                    raise AuditRejected("scope_missing")
                import json
                catalog = json.loads(scope[0])
                totals: dict[str, Decimal] = {}
                with localcontext(_MATH):
                    for symbol, value in db.execute(
                        "SELECT symbol,quote_turnover FROM candles ORDER BY symbol,open_ms"
                    ):
                        if type(symbol) is not str or type(value) is not str:
                            raise AuditRejected("turnover_invalid")
                        totals[symbol] = totals.get(symbol, Decimal(0)) + _dec(value)
                # Replayed every 24-row series above; compare the independent
                # D256 rank digest, including ordering and Decimal spelling.
                from scripts.audit_bybit_marketwide_closed24h import _digest
                ranked = sorted(totals, key=lambda s: (-totals[s], s))
                if (len(totals) != proof["completed_contracts"]
                        or _digest([[s, str(totals[s])] for s in ranked[:50]]) !=
                            proof["top50_complete_subset_digest_sha256"]):
                    raise AuditRejected("rank_digest_invalid")
                pressure = pressure_from_closed_turnover(
                    catalog_symbols=catalog,
                    closed_turnover_usdt=totals,
                    positively_reviewed_crypto=(),
                    independently_excluded_noncrypto=(),
                    include_public_symbols=include_public_symbols,
                )
                out.update(pressure)
                out.update({
                    "schema_version": "j1-top50-private-pressure-bridge-v1",
                    "status": "existing_census_rank_review_queue_unverified",
                    "capture_window_end_ms": proof["capture_window_end_ms"],
                    "catalog_members": proof["basic_eligible_contracts"],
                    "completed_contracts": proof["completed_contracts"],
                    "short_contracts": proof["incomplete_24h_contracts"],
                    "remaining_contracts": proof["remaining_contracts"],
                    "identity_reviewed_positive_count": 0,
                    "retrospective_negative_auto_promoted_count": 0,
                    "marketwide_top50_verified": False,
                    "trading_enabled": False,
                })
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except (AuditRejected, Top50PressureRejected, OSError,
            sqlite3.Error, ValueError, TypeError, OverflowError):
        out = _empty("abstain")
    return out
