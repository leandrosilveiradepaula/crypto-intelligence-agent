"""Paged, resumable market-data backfill with fail-closed checkpoint recovery.

A checkpoint is a claim of contiguous history. Before skipping any data, verify
that its entire prefix is still present; never mistake an unrelated later
collection window for proof that an earlier window was populated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .market_data import ClosedCandle, DataGapError, MarketDataCheckpoint, interval_duration_ms
from .storage import MarketDataStore


class CandleSource(Protocol):
    def closed_candles(
        self, symbol: str, interval: str, *, observed_at_ms: int,
        start_time_ms: int | None = None, end_time_ms: int | None = None,
        limit: int = 500,
    ) -> tuple[ClosedCandle, ...]: ...


@dataclass(frozen=True)
class BackfillResult:
    start_open_ms: int
    end_open_ms: int
    pages_committed: int
    candles_committed: int
    checkpoint: MarketDataCheckpoint | None


def _is_aligned(time_ms: int, interval: str, duration_ms: int) -> bool:
    # Binance weekly klines begin on Monday UTC. Unix epoch began Thursday,
    # thus a weekly start is four days after the epoch, not epoch % week == 0.
    offset = 4 * 86_400_000 if interval == "1w" else 0
    return (time_ms - offset) % duration_ms == 0


class HistoricalBackfill:
    """Collect exact [start_open_ms, end_open_ms) windows with atomic checkpoints."""

    def __init__(self, source: CandleSource, store: MarketDataStore, *, page_size: int = 500, contract_version: str = "j1-wu2-v1") -> None:
        if type(page_size) is not int or page_size < 1 or page_size > 1_500:
            raise ValueError("page_size must be between 1 and 1500")
        if not contract_version:
            raise ValueError("contract_version must be nonempty")
        self._source = source
        self._store = store
        self._page_size = page_size
        self._contract_version = contract_version

    def run(
        self, *, exchange: str, market: str, symbol: str, interval: str,
        start_open_ms: int, end_open_ms: int, observed_at_ms: int, source_name: str,
    ) -> BackfillResult:
        duration = interval_duration_ms(interval)
        if (type(start_open_ms) is not int or type(end_open_ms) is not int
                or type(observed_at_ms) is not int or start_open_ms < 0
                or observed_at_ms < 0 or end_open_ms <= start_open_ms
                or not _is_aligned(start_open_ms, interval, duration)
                or not _is_aligned(end_open_ms, interval, duration)):
            raise ValueError("backfill needs a nonnegative, interval-aligned [start, end) window and UTC observation")
        if not (exchange and market and symbol and source_name):
            raise ValueError("exchange, market, symbol and source_name must be nonempty")

        checkpoint = self._store.latest_checkpoint(
            data_type="closed_candle", exchange=exchange, symbol=symbol, interval=interval,
        )
        cursor = start_open_ms
        lineage_start = start_open_ms
        if checkpoint is not None:
            if checkpoint.integrity != "complete":
                raise DataGapError("checkpoint integrity is not complete")
            if checkpoint.source != source_name or checkpoint.contract_version != self._contract_version:
                raise DataGapError("checkpoint source/version does not match requested collection lineage")
            saved_next = checkpoint.confirmed_end_ms + 1
            lineage_start = checkpoint.confirmed_start_ms
            if (not _is_aligned(lineage_start, interval, duration)
                    or not _is_aligned(saved_next, interval, duration)
                    or start_open_ms < lineage_start
                    or start_open_ms > saved_next):
                raise DataGapError("requested window is outside the contiguous checkpoint lineage")

            # Check the full prefix rather than trusting a watermark whose
            # underlying files/rows may have been removed or corrupted.
            saved_rows = self._store.candles(
                exchange=exchange, market=market, symbol=symbol, interval=interval,
                start_open_ms=lineage_start, end_open_ms=saved_next,
            )
            expected = tuple(range(lineage_start, saved_next, duration))
            if (len(saved_rows) != len(expected)
                    or any(c.open_time_ms != tick or c.close_time_ms != tick + duration - 1
                           for c, tick in zip(saved_rows, expected))):
                raise DataGapError("checkpoint prefix is absent, damaged or belongs to a different market")
            cursor = max(cursor, saved_next)

        pages, committed = 0, 0
        while cursor < end_open_ms:
            page_end = min(cursor + self._page_size * duration, end_open_ms)
            candles = self._source.closed_candles(
                symbol, interval, observed_at_ms=observed_at_ms,
                start_time_ms=cursor, end_time_ms=page_end - 1,
                limit=self._page_size,
            )
            _validate_exact_page(candles, exchange, market, symbol, interval, cursor, page_end, duration)
            checkpoint = MarketDataCheckpoint(
                data_type="closed_candle", exchange=exchange, symbol=symbol, interval=interval,
                confirmed_start_ms=lineage_start, confirmed_end_ms=candles[-1].close_time_ms,
                source=source_name, contract_version=self._contract_version, integrity="complete",
            )
            self._store.commit_candle_page(candles, checkpoint)
            pages += 1
            committed += len(candles)
            cursor = page_end
        return BackfillResult(start_open_ms, end_open_ms, pages, committed, checkpoint)


def _validate_exact_page(
    candles: tuple[ClosedCandle, ...], exchange: str, market: str, symbol: str,
    interval: str, page_start: int, page_end: int, duration: int,
) -> None:
    expected_opens = tuple(range(page_start, page_end, duration))
    if len(candles) != len(expected_opens):
        raise DataGapError(f"insufficient historical coverage for [{page_start}, {page_end})")
    actual_opens = tuple(candle.open_time_ms for candle in candles)
    if actual_opens != expected_opens:
        raise DataGapError(f"gap, duplicate, or out-of-window candle in [{page_start}, {page_end})")
    for candle in candles:
        if (candle.exchange, candle.market, candle.symbol, candle.interval) != (exchange, market, symbol, interval):
            raise DataGapError("candle identity does not match requested historical window")
        if candle.close_time_ms != candle.open_time_ms + duration - 1:
            raise DataGapError("candle closes outside its expected interval")
