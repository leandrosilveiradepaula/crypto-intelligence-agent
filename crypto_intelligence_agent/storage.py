"""Durable, local reference storage for J1 market-data records.

SQLite is intentionally an implementation behind ``MarketDataStore``. Decimal
values are stored as their canonical text representations, never as SQLite
REAL values, so replay preserves the source precision.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Protocol, Sequence

from .market_data import (
    ClosedCandle, ContractSpec, DataGapError, DuplicateCandleError,
    MarketDataCheckpoint, UniverseMember, UniverseSnapshot, interval_duration_ms, interval_open_aligned,
)


class MarketDataStore(Protocol):
    def commit_candle_page(self, candles: Sequence[ClosedCandle], checkpoint: MarketDataCheckpoint) -> None: ...
    def latest_checkpoint(self, *, data_type: str, exchange: str, symbol: str, interval: str | None) -> MarketDataCheckpoint | None: ...
    def candles(self, *, exchange: str, market: str, symbol: str, interval: str, start_open_ms: int, end_open_ms: int) -> tuple[ClosedCandle, ...]: ...
    def save_contracts(self, contracts: Sequence[ContractSpec]) -> None: ...
    def contracts(self, *, exchange: str, market: str, observed_at_ms: int) -> tuple[ContractSpec, ...]: ...
    def save_universe_snapshot(self, snapshot: UniverseSnapshot) -> None: ...
    def universe_snapshot(self, *, observed_at_ms: int, selection_rule_version: str, source: str) -> UniverseSnapshot | None: ...
    def quality_report(self, *, exchange: str, market: str, symbol: str, interval: str, start_open_ms: int, end_open_ms: int) -> DataQualityReport: ...
    def record_collection_event(self, event: CollectionEvent) -> None: ...


@dataclass(frozen=True)
class CollectionEvent:
    """Durable metadata about public reads; no credentials or private URLs."""

    observed_start_ms: int
    observed_end_ms: int
    mode: str
    source: str
    exchange: str
    endpoint: str
    selection_rule_version: str
    symbol: str | None
    interval: str | None
    status: str
    detail: str
    pages_committed: int = 0
    candles_committed: int = 0


@dataclass(frozen=True)
class DataQualityReport:
    exchange: str
    market: str
    symbol: str
    interval: str
    start_open_ms: int
    end_open_ms: int
    expected_candles: int
    persisted_candles: int
    missing_open_times_ms: tuple[int, ...]
    # Rejected conflicts are not retained as market data. We intentionally
    # report "not measured" rather than fabricating a zero incident count.
    conflicting_duplicates: int | None
    latest_checkpoint: MarketDataCheckpoint | None

    @property
    def complete(self) -> bool:
        checkpoint = self.latest_checkpoint
        return bool(
            not self.missing_open_times_ms
            and self.persisted_candles == self.expected_candles
            and checkpoint is not None
            and checkpoint.integrity == "complete"
            and checkpoint.confirmed_start_ms <= self.start_open_ms
            and checkpoint.confirmed_end_ms >= self.end_open_ms - 1
        )


class SQLiteMarketDataStore:
    """SQLite reference store for local development and offline test replay."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        # Every operation uses a fresh connection for explicit transaction
        # boundaries. Plain :memory: would silently lose its schema on close.
        if not self._path or self._path == ":memory:":
            raise ValueError("provide a durable SQLite file path, not ':memory:'")
        self._initialize()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._transaction() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS candles (
                    exchange TEXT NOT NULL, market TEXT NOT NULL, symbol TEXT NOT NULL, interval TEXT NOT NULL,
                    open_time_ms INTEGER NOT NULL, close_time_ms INTEGER NOT NULL,
                    open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
                    base_volume TEXT NOT NULL, quote_volume TEXT NOT NULL, quality TEXT NOT NULL,
                    PRIMARY KEY (exchange, market, symbol, interval, open_time_ms)
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    data_type TEXT NOT NULL, exchange TEXT NOT NULL, symbol TEXT NOT NULL, interval TEXT,
                    confirmed_start_ms INTEGER NOT NULL, confirmed_end_ms INTEGER NOT NULL,
                    source TEXT NOT NULL, contract_version TEXT NOT NULL, integrity TEXT NOT NULL,
                    PRIMARY KEY (data_type, exchange, symbol, interval)
                );
                CREATE TABLE IF NOT EXISTS contract_specs (
                    exchange TEXT NOT NULL, market TEXT NOT NULL, symbol TEXT NOT NULL, observed_at_ms INTEGER NOT NULL,
                    base_asset TEXT NOT NULL, quote_asset TEXT NOT NULL, contract_type TEXT NOT NULL, status TEXT NOT NULL,
                    onboard_time_ms INTEGER NOT NULL, tick_size TEXT NOT NULL, step_size TEXT NOT NULL, min_qty TEXT NOT NULL,
                    min_notional TEXT, source TEXT NOT NULL,
                    PRIMARY KEY (exchange, market, symbol, observed_at_ms)
                );
                CREATE TABLE IF NOT EXISTS universe_snapshots (
                    observed_at_ms INTEGER NOT NULL, selection_rule_version TEXT NOT NULL, source TEXT NOT NULL,
                    eligible_json TEXT NOT NULL, excluded_json TEXT NOT NULL,
                    PRIMARY KEY (observed_at_ms, selection_rule_version, source)
                );
                CREATE TABLE IF NOT EXISTS collection_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_start_ms INTEGER NOT NULL, observed_end_ms INTEGER NOT NULL,
                    mode TEXT NOT NULL, source TEXT NOT NULL, exchange TEXT NOT NULL,
                    endpoint TEXT NOT NULL, selection_rule_version TEXT NOT NULL,
                    symbol TEXT, interval TEXT, status TEXT NOT NULL,
                    detail TEXT NOT NULL, pages_committed INTEGER NOT NULL,
                    candles_committed INTEGER NOT NULL
                );
            """)

    def commit_candle_page(self, candles: Sequence[ClosedCandle], checkpoint: MarketDataCheckpoint) -> None:
        if not candles:
            raise DataGapError("cannot checkpoint an empty candle page")
        _validate_checkpoint_page(candles, checkpoint)
        with self._transaction() as connection:
            for candle in candles:
                existing = connection.execute(
                    "SELECT * FROM candles WHERE exchange=? AND market=? AND symbol=? AND interval=? AND open_time_ms=?",
                    candle.identity,
                ).fetchone()
                if existing is not None and _candle_from_row(existing) != candle:
                    raise DuplicateCandleError(f"conflicting persisted duplicate candle at {candle.identity}")
            for candle in candles:
                connection.execute(
                    "INSERT OR IGNORE INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _candle_values(candle),
                )
            previous = _checkpoint_from_row(connection.execute(
                "SELECT * FROM checkpoints WHERE data_type=? AND exchange=? AND symbol=? AND interval IS ?",
                (checkpoint.data_type, checkpoint.exchange, checkpoint.symbol, checkpoint.interval),
            ).fetchone())
            if previous is None:
                if checkpoint.confirmed_start_ms != candles[0].open_time_ms:
                    raise DataGapError("first checkpoint must begin at first persisted candle")
            else:
                if (checkpoint.source != previous.source
                        or checkpoint.contract_version != previous.contract_version
                        or checkpoint.confirmed_start_ms != previous.confirmed_start_ms
                        or previous.integrity != "complete"):
                    raise DataGapError("checkpoint provenance, start or integrity has changed")
                if checkpoint.confirmed_end_ms < previous.confirmed_end_ms:
                    raise DataGapError("checkpoint cannot move backwards")
                if checkpoint.confirmed_end_ms > previous.confirmed_end_ms:
                    if candles[0].open_time_ms != previous.confirmed_end_ms + 1:
                        raise DataGapError("checkpoint extension must be adjacent to saved history")
                    prev_open = previous.confirmed_end_ms + 1 - interval_duration_ms(previous.interval)
                    last_saved = connection.execute(
                        """SELECT * FROM candles WHERE exchange=? AND market=? AND symbol=?
                           AND interval=? AND open_time_ms=?""",
                        (previous.exchange, candles[0].market, previous.symbol, previous.interval, prev_open),
                    ).fetchone()
                    if last_saved is None or last_saved["close_time_ms"] != previous.confirmed_end_ms:
                        raise DataGapError("checkpoint belongs to missing or different-market history")
            connection.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _checkpoint_values(checkpoint),
            )

    def latest_checkpoint(self, *, data_type: str, exchange: str, symbol: str, interval: str | None) -> MarketDataCheckpoint | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE data_type=? AND exchange=? AND symbol=? AND interval IS ?",
                (data_type, exchange, symbol, interval),
            ).fetchone()
        return _checkpoint_from_row(row)

    def candles(self, *, exchange: str, market: str, symbol: str, interval: str, start_open_ms: int, end_open_ms: int) -> tuple[ClosedCandle, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM candles WHERE exchange=? AND market=? AND symbol=? AND interval=?
                   AND open_time_ms>=? AND open_time_ms<? ORDER BY open_time_ms""",
                (exchange, market, symbol, interval, start_open_ms, end_open_ms),
            ).fetchall()
        return tuple(_candle_from_row(row) for row in rows)

    def save_contracts(self, contracts: Sequence[ContractSpec]) -> None:
        with self._transaction() as connection:
            for contract in contracts:
                values = (
                    contract.exchange, contract.market, contract.symbol, contract.observed_at_ms, contract.base_asset,
                    contract.quote_asset, contract.contract_type, contract.status, contract.onboard_time_ms,
                    str(contract.tick_size), str(contract.step_size), str(contract.min_qty),
                    str(contract.min_notional) if contract.min_notional is not None else None, contract.source,
                )
                existing = connection.execute(
                    """SELECT * FROM contract_specs WHERE exchange=? AND market=? AND symbol=?
                       AND observed_at_ms=?""",
                    (contract.exchange, contract.market, contract.symbol, contract.observed_at_ms),
                ).fetchone()
                if existing is not None and _contract_from_row(existing) != contract:
                    raise DuplicateCandleError(
                        f"conflicting immutable contract snapshot at {contract.exchange}/{contract.symbol}/{contract.observed_at_ms}"
                    )
                connection.execute(
                    "INSERT OR IGNORE INTO contract_specs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values
                )

    def contracts(self, *, exchange: str, market: str, observed_at_ms: int) -> tuple[ContractSpec, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                """SELECT * FROM contract_specs WHERE exchange=? AND market=? AND observed_at_ms=?
                   ORDER BY symbol""",
                (exchange, market, observed_at_ms),
            ).fetchall()
        return tuple(_contract_from_row(row) for row in rows)

    def save_universe_snapshot(self, snapshot: UniverseSnapshot) -> None:
        eligible_json = json.dumps(
            [{"symbol": member.symbol, "rank": member.rank, "quote_volume": str(member.quote_volume)} for member in snapshot.eligible],
            separators=(",", ":"), sort_keys=True,
        )
        excluded_json = json.dumps(dict(snapshot.excluded), separators=(",", ":"), sort_keys=True)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT eligible_json, excluded_json FROM universe_snapshots WHERE observed_at_ms=? AND selection_rule_version=? AND source=?",
                (snapshot.observed_at_ms, snapshot.selection_rule_version, snapshot.source),
            ).fetchone()
            if existing and (existing["eligible_json"] != eligible_json or existing["excluded_json"] != excluded_json):
                raise DuplicateCandleError("conflicting universe snapshot at the same observed timestamp")
            connection.execute(
                "INSERT OR IGNORE INTO universe_snapshots VALUES (?, ?, ?, ?, ?)",
                (snapshot.observed_at_ms, snapshot.selection_rule_version, snapshot.source, eligible_json, excluded_json),
            )

    def universe_snapshot(self, *, observed_at_ms: int, selection_rule_version: str, source: str) -> UniverseSnapshot | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM universe_snapshots WHERE observed_at_ms=? AND selection_rule_version=? AND source=?",
                (observed_at_ms, selection_rule_version, source),
            ).fetchone()
        if row is None:
            return None
        return UniverseSnapshot(
            observed_at_ms=row["observed_at_ms"], selection_rule_version=row["selection_rule_version"], source=row["source"],
            eligible=tuple(UniverseMember(item["symbol"], item["rank"], Decimal(item["quote_volume"])) for item in json.loads(row["eligible_json"])),
            excluded=json.loads(row["excluded_json"]),
        )

    def record_collection_event(self, event: CollectionEvent) -> None:
        if (type(event.observed_start_ms) is not int or type(event.observed_end_ms) is not int
                or event.observed_start_ms < 0 or event.observed_end_ms < event.observed_start_ms
                or event.mode not in {"offline", "live"}
                or event.status not in {"success", "failure"}
                or event.pages_committed < 0 or event.candles_committed < 0
                or not event.source or not event.exchange or not event.endpoint
                or not event.selection_rule_version):
            raise ValueError("invalid collection audit event")
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO collection_events (
                    observed_start_ms, observed_end_ms, mode, source, exchange,
                    endpoint, selection_rule_version, symbol, interval, status,
                    detail, pages_committed, candles_committed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.observed_start_ms, event.observed_end_ms,
                    event.mode, event.source, event.exchange, event.endpoint,
                    event.selection_rule_version, event.symbol, event.interval,
                    event.status, event.detail, event.pages_committed,
                    event.candles_committed,
                ),
            )

    def collection_events(self) -> tuple[CollectionEvent, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM collection_events ORDER BY event_id"
            ).fetchall()
        return tuple(CollectionEvent(
            observed_start_ms=row["observed_start_ms"],
            observed_end_ms=row["observed_end_ms"],
            mode=row["mode"], source=row["source"], exchange=row["exchange"],
            endpoint=row["endpoint"], selection_rule_version=row["selection_rule_version"],
            symbol=row["symbol"], interval=row["interval"], status=row["status"],
            detail=row["detail"], pages_committed=row["pages_committed"],
            candles_committed=row["candles_committed"],
        ) for row in rows)

    def quality_report(self, *, exchange: str, market: str, symbol: str, interval: str, start_open_ms: int, end_open_ms: int) -> DataQualityReport:
        duration = interval_duration_ms(interval)
        if (end_open_ms <= start_open_ms or not interval_open_aligned(interval, start_open_ms)
                or not interval_open_aligned(interval, end_open_ms)):
            raise ValueError("quality window must be a non-empty interval-aligned [start, end) range")
        candles = self.candles(exchange=exchange, market=market, symbol=symbol, interval=interval, start_open_ms=start_open_ms, end_open_ms=end_open_ms)
        opens = {candle.open_time_ms for candle in candles}
        missing = tuple(open_time for open_time in range(start_open_ms, end_open_ms, duration) if open_time not in opens)
        return DataQualityReport(
            exchange=exchange, market=market, symbol=symbol, interval=interval, start_open_ms=start_open_ms, end_open_ms=end_open_ms,
            expected_candles=(end_open_ms - start_open_ms) // duration, persisted_candles=len(candles), missing_open_times_ms=missing,
            conflicting_duplicates=None,
            latest_checkpoint=self.latest_checkpoint(data_type="closed_candle", exchange=exchange, symbol=symbol, interval=interval),
        )


def _validate_checkpoint_page(candles: Sequence[ClosedCandle], checkpoint: MarketDataCheckpoint) -> None:
    first, last = candles[0], candles[-1]
    duration = interval_duration_ms(first.interval)
    if (checkpoint.data_type != "closed_candle" or checkpoint.exchange != first.exchange
            or checkpoint.symbol != first.symbol or checkpoint.interval != first.interval
            or checkpoint.confirmed_end_ms != last.close_time_ms
            or checkpoint.confirmed_start_ms > first.open_time_ms
            or checkpoint.integrity != "complete"):
        raise DataGapError("checkpoint does not describe a complete candle page")
    for index, candle in enumerate(candles):
        if (candle.exchange, candle.market, candle.symbol, candle.interval) != (
            first.exchange, first.market, first.symbol, first.interval
        ):
            raise DataGapError("mixed candle identities inside one committed page")
        if candle.close_time_ms != candle.open_time_ms + duration - 1:
            raise DataGapError("invalid candle duration in committed page")
        if index and candle.open_time_ms != candles[index - 1].open_time_ms + duration:
            raise DataGapError("gap or non-monotonic ordering inside committed page")
        values = (candle.open, candle.high, candle.low, candle.close, candle.base_volume, candle.quote_volume)
        if any(not isinstance(v, Decimal) or not v.is_finite() for v in values):
            raise DataGapError("non-decimal or nonfinite market data in committed page")
        if (min(candle.open, candle.high, candle.low, candle.close) <= 0
                or candle.high < max(candle.open, candle.close)
                or candle.low > min(candle.open, candle.close)
                or candle.base_volume < 0 or candle.quote_volume < 0):
            raise DataGapError("invalid OHLC or negative volume in committed page")


def _candle_values(candle: ClosedCandle) -> tuple[object, ...]:
    return (*candle.identity, candle.close_time_ms, str(candle.open), str(candle.high), str(candle.low), str(candle.close), str(candle.base_volume), str(candle.quote_volume), candle.quality)


def _candle_from_row(row: sqlite3.Row) -> ClosedCandle:
    return ClosedCandle(
        exchange=row["exchange"], market=row["market"], symbol=row["symbol"], interval=row["interval"],
        open_time_ms=row["open_time_ms"], close_time_ms=row["close_time_ms"], open=Decimal(row["open"]), high=Decimal(row["high"]),
        low=Decimal(row["low"]), close=Decimal(row["close"]), base_volume=Decimal(row["base_volume"]), quote_volume=Decimal(row["quote_volume"]), quality=row["quality"],
    )


def _checkpoint_values(checkpoint: MarketDataCheckpoint) -> tuple[object, ...]:
    return (checkpoint.data_type, checkpoint.exchange, checkpoint.symbol, checkpoint.interval, checkpoint.confirmed_start_ms, checkpoint.confirmed_end_ms, checkpoint.source, checkpoint.contract_version, checkpoint.integrity)


def _contract_from_row(row: sqlite3.Row) -> ContractSpec:
    return ContractSpec(
        exchange=row["exchange"], market=row["market"], symbol=row["symbol"], base_asset=row["base_asset"],
        quote_asset=row["quote_asset"], contract_type=row["contract_type"], status=row["status"], onboard_time_ms=row["onboard_time_ms"],
        tick_size=Decimal(row["tick_size"]), step_size=Decimal(row["step_size"]), min_qty=Decimal(row["min_qty"]),
        min_notional=Decimal(row["min_notional"]) if row["min_notional"] is not None else None,
        observed_at_ms=row["observed_at_ms"], source=row["source"],
    )


def _checkpoint_from_row(row: sqlite3.Row | None) -> MarketDataCheckpoint | None:
    if row is None:
        return None
    return MarketDataCheckpoint(
        data_type=row["data_type"], exchange=row["exchange"], symbol=row["symbol"], interval=row["interval"],
        confirmed_start_ms=row["confirmed_start_ms"], confirmed_end_ms=row["confirmed_end_ms"], source=row["source"],
        contract_version=row["contract_version"], integrity=row["integrity"],
    )
