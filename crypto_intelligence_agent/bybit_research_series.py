"""J1 #245: consistent read-only replay of existing UNVERIFIED Bybit pages."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .bybit_research_storage import (
    SQLiteBybitResearchStore, BybitResearchStoredCandle,
    _ALLOWED_TABLES, _check_window, _digest, SCHEMA_VERSION, INPUT_ORIGIN,
)
from .market_data import DataGapError, DataValidationError, interval_duration_ms
from .paper_position_inspection import _checked_path


@dataclass(frozen=True)
class BybitResearchSeries:
    start_open_ms: int
    end_open_ms: int
    page_count: int
    candles: tuple[BybitResearchStoredCandle, ...]
    header_digest_sha256: str

    @property
    def source_authenticated(self) -> bool:
        return False

    @property
    def rights_authorized(self) -> bool:
        return False

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def historical_top50_approved(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def inspect_existing_bybit_research_series(
    path: str | Path, *, symbol: str, interval: str,
    start_open_ms: int, end_open_ms: int, as_of_ms: int,
) -> BybitResearchSeries:
    """Inspect a single coherent SQLite snapshot without creating a database.

    Never feed returned data to J2/J3/canonical paths or claim provenance.
    """
    expected = _check_window(symbol, interval, start_open_ms, end_open_ms)
    if (type(as_of_ms) is not int or as_of_ms <= 0
            or end_open_ms + 1000 > as_of_ms):
        raise DataValidationError("research series not fully closed at UTC cutoff")
    if expected < 3:
        raise DataValidationError("research series needs at least three bars")
    source = _checked_path(path)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            objects = db.execute(
                "SELECT type,name FROM sqlite_master "
                "WHERE type IN ('table','trigger','view') AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if (any(x["type"] != "table" for x in objects)
                    or {x["name"] for x in objects} != _ALLOWED_TABLES):
                raise DataValidationError("unknown research schema")
            meta = db.execute("SELECT * FROM bybit_research_meta").fetchall()
            if (len(meta) != 1 or meta[0]["id"] != 1
                    or meta[0]["schema_version"] != SCHEMA_VERSION
                    or meta[0]["input_origin"] != INPUT_ORIGIN):
                raise DataValidationError("unrecognized research origin")
            pages = db.execute(
                "SELECT * FROM bybit_research_pages WHERE symbol=? AND interval=? "
                "AND end_open_ms>? AND start_open_ms<? ORDER BY start_open_ms",
                (symbol, interval, start_open_ms, end_open_ms),
            ).fetchall()
            if not 1 <= len(pages) <= 140:
                raise DataGapError("unavailable bounded research series")
            cursor, base, quote, registry, environment = (
                start_open_ms, None, None, None, None
            )
            out = []
            headers = []
            for page in pages:
                if (page["start_open_ms"] != cursor
                        or page["end_open_ms"] <= cursor
                        or page["end_open_ms"] > end_open_ms
                        or (page["end_open_ms"] - cursor)
                           % interval_duration_ms(interval) != 0
                        or page["instrument_observed_at_ms"] >
                           page["kline_observed_at_ms"]
                        or page["kline_observed_at_ms"] < page["end_open_ms"] + 1000):
                    raise DataGapError("research page gap, overlap or invalid timestamp")
                if base is None:
                    base, quote = page["base_unit"], page["quote_unit"]
                    registry = page["registry_sha256"]
                    environment = page["capture_environment"]
                if (page["base_unit"] != base or page["quote_unit"] != quote
                        or page["registry_sha256"] != registry
                        or page["capture_environment"] != environment
                        or not isinstance(registry, str) or len(registry) != 64
                        or environment not in ("offline_fixture", "private_local_unverified")
                        or quote not in ("USDT", "USDC")
                        or not symbol.endswith(quote)
                        or base != symbol[:-len(quote)]):
                    raise DataValidationError("mixed research contract or origin")
                rows = SQLiteBybitResearchStore._read_rows(db, page["id"])
                if (_digest(rows) != page["content_sha256"]
                        or len(rows) != (page["end_open_ms"] - cursor)
                           // interval_duration_ms(interval)):
                    raise DataGapError("corrupted research page digest or row count")
                from decimal import Decimal
                for idx, row in enumerate(rows):
                    opened = cursor + idx * interval_duration_ms(interval)
                    if row[0] != opened or row[1] != opened + interval_duration_ms(interval) - 1:
                        raise DataGapError("research candle timestamp invalid")
                    try:
                        v = tuple(Decimal(x) for x in row[2:])
                        if (any(not x.is_finite() or len(x.as_tuple().digits) > 40 for x in v)
                                or min(v[:4]) <= 0 or v[1] < max(v[0], v[3])
                                or v[2] > min(v[0], v[3])
                                or min(v[4:]) < 0):
                            raise ValueError("bad decimal")
                    except (ArithmeticError, ValueError, TypeError):
                        raise DataGapError("research decimal invalid") from None
                    out.append(BybitResearchStoredCandle(row[0], row[1], *v))
                headers.append((
                    page["symbol"], page["interval"], page["start_open_ms"],
                    page["end_open_ms"], page["registry_sha256"],
                    page["capture_environment"], page["instrument_bytes_sha256"],
                    page["kline_bytes_sha256"], page["content_sha256"],
                ))
                cursor = page["end_open_ms"]
            if cursor != end_open_ms or len(out) != expected:
                raise DataGapError("incomplete research series")
            digest = sha256(json.dumps(headers, separators=(",", ":")).encode()).hexdigest()
            return BybitResearchSeries(start_open_ms, end_open_ms, len(pages),
                                       tuple(out), digest)
    except sqlite3.DatabaseError:
        raise DataValidationError("unreadable read-only research database") from None
