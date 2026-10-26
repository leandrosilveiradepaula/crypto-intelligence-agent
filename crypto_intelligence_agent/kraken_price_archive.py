"""J1/WU34 opt-in SQLite research archive for Kraken trade-price candles.

This is an extension of SQLiteMarketDataStore for LOCAL private research, not
an adapter to the canonical ClosedCandle data model. No base/quote financial
volumes, market eligibility, trading, external access or publish capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

from .kraken_candle_validation import (
    KRAKEN_RESOLUTIONS, MAX_CANDLES, SOURCE as CANDLE_SOURCE,
    KrakenStagedCandlePage, KrakenTradeCandleStaging,
)
from .kraken_public_readonly import (
    SOURCE as CAPTURE_SOURCE, KrakenCapturedCandleResearchPage,
)
from .market_data import (
    DataGapError, DuplicateCandleError, UniverseSnapshot, interval_duration_ms,
    interval_open_aligned,
)
from .storage import SQLiteMarketDataStore


@dataclass(frozen=True)
class PriceOnlyCandle:
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    first_observed_at_ms: int
    source: str

    @property
    def canonical_ohlcv(self) -> bool:
        return False


@dataclass(frozen=True)
class PriceOnlyQuality:
    expected: int
    captured: int
    missing_open_times_ms: tuple[int, ...]
    backed_by_page_receipts: bool

    @property
    def complete(self) -> bool:
        return self.captured == self.expected and not self.missing_open_times_ms and self.backed_by_page_receipts

    @property
    def canonical_ohlcv(self) -> bool:
        return False


def _check_window(symbol: str, interval: str, start: int, end: int, as_of: int) -> int:
    if (type(symbol) is not str or not symbol.isascii()
            or not symbol.isupper() or not symbol.startswith("PF_")
            or len(symbol) > 48 or not symbol[3:].isalnum()
            or interval not in KRAKEN_RESOLUTIONS):
        raise DataGapError("invalid Kraken price-only identity")
    if (type(start) is not int or type(end) is not int or type(as_of) is not int
            or start < 0 or end <= start or as_of <= 0
            or not interval_open_aligned(interval, start)
            or not interval_open_aligned(interval, end)):
        raise DataGapError("invalid price-only UTC capture window")
    duration = interval_duration_ms(interval)
    if (end - start) // duration > MAX_CANDLES:
        raise DataGapError("price-only window exceeds bounded Kraken page")
    return duration


def _validated_rows(page: KrakenCapturedCandleResearchPage) -> tuple[PriceOnlyCandle, ...]:
    if (type(page) is not KrakenCapturedCandleResearchPage
            or page.source != CAPTURE_SOURCE
            or type(page.observed_at_ms) is not int
            or type(page.staged) is not KrakenStagedCandlePage):
        raise DataGapError("price-only import requires Kraken captured staging page")
    staged = page.staged
    duration = _check_window(
        staged.symbol, staged.interval,
        staged.start_open_ms, staged.end_open_ms, page.observed_at_ms,
    )
    if (type(staged.provider_reports_more_candles) is not bool
            or type(staged.candles) is not tuple
            or len(staged.candles) !=
            (staged.end_open_ms - staged.start_open_ms) // duration):
        raise DataGapError("price-only captured page must be exact and contiguous")
    output = []
    for i, candle in enumerate(staged.candles):
        if (type(candle) is not KrakenTradeCandleStaging
                or candle.symbol != staged.symbol or candle.interval != staged.interval
                or candle.source != CANDLE_SOURCE or candle.raw_volume_unit != "unverified"
                or type(candle.open_time_ms) is not int
                or candle.open_time_ms != staged.start_open_ms + i * duration
                or type(candle.close_time_ms) is not int
                or candle.close_time_ms != candle.open_time_ms + duration - 1
                or candle.close_time_ms + 1_000 > page.observed_at_ms):
            raise DataGapError("untrusted Kraken staged row identity or closure")
        vals = (candle.open, candle.high, candle.low, candle.close)
        if (any(type(v) is not Decimal or not v.is_finite() or v <= 0 for v in vals)
                or candle.high < max(candle.open, candle.low, candle.close)
                or candle.low > min(candle.open, candle.high, candle.close)
                or type(candle.raw_trade_volume_unverified) is not Decimal
                or not candle.raw_trade_volume_unverified.is_finite()
                or candle.raw_trade_volume_unverified < 0):
            raise DataGapError("invalid price/opaque volume staging values")
        output.append(PriceOnlyCandle(
            staged.symbol, staged.interval, candle.open_time_ms, candle.close_time_ms,
            candle.open, candle.high, candle.low, candle.close,
            page.observed_at_ms, page.source,
        ))
    return tuple(output)


class SQLiteKrakenPriceOnlyArchive(SQLiteMarketDataStore):
    """Reuses the existing local SQLite store. No change to canonical schema."""

    def _initialize(self) -> None:
        super()._initialize()
        # These tables exist only on a database explicitly opened for research.
        with self._transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kraken_research_prices (
                    symbol TEXT NOT NULL, interval TEXT NOT NULL,
                    open_time_ms INTEGER NOT NULL, close_time_ms INTEGER NOT NULL,
                    open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
                    first_observed_at_ms INTEGER NOT NULL, source TEXT NOT NULL,
                    PRIMARY KEY (symbol, interval, open_time_ms)
                );
                CREATE TABLE IF NOT EXISTS kraken_research_price_pages (
                    symbol TEXT NOT NULL, interval TEXT NOT NULL,
                    start_open_ms INTEGER NOT NULL, end_open_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    sha256_digest TEXT NOT NULL, count INTEGER NOT NULL,
                    source TEXT NOT NULL, provider_reports_more INTEGER NOT NULL,
                    PRIMARY KEY (symbol, interval, start_open_ms, end_open_ms, observed_at_ms)
                );
            """)

    @staticmethod
    def _commit_price_only_on_connection(
        conn: sqlite3.Connection,
        page: KrakenCapturedCandleResearchPage,
        candles: tuple[PriceOnlyCandle, ...],
    ) -> int:
        """Insert exactly one prevalidated page on a caller's transaction."""
        staged = page.staged
        digest_value = {
            "symbol": staged.symbol, "interval": staged.interval,
            "start": staged.start_open_ms, "end": staged.end_open_ms,
            "observed_at": page.observed_at_ms, "source": page.source,
            "more": staged.provider_reports_more_candles,
            "prices": [
                [c.open_time_ms, c.close_time_ms, str(c.open), str(c.high),
                 str(c.low), str(c.close)] for c in candles
            ],
        }
        digest = sha256(json.dumps(digest_value, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()
        inserted = 0
        old_page = conn.execute(
            """SELECT sha256_digest FROM kraken_research_price_pages
               WHERE symbol=? AND interval=? AND start_open_ms=? AND
               end_open_ms=? AND observed_at_ms=?""",
            (staged.symbol, staged.interval, staged.start_open_ms,
             staged.end_open_ms, page.observed_at_ms),
        ).fetchone()
        if old_page is not None and old_page["sha256_digest"] != digest:
            raise DuplicateCandleError("conflicting research price page receipt")
        for candle in candles:
            existing = conn.execute(
                """SELECT * FROM kraken_research_prices
                   WHERE symbol=? AND interval=? AND open_time_ms=?""",
                (candle.symbol, candle.interval, candle.open_time_ms),
            ).fetchone()
            if existing is not None:
                same_price = (
                    existing["close_time_ms"] == candle.close_time_ms
                    and tuple(Decimal(existing[k]) for k in
                              ("open", "high", "low", "close")) ==
                    (candle.open, candle.high, candle.low, candle.close)
                    and existing["source"] == candle.source
                )
                if not same_price or page.observed_at_ms < existing["first_observed_at_ms"]:
                    raise DuplicateCandleError(
                        "conflicting or backdated persisted Kraken research price"
                    )
        for candle in candles:
            inserted += conn.execute(
                """INSERT OR IGNORE INTO kraken_research_prices VALUES
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (candle.symbol, candle.interval, candle.open_time_ms,
                 candle.close_time_ms, str(candle.open), str(candle.high),
                 str(candle.low), str(candle.close),
                 candle.first_observed_at_ms, candle.source),
            ).rowcount
        conn.execute(
            """INSERT OR IGNORE INTO kraken_research_price_pages
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (staged.symbol, staged.interval, staged.start_open_ms,
             staged.end_open_ms, page.observed_at_ms, digest,
             len(candles), page.source, int(staged.provider_reports_more_candles)),
        )
        return inserted

    def commit_price_only(self, page: KrakenCapturedCandleResearchPage) -> int:
        """Preserve standalone page atomicity/idempotence for existing callers."""
        candles = _validated_rows(page)
        with self._transaction() as conn:
            return self._commit_price_only_on_connection(conn, page, candles)

    def commit_research_session(
        self, snapshot: UniverseSnapshot,
        pages: tuple[KrakenCapturedCandleResearchPage, ...],
    ) -> tuple[int, ...]:
        """One SQLite transaction: universe snapshot AND every price page.

        Fail entirely on a later page collision even in an existing database.
        Legacy standalone commit_price_only/save_universe_snapshot remain
        available with their own transaction boundaries.
        """
        if (type(snapshot) is not UniverseSnapshot
                or type(snapshot.observed_at_ms) is not int
                or snapshot.observed_at_ms <= 0
                or type(pages) is not tuple
                or not 1 <= len(pages) <= 5
                or type(snapshot.eligible) is not tuple):
            raise DataGapError("invalid private research session input")
        eligible_symbols = tuple(member.symbol for member in snapshot.eligible)
        if len(set(eligible_symbols)) != len(eligible_symbols):
            raise DataGapError("duplicate eligible symbols in private session")
        first_window = None
        last_observed = snapshot.observed_at_ms
        validated = []
        seen = set()
        for page in pages:
            candles = _validated_rows(page)  # all page contracts before disk IO
            staged = page.staged
            window = (staged.interval, staged.start_open_ms, staged.end_open_ms)
            if (staged.symbol not in eligible_symbols
                    or staged.symbol in seen
                    or page.observed_at_ms < last_observed
                    or (first_window is not None and window != first_window)):
                raise DataGapError("private research session symbol/window/time mismatch")
            seen.add(staged.symbol)
            if first_window is None:
                first_window = window
            last_observed = page.observed_at_ms
            validated.append((page, candles))
        # SQLite BEGIN IMMEDIATE; failure at ANY insert rolls back even earlier
        # pages, receipts and the universe snapshot in this same session.
        with self._transaction() as conn:
            self._save_universe_snapshot_on_connection(conn, snapshot)
            return tuple(
                self._commit_price_only_on_connection(conn, page, candles)
                for page, candles in validated
            )

    def prices_as_of(
        self, *, symbol: str, interval: str, start_open_ms: int,
        end_open_ms: int, as_of_ms: int,
    ) -> tuple[PriceOnlyCandle, ...]:
        _check_window(symbol, interval, start_open_ms, end_open_ms, as_of_ms)
        with self._transaction() as conn:
            rows = conn.execute(
                """SELECT * FROM kraken_research_prices WHERE symbol=? AND interval=?
                   AND open_time_ms>=? AND open_time_ms<? AND first_observed_at_ms<=?
                   ORDER BY open_time_ms ASC""",
                (symbol, interval, start_open_ms, end_open_ms, as_of_ms),
            ).fetchall()
        return tuple(PriceOnlyCandle(
            row["symbol"], row["interval"], row["open_time_ms"],
            row["close_time_ms"], Decimal(row["open"]), Decimal(row["high"]),
            Decimal(row["low"]), Decimal(row["close"]),
            row["first_observed_at_ms"], row["source"],
        ) for row in rows)

    def price_quality(
        self, *, symbol: str, interval: str, start_open_ms: int,
        end_open_ms: int, as_of_ms: int,
    ) -> PriceOnlyQuality:
        duration = _check_window(symbol, interval, start_open_ms, end_open_ms, as_of_ms)
        rows = self.prices_as_of(
            symbol=symbol, interval=interval,
            start_open_ms=start_open_ms, end_open_ms=end_open_ms, as_of_ms=as_of_ms,
        )
        timestamps = tuple(range(start_open_ms, end_open_ms, duration))
        observed = {row.open_time_ms for row in rows}
        with self._transaction() as conn:
            receipts = conn.execute(
                """SELECT start_open_ms, end_open_ms FROM kraken_research_price_pages
                   WHERE symbol=? AND interval=? AND observed_at_ms<=?
                   AND start_open_ms<? AND end_open_ms>?""",
                (symbol, interval, as_of_ms, end_open_ms, start_open_ms),
            ).fetchall()
        coverage = all(
            any(rec["start_open_ms"] <= t < rec["end_open_ms"] for rec in receipts)
            for t in timestamps
        )
        return PriceOnlyQuality(
            expected=len(timestamps), captured=len(rows),
            missing_open_times_ms=tuple(t for t in timestamps if t not in observed),
            backed_by_page_receipts=coverage,
        )
