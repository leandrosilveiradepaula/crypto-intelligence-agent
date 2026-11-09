"""J1/M1: owner-only incremental REST research candles, one closed UTC hour.

A new isolated SQLite journal is populated from the frozen D264 research
frontier. Source history/snapshot is ALWAYS read-only; no retroactive PIT,
crypto-identity approval, marketwide Top50 claim or live trading. The default
call performs no IO. A quota/access denial latches a fail-stop until operator
review, so an hourly timer cannot spin against the provider.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable
try:
    import fcntl
except ImportError:  # Off on Windows; portability tests cover the default.
    fcntl = None

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, kline_url,
)
from crypto_intelligence_agent.bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE
from scripts.audit_bybit_marketwide_closed24h import (
    CensusAbstain, _closed_candles, _digest, _new_private_file, _strict_owner,
)
from scripts.j1_d264_private_metadata_snapshot import replay_private_snapshot

HOUR_MS = 3_600_000
MAX_ASSETS = 50
MAX_CATCHUP_HOURS = 48
PAGE_HOURS = 24
MAX_DB_BYTES = 512 * 1024 * 1024
_DB_NAME = "j1-rest-hourly-research.sqlite"
_LOCK_NAME = ".j1-rest-hourly-research.lock"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SYM = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_ALLOWED_CATEGORIES = frozenset({
    "archived_crypto_reference_only", "crypto_token_candidate_unverified",
    "ticker_collision_unresolved", "tokenized_gold_policy_gate",
    "identity_unresolved",
})
_PERMANENT_TRANSPORT = frozenset({
    "access_region_or_rate_limit_no_retry", "provider_region_restriction",
    "provider_rate_limit_no_retry",
    "provider_access_or_permission_denied_no_retry",
    "provider_request_parameters_rejected_no_retry",
    "provider_route_or_symbol_unavailable_no_retry",
    "provider_request_identity_rejected_no_retry",
    "provider_unclassified_ret_code_no_retry",
    "provider_retcode_invalid_no_retry",
})
_ALLOWED_FAILURES = _PERMANENT_TRANSPORT | frozenset({
    "network_error_no_retry", "provider_server_unavailable_no_retry",
    "provider_http_error_no_retry", "origin_or_media_type_rejected",
    "response_size_rejected", "invalid_provider_json",
    "response_body_type_or_size_rejected", "origin_or_get_budget_rejected",
    "unexpected_market_data_query_rejected",
})


def _result(status: str = "owner_optin_required") -> dict[str, Any]:
    return {
        "schema_version": "j1-m1-rest-hourly-research-v1",
        "status": status, "failure_category": None,
        "decision_end_ms": None,
        "selected_research_contracts": 0,
        "contracts_at_decision": 0, "new_closed_candles": 0,
        "requests_attempted": 0, "research_only": True,
        "frozen_history_modified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "continuous_collector_verified": False,
        "signal_authorized": False, "live_trading_authorized": False,
        "orders_sent": False,
    }


def _frontier(value: Any, *, now: int, max_assets: int) -> tuple[tuple[str, ...], str]:
    if (type(value) is not dict
            or value.get("status") != "retrospective_negative_overlay_research_only"
            or value.get("research_frontier_count") != 50
            or value.get("research_frontier_not_eligible_top50") is not True
            or value.get("marketwide_top50_verified") is not False
            or value.get("orders_sent") is not False
            or value.get("network_accessed") is not False
            or value.get("database_modified") is not False
            or value.get("current_eligible_contracts_verified") != 0):
        raise ValueError("untrusted_research_frontier")
    members = value.get("private_research_symbols_only")
    if (type(members) is not list or len(members) != 50
            or not all(type(x) is dict
                       and set(x) == {"position", "symbol", "category_unverified"}
                       and type(x["position"]) is int and x["position"] == i
                       and type(x["symbol"]) is str and _SYM.fullmatch(x["symbol"])
                       and x["symbol"] not in NEGATIVE_EVIDENCE
                       and x["category_unverified"] in _ALLOWED_CATEGORIES
                       for i, x in enumerate(members, 1))):
        raise ValueError("untrusted_research_frontier_members")
    symbols = tuple(x["symbol"] for x in members)
    if len(set(symbols)) != 50:
        raise ValueError("duplicate_research_members")
    keys = ("research_frontier_digest_sha256", "private_snapshot_sha256",
            "frozen_raw_top50_digest_sha256")
    if any(type(value.get(k)) is not str or _SHA.fullmatch(value[k]) is None for k in keys):
        raise ValueError("untrusted_frozen_digests")
    old, seen = (value.get("frozen_capture_window_end_ms"),
                 value.get("current_metadata_observed_at_ms"))
    if (type(old) is not int or type(seen) is not int
            or old % HOUR_MS or not 0 < old < seen <= now):
        raise ValueError("untrusted_scope_clock")
    # Bind the new research journal to exactly this immutable D264 evidence.
    scope_digest = _digest([value[k] for k in keys] + [list(symbols[:max_assets])])
    return symbols[:max_assets], scope_digest


def _db_open(path: Path) -> sqlite3.Connection:
    if not path.exists() and not path.is_symlink():
        _new_private_file(path)
    _strict_owner(path, directory=False)
    if path.stat().st_size > MAX_DB_BYTES:
        raise ValueError("research_journal_size_limit")
    db = sqlite3.connect(path, timeout=0.1)
    db.execute("PRAGMA busy_timeout=100")
    db.execute("PRAGMA foreign_keys=ON")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        db.close()
        raise ValueError("research_journal_corrupt")
    return db


def _init(db: sqlite3.Connection, *, symbols: tuple[str, ...],
          scope_digest: str, decision: int) -> tuple[int, str | None]:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS scope (
          id INTEGER PRIMARY KEY CHECK(id=1),
          scope_digest TEXT NOT NULL, members_json TEXT NOT NULL,
          initial_end_ms INTEGER NOT NULL, halted_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS cursor (
          symbol TEXT PRIMARY KEY, next_open_ms INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS candles (
          symbol TEXT NOT NULL, open_ms INTEGER NOT NULL,
          open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL,
          close TEXT NOT NULL, base_volume TEXT NOT NULL,
          quote_turnover TEXT NOT NULL, received_at_ms INTEGER NOT NULL,
          digest_sha256 TEXT NOT NULL,
          PRIMARY KEY(symbol, open_ms),
          FOREIGN KEY(symbol) REFERENCES cursor(symbol)
        );
        CREATE TABLE IF NOT EXISTS published_hour (
          end_ms INTEGER PRIMARY KEY, observed_at_ms INTEGER NOT NULL,
          scope_digest TEXT NOT NULL, observed_contracts INTEGER NOT NULL
        );
    """)
    row = db.execute(
        "SELECT scope_digest,members_json,initial_end_ms,halted_reason "
        "FROM scope WHERE id=1").fetchone()
    members = json.dumps(symbols, ensure_ascii=True, separators=(",", ":"))
    if row is None:
        with db:
            db.execute("INSERT INTO scope VALUES (1,?,?,?,NULL)",
                       (scope_digest, members, decision))
            db.executemany("INSERT INTO cursor VALUES (?,?)",
                           [(symbol, decision-24*HOUR_MS) for symbol in symbols])
        initial, halted = decision, None
    else:
        if row[:2] != (scope_digest, members):
            raise ValueError("frozen_scope_changed_requires_new_journal")
        initial, halted = row[2], row[3]
        if (type(initial) is not int or initial % HOUR_MS
                or initial > decision or initial <= 24*HOUR_MS
                or (halted is not None and halted not in
                    ("provider_denied_owner_review", "candle_or_storage_integrity"))):
            raise ValueError("research_scope_metadata_invalid")
    return initial, halted


def _validate_cursor(db: sqlite3.Connection, symbol: str,
                     initial: int, decision: int) -> int:
    got = db.execute("SELECT next_open_ms FROM cursor WHERE symbol=?", (symbol,)).fetchone()
    if got is None or type(got[0]) is not int:
        raise ValueError("research_cursor_missing")
    next_open = got[0]
    start = initial-24*HOUR_MS
    if (next_open % HOUR_MS or not start <= next_open <= decision):
        raise ValueError("research_cursor_invalid")
    rows = db.execute(
        "SELECT open_ms,open,high,low,close,base_volume,quote_turnover,"
        "received_at_ms,digest_sha256 FROM candles WHERE symbol=? "
        "ORDER BY open_ms", (symbol,)).fetchall()
    expected = (next_open-start)//HOUR_MS
    if len(rows) != expected:
        raise ValueError("research_candle_gap_or_cursor_conflict")
    for i, row in enumerate(rows):
        opened, *data = row
        expected_open = start+i*HOUR_MS
        if (type(opened) is not int or opened != expected_open
                or any(type(x) is not str for x in data[:6])
                or type(data[6]) is not int or data[6] < opened+HOUR_MS
                or type(data[7]) is not str or
                not _SHA.fullmatch(data[7])):
            raise ValueError("research_saved_row_invalid")
        _closed_candles(
            {"retCode":0,"result":{"category":"linear","symbol":symbol,
                                   "list":[[str(opened),*data[:6]]]}},
            symbol, opened+HOUR_MS, allow_short=True)
        if data[7] != _digest([symbol, (str(opened),*data[:6])]):
            raise ValueError("research_saved_row_digest_conflict")
    return next_open


def run_hourly_once(*, frozen_directory: Path, output_directory: Path,
                    max_assets: int = 2,
                    allow_public_network: bool = False,
                    allow_private_storage: bool = False,
                    confirm_region_and_personal_research: bool = False,
                    owner_ok: bool | None = None,
                    clock_ms: Callable[[], int] | None = None,
                    client: BoundedBybitPublicClient | None = None,
                    frontier_reader: Callable[..., dict] = replay_private_snapshot,
                    ) -> dict[str, Any]:
    """Incremental, one owner invocation; timer/deployment is separately gated."""
    result = _result()
    permitted = (os.name == "posix" and fcntl is not None
                 and os.getuid() == os.geteuid() and os.geteuid() != 0
                 ) if owner_ok is None else owner_ok
    if (not permitted or allow_public_network is not True
            or allow_private_storage is not True
            or confirm_region_and_personal_research is not True):
        return result
    if (type(max_assets) is not int or not 1 <= max_assets <= MAX_ASSETS
            or not isinstance(frozen_directory, Path)
            or not isinstance(output_directory, Path)
            or not frozen_directory.is_absolute()
            or not output_directory.is_absolute()
            or frozen_directory == output_directory
            or frozen_directory in output_directory.parents
            or output_directory in frozen_directory.parents
            or type(client) not in (BoundedBybitPublicClient, type(None))
            or not callable(frontier_reader)
            or (clock_ms is not None and not callable(clock_ms))):
        return _result("invalid_configuration")
    read_clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
    fetch: BoundedBybitPublicClient | None = client
    try:
        now = read_clock()
        if (type(now) is not int or not 1_600_000_000_000 <= now < 4_102_444_800_000):
            return _result("invalid_clock")
        decision = now // HOUR_MS * HOUR_MS
        result["decision_end_ms"] = decision

        def within_safe_window() -> bool:
            current = read_clock()
            return (type(current) is int
                    and decision + 60_000 <= current <= decision + 900_000)

        if not within_safe_window():
            result["status"] = "outside_safe_utc_close_window"
            return result
        _strict_owner(output_directory, directory=True)
        # D264 replays the private historical snapshot read-only (incl. lock).
        original = frontier_reader(frozen_directory, include_private_symbols=True)
        selected, scope_digest = _frontier(original, now=now, max_assets=max_assets)
        result["selected_research_contracts"] = len(selected)

        lock_path = output_directory / _LOCK_NAME
        if not lock_path.exists() and not lock_path.is_symlink():
            _new_private_file(lock_path)
        _strict_owner(lock_path, directory=False)
        fd = os.open(lock_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                result["status"] = "another_hourly_worker_running"
                return result
            with closing(_db_open(output_directory / _DB_NAME)) as db:
                initial, halted = _init(
                    db, symbols=selected, scope_digest=scope_digest, decision=decision)
                if halted is not None:
                    result["status"] = "halted_owner_review_required"
                    result["failure_category"] = halted
                    return result
                for symbol in selected:
                    try:
                        start = _validate_cursor(db, symbol, initial, decision)
                    except CensusAbstain:
                        _latch_halt(db, "candle_or_storage_integrity")
                        raise
                    if start == decision:
                        continue
                    if decision-start > MAX_CATCHUP_HOURS*HOUR_MS:
                        raise ValueError("catchup_exceeds_48h_owner_review")
                    while start < decision:
                        end = min(start+PAGE_HOURS*HOUR_MS, decision)
                        if not within_safe_window():
                            raise ValueError("utc_close_window_elapsed_before_commit")
                        if fetch is None:
                            fetch = BoundedBybitPublicClient()
                        try:
                            _, payload = fetch.get(kline_url(symbol, start, end))
                            if not within_safe_window():
                                raise ValueError("utc_close_window_elapsed_before_commit")
                            rows = _closed_candles(
                                payload, symbol, end, allow_short=True)
                            if len(rows) != (end-start)//HOUR_MS:
                                raise CensusAbstain("kline_not_24_closed_hours")
                        except J1BybitCaptureError as exc:
                            if str(exc) in _PERMANENT_TRANSPORT:
                                _latch_halt(db, "provider_denied_owner_review")
                            raise
                        except CensusAbstain:
                            _latch_halt(db, "candle_or_storage_integrity")
                            raise
                        receipt = read_clock()
                        if (type(receipt) is not int or receipt < now
                                or not decision + 60_000 <= receipt <= decision + 900_000):
                            raise ValueError("utc_close_window_elapsed_before_commit")
                        with db:
                            for row in reversed(rows):
                                db.execute(
                                    "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)",
                                    (symbol, int(row[0]), *row[1:], receipt,
                                     _digest([symbol, row])))
                            db.execute(
                                "UPDATE cursor SET next_open_ms=? WHERE symbol=? "
                                "AND next_open_ms=?",
                                (end, symbol, start))
                            if db.execute("SELECT changes()").fetchone()[0] != 1:
                                raise ValueError("concurrent_research_cursor_change")
                        result["new_closed_candles"] += len(rows)
                        start = end
                try:
                    full = sum(_validate_cursor(db, symbol, initial, decision) == decision
                               for symbol in selected)
                except CensusAbstain:
                    _latch_halt(db, "candle_or_storage_integrity")
                    raise
                result["contracts_at_decision"] = full
                if full == len(selected):
                    if not within_safe_window():
                        raise ValueError("utc_close_window_elapsed_before_commit")
                    # A stored observation is NOT a historical PIT for any
                    # missed hour or proof of identity/global Top50.
                    with db:
                        db.execute(
                            "INSERT OR IGNORE INTO published_hour VALUES (?,?,?,?)",
                            (decision, read_clock(), scope_digest, full))
                    result["status"] = "research_sample_closed_hour_persisted"
                else:
                    result["status"] = "research_sample_partial_no_publication"
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
    except J1BybitCaptureError as exc:
        category = str(exc)
        result["status"] = "research_provider_fail_stop"
        result["failure_category"] = (
            category if category in _ALLOWED_FAILURES else "provider_unclassified")
    except (CensusAbstain, ValueError, OSError, sqlite3.Error, TypeError) as exc:
        result["status"] = "research_integrity_or_environment_abstain"
        safe = frozenset({
            "research_cursor_missing", "research_cursor_invalid",
            "research_candle_gap_or_cursor_conflict", "research_saved_row_invalid",
            "research_saved_row_digest_conflict",
            "frozen_scope_changed_requires_new_journal",
            "untrusted_research_frontier", "untrusted_research_frontier_members",
            "untrusted_frozen_digests", "untrusted_scope_clock",
            "research_scope_metadata_invalid", "utc_close_window_elapsed_before_commit",
            "catchup_exceeds_48h_owner_review",
        })
        result["failure_category"] = (
            str(exc) if type(exc) is ValueError and str(exc) in safe
            else str(exc) if type(exc) is CensusAbstain and str(exc) in (
                "kline_not_24_closed_hours", "kline_missing_open_or_future_hour",
                "kline_ohlcv_integrity_abstain", "kline_row_invalid",
            ) else "sqlite_or_environment_or_integrity"
        )
    finally:
        if fetch is not None:
            result["requests_attempted"] = fetch.requests_attempted
    return result



def _latch_halt(db: sqlite3.Connection, why: str) -> None:
    """Persist the fail-stop under the active single-writer flock.

    The next hourly invocation must observe the latch before issuing a GET.
    If the write fails, do not swallow the storage error.
    """
    with db:
        cursor = db.execute(
            "UPDATE scope SET halted_reason=? WHERE id=1 AND halted_reason IS NULL",
            (why,))
        if cursor.rowcount != 1:
            raise ValueError("research_halt_latch_failed")
