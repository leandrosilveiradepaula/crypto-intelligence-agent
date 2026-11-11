"""J1/OPS2: read-only readiness of the *existing* two-contract REST journal.

No network, SQLite writes, systemctl, timer activation, or Top50 assertions.
A missed UTC hour is never fabricated as a published historical checkpoint.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from .j1_rest_incremental_owner import (
    HOUR_MS, MAX_CATCHUP_HOURS, _DB_NAME, _SHA, _SYM, _validate_cursor,
)
from scripts.audit_bybit_marketwide_closed24h import CensusAbstain, _dec, _strict_owner

SETTLE_MS = 60_000
LATEST_START_MS = 900_000
MAX_DB_BYTES = 512 * 1024 * 1024
# Default preserves the existing 2-member trial; research-only 1..50 allowed.
EXPECTED_MEMBERS = 2
MAX_RESEARCH_MEMBERS = 50
MAX_PUBLISHED = 4096


def _base(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1_rest_resume_readiness_v1",
        "status": status,
        "last_published_end_ms": None,
        "next_eligible_end_ms": None,
        "published_hours": 0,
        "historical_unpublished_hours": None,
        "historical_checkpoint_gaps_present": False,
        "stored_candles": 0,
        "reviewed_research_contracts": 0,
        "research_closed_24h_ranked_contracts": 0,
        "research_closed_24h_rank_digest_sha256": None,
        "research_closed_24h_window_end_ms": None,
        "rank_is_sample_only_not_marketwide": True,
        "hours_since_last_publication": None,
        "unobserved_closed_hours": None,
        "catchup_hours": None,
        "catchup_within_worker_limit": False,
        "journal_integrity_verified": False,
        "activation_authorized": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "source_authenticated": False,
        "signal_authorized": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
    }


def _next_safe_target(now_ms: int) -> int:
    """Next *scheduled* HH:02 deadline with M1's safe [HH:01,HH:15] window.

    At HH:00, the previous hour has just closed but cannot yet be fetched.
    At HH:16, the current hour's window is closed; the next target is HH+1.
    """
    hour = now_ms // HOUR_MS * HOUR_MS
    phase = now_ms - hour
    if phase < SETTLE_MS or phase > LATEST_START_MS:
        return hour + HOUR_MS if phase > LATEST_START_MS else hour
    return hour


def audit_existing_rest_resume(
    *, output_directory: Path, now_ms: int,
    allow_private_readonly_audit: bool = False,
    owner_ok: bool | None = None,
    expected_members: int = EXPECTED_MEMBERS,
) -> dict[str, Any]:
    """Read an owner-only research journal of 1..50 pinned members without IO writes.

    A catch-up window <=48h means only *capacity*, NOT approval to issue a
    request: unobserved UTC gaps require operator policy review before restart.
    A 48h gap exactly matches the worker bound; 49h is blocked.
    """
    out = _base("optin_required")
    if allow_private_readonly_audit is not True:
        return out
    if (type(now_ms) is not int or not 1_600_000_000_000 <= now_ms < 4_102_444_800_000
            or not isinstance(output_directory, Path)
            or not output_directory.is_absolute()
            or type(owner_ok) not in (bool, type(None))
            or type(expected_members) is not int
            or not 1 <= expected_members <= MAX_RESEARCH_MEMBERS):
        return _base("invalid_configuration")
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if owner is not True:
        return _base("owner_required")
    out = _base("journal_unavailable_or_integrity_blocked")
    try:
        if output_directory.is_symlink():
            return out
        _strict_owner(output_directory, directory=True)
        path = output_directory / _DB_NAME
        if path.is_symlink() or not path.is_file():
            return out
        _strict_owner(path, directory=False)
        if path.stat().st_size > MAX_DB_BYTES:
            return out
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                return out
            schema = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"scope", "cursor", "candles", "published_hour"} <= schema:
                return out
            scopes = db.execute(
                "SELECT id,scope_digest,members_json,initial_end_ms,halted_reason "
                "FROM scope ORDER BY id LIMIT 2").fetchall()
            if len(scopes) != 1 or type(scopes[0][0]) is not int or scopes[0][0] != 1:
                return out
            _, scope_digest, raw_members, initial, halted = scopes[0]
            if (type(scope_digest) is not str or _SHA.fullmatch(scope_digest) is None
                    or type(raw_members) is not str
                    or len(raw_members) > max(300, expected_members * 40)
                    or type(initial) is not int or initial % HOUR_MS
                    or initial < 25 * HOUR_MS or initial > now_ms
                    or halted not in (None, "provider_denied_owner_review",
                                      "candle_or_storage_integrity")):
                return out
            members = json.loads(raw_members)
            if (type(members) is not list or len(members) != expected_members
                    or any(type(s) is not str or _SYM.fullmatch(s) is None
                           for s in members)
                    or len(set(members)) != expected_members):
                return out
            published = db.execute(
                "SELECT end_ms,observed_at_ms,scope_digest,observed_contracts "
                "FROM published_hour ORDER BY end_ms LIMIT ?",
                (MAX_PUBLISHED + 1,)).fetchall()
            if not 1 <= len(published) <= MAX_PUBLISHED:
                return out
            # The real 24-run trial had a 2-hour catch-up: 18:00 candles
            # were stored but no retroactive 18:00 published_hour was forged.
            # Verify all *existing* publication timestamps, preserve explicit
            # skipped-checkpoint counts; never treat them as market PIT proofs.
            first_end = published[0][0]
            if (type(first_end) is not int or first_end not in
                    (initial, initial + HOUR_MS)):
                return out
            historical_missing = (first_end - initial) // HOUR_MS
            prior_end = None
            for end, observed, digest, count in published:
                if (type(end) is not int or end % HOUR_MS != 0
                        or type(observed) is not int
                        or not end + SETTLE_MS <= observed <= end + LATEST_START_MS
                        or digest != scope_digest or type(count) is not int
                        or count != len(members)):
                    return out
                if prior_end is not None:
                    delta = (end - prior_end) // HOUR_MS
                    if not 1 <= delta <= MAX_CATCHUP_HOURS:
                        return out
                    historical_missing += delta - 1
                prior_end = end
            last = published[-1][0]
            if last > now_ms:
                return out
            cursors = [_validate_cursor(db, symbol, initial, last)
                       for symbol in members]
            if any(cursor != last for cursor in cursors):
                return out
            expected_candles = expected_members * (24 + (last - initial)//HOUR_MS)
            stored = db.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
            if type(stored) is not int or stored != expected_candles:
                return out
            if (db.execute("SELECT COUNT(*) FROM cursor").fetchone()[0]
                    != expected_members):
                return out
            # Rank only this PINNED research cohort on 24 verified closed hours.
            # It is not a dynamic universe scan or exchange-wide Top50.
            rank_window_start = last - 24 * HOUR_MS
            ranking = []
            with localcontext(Context(prec=72)):
                for symbol in members:
                    bars = db.execute(
                        "SELECT open_ms,quote_turnover FROM candles "
                        "WHERE symbol=? AND open_ms>=? AND open_ms<? "
                        "ORDER BY open_ms",
                        (symbol, rank_window_start, last),
                    ).fetchall()
                    if (len(bars) != 24
                            or any(type(opened) is not int
                                   or opened != rank_window_start + i * HOUR_MS
                                   for i, (opened, _) in enumerate(bars))):
                        return out
                    total = sum((_dec(value, field="quote_turnover")
                                 for _, value in bars), Decimal(0))
                    if total > 0:
                        ranking.append((symbol, total))
                ranking.sort(key=lambda p: (-p[1], p[0]))
                canonical = json.dumps(
                    [[symbol, format(turnover, "f")]
                     for symbol, turnover in ranking],
                    separators=(",", ":"), ensure_ascii=True,
                )
            # Every published hour is proven to include every member's
            # complete, contiguous and digest-verified history.
            out.update({
                "last_published_end_ms": last,
                "published_hours": len(published),
                "historical_unpublished_hours": historical_missing,
                "historical_checkpoint_gaps_present": historical_missing > 0,
                "stored_candles": stored,
                "reviewed_research_contracts": len(members),
                "research_closed_24h_ranked_contracts": len(ranking),
                "research_closed_24h_rank_digest_sha256": sha256(
                    canonical.encode("ascii")).hexdigest(),
                "research_closed_24h_window_end_ms": last,
                "journal_integrity_verified": True,
            })
            if halted is not None:
                out["status"] = "halted_owner_review"
                return out
            target = _next_safe_target(now_ms)
            out["next_eligible_end_ms"] = target
            delta = (target - last) // HOUR_MS
            out["hours_since_last_publication"] = delta
            out["unobserved_closed_hours"] = max(0, delta - 1)
            out["catchup_hours"] = max(0, delta)
            out["catchup_within_worker_limit"] = 0 <= delta <= MAX_CATCHUP_HOURS
            if delta < 0:
                out["status"] = "clock_before_last_publication"
            elif delta > MAX_CATCHUP_HOURS:
                out["status"] = "catchup_exceeds_48h_blocked"
            elif delta >= 2:
                out["status"] = "catchup_with_unobserved_hours_requires_review"
            elif historical_missing:
                out["status"] = "historical_checkpoint_gaps_require_review"
            else:
                out["status"] = "no_gap"
            return out
    except (CensusAbstain, ValueError, TypeError, OSError, sqlite3.Error, UnicodeError,
            OverflowError, json.JSONDecodeError):
        return out
