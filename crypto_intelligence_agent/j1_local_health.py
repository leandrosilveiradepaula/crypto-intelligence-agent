"""Read-only J1 SQLite health audit for an existing, *unverified* PIT sample.

This is a bounded observer, NOT a collector, Top50 certifier or process supervisor.
Do not instantiate SQLiteMarketDataStore here: its read methods initialise the
schema and enter BEGIN IMMEDIATE transactions. All SQL below is SELECT/PRAGMA.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

HOUR_MS = 3_600_000
SETTLE_MS = 60_000
MAX_MEMBERS = 50
MAX_SNAPSHOT_JSON_BYTES = 128_000
MAX_DECISION_MS = 4_102_444_800_000
_SCOPE = re.compile(r"[a-z][a-z0-9_]{1,31}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{2,32}\Z")
_REQUIRED_TABLES = frozenset({"candles", "checkpoints", "universe_snapshots", "collection_events"})


def _empty_report(decision_at_ms: int, window_end_ms: int, status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1_local_health_v2",
        "status": status,
        "decision_at_ms": decision_at_ms,
        "window_start_ms": window_end_ms - 24 * HOUR_MS,
        "window_end_exclusive_ms": window_end_ms,
        "snapshot_observed_at_ms": None,
        "snapshot_age_ms": None,
        "selected_members": 0,
        "complete_24h_members": 0,
        "checkpoint_complete_members": 0,
        "expected_candles": 0,
        "observed_candles": 0,
        "ohlcv_rows_validated": 0,
        "missing_or_invalid_candles": 0,
        "last_live_collection_event": "unknown",
        "last_live_collection_age_ms": None,
        "sample_identity_authenticated": False,
        "marketwide_top50_verified": False,
        "canonical_ohlcv_approved": False,
        "continuous_collector_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
    }


def _members(raw: str) -> tuple[str, ...]:
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_SNAPSHOT_JSON_BYTES:
        raise ValueError("invalid snapshot JSON size")
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError("duplicate snapshot JSON key")
            obj[k] = v
        return obj
    obj = json.loads(raw, object_pairs_hook=unique_pairs,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if type(obj) is not list or not 1 <= len(obj) <= MAX_MEMBERS:
        raise ValueError("invalid snapshot member count")
    symbols: list[str] = []
    for index, member in enumerate(obj, 1):
        if type(member) is not dict or set(member) != {"symbol", "rank", "quote_volume"}:
            raise ValueError("invalid snapshot member schema")
        symbol, rank, volume = member["symbol"], member["rank"], member["quote_volume"]
        if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
                or type(rank) is not int or rank != index or type(volume) is not str):
            raise ValueError("invalid snapshot rank or symbol")
        try:
            v = Decimal(volume)
        except InvalidOperation as exc:
            raise ValueError("invalid snapshot volume") from exc
        if not v.is_finite() or v <= 0:
            raise ValueError("invalid snapshot volume")
        symbols.append(symbol)
    if len(set(symbols)) != len(symbols):
        raise ValueError("duplicate snapshot symbol")
    return tuple(symbols)


def _stored_decimal(value: Any) -> Decimal:
    """Require canonical, finite SQLite TEXT, never SQLite REAL / float."""
    if type(value) is not str or not 1 <= len(value) <= 96 or not value.isascii():
        raise ValueError("stored financial value must be bounded Decimal TEXT")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("stored financial value invalid") from exc
    if not parsed.is_finite() or str(parsed) != value:
        raise ValueError("stored financial value noncanonical or nonfinite")
    return parsed


def audit_local_sqlite_health(*, db_path: str | Path, decision_at_ms: int,
    exchange: str, market: str = "linear_perpetual",
    snapshot_source: str | None = None,
    selection_rule_version: str | None = None,
    max_snapshot_age_ms: int = 2 * HOUR_MS,
) -> dict[str, Any]:
    """Observe only 24 finished 1h bars for the latest local PIT selection.

    Returns counts, not symbols or private URLs. The existing SQLite schema is
    queried in a single read transaction; no new database is created.
    Completion says NOTHING about exchange authenticity, identity review,
    Top50 market coverage, trading authorization, or running systemd workers.
    """
    if (type(decision_at_ms) is not int or
            not 25 * HOUR_MS <= decision_at_ms < MAX_DECISION_MS or
            type(max_snapshot_age_ms) is not int or
            not HOUR_MS <= max_snapshot_age_ms <= 7 * 86_400_000 or
            type(exchange) is not str or _SCOPE.fullmatch(exchange) is None or
            type(market) is not str or _SCOPE.fullmatch(market) is None or
            any(x is not None and (type(x) is not str or not 1 <= len(x) <= 80 or
                                  any(ord(ch) < 33 or ord(ch) > 126 for ch in x))
                for x in (snapshot_source, selection_rule_version))):
        raise ValueError("invalid J1 health configuration")
    end_ms = (decision_at_ms - SETTLE_MS) // HOUR_MS * HOUR_MS
    start_ms = end_ms - 24 * HOUR_MS
    report = _empty_report(decision_at_ms, end_ms, "database_unavailable")
    try:
        path = Path(db_path)
        if (path.is_symlink() or not path.is_file()):
            return report
        # URI-escape the path, so '?' or '#' in file names cannot alter mode=ro.
        uri = path.resolve(strict=True).as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.execute("BEGIN")
            tables = {x[0] for x in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not _REQUIRED_TABLES <= tables:
                report["status"] = "database_schema_incomplete"
                return report
            # A fixture with just timestamps/quality is NOT the canonical J1
            # candle table: inspect the actual stored OHLC and both volumes.
            required_columns = {
                "candles": {"exchange", "market", "symbol", "interval",
                            "open_time_ms", "close_time_ms", "open", "high",
                            "low", "close", "base_volume", "quote_volume", "quality"},
                "checkpoints": {"data_type", "exchange", "symbol", "interval",
                                "confirmed_start_ms", "confirmed_end_ms", "integrity"},
                "universe_snapshots": {"observed_at_ms", "eligible_json",
                                       "selection_rule_version", "source"},
                "collection_events": {"event_id", "observed_end_ms", "status",
                                      "mode", "exchange"},
            }
            for table, required in required_columns.items():
                # Table names above are fixed internal literals, not user input.
                available = {column[1] for column in
                             conn.execute(f"PRAGMA table_info({table})")}
                if not required <= available:
                    report["status"] = "database_schema_incomplete"
                    return report
            sql = ("SELECT observed_at_ms, eligible_json FROM universe_snapshots "
                   "WHERE observed_at_ms <= ?")
            params: list[Any] = [decision_at_ms]
            if snapshot_source is not None:
                sql += " AND source = ?"
                params.append(snapshot_source)
            if selection_rule_version is not None:
                sql += " AND selection_rule_version = ?"
                params.append(selection_rule_version)
            sql += " ORDER BY observed_at_ms DESC LIMIT 2"
            snapshots = conn.execute(sql, params).fetchall()
            if not snapshots:
                report["status"] = "snapshot_missing"
                return report
            if len(snapshots) > 1 and snapshots[0][0] == snapshots[1][0]:
                report["status"] = "snapshot_ambiguous"
                return report
            observed_ms, eligible_json = snapshots[0]
            if type(observed_ms) is not int or observed_ms <= 0:
                report["status"] = "snapshot_invalid"
                return report
            report["snapshot_observed_at_ms"] = observed_ms
            report["snapshot_age_ms"] = decision_at_ms - observed_ms
            try:
                symbols = _members(eligible_json)
            except (ValueError, TypeError, UnicodeError, RecursionError):
                report["status"] = "snapshot_invalid"
                return report
            report["selected_members"] = len(symbols)
            report["expected_candles"] = len(symbols) * 24
            if report["snapshot_age_ms"] > max_snapshot_age_ms:
                report["status"] = "snapshot_stale"
                return report

            placeholders = ",".join("?" for _ in symbols)
            rows = conn.execute(
                "SELECT symbol,open_time_ms,close_time_ms,quality,open,high,low,close,base_volume,quote_volume FROM candles "
                "WHERE exchange=? AND market=? AND interval='1h' "
                "AND open_time_ms>=? AND open_time_ms<? "
                f"AND symbol IN ({placeholders}) ORDER BY symbol,open_time_ms",
                [exchange, market, start_ms, end_ms, *symbols],
            ).fetchmany(len(symbols) * 24 + 1)
            if len(rows) > len(symbols) * 24:
                report["status"] = "candle_window_invalid"
                return report
            report["observed_candles"] = len(rows)
            seen: dict[str, set[int]] = {s: set() for s in symbols}
            for row in rows:
                (symbol, opened, closed, quality, open_text, high_text,
                 low_text, close_text, base_text, quote_text) = row
                if (symbol not in seen or type(opened) is not int or
                        opened % HOUR_MS or opened in seen[symbol] or
                        type(closed) is not int or closed != opened + HOUR_MS - 1 or
                        quality != "source_closed"):
                    report["status"] = "candle_window_invalid"
                    return report
                try:
                    op, hi, lo, cl, base, quote = map(_stored_decimal,
                        (open_text, high_text, low_text, close_text, base_text, quote_text))
                except ValueError:
                    report["status"] = "candle_window_invalid"
                    return report
                if (min(op, hi, lo, cl) <= 0 or hi < max(op, cl) or
                        lo > min(op, cl) or lo > hi or base < 0 or quote < 0):
                    report["status"] = "candle_window_invalid"
                    return report
                seen[symbol].add(opened)
            report["ohlcv_rows_validated"] = len(rows)
            full = {s for s, times in seen.items() if len(times) == 24}
            report["missing_or_invalid_candles"] = len(symbols) * 24 - len(rows)
            checkpoints = conn.execute(
                "SELECT symbol,confirmed_start_ms,confirmed_end_ms,integrity "
                "FROM checkpoints WHERE data_type='closed_candle' AND "
                "exchange=? AND interval='1h' "
                f"AND symbol IN ({placeholders})", [exchange, *symbols],
            ).fetchall()
            if (len(checkpoints) != len(symbols) or
                    len({row[0] for row in checkpoints}) != len(symbols)):
                report["status"] = "checkpoint_rows_invalid"
                return report
            covering = {symbol for symbol, a, b, integrity in checkpoints
                        if (symbol in seen and type(a) is int and type(b) is int
                            and a <= start_ms and end_ms - 1 <= b < decision_at_ms
                            and integrity == "complete")}
            report["checkpoint_complete_members"] = len(covering)
            report["complete_24h_members"] = len(full & covering)
            event = conn.execute(
                "SELECT observed_end_ms,status FROM collection_events WHERE "
                "exchange=? AND mode='live' AND observed_end_ms<=? "
                "ORDER BY observed_end_ms DESC,event_id DESC LIMIT 1",
                (exchange, decision_at_ms),
            ).fetchone()
            if event and type(event[0]) is int and event[0] >= 0:
                report["last_live_collection_event"] = (
                    event[1] if event[1] in ("success", "failure") else "unknown"
                )
                report["last_live_collection_age_ms"] = decision_at_ms - event[0]
            report["status"] = ("sample_window_complete_unverified" if
                len(full & covering) == len(symbols) else "sample_window_incomplete")
            return report
    except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError):
        report["status"] = "database_unavailable"
        return report
