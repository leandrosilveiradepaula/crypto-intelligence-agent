"""J1/WU54 — isolated SQLite lab for UNVERIFIED Bybit V5 research candles.

Only bounded raw JSON bytes plus an explicitly self-declared local manifest can
enter this store. They are validated by the existing WU39 parser on EVERY write.
No network, credentials, canonical ClosedCandle, signals, trades or rights grant.
The separate, opt-in SQLite file must never be a canonical market-data database.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .bybit_instrument_volume_contract import stage_bybit_documented_linear_pair
from .bybit_local_json_audit import (
    LocalBybitCaptureManifest, MAX_LOCAL_BODY, MAX_WINDOW_CANDLES,
)
from .decimal_json import decode_public_market_json_exact
from .market_data import (
    DataGapError, DataValidationError, DuplicateCandleError,
    interval_duration_ms, interval_open_aligned,
)

SCHEMA_VERSION = "bybit-private-research-staging-v1"
INPUT_ORIGIN = "unverified_fixture_or_private_research"
EXCHANGE = "bybit_v5"
MARKET = "linear_perpetual"
_ENVIRONMENTS = frozenset({"offline_fixture", "private_local_unverified"})
_CANONICAL_TABLES = frozenset({
    "candles", "checkpoints", "contract_specs", "universe_snapshots",
    "collection_events",
})
_ALLOWED_TABLES = frozenset({
    "bybit_research_meta", "bybit_research_pages", "bybit_research_candles",
})
_MAX_QUALITY_CANDLES = 10_000


@dataclass(frozen=True)
class BybitResearchStoredCandle:
    """Exact decimals but not a canonical ClosedCandle."""
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    documented_base_volume: Decimal
    documented_quote_turnover: Decimal


@dataclass(frozen=True)
class BybitResearchStoredPage:
    symbol: str
    interval: str
    start_open_ms: int
    end_open_ms: int
    instrument_observed_at_ms: int
    kline_observed_at_ms: int
    capture_environment: str
    registry_sha256: str
    base_unit: str
    quote_unit: str
    instrument_bytes_sha256: str
    kline_bytes_sha256: str
    content_sha256: str
    candles: tuple[BybitResearchStoredCandle, ...]

    @property
    def exchange(self) -> str:
        return EXCHANGE

    @property
    def market(self) -> str:
        return MARKET

    @property
    def input_origin(self) -> str:
        return INPUT_ORIGIN

    @property
    def provider_origin_authenticated(self) -> bool:
        return False

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def historical_top50_approved(self) -> bool:
        return False

    @property
    def rights_authorized(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class BybitResearchQualityReport:
    symbol: str
    interval: str
    start_open_ms: int
    end_open_ms: int
    expected_candles: int
    persisted_candles: int
    missing_open_times_ms: tuple[int, ...]
    conflicting_duplicates: int | None = None

    @property
    def complete_for_offline_staging_only(self) -> bool:
        return (self.persisted_candles == self.expected_candles
                and not self.missing_open_times_ms)

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def rights_authorized(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False


def _rows_of(candles) -> tuple[tuple[object, ...], ...]:
    """Values follow exactly the research-only SQLite column order."""
    return tuple((
        c.open_time_ms, c.close_time_ms, str(c.open), str(c.high),
        str(c.low), str(c.close), str(c.documented_base_volume),
        str(c.documented_quote_turnover),
    ) for c in candles)


def _digest(rows: tuple[tuple[object, ...], ...]) -> str:
    return sha256(json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
                  .encode("ascii")).hexdigest()


def _check_window(symbol: str, interval: str, start: int, end: int) -> int:
    if (type(symbol) is not str or not symbol.isascii()
            or not 6 <= len(symbol) <= 30 or not symbol.isupper()
            or not (symbol.endswith("USDT") or symbol.endswith("USDC"))
            or interval != "1h"
            or type(start) is not int or type(end) is not int
            or start < 0 or end <= start
            or not interval_open_aligned(interval, start)
            or not interval_open_aligned(interval, end)):
        raise DataValidationError("invalid UTC research replay window")
    count = (end - start) // interval_duration_ms(interval)
    if count > _MAX_QUALITY_CANDLES:
        raise DataValidationError("research replay window exceeds bounded capacity")
    return count


class SQLiteBybitResearchStore:
    """Explicit opt-in lab DB, never sharing canonical candle/checkpoint tables."""

    def __init__(self, path: str | Path) -> None:
        if (type(path) not in (str, Path) or not str(path)
                or str(path) == ":memory:" or Path(path).is_symlink()
                or Path(path).is_dir()):
            raise ValueError("research-only SQLite requires a separate local file")
        self._path = str(path)
        self._initialize()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        # Zero busy wait: a concurrent writer must fail, never skip/reorder.
        connection = sqlite3.connect(self._path, timeout=0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._transaction() as db:
            current = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'sqlite_%'"
            )}
            if current & _CANONICAL_TABLES or current - _ALLOWED_TABLES:
                raise DataValidationError(
                    "research DB must not reuse canonical or unknown SQLite tables"
                )
            db.execute("""
                CREATE TABLE IF NOT EXISTS bybit_research_meta (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    schema_version TEXT NOT NULL,
                    input_origin TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS bybit_research_pages (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL, interval TEXT NOT NULL,
                    start_open_ms INTEGER NOT NULL, end_open_ms INTEGER NOT NULL,
                    instrument_observed_at_ms INTEGER NOT NULL,
                    kline_observed_at_ms INTEGER NOT NULL,
                    capture_environment TEXT NOT NULL,
                    registry_sha256 TEXT NOT NULL,
                    base_unit TEXT NOT NULL, quote_unit TEXT NOT NULL,
                    instrument_bytes_sha256 TEXT NOT NULL,
                    kline_bytes_sha256 TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    UNIQUE(symbol, interval, start_open_ms, end_open_ms)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS bybit_research_candles (
                    page_id INTEGER NOT NULL,
                    open_time_ms INTEGER NOT NULL,
                    close_time_ms INTEGER NOT NULL,
                    open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    documented_base_volume TEXT NOT NULL,
                    documented_quote_turnover TEXT NOT NULL,
                    PRIMARY KEY(page_id, open_time_ms),
                    FOREIGN KEY(page_id) REFERENCES bybit_research_pages(id)
                )
            """)
            row = db.execute("SELECT * FROM bybit_research_meta").fetchall()
            if row and (len(row) != 1 or row[0]["id"] != 1
                        or row[0]["schema_version"] != SCHEMA_VERSION
                        or row[0]["input_origin"] != INPUT_ORIGIN):
                raise DataValidationError("unrecognized research DB schema or origin")
            if not row:
                db.execute(
                    "INSERT INTO bybit_research_meta VALUES(1, ?, ?)",
                    (SCHEMA_VERSION, INPUT_ORIGIN),
                )

    @staticmethod
    def _read_rows(db: sqlite3.Connection, page_id: int
                   ) -> tuple[tuple[object, ...], ...]:
        return tuple(tuple(row) for row in db.execute(
            """SELECT open_time_ms, close_time_ms, open, high, low, close,
                      documented_base_volume, documented_quote_turnover
               FROM bybit_research_candles
               WHERE page_id=? ORDER BY open_time_ms""", (page_id,),
        ).fetchall())

    def commit_raw_pair(
        self, *, instrument_raw: bytes, kline_raw: bytes,
        manifest: LocalBybitCaptureManifest,
        capture_environment: str = "offline_fixture",
    ) -> BybitResearchStoredPage:
        """Parse raw bytes anew, then atomically save only UNVERIFIED research.

        A caller's timestamp/environment/hash is NOT a provider attestation.
        Identical raw bytes + manifest replay idempotently; changed bytes,
        economic values or capture metadata in the same window fail closed.
        """
        if type(manifest) is not LocalBybitCaptureManifest:
            raise DataValidationError("typed self-declared manifest is required")
        if (type(capture_environment) is not str
                or capture_environment not in _ENVIRONMENTS):
            raise DataValidationError("unrecognized offline research environment")
        if (type(instrument_raw) is not bytes or type(kline_raw) is not bytes
                or not 1 <= len(instrument_raw) <= MAX_LOCAL_BODY
                or not 1 <= len(kline_raw) <= MAX_LOCAL_BODY):
            raise DataValidationError("bounded raw Bybit JSON bytes required")
        instrument = decode_public_market_json_exact(
            instrument_raw, max_bytes=MAX_LOCAL_BODY
        )
        kline = decode_public_market_json_exact(
            kline_raw, max_bytes=MAX_LOCAL_BODY
        )
        page = stage_bybit_documented_linear_pair(
            instrument_payload=instrument, kline_payload=kline,
            symbol=manifest.symbol,
            instrument_observed_at_ms=manifest.instrument_received_ms,
            kline_observed_at_ms=manifest.kline_received_ms,
            interval=manifest.interval,
            start_open_ms=manifest.start_open_ms,
            end_open_ms=manifest.end_open_ms,
            registry_variant=manifest.registry_variant,
            max_contract_age_ms=30_000,
            close_safety_ms=1_000,
        )
        count = _check_window(
            manifest.symbol, manifest.interval,
            manifest.start_open_ms, manifest.end_open_ms,
        )
        if (count > MAX_WINDOW_CANDLES or len(page.page.candles) != count
                or page.canonical_ohlcv or page.live_provider_verified
                or page.public_or_commercial_use_authorized
                or page.quote_turnover_unit not in ("USDT", "USDC")
                or page.base_volume_unit != page.instrument.base_coin):
            raise DataValidationError("invalid unverified Bybit research page")
        rows = _rows_of(page.page.candles)
        header = (
            manifest.symbol, manifest.interval, manifest.start_open_ms,
            manifest.end_open_ms, manifest.instrument_received_ms,
            manifest.kline_received_ms, capture_environment,
            page.instrument.registry_sha256,
            page.base_volume_unit, page.quote_turnover_unit,
            sha256(instrument_raw).hexdigest(), sha256(kline_raw).hexdigest(),
            _digest(rows),
        )
        with self._transaction() as db:
            existing = db.execute(
                """SELECT * FROM bybit_research_pages
                   WHERE symbol=? AND interval=?
                     AND start_open_ms=? AND end_open_ms=?""",
                (manifest.symbol, manifest.interval,
                 manifest.start_open_ms, manifest.end_open_ms),
            ).fetchone()
            if existing is not None:
                same = tuple(existing[key] for key in (
                    "symbol", "interval", "start_open_ms", "end_open_ms",
                    "instrument_observed_at_ms", "kline_observed_at_ms",
                    "capture_environment", "registry_sha256", "base_unit",
                    "quote_unit", "instrument_bytes_sha256",
                    "kline_bytes_sha256", "content_sha256",
                )) == header
                if not same or self._read_rows(db, existing["id"]) != rows:
                    raise DuplicateCandleError(
                        "conflicting immutable Bybit research page replay"
                    )
            else:
                # Every symbol/interval forms one contiguous, time-ordered
                # research-only chain. Never fill holes without explicit review.
                history = db.execute(
                    """SELECT start_open_ms, end_open_ms, registry_sha256,
                              capture_environment
                       FROM bybit_research_pages
                       WHERE symbol=? AND interval=? ORDER BY start_open_ms""",
                    (manifest.symbol, manifest.interval),
                ).fetchall()
                cursor = None
                for previous in history:
                    if cursor is not None and previous["start_open_ms"] != cursor:
                        raise DataGapError("stored research chain is not contiguous")
                    cursor = previous["end_open_ms"]
                    if (previous["registry_sha256"] != header[7]
                            or previous["capture_environment"] != capture_environment):
                        raise DataValidationError(
                            "research history cannot silently change registry or origin"
                        )
                if cursor is not None and manifest.start_open_ms != cursor:
                    raise DataGapError("new research page must extend exactly one UTC window")
                db.execute(
                    """INSERT INTO bybit_research_pages (
                       symbol, interval, start_open_ms, end_open_ms,
                       instrument_observed_at_ms, kline_observed_at_ms,
                       capture_environment, registry_sha256, base_unit,
                       quote_unit, instrument_bytes_sha256,
                       kline_bytes_sha256, content_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    header,
                )
                page_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                db.executemany(
                    """INSERT INTO bybit_research_candles (
                       page_id, open_time_ms, close_time_ms, open, high, low,
                       close, documented_base_volume, documented_quote_turnover
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ((page_id, *r) for r in rows),
                )
        return self.replay_page(
            symbol=manifest.symbol, interval=manifest.interval,
            start_open_ms=manifest.start_open_ms,
            end_open_ms=manifest.end_open_ms,
        )

    def replay_page(
        self, *, symbol: str, interval: str,
        start_open_ms: int, end_open_ms: int,
    ) -> BybitResearchStoredPage:
        expected = _check_window(symbol, interval, start_open_ms, end_open_ms)
        with self._transaction() as db:
            page = db.execute(
                """SELECT * FROM bybit_research_pages
                   WHERE symbol=? AND interval=?
                     AND start_open_ms=? AND end_open_ms=?""",
                (symbol, interval, start_open_ms, end_open_ms),
            ).fetchone()
            if page is None:
                raise DataGapError("unavailable research page: no implicit fetch")
            rows = self._read_rows(db, page["id"])
        if len(rows) != expected or _digest(rows) != page["content_sha256"]:
            raise DataGapError("research candle content or page digest inconsistent")
        duration = interval_duration_ms(interval)
        candles = []
        try:
            for i, values in enumerate(rows):
                if (values[0] != start_open_ms + i * duration
                        or values[1] != values[0] + duration - 1):
                    raise DataGapError("research replay timestamps are inconsistent")
                parsed = tuple(Decimal(v) for v in values[2:])
                if (any(not v.is_finite() for v in parsed)
                        or min(parsed[:4]) <= 0
                        or parsed[1] < max(parsed[0], parsed[3])
                        or parsed[2] > min(parsed[0], parsed[3])
                        or parsed[4] < 0 or parsed[5] < 0):
                    raise DataGapError("invalid replayed research OHLC/volumes")
                candles.append(BybitResearchStoredCandle(values[0], values[1], *parsed))
        except (ValueError, ArithmeticError) as exc:
            raise DataGapError("corrupt decimal text in research page") from exc
        if (page["quote_unit"] not in ("USDT", "USDC")
                or not symbol.endswith(page["quote_unit"])
                or page["base_unit"] != symbol[:-len(page["quote_unit"])]
                or page["capture_environment"] not in _ENVIRONMENTS
                or page["registry_sha256"] is None):
            raise DataGapError("corrupt or mixed Bybit research metadata")
        return BybitResearchStoredPage(
            symbol, interval, start_open_ms, end_open_ms,
            page["instrument_observed_at_ms"], page["kline_observed_at_ms"],
            page["capture_environment"], page["registry_sha256"],
            page["base_unit"], page["quote_unit"],
            page["instrument_bytes_sha256"], page["kline_bytes_sha256"],
            page["content_sha256"], tuple(candles),
        )

    def quality_report(
        self, *, symbol: str, interval: str,
        start_open_ms: int, end_open_ms: int,
    ) -> BybitResearchQualityReport:
        expected = _check_window(symbol, interval, start_open_ms, end_open_ms)
        with self._transaction() as db:
            found = {row[0] for row in db.execute(
                """SELECT c.open_time_ms FROM bybit_research_candles c
                   JOIN bybit_research_pages p ON p.id=c.page_id
                   WHERE p.symbol=? AND p.interval=?
                     AND c.open_time_ms>=? AND c.open_time_ms<?
                   ORDER BY c.open_time_ms""",
                (symbol, interval, start_open_ms, end_open_ms),
            )}
            page_windows = tuple(tuple(row) for row in db.execute(
                """SELECT start_open_ms, end_open_ms FROM bybit_research_pages
                   WHERE symbol=? AND interval=? AND start_open_ms<?
                     AND end_open_ms>? ORDER BY start_open_ms""",
                (symbol, interval, end_open_ms, start_open_ms),
            ))
        # A count of timestamps is not proof that persisted decimals or the
        # page digest are intact. Validate every overlapping whole page first.
        for begin, finish in page_windows:
            self.replay_page(
                symbol=symbol, interval=interval,
                start_open_ms=begin, end_open_ms=finish,
            )
        missing = tuple(i for i in range(
            start_open_ms, end_open_ms, interval_duration_ms(interval)
        ) if i not in found)
        return BybitResearchQualityReport(
            symbol, interval, start_open_ms, end_open_ms,
            expected, len(found), missing,
        )
