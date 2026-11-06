"""J1/TOP50: bounded, resumable private basic-contract 24h candle census.

This does not authenticate crypto identity, Top50, continuous collection,
or rights to trade. Defaults OFF; no network without owner gates.
Private symbols and bars stay in a separate owner-only SQLite database.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from decimal import Context, Decimal, InvalidOperation, localcontext
try:
    import fcntl
except ImportError:  # Windows import inert; network owner gate remains closed.
    fcntl = None
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from typing import Any, Callable

HOUR_MS = 3_600_000
MAX_ROWS = 1000
MAX_BATCH = 120
MAX_WINDOW_AGE_MS = 48 * HOUR_MS
MAX_DB_BYTES = 32 * 1024 * 1024
_DB_NAME = "j1-marketwide-closed24h.sqlite"
_LOCK_NAME = ".j1-marketwide-closed24h.lock"
_SYMBOL = re.compile(r"[A-Z0-9]{2,32}\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?(?:[eE][+-]?[0-9]{1,3})?\Z")
_MAX_SCIENTIFIC_EXPONENT = 48
_FINANCIAL_FIELDS = frozenset({
    "open", "high", "low", "close", "base_volume", "quote_turnover",
})
_MATH = Context(prec=128)


class CensusAbstain(ValueError):
    """Only a fixed error code and optional fixed field enum are observable."""

    def __init__(self, code: str, *, field: str | None = None):
        super().__init__(code)
        self.field = field if field in _FINANCIAL_FIELDS else None


# Never interpolate an exception, symbol, URL, JSON payload or account value in
# the printed result. These exact string codes are authored in this module
# and the bounded public transport, NOT read from third-party responses.
_CENSUS_CODES = frozenset({
    "invalid_candle_decimal", "catalog_provider_response_invalid",
    "catalog_clock_invalid", "catalog_chain_incomplete",
    "catalog_count_invalid", "catalog_row_invalid",
    "catalog_identity_or_duplicate_invalid", "catalog_eligible_symbol_invalid",
    "catalog_not_enough_basic_contracts", "kline_provider_response_invalid",
    "kline_symbol_or_market_mismatch", "kline_not_24_closed_hours",
    "kline_row_invalid", "kline_missing_open_or_future_hour",
    "kline_ohlcv_integrity_abstain", "owner_private_path_rejected",
    "invalid_utc_clock", "closed_hour_safety_margin_required",
    "private_db_size_limit", "sqlite_integrity_rejected",
    "window_age_invalid", "catalog_scope_changed_recovery_abstain",
    "window_age_expired", "saved_rows_exceeded",
    "saved_symbol_out_of_scope", "partial_asset_transaction_found",
    "stored_financial_storage_type_invalid",
    "short_history_replay_invalid", "short_history_catalog_hint_changed",
})
_TRANSPORT_CODES = frozenset({
    "origin_or_media_type_rejected", "response_size_rejected",
    "access_region_or_rate_limit_no_retry", "provider_http_error_no_retry",
    "network_error_no_retry", "invalid_instrument_symbol",
    "unsafe_instrument_cursor", "invalid_kline_window",
    "origin_or_get_budget_rejected", "unexpected_market_data_query_rejected",
    "response_body_type_or_size_rejected", "invalid_provider_json",
    "provider_region_restriction", "provider_rate_limit_no_retry",
    "provider_request_parameters_rejected_no_retry",
    "provider_server_unavailable_no_retry",
    "provider_route_or_symbol_unavailable_no_retry",
    "provider_access_or_permission_denied_no_retry",
    "provider_request_identity_rejected_no_retry",
    "provider_unclassified_ret_code_no_retry",
    "provider_retcode_invalid_no_retry",
})
_INSUFFICIENT = frozenset({"kline_not_24_closed_hours"})
_CANDLE_INTEGRITY = frozenset({
    "invalid_candle_decimal", "kline_row_invalid",
    "kline_ohlcv_integrity_abstain",
    "kline_missing_open_or_future_hour",
    "kline_symbol_or_market_mismatch",
})
_NETWORK_CODES = frozenset({
    "network_error_no_retry", "origin_or_media_type_rejected",
    "response_size_rejected", "provider_http_error_no_retry",
    "access_region_or_rate_limit_no_retry",
})
_RATE_CODES = frozenset({
    "provider_rate_limit_no_retry", "provider_server_unavailable_no_retry",
})
_OWNER_CODES = frozenset({
    "owner_private_path_rejected", "invalid_utc_clock",
    "closed_hour_safety_margin_required", "window_age_invalid",
    "window_age_expired", "private_db_size_limit",
    "catalog_scope_changed_recovery_abstain",
})


def _failure_details(error: BaseException) -> tuple[str, str]:
    """Return a category and allowlisted code; unknown errors are opaque."""
    from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError
    if type(error) is CensusAbstain:
        code = str(error)
        if code not in _CENSUS_CODES:
            return "unclassified", "unclassified_abstain"
        if code in _INSUFFICIENT:
            return "closed_history_incomplete", code
        if code in _CANDLE_INTEGRITY:
            return "candle_integrity_or_time", code
        if code in _OWNER_CODES:
            return "environment_or_scope", code
        return "catalog_or_storage_validation", code
    if type(error) is J1BybitCaptureError:
        code = str(error)
        if code not in _TRANSPORT_CODES:
            return "unclassified", "unclassified_transport"
        if code in _NETWORK_CODES:
            return "transport_or_http", code
        if code in _RATE_CODES:
            return "provider_capacity_or_rate", code
        return "provider_or_request_validation", code
    if isinstance(error, sqlite3.Error):
        return "database", "sqlite_error"
    if isinstance(error, OSError):
        return "filesystem", "os_error"
    return "unclassified", "unexpected_error"


def _dec(value: Any, *, field: str | None = None) -> Decimal:
    """Finite nonnegative bounded ASCII decimal, optionally scientific.

    Do not round or normalize the provider's TEXT; exact Decimal is used for
    aggregation and replay. Bound the exponent before creating a Decimal.
    """
    if (type(value) is not str or len(value) > 96
            or _DECIMAL.fullmatch(value) is None):
        raise CensusAbstain("invalid_candle_decimal", field=field)
    match = re.search(r"[eE]([+-]?[0-9]{1,3})\Z", value)
    if match is not None and abs(int(match.group(1))) > _MAX_SCIENTIFIC_EXPONENT:
        raise CensusAbstain("invalid_candle_decimal", field=field)
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise CensusAbstain("invalid_candle_decimal", field=field) from None
    if not parsed.is_finite() or parsed < 0:
        raise CensusAbstain("invalid_candle_decimal", field=field)
    return parsed


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return sha256(_stable_json(value).encode("ascii")).hexdigest()


def _catalog(payload: dict, now_ms: int) -> tuple[tuple[str, ...], str, int]:
    """Basic provider shape, NOT independently authenticated crypto identity."""
    if type(payload) is not dict or type(payload.get("retCode")) is not int or payload["retCode"] != 0:
        raise CensusAbstain("catalog_provider_response_invalid")
    server_time = payload.get("time")
    if (type(server_time) is not int or not 0 < server_time <= now_ms
            or now_ms - server_time > 60_000):
        raise CensusAbstain("catalog_clock_invalid")
    result = payload.get("result")
    if (type(result) is not dict or result.get("category") != "linear"
            or result.get("nextPageCursor") != ""):
        raise CensusAbstain("catalog_chain_incomplete")
    rows = result.get("list")
    if type(rows) is not list or not 50 <= len(rows) <= MAX_ROWS:
        raise CensusAbstain("catalog_count_invalid")
    seen: set[str] = set()
    members: dict[str, tuple[str, ...]] = {}
    for row in rows:
        if type(row) is not dict:
            raise CensusAbstain("catalog_row_invalid")
        symbol = row.get("symbol")
        if (type(symbol) is not str or not 1 <= len(symbol) <= 80
                or not symbol.isascii() or not symbol.isprintable()
                or any(ch.isspace() for ch in symbol) or symbol in seen):
            raise CensusAbstain("catalog_identity_or_duplicate_invalid")
        seen.add(symbol)
        base = row.get("baseCoin")
        if (row.get("status") != "Trading"
                or row.get("contractType") != "LinearPerpetual"
                or row.get("quoteCoin") != "USDT"
                or row.get("settleCoin") != "USDT"):
            continue
        if (type(base) is not str or symbol != base + "USDT"
                or _SYMBOL.fullmatch(symbol) is None):
            raise CensusAbstain("catalog_eligible_symbol_invalid")
        members[symbol] = (symbol, base, "USDT", "USDT", "LinearPerpetual", "Trading")
    if not 50 <= len(members) <= MAX_ROWS:
        raise CensusAbstain("catalog_not_enough_basic_contracts")
    return tuple(sorted(members)), _digest([members[x] for x in sorted(members)]), len(rows)


def _closed_candles(payload: dict, symbol: str, end_ms: int, *, allow_short: bool = False) -> tuple[tuple[str, ...], ...]:
    if type(payload) is not dict or type(payload.get("retCode")) is not int or payload["retCode"] != 0:
        raise CensusAbstain("kline_provider_response_invalid")
    result = payload.get("result")
    if (type(result) is not dict or result.get("category") != "linear"
            or result.get("symbol") != symbol):
        raise CensusAbstain("kline_symbol_or_market_mismatch")
    rows = result.get("list")
    if (type(rows) is not list or len(rows) > 24 or
            (not allow_short and len(rows) != 24)):
        raise CensusAbstain("kline_not_24_closed_hours")
    accepted: list[tuple[str, ...]] = []
    for index, row in enumerate(rows):
        if type(row) is not list or len(row) != 7:
            raise CensusAbstain("kline_row_invalid")
        opened = row[0]
        if (type(opened) is not str or not opened.isascii() or not opened.isdecimal()
                or str(int(opened)) != opened or int(opened) != end_ms-(index+1)*HOUR_MS):
            raise CensusAbstain("kline_missing_open_or_future_hour")
        fields = ("open", "high", "low", "close", "base_volume", "quote_turnover")
        op, high, low, close, base_vol, quote_vol = tuple(
            _dec(value, field=field) for field, value in zip(fields, row[1:])
        )
        if (min(op, high, low, close) <= 0 or high < max(op, close)
                or low > min(op, close) or low > high
                or base_vol < 0 or quote_vol < 0):
            raise CensusAbstain("kline_ohlcv_integrity_abstain")
        accepted.append(tuple([opened] + list(row[1:])))
    return tuple(accepted)


def _catalog_launch_hints(payload: dict, members: tuple[str, ...],
                          now_ms: int) -> dict[str, int | None]:
    """Unverified catalog launch metadata; never eligibility proof."""
    allowed = set(members)
    result: dict[str, int | None] = {}
    for row in payload["result"]["list"]:
        symbol = row["symbol"]
        if symbol not in allowed:
            continue
        value = row.get("launchTime")
        hint = int(value) if (type(value) is str and len(value) == 13
                              and value.isascii() and value.isdecimal()) else None
        result[symbol] = hint if (hint is not None
                                  and 1_600_000_000_000 <= hint <= now_ms) else None
    if set(result) != allowed:
        raise CensusAbstain("catalog_identity_or_duplicate_invalid")
    return result


def _short_digest(symbol: str, end_ms: int, launch_ms: int | None,
                  bars: tuple[tuple[str, ...], ...]) -> str:
    return _digest([symbol, end_ms, launch_ms, bars])


def _strict_owner(path: Path, *, directory: bool) -> None:
    s = path.lstat()
    expected_mode = 0o700 if directory else 0o600
    if (s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != expected_mode
            or (s.st_nlink < 2 if directory else s.st_nlink != 1)
            or not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))):
        raise CensusAbstain("owner_private_path_rejected")


def _new_private_file(path: Path) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)


def _report(status: str) -> dict[str, Any]:
    return {
        "status": status, "schema_version": "j1-marketwide-basic-24h-v1",
        "requests_attempted": 0, "capture_window_end_ms": None,
        "catalog_rows": 0, "basic_eligible_contracts": 0,
        "completed_contracts": 0, "validated_closed_1h_rows": 0,
        "incomplete_24h_contracts": 0, "incomplete_24h_rows": 0,
        "inspected_contracts": 0, "remaining_contracts": 0,
        "top50_complete_subset_count": 0,
        "top50_complete_subset_digest_sha256": None,
        "top50_basic_count": 0,
        "top50_basic_digest_sha256": None,
        "full_basic_contract_24h_ranking_complete": False,
        "crypto_identity_independently_verified": False,
        "marketwide_top50_verified": False,
        "continuous_collector_verified": False,
        "orders_sent": False,
        "historical_private_database_modified": False,
    }


def run_census(*, directory: Path, now_ms: Callable[[], int],
               client: Any, max_contracts: int,
               allow_public_network: bool, allow_private_storage: bool,
               confirm_region_and_personal_research: bool,
               owner_ok: bool | None = None) -> dict[str, Any]:
    """One finite resumable batch with a single writer and no GET retries."""
    report = _report("owner_gate_required")
    allowed = (os.name == "posix" and fcntl is not None and os.getuid() == os.geteuid()
               and os.geteuid() != 0) if owner_ok is None else owner_ok
    if not (allowed and allow_public_network is True
            and allow_private_storage is True
            and confirm_region_and_personal_research is True):
        return report
    if (type(max_contracts) is not int or not 1 <= max_contracts <= MAX_BATCH
            or not isinstance(directory, Path) or not directory.is_absolute()
            or directory.name in ("", ".", "..")):
        return _report("invalid_configuration")
    stage = "owner_path"
    try:
        parent = directory.parent
        _strict_owner(parent, directory=True)
        if not directory.exists() and not directory.is_symlink():
            directory.mkdir(mode=0o700)
        _strict_owner(directory, directory=True)
        lock_path = directory / _LOCK_NAME
        if not lock_path.exists() and not lock_path.is_symlink():
            _new_private_file(lock_path)
        _strict_owner(lock_path, directory=False)
        fd = os.open(lock_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return _report("another_batch_active_abstain")
        try:
            stage = "catalog"
            moment = now_ms()
            if type(moment) is not int or moment <= 25 * HOUR_MS:
                raise CensusAbstain("invalid_utc_clock")
            candidate_end = moment // HOUR_MS * HOUR_MS
            if moment - candidate_end < 30_000:
                raise CensusAbstain("closed_hour_safety_margin_required")
            from crypto_intelligence_agent.bybit_public_j1_transport import instruments_url
            _, payload = client.get(instruments_url())
            members, scope_hash, total_catalog = _catalog(payload, now_ms())
            hints = _catalog_launch_hints(payload, members, now_ms())
            report["catalog_rows"] = total_catalog
            report["basic_eligible_contracts"] = len(members)
            db_path = directory / _DB_NAME
            if db_path.exists() or db_path.is_symlink():
                _strict_owner(db_path, directory=False)
                if db_path.stat().st_size > MAX_DB_BYTES:
                    raise CensusAbstain("private_db_size_limit")
            else:
                _new_private_file(db_path)
            stage = "sqlite_integrity"
            with closing(sqlite3.connect(db_path, timeout=0.1)) as db:
                db.execute("PRAGMA busy_timeout=100")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CensusAbstain("sqlite_integrity_rejected")
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS scope (
                      id INTEGER PRIMARY KEY CHECK (id=1),
                      window_end_ms INTEGER NOT NULL,
                      catalog_rows INTEGER NOT NULL,
                      scope_sha256 TEXT NOT NULL,
                      members_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS candles (
                      symbol TEXT NOT NULL, open_ms INTEGER NOT NULL,
                      open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL,
                      close TEXT NOT NULL, base_volume TEXT NOT NULL,
                      quote_turnover TEXT NOT NULL,
                      PRIMARY KEY(symbol,open_ms)
                    );
                    CREATE TABLE IF NOT EXISTS incomplete (
                      symbol TEXT PRIMARY KEY, launch_hint_ms INTEGER,
                      observed_count INTEGER NOT NULL,
                      candles_json TEXT NOT NULL, digest_sha256 TEXT NOT NULL
                    );
                """)
                saved = db.execute(
                    "SELECT window_end_ms,catalog_rows,scope_sha256,members_json "
                    "FROM scope WHERE id=1").fetchone()
                if saved is None:
                    end_ms = candidate_end
                    if not 30_000 <= now_ms() - end_ms <= MAX_WINDOW_AGE_MS:
                        raise CensusAbstain("window_age_invalid")
                    with db:
                        db.execute("INSERT INTO scope VALUES (1,?,?,?,?)",
                                   (end_ms, total_catalog, scope_hash, _stable_json(members)))
                else:
                    end_ms, saved_rows, saved_sha, saved_members = saved
                    if (type(end_ms) is not int or end_ms % HOUR_MS
                            or saved_rows != total_catalog or saved_sha != scope_hash
                            or saved_members != _stable_json(members)):
                        raise CensusAbstain("catalog_scope_changed_recovery_abstain")
                    if not 30_000 <= now_ms()-end_ms <= MAX_WINDOW_AGE_MS:
                        raise CensusAbstain("window_age_expired")
                report["capture_window_end_ms"] = end_ms
                stage = "replay"
                rows = db.execute(
                    "SELECT symbol,open_ms,open,high,low,close,base_volume,quote_turnover "
                    "FROM candles ORDER BY symbol,open_ms DESC").fetchall()
                if len(rows) > len(members)*24:
                    raise CensusAbstain("saved_rows_exceeded")
                groups: dict[str,list] = {}
                for row in rows:
                    symbol = row[0]
                    if symbol not in members:
                        raise CensusAbstain("saved_symbol_out_of_scope")
                    groups.setdefault(symbol, []).append(row)
                totals: dict[str, Decimal] = {}
                with localcontext(_MATH):
                    for symbol, entries in groups.items():
                        if len(entries) != 24:
                            raise CensusAbstain("partial_asset_transaction_found")
                        if any(type(entry[1]) is not int or
                               any(type(value) is not str for value in entry[2:])
                               for entry in entries):
                            raise CensusAbstain("stored_financial_storage_type_invalid")
                        public_rows = [[str(v) for v in entry[1:]] for entry in entries]
                        _closed_candles({"retCode": 0, "result": {
                            "category": "linear", "symbol": symbol, "list": public_rows}},
                            symbol, end_ms)
                        totals[symbol] = sum(
                            (_dec(x[-1]) for x in public_rows), Decimal(0))
                report.update({
                    "completed_contracts": len(totals),
                    "validated_closed_1h_rows": len(totals)*24,
                    "remaining_contracts": len(members)-len(totals),
                })
                stage = "kline"
                from crypto_intelligence_agent.bybit_public_j1_transport import kline_url
                count_new = 0
                for symbol in members:
                    if symbol in totals:
                        continue
                    if count_new >= max_contracts:
                        break
                    if now_ms() - end_ms > MAX_WINDOW_AGE_MS:
                        raise CensusAbstain("window_age_expired")
                    _, result = client.get(kline_url(symbol, end_ms-24*HOUR_MS, end_ms))
                    bars = _closed_candles(result, symbol, end_ms)
                    with localcontext(_MATH):
                        total = sum((_dec(bar[-1]) for bar in bars), Decimal(0))
                    with db:
                        db.executemany(
                            "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?)",
                            [(symbol, int(bar[0]), *bar[1:]) for bar in bars])
                    totals[symbol] = total
                    count_new += 1
                    report["completed_contracts"] = len(totals)
                    report["validated_closed_1h_rows"] = len(totals)*24
                    report["remaining_contracts"] = len(members)-len(totals)
                if len(totals) == len(members):
                    ranked = sorted(members, key=lambda s: (-totals[s], s))
                    report["top50_basic_count"] = len(ranked[:50])
                    report["top50_basic_digest_sha256"] = _digest([
                        [s, str(totals[s])] for s in ranked[:50]])
                    report["full_basic_contract_24h_ranking_complete"] = True
                    report["status"] = "basic_market_24h_closed_rank_complete_unverified"
                else:
                    report["status"] = "basic_market_24h_batch_partial_unverified"
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except (CensusAbstain, OSError, sqlite3.Error, ValueError, TypeError, OverflowError) as error:
        report["status"] = "abstain"
        report["failure_stage"] = stage
        report["failure_category"], report["failure_code"] = _failure_details(error)
        if (type(error) is CensusAbstain
                and report["failure_code"] == "invalid_candle_decimal"
                and error.field is not None):
            report["invalid_decimal_field"] = error.field
        report["last_request_stage"] = (
            getattr(client, "last_request_stage", None) or "before_first_get")
        report["provider_ret_code"] = getattr(client, "last_provider_retcode", None)
    report["requests_attempted"] = client.requests_attempted
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--max-contracts", type=int, default=60)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-storage", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = parser.parse_args(argv)
    from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient
    client = BoundedBybitPublicClient()
    result = run_census(
        directory=args.directory, now_ms=lambda: time.time_ns()//1_000_000,
        client=client, max_contracts=args.max_contracts,
        allow_public_network=args.allow_public_network,
        allow_private_storage=args.allow_private_storage,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
    )
    print(_stable_json(result))
    return 0 if result["status"] == "basic_market_24h_closed_rank_complete_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
