"""Owner-only, network-free, read-only audit of the J1 marketwide 24h census.

Replays every saved candle and short observation against the existing J1
validators. A verified SQLite snapshot is NOT a verified HTTP request trace,
independent crypto identity, or authorization for a live Top50.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from decimal import Decimal, InvalidOperation, localcontext
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

try:
    import fcntl
except ImportError:  # Windows CI import only; owner audit remains disabled.
    fcntl = None

from scripts.audit_bybit_marketwide_closed24h import (
    HOUR_MS, MAX_DB_BYTES, MAX_ROWS, CensusAbstain, _MATH, _closed_candles,
    _dec, _digest, _short_digest, _stable_json, _strict_owner,
)

_DB = "j1-marketwide-closed24h.sqlite"
_LOCK = ".j1-marketwide-closed24h.lock"


class AuditRejected(ValueError):
    """Fixed diagnostic; never include a symbol, SQL payload, or filename."""


def _blank() -> dict[str, Any]:
    return {
        "schema_version": "j1-marketwide-readonly-proof-v1",
        "status": "abstain",
        "requests_attempted": 0,
        "network_accessed": False,
        "database_modified": False,
        "orders_sent": False,
        "capture_window_end_ms": None,
        "catalog_rows": 0,
        "basic_eligible_contracts": 0,
        "completed_contracts": 0,
        "validated_closed_1h_rows": 0,
        "incomplete_24h_contracts": 0,
        "incomplete_24h_rows": 0,
        "inspected_contracts": 0,
        "remaining_contracts": 0,
        "top50_complete_subset_count": 0,
        "top50_complete_subset_digest_sha256": None,
        "full_basic_contract_24h_ranking_complete": False,
        "crypto_identity_independently_verified": False,
        "marketwide_top50_verified": False,
        "continuous_collector_verified": False,
        "request_trace_complete_verified": False,
        "minimum_unattributed_inspections": None,
    }


def _members_from_scope(text: object, fingerprint: object) -> tuple[str, ...]:
    try:
        rows = json.loads(text) if type(text) is str else None
    except (ValueError, TypeError, RecursionError):
        raise AuditRejected("scope_invalid") from None
    if (type(rows) is not list or not 50 <= len(rows) <= MAX_ROWS
            or any(type(s) is not str for s in rows)):
        raise AuditRejected("scope_invalid")
    members = tuple(rows)
    if tuple(sorted(set(members))) != members or _stable_json(members) != text:
        raise AuditRejected("scope_invalid")
    if any(
        not 5 <= len(s) <= 32 or not s.endswith("USDT")
        or not s.isascii() or not s.isalnum() or s != s.upper()
        for s in members
    ):
        raise AuditRejected("scope_invalid")
    rebuilt = [
        [s, s[:-4], "USDT", "USDT", "LinearPerpetual", "Trading"]
        for s in members
    ]
    if type(fingerprint) is not str or fingerprint != _digest(rebuilt):
        raise AuditRejected("scope_fingerprint_invalid")
    return members


def _replay(db: sqlite3.Connection) -> dict[str, Any]:
    report = _blank()
    scopes = db.execute(
        "SELECT window_end_ms,catalog_rows,scope_sha256,members_json FROM scope"
    ).fetchall()
    if len(scopes) != 1:
        raise AuditRejected("scope_invalid")
    end_ms, catalog_rows, fingerprint, members_json = scopes[0]
    members = _members_from_scope(members_json, fingerprint)
    if (type(end_ms) is not int or end_ms < 1_600_000_000_000
            or end_ms % HOUR_MS or type(catalog_rows) is not int
            or not len(members) <= catalog_rows <= MAX_ROWS):
        raise AuditRejected("scope_invalid")
    known = set(members)
    rows = db.execute(
        "SELECT symbol,open_ms,open,high,low,close,base_volume,quote_turnover "
        "FROM candles ORDER BY symbol,open_ms DESC"
    ).fetchall()
    if len(rows) > len(members) * 24:
        raise AuditRejected("stored_candles_invalid")
    groups: dict[str, list[tuple[Any, ...]]] = {}
    for row in rows:
        symbol, open_ms, *fields = row
        if (type(symbol) is not str or symbol not in known
                or type(open_ms) is not int
                or any(type(f) is not str for f in fields)):
            raise AuditRejected("stored_candles_invalid")
        groups.setdefault(symbol, []).append(row)
    totals: dict[str, Decimal] = {}
    for symbol, entries in groups.items():
        if len(entries) != 24:
            raise AuditRejected("stored_candles_invalid")
        public_rows = [[str(row[1]), *row[2:]] for row in entries]
        try:
            checked = _closed_candles({
                "retCode": 0, "result": {
                    "category": "linear", "symbol": symbol, "list": public_rows,
                },
            }, symbol, end_ms)
            with localcontext(_MATH):
                totals[symbol] = sum(
                    (_dec(row[-1]) for row in checked), Decimal(0)
                )
        except (CensusAbstain, InvalidOperation):
            raise AuditRejected("stored_candles_invalid") from None
    short_rows = db.execute(
        "SELECT symbol,launch_hint_ms,observed_count,candles_json,digest_sha256 "
        "FROM incomplete ORDER BY symbol"
    ).fetchall()
    shorts: dict[str, int] = {}
    incomplete_rows = 0
    for symbol, hint, count, encoded, fingerprint in short_rows:
        if (type(symbol) is not str or symbol not in known
                or symbol in totals or symbol in shorts
                or type(count) is not int or not 0 <= count < 24
                or (hint is not None and
                    (type(hint) is not int or hint < 1_600_000_000_000))
                or type(encoded) is not str or type(fingerprint) is not str):
            raise AuditRejected("stored_shorts_invalid")
        try:
            bars = json.loads(encoded)
            if (type(bars) is not list or len(bars) != count
                    or _stable_json(bars) != encoded):
                raise AuditRejected("stored_shorts_invalid")
            checked = _closed_candles({
                "retCode": 0, "result": {
                    "category": "linear", "symbol": symbol, "list": bars,
                },
            }, symbol, end_ms, allow_short=True)
            if (len(checked) != count or
                    fingerprint != _short_digest(symbol, end_ms, hint, checked)):
                raise AuditRejected("stored_shorts_invalid")
        except (ValueError, TypeError, RecursionError, CensusAbstain):
            raise AuditRejected("stored_shorts_invalid") from None
        shorts[symbol] = count
        incomplete_rows += count
    report.update({
        "capture_window_end_ms": end_ms,
        "catalog_rows": catalog_rows,
        "basic_eligible_contracts": len(members),
        "completed_contracts": len(totals),
        "validated_closed_1h_rows": len(totals) * 24,
        "incomplete_24h_contracts": len(shorts),
        "incomplete_24h_rows": incomplete_rows,
        "inspected_contracts": len(totals) + len(shorts),
        "remaining_contracts": len(members) - len(totals) - len(shorts),
    })
    if len(totals) >= 50:
        ordered = sorted(totals, key=lambda s: (-totals[s], s))
        report["top50_complete_subset_count"] = 50
        report["top50_complete_subset_digest_sha256"] = _digest([
            [s, str(totals[s])] for s in ordered[:50]
        ])
    if report["remaining_contracts"] > 0:
        report["status"] = "basic_survey_partial_integrity_pass_unverified"
    elif shorts:
        report["status"] = "basic_survey_integrity_pass_incomplete_unverified"
    else:
        report["status"] = "basic_rank_integrity_pass_crypto_unverified"
        report["full_basic_contract_24h_ranking_complete"] = True
    return report


def audit_private_checkpoint(
    directory: Path, *,
    previous_inspected: int | None = None,
    last_run_requests: int | None = None,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    """Replay an existing private DB without any HTTP calls or SQLite writes.

    Optional previous/last values are unverified operator assertions. They can
    disprove a complete adjacent-run trace, but never prove such a trace.
    """
    report = _blank()
    stage = "owner_gate"
    allowed = (
        os.name == "posix" and fcntl is not None
        and os.getuid() == os.geteuid() and os.geteuid() != 0
    ) if owner_ok is None else owner_ok
    if not allowed:
        report["failure_stage"] = stage
        report["failure_code"] = "owner_gate_required"
        return report
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or (previous_inspected is None) != (last_run_requests is None)
            or (previous_inspected is not None
                and (type(previous_inspected) is not int
                     or not 0 <= previous_inspected <= MAX_ROWS))
            or (last_run_requests is not None
                and (type(last_run_requests) is not int
                     or not 1 <= last_run_requests <= 500))):
        report["failure_stage"] = stage
        report["failure_code"] = "audit_configuration_invalid"
        return report
    try:
        stage = "private_files"
        _strict_owner(directory.parent, directory=True)
        _strict_owner(directory, directory=True)
        db_path = directory / _DB
        lock_path = directory / _LOCK
        _strict_owner(db_path, directory=False)
        _strict_owner(lock_path, directory=False)
        if not 0 < db_path.stat().st_size <= MAX_DB_BYTES:
            raise AuditRejected("database_size_invalid")
        lock_fd = os.open(
            lock_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                raise AuditRejected("writer_active") from None
            stage = "sqlite_replay"
            with closing(sqlite3.connect(
                db_path.as_uri() + "?mode=ro", uri=True, timeout=0.1
            )) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise AuditRejected("sqlite_integrity_invalid")
                report = _replay(db)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        stage = "request_trace"
        if previous_inspected is not None:
            if previous_inspected > report["inspected_contracts"]:
                raise AuditRejected("request_trace_inputs_invalid")
            delta = report["inspected_contracts"] - previous_inspected
            # Each new inspected contract needs at least one kline GET.
            # The observed invocation also needs one catalog GET.
            max_new_from_last = last_run_requests - 1
            report["minimum_unattributed_inspections"] = max(
                0, delta - max_new_from_last
            )
            report["adjacent_run_counts_consistent"] = (
                report["minimum_unattributed_inspections"] == 0
            )
            report["request_trace_inputs_operator_supplied"] = True
            # Counts alone cannot establish actual requests, even if equal.
            report["request_trace_complete_verified"] = False
    except AuditRejected as error:
        # Fixed authored errors; never echo raw SQL, symbols, exceptions or paths.
        report["status"] = "abstain"
        report["failure_stage"] = stage
        report["failure_code"] = str(error)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        report["status"] = "abstain"
        report["failure_stage"] = stage
        report["failure_code"] = "storage_or_schema_invalid"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--previous-inspected", type=int)
    parser.add_argument("--last-run-requests", type=int)
    args = parser.parse_args(argv)
    report = audit_private_checkpoint(
        args.directory, previous_inspected=args.previous_inspected,
        last_run_requests=args.last_run_requests,
    )
    print(_stable_json(report))
    return 2 if report["status"] == "abstain" else 0


if __name__ == "__main__":
    raise SystemExit(main())
