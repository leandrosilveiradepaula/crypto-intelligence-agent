"""J1 #326: offline-only Bybit V5 confirmed-kline fixture journal.

Consumes caller-provided dictionaries; NO socket, HTTP, credentials or orders.
Only an independently reviewed *offline* instrument scan may admit symbols.
The journal is intentionally separate from the owner-only raw REST-pair store:
WebSocket events have no instrument/kline HTTP raw-pair provenance. Neither
kind of cache authenticates the provider, authorizes live data, or proves Top50.

Provider shapes: https://bybit-exchange.github.io/docs/v5/websocket/public/kline
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
from bisect import bisect_right
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import os
from urllib.parse import quote
from pathlib import Path
import re
import sqlite3
from typing import Mapping

from .bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from .bybit_linear_candle_research import stage_bybit_linear_kline, _strict_decimal
from .bybit_paginated_universe_research import BybitInstrumentScanResearch
from .market_data import DataGapError, DataValidationError
from .research_registry_catalog import load_reviewed_registry

HOUR_MS = 3_600_000
MAX_WS_LAG_MS = 120_000
MAX_SERVER_SKEW_MS = 30_000
MAX_SCOPE_AGE_MS = 7 * 86_400_000
MAX_FRAME_BYTES = 16_384
MAX_JOURNAL_ROWS = 100_000
MAX_SCOPE_CONTRACTS = 500
MAX_PIT_SCOPES = 64
HISTORICAL_HOURS = 720
MAX_UTC_MS = 4_102_444_800_000  # Conservative year-2100 bound.
_VERSION = "j1-bybit-ws-closed-fixture-v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ROW_FIELDS = frozenset({
    "start", "end", "interval", "open", "high", "low", "close",
    "volume", "turnover", "confirm", "timestamp",
})
_PAYLOAD_FIELDS = frozenset({
    "schema", "symbol", "registry_sha256", "scope_observed_ms", "launch_ms",
    "open_ms", "end_ms", "received_ms", "server_ms", "trade_ms",
    "open", "high", "low", "close", "volume_base", "turnover_usdt",
})


def _json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _sha(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class OfflineReviewedStreamScope:
    """An already-checked *offline* scan; its content is not live provenance."""

    observed_at_ms: int
    registry_sha256: str
    contracts: tuple[BybitLinearInstrumentResearch, ...]
    asserted_full_catalog_rows: int

    @classmethod
    def from_scan(cls, scan: BybitInstrumentScanResearch, *, registry_variant: str):
        if (type(scan) is not BybitInstrumentScanResearch
                or type(registry_variant) is not str
                or type(scan.observed_at_ms) is not int
                or not 0 < scan.observed_at_ms < MAX_UTC_MS
                or type(scan.instruments) is not tuple
                or not 1 <= len(scan.instruments) <= MAX_SCOPE_CONTRACTS
                or type(scan.instrument_row_count) is not int
                or scan.instrument_row_count < len(scan.instruments)
                or type(scan.page_count) is not int or scan.page_count < 1):
            raise DataValidationError("offline complete reviewed instrument scope required")
        registry = load_reviewed_registry(registry_variant, as_of_ms=scan.observed_at_ms)
        if (scan.registry_sha256 != registry.sha256_digest
                or _DIGEST.fullmatch(scan.registry_sha256) is None):
            raise DataValidationError("reviewed instrument registry identity mismatch")
        seen: set[str] = set()
        for m in scan.instruments:
            if (type(m) is not BybitLinearInstrumentResearch
                    or type(m.symbol) is not str
                    or m.symbol != m.base_coin + "USDT"
                    or m.base_coin not in registry.verified_crypto_bases
                    or m.quote_coin != "USDT" or m.settle_coin != "USDT"
                    or m.symbol in seen or m.registry_sha256 != scan.registry_sha256
                    or type(m.observed_at_ms) is not int
                    or not 0 < m.observed_at_ms <= scan.observed_at_ms
                    or type(m.launch_time_ms) is not int
                    or not 0 < m.launch_time_ms <= m.observed_at_ms):
                raise DataValidationError("invalid or unreviewed offline stream contract")
            seen.add(m.symbol)
        return cls(scan.observed_at_ms, scan.registry_sha256,
                   scan.instruments, scan.instrument_row_count)

    def member(self, symbol: object) -> BybitLinearInstrumentResearch:
        for m in self.contracts:
            if m.symbol == symbol:
                return m
        raise DataValidationError("WS symbol not present in reviewed scan")


@dataclass(frozen=True)
class OfflineConfirmedKline:
    """Checked deterministic research bytes; NOT an authenticated exchange tick."""

    symbol: str
    open_ms: int
    received_ms: int
    registry_sha256: str
    payload: str
    digest: str


def parse_offline_confirmed_kline(
    message: Mapping, *, scope: OfflineReviewedStreamScope,
    received_at_ms: int,
) -> OfflineConfirmedKline:
    """Strict Bybit public linear kline.60 snapshot -> existing REST parser.

    A closed WS event is not historical backfill: only its own UTC hour enters
    the research fixture. Open updates are *rejected*, never silently stored.
    """
    if (type(scope) is not OfflineReviewedStreamScope
            or type(received_at_ms) is not int or not 0 < received_at_ms < MAX_UTC_MS
            or type(message) is not dict):
        raise DataValidationError("bounded offline WS frame and receipt required")
    if (set(message) != {"topic", "type", "ts", "data"}
            or message.get("type") != "snapshot"
            or type(message.get("topic")) is not str
            or type(message.get("ts")) is not int
            or type(message.get("data")) is not list
            or len(message["data"]) != 1):
        raise DataValidationError("unsupported WS snapshot envelope")
    try:
        if len(_json(message).encode("utf-8")) > MAX_FRAME_BYTES:
            raise DataValidationError("offline WS frame too large")
    except (ValueError, TypeError, OverflowError):
        raise DataValidationError("offline WS frame is not bounded JSON") from None
    topic = message["topic"]
    if not topic.startswith("kline.60."):
        raise DataValidationError("only 1h Bybit public kline stream is supported")
    symbol = topic.removeprefix("kline.60.")
    member = scope.member(symbol)
    row = message["data"][0]
    if type(row) is not dict or set(row) != _ROW_FIELDS:
        raise DataValidationError("unexpected Bybit WS kline fields")
    start, end, trade_ms = row["start"], row["end"], row["timestamp"]
    server_ms = message["ts"]
    if (row["interval"] != "60" or row["confirm"] is not True
            or any(type(x) is not int for x in (start, end, trade_ms))
            or start <= 0 or start % HOUR_MS or end != start + HOUR_MS - 1
            or end >= MAX_UTC_MS
            or not start <= trade_ms <= end
            or type(server_ms) is not int or server_ms < end + 1
            or server_ms > received_at_ms
            or received_at_ms - server_ms > MAX_SERVER_SKEW_MS
            or received_at_ms - (end + 1) < 1000
            or received_at_ms - (end + 1) > MAX_WS_LAG_MS
            or scope.observed_at_ms > server_ms
            or server_ms - scope.observed_at_ms > MAX_SCOPE_AGE_MS
            or member.launch_time_ms > start):
        raise DataValidationError("WS confirmation, UTC clock or scope chronology invalid")
    for name in ("open", "high", "low", "close", "volume", "turnover"):
        if type(row[name]) is not str:
            raise DataValidationError("WS values must be exact decimal strings")
    # Reuse the already strict Bybit linear OHLC/BASE/QUOTE research validator.
    # Adapt WS fields to a *synthetic* single-row REST-shaped fixture; do not
    # mislabel the result as a raw REST response or authenticated provider data.
    rest_shaped = {"retCode": 0, "result": {"category": "linear", "symbol": symbol, "list": [[
        str(start), row["open"], row["high"], row["low"], row["close"],
        row["volume"], row["turnover"],
    ]]}}
    candle = stage_bybit_linear_kline(
        rest_shaped, symbol=symbol, quote_currency="USDT",
        contract_type="LinearPerpetual", contract_status="Trading",
        contract_observed_at_ms=member.observed_at_ms,
        observed_at_ms=received_at_ms, max_contract_age_ms=MAX_SCOPE_AGE_MS,
        interval="1h", start_open_ms=start, end_open_ms=start + HOUR_MS,
        close_safety_ms=1000, max_candles=1,
    ).candles[0]
    payload = _json({
        "schema": _VERSION, "symbol": symbol,
        "registry_sha256": scope.registry_sha256,
        "scope_observed_ms": scope.observed_at_ms,
        "launch_ms": member.launch_time_ms,
        "open_ms": start, "end_ms": end,
        "received_ms": received_at_ms, "server_ms": server_ms,
        "trade_ms": trade_ms,
        "open": format(candle.open, "f"),
        "high": format(candle.high, "f"),
        "low": format(candle.low, "f"),
        "close": format(candle.close, "f"),
        "volume_base": format(candle.documented_base_volume, "f"),
        "turnover_usdt": format(candle.documented_quote_turnover, "f"),
    })
    return OfflineConfirmedKline(symbol, start, received_at_ms,
                                 scope.registry_sha256, payload, _sha(payload))


def _validated_payload(raw: str, digest: str) -> dict:
    if (type(raw) is not str or len(raw) > MAX_FRAME_BYTES
            or type(digest) is not str or _DIGEST.fullmatch(digest) is None
            or _sha(raw) != digest):
        raise DataGapError("offline candle record digest invalid")
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise DataGapError("offline candle record JSON invalid") from None
    if (type(value) is not dict or set(value) != _PAYLOAD_FIELDS
            or _json(value) != raw or value["schema"] != _VERSION
            or type(value["symbol"]) is not str
            or not re.fullmatch(r"[A-Z0-9]{2,24}USDT", value["symbol"])
            or type(value["registry_sha256"]) is not str
            or _DIGEST.fullmatch(value["registry_sha256"]) is None):
        raise DataGapError("offline candle record structure invalid")
    for name in ("open_ms", "end_ms", "received_ms", "server_ms",
                 "trade_ms", "scope_observed_ms", "launch_ms"):
        if type(value[name]) is not int or not 0 < value[name] < MAX_UTC_MS:
            raise DataGapError("offline candle record clock invalid")
    start, end = value["open_ms"], value["end_ms"]
    if (start <= 0 or start % HOUR_MS or end != start + HOUR_MS - 1
            or value["launch_ms"] > start
            or not 0 < value["scope_observed_ms"] <= value["server_ms"]
            or value["server_ms"] - value["scope_observed_ms"] > MAX_SCOPE_AGE_MS
            or not start <= value["trade_ms"] <= end
            or not end + 1 <= value["server_ms"] <= value["received_ms"]
            or not 1000 <= value["received_ms"] - (end + 1) <= MAX_WS_LAG_MS
            or value["received_ms"] - value["server_ms"] > MAX_SERVER_SKEW_MS):
        raise DataGapError("offline candle record temporal tamper")
    try:
        prices = {k: _strict_decimal(value[k], label=k, may_be_zero=False)
                  for k in ("open", "high", "low", "close")}
        for k in ("volume_base", "turnover_usdt"):
            _strict_decimal(value[k], label=k, may_be_zero=True)
    except (DataValidationError, KeyError, TypeError):
        raise DataGapError("offline candle record decimals invalid") from None
    if (prices["high"] < max(prices["open"], prices["low"], prices["close"])
            or prices["low"] > min(prices["open"], prices["high"], prices["close"])):
        raise DataGapError("offline candle record price range invalid")
    return value



def _scope_contract_fingerprint(scope: OfflineReviewedStreamScope) -> tuple:
    """Check bounded offline metadata shape; never authenticate an exchange."""
    if (type(scope) is not OfflineReviewedStreamScope
            or type(scope.observed_at_ms) is not int
            or not 0 < scope.observed_at_ms < MAX_UTC_MS
            or type(scope.registry_sha256) is not str
            or _DIGEST.fullmatch(scope.registry_sha256) is None
            or type(scope.contracts) is not tuple
            or not 1 <= len(scope.contracts) <= MAX_SCOPE_CONTRACTS
            or type(scope.asserted_full_catalog_rows) is not int
            or scope.asserted_full_catalog_rows < len(scope.contracts)):
        raise DataValidationError("offline PIT scope structure invalid")
    checked = []
    seen = set()
    for member in scope.contracts:
        if (type(member) is not BybitLinearInstrumentResearch
                or type(member.symbol) is not str
                or type(member.base_coin) is not str
                or member.symbol != member.base_coin + "USDT"
                or member.symbol in seen
                or member.quote_coin != "USDT" or member.settle_coin != "USDT"
                or member.registry_sha256 != scope.registry_sha256
                or type(member.observed_at_ms) is not int
                or not 0 < member.observed_at_ms <= scope.observed_at_ms
                or scope.observed_at_ms - member.observed_at_ms > MAX_SCOPE_AGE_MS
                or type(member.launch_time_ms) is not int
                or not 0 < member.launch_time_ms <= scope.observed_at_ms
                or type(member.source) is not str
                or any(type(value) is not Decimal or not value.is_finite() or value <= 0
                       for value in (member.max_leverage, member.tick_size,
                                     member.quantity_step))):
            raise DataValidationError("offline PIT member is malformed or stale")
        seen.add(member.symbol)
        # Only observation timestamps may vary across the epochs. A changed
        # contract specification is NOT silently carried into the same rank.
        checked.append((
            member.symbol, member.base_coin, member.quote_coin, member.settle_coin,
            member.launch_time_ms, member.max_leverage, member.tick_size,
            member.quantity_step, member.registry_sha256, member.source,
        ))
    return tuple(sorted(checked, key=lambda entry: entry[0]))


def _validate_pit_scopes(
    scope: OfflineReviewedStreamScope,
    historical_scopes: tuple[OfflineReviewedStreamScope, ...],
    decision_at_ms: int,
) -> tuple[int, ...]:
    """Verify a strict, bounded PIT chain of the SAME offline reviewed universe."""
    if (type(historical_scopes) is not tuple
            or not 1 <= len(historical_scopes) <= MAX_PIT_SCOPES
            or historical_scopes[-1] != scope):
        raise DataValidationError("offline PIT epochs missing or latest scope mismatched")
    identity = _scope_contract_fingerprint(scope)
    previous_ms = 0
    times = []
    for epoch in historical_scopes:
        if (epoch.registry_sha256 != scope.registry_sha256
                or epoch.observed_at_ms <= previous_ms
                or epoch.observed_at_ms > decision_at_ms
                or _scope_contract_fingerprint(epoch) != identity):
            raise DataValidationError("offline PIT epochs unordered or universe drifted")
        times.append(epoch.observed_at_ms)
        previous_ms = epoch.observed_at_ms
    return tuple(times)


@dataclass(frozen=True)
class OfflineStreamAudit:
    status: str
    persisted_rows: int
    observed_symbols: int
    journal_digest_sha256: str
    missing_24h_symbols: int
    complete_24h_symbols: int
    rank_digest_sha256: str | None
    complete_720h_symbols: int | None = None
    missing_720h_symbols: int | None = None
    missing_720h_hour_slots: int | None = None
    history_720h_digest_sha256: str | None = None
    pit_scope_count: int | None = None

    def sanitized_report(self) -> dict:
        result = {
            "status": self.status,
            "persisted_rows": self.persisted_rows,
            "observed_symbols": self.observed_symbols,
            "journal_digest_sha256": self.journal_digest_sha256,
            "missing_24h_symbols": self.missing_24h_symbols,
            "complete_24h_symbols": self.complete_24h_symbols,
            "rank_digest_sha256": self.rank_digest_sha256,
            "source_authenticated": False, "marketwide_top50_verified": False,
            "canonical_ohlcv_approved": False, "rights_for_live_authorized": False,
            "network_requests": 0, "orders_sent": False,
        }
        if self.pit_scope_count is not None:
            result.update({
                "historical_720h_status": (
                    "offline_720h_complete_not_marketwide"
                    if self.missing_720h_symbols == 0 and self.complete_720h_symbols
                    else "offline_720h_incomplete_abstain"),
                "complete_720h_symbols": self.complete_720h_symbols,
                "missing_720h_symbols": self.missing_720h_symbols,
                "missing_720h_hour_slots": self.missing_720h_hour_slots,
                "history_720h_digest_sha256": self.history_720h_digest_sha256,
                "pit_scope_count": self.pit_scope_count,
            })
        return result


class SQLiteOfflineClosedStreamJournal:
    """Explicit new offline-only SQLite; never touch owner REST research database.

    create() uses exclusive file creation to avoid overwriting any existing file.
    append() is single-event transactional and fail-closed on gaps or conflict.
    audit() opens a read-only consistent SQLite snapshot and validates all rows.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @classmethod
    def create(cls, path: str | Path):
        p = Path(path)
        if p.is_symlink() or not p.parent.is_dir():
            raise DataValidationError("offline journal needs existing safe parent")
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created = os.fstat(fd)
        os.close(fd)
        try:
            with closing(sqlite3.connect(p)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.executescript("""
                    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    INSERT INTO meta VALUES ('schema', 'j1-bybit-ws-closed-fixture-v1');
                    CREATE TABLE confirmed (
                      symbol TEXT NOT NULL, open_ms INTEGER NOT NULL,
                      received_ms INTEGER NOT NULL, registry_sha256 TEXT NOT NULL,
                      payload TEXT NOT NULL, digest TEXT NOT NULL,
                      PRIMARY KEY (symbol, open_ms)
                    );
                """)
        except Exception:
            # Do not delete a competing process's replacement at the same path.
            try:
                current = p.lstat()
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    p.unlink()
            except FileNotFoundError:
                pass
            raise
        return cls(p)

    def _check_schema(self, db: sqlite3.Connection):
        try:
            meta = db.execute("SELECT key, value FROM meta").fetchall()
            objects = set(db.execute(
                "SELECT type, name FROM sqlite_master "
                "WHERE type IN ('table', 'trigger', 'view')"))
            if meta != [("schema", _VERSION)] or objects != {
                ("table", "meta"), ("table", "confirmed")
            }:
                raise DataGapError("offline journal schema mismatch")
        except sqlite3.DatabaseError:
            raise DataGapError("offline journal schema unreadable") from None

    def append(self, event: OfflineConfirmedKline) -> str:
        if (type(event) is not OfflineConfirmedKline
                or type(event.open_ms) is not int
                or type(event.received_ms) is not int):
            raise DataValidationError("only parsed confirmed offline kline may be appended")
        payload = _validated_payload(event.payload, event.digest)
        if (payload["symbol"] != event.symbol
                or payload["open_ms"] != event.open_ms
                or payload["received_ms"] != event.received_ms
                or payload["registry_sha256"] != event.registry_sha256):
            raise DataGapError("offline event metadata mismatch")
        if self.path.is_symlink() or not self.path.is_file():
            raise DataGapError("offline journal file not present or not regular")
        try:
            with closing(sqlite3.connect(self.path, timeout=1)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                self._check_schema(db)
                previous = db.execute(
                    "SELECT payload, digest FROM confirmed WHERE symbol=? AND open_ms=?",
                    (event.symbol, event.open_ms),
                ).fetchone()
                if previous:
                    _validated_payload(previous[0], previous[1])
                    if previous != (event.payload, event.digest):
                        raise DataGapError("conflicting replay of closed hour")
                    return "idempotent"
                count = db.execute("SELECT COUNT(*) FROM confirmed").fetchone()[0]
                if count >= MAX_JOURNAL_ROWS:
                    raise DataGapError("offline journal row budget exhausted")
                newest = db.execute(
                    "SELECT open_ms, received_ms, registry_sha256, payload, digest FROM confirmed "
                    "WHERE symbol=? ORDER BY open_ms DESC LIMIT 1", (event.symbol,),
                ).fetchone()
                if newest:
                    old = _validated_payload(newest[3], newest[4])
                    if (old["symbol"] != event.symbol or old["open_ms"] != newest[0]
                            or old["received_ms"] != newest[1]
                            or old["registry_sha256"] != newest[2]):
                        raise DataGapError("offline predecessor was corrupted")
                if newest and (event.open_ms != newest[0] + HOUR_MS
                               or event.received_ms <= newest[1]
                               or event.registry_sha256 != newest[2]):
                    raise DataGapError("offline kline gap, backfill or registry drift: abstain")
                db.execute(
                    "INSERT INTO confirmed VALUES (?, ?, ?, ?, ?, ?)",
                    (event.symbol, event.open_ms, event.received_ms,
                     event.registry_sha256, event.payload, event.digest),
                )
            return "appended"
        except sqlite3.DatabaseError:
            raise DataGapError("offline journal write failed closed") from None

    def audit(self, *, scope: OfflineReviewedStreamScope,
              decision_at_ms: int, as_of_ms: int,
              historical_scopes: tuple[OfflineReviewedStreamScope, ...] | None = None,
              ) -> OfflineStreamAudit:
        if (type(scope) is not OfflineReviewedStreamScope
                or type(decision_at_ms) is not int
                or type(as_of_ms) is not int or decision_at_ms <= 0
                or decision_at_ms % HOUR_MS
                or not decision_at_ms + 1000 <= as_of_ms < decision_at_ms + HOUR_MS):
            raise DataValidationError("offline ranking requires closed UTC decision clock")
        # Legacy 24h calls preserve the original one-scope contract. The 720h
        # path explicitly opts into a bounded PIT series without altering DB.
        epoch_times = (_validate_pit_scopes(scope, historical_scopes, decision_at_ms)
                       if historical_scopes is not None else None)
        if epoch_times is not None and decision_at_ms <= HISTORICAL_HOURS * HOUR_MS:
            raise DataValidationError("offline 720h decision predates valid UTC history")
        # mode=ro and BEGIN ensure all checks observe exactly ONE SQLite snapshot.
        # SQLite returns a complete report or throws: no partial accepted rank.
        if self.path.is_symlink() or not self.path.is_file():
            raise DataGapError("offline journal is missing or unsafe")
        uri = "file:" + quote(self.path.absolute().as_posix(), safe="/") + "?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True)) as db:
                db.execute("BEGIN")
                if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise DataGapError("offline journal integrity check failed")
                self._check_schema(db)
                rows = db.execute(
                    "SELECT symbol, open_ms, received_ms, registry_sha256, payload, digest "
                    "FROM confirmed ORDER BY symbol, open_ms"
                ).fetchall()
                if len(rows) > MAX_JOURNAL_ROWS:
                    raise DataGapError("offline journal exceeds bounded row budget")
                allowed = {m.symbol: m for m in scope.contracts}
                by_symbol: dict[str, dict[int, dict]] = {}
                last: dict[str, tuple[int, int]] = {}
                summary = []
                for symbol, open_ms, received_ms, registry, raw, digest in rows:
                    data = _validated_payload(raw, digest)
                    member = allowed.get(symbol)
                    expected_scope_ms = scope.observed_at_ms
                    if epoch_times is not None:
                        # At every server close, the most recent known snapshot
                        # must be used; a later review cannot validate older data.
                        epoch_index = bisect_right(epoch_times, data["server_ms"]) - 1
                        if epoch_index < 0:
                            raise DataGapError("offline PIT candle predates first scope")
                        expected_scope_ms = epoch_times[epoch_index]
                    if (member is None or symbol != data["symbol"]
                            or open_ms != data["open_ms"]
                            or received_ms != data["received_ms"]
                            or registry != scope.registry_sha256
                            or registry != data["registry_sha256"]
                            or data["launch_ms"] != member.launch_time_ms
                            or data["scope_observed_ms"] != expected_scope_ms):
                        raise DataGapError("offline journal membership/identity changed")
                    earlier = last.get(symbol)
                    if earlier and (open_ms != earlier[0] + HOUR_MS
                                    or received_ms <= earlier[1]):
                        raise DataGapError("offline journal chronology or gap detected")
                    last[symbol] = (open_ms, received_ms)
                    by_symbol.setdefault(symbol, {})[open_ms] = data
                    summary.append([symbol, open_ms, digest])
                journal_digest = _sha(_json({"rows": summary, "schema": _VERSION}))
                missing = 0
                values: list[tuple[str, Decimal]] = []
                required = range(decision_at_ms - 24 * HOUR_MS,
                                 decision_at_ms, HOUR_MS)
                with localcontext(Context(prec=72)):
                    for member in scope.contracts:
                        if member.launch_time_ms > decision_at_ms - 24 * HOUR_MS:
                            missing += 1
                            continue
                        bars = by_symbol.get(member.symbol, {})
                        if any(t not in bars or bars[t]["received_ms"] > as_of_ms
                               for t in required):
                            missing += 1
                            continue
                        total = sum((Decimal(bars[t]["turnover_usdt"]) for t in required), Decimal(0))
                        if not total.is_finite() or total < 0:
                            raise DataGapError("nonfinite offline turnover sum")
                        values.append((member.symbol, total))
                    values.sort(key=lambda x: (-x[1], x[0]))
                    rank_digest = (_sha(_json({"decision": decision_at_ms,
                                               "registry": scope.registry_sha256,
                                               "ranked": [[s, format(v, "f")] for s, v in values]}))
                                   if values and not missing else None)
                history_complete = history_missing = history_slots = None
                history_digest = None
                if epoch_times is not None:
                    history_complete = history_missing = history_slots = 0
                    start_720 = decision_at_ms - HISTORICAL_HOURS * HOUR_MS
                    required_720 = range(start_720, decision_at_ms, HOUR_MS)
                    for member in scope.contracts:
                        bars = by_symbol.get(member.symbol, {})
                        missing_slots = sum(
                            member.launch_time_ms > t or t not in bars
                            or bars[t]["received_ms"] > as_of_ms
                            for t in required_720
                        )
                        history_slots += missing_slots
                        if missing_slots:
                            history_missing += 1
                        else:
                            history_complete += 1
                    if history_complete and not history_missing:
                        # Hash of a bounded closed window and PIT epochs, not a
                        # signature, licensed data or a live venue attestation.
                        history_digest = _sha(_json({
                            "decision": decision_at_ms,
                            "hours": HISTORICAL_HOURS,
                            "registry": scope.registry_sha256,
                            "epochs": list(epoch_times),
                            "rows": [item for item in summary
                                     if start_720 <= item[1] < decision_at_ms],
                        }))
                # 24h sample ranking is unchanged by an incomplete 720h window.
                # Neither is an authenticated marketwide ranking.
                return OfflineStreamAudit(
                    ("offline_reviewed_24h_complete_not_top50" if not missing and values
                     else "offline_closed_stream_incomplete_abstain"),
                    len(rows), len(by_symbol), journal_digest, missing,
                    len(values), rank_digest,
                    history_complete, history_missing, history_slots,
                    history_digest, len(epoch_times) if epoch_times is not None else None,
                )
        except sqlite3.DatabaseError:
            raise DataGapError("offline journal read-only audit failed") from None
