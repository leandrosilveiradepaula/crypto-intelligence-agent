"""Paged, resumable historical collection built on the WU1 read-only adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .market_data import ClosedCandle, DataGapError, MarketDataCheckpoint, interval_duration_ms
from .storage import MarketDataStore


class CandleSource(Protocol):
    def closed_candles(self, symbol: str, interval: str, *, observed_at_ms: int, start_time_ms: int | None = None, end_time_ms: int | None = None, limit: int = 500) -> tuple[ClosedCandle, ...]: ...


@dataclass(frozen=True)
class BackfillResult:
    start_open_ms: int
    end_open_ms: int
    pages_committed: int
    candles_committed: int
    checkpoint: MarketDataCheckpoint | None


class HistoricalBackfill:
    """Collect exact [start_open_ms, end_open_ms) windows with atomic checkpoints."""

    def __init__(self, source: CandleSource, store: MarketDataStore, *, page_size: int = 500, contract_version: str = "j1-wu2-v1") -> None:
        if page_size < 1 or page_size > 1_500:
            raise ValueError("page_size must be between 1 and 1500")
        self._source = source
        self._store = store
        self._page_size = page_size
        self._contract_version = contract_version

    def run(self, *, exchange: str, market: str, symbol: str, interval: str, start_open_ms: int, end_open_ms: int, observed_at_ms: int, source_name: str) -> BackfillResult:
        duration = interval_duration_ms(interval)
        if end_open_ms <= start_open_ms or start_open_ms % duration or end_open_ms % duration:
            raise ValueError("backfill window must be a non-empty interval-aligned [start, end) range")
        checkpoint = self._store.latest_checkpoint(data_type="closed_candle", exchange=exchange, symbol=symbol, interval=interval)
        cursor = start_open_ms
        if checkpoint is not None and checkpoint.integrity == "complete":
            cursor = max(cursor, checkpoint.confirmed_end_ms + 1)
        pages, committed = 0, 0
        while cursor < end_open_ms:
            page_end = min(cursor + self._page_size * duration, end_open_ms)
            candles = self._source.closed_candles(symbol, interval, observed_at_ms=observed_at_ms, start_time_ms=cursor, end_time_ms=page_end - 1, limit=self._page_size)
            _validate_exact_page(candles, exchange, market, symbol, interval, cursor, page_end, duration)
            checkpoint = MarketDataCheckpoint(
                data_type="closed_candle", exchange=exchange, symbol=symbol, interval=interval,
                confirmed_start_ms=start_open_ms, confirmed_end_ms=candles[-1].close_time_ms,
                source=source_name, contract_version=self._contract_version, integrity="complete",
            )
            self._store.commit_candle_page(candles, checkpoint)
            pages += 1
            committed += len(candles)
            cursor = page_end
        return BackfillResult(start_open_ms, end_open_ms, pages, committed, checkpoint)


def _validate_exact_page(candles: tuple[ClosedCandle, ...], exchange: str, market: str, symbol: str, interval: str, page_start: int, page_end: int, duration: int) -> None:
    expected_opens = tuple(range(page_start, page_end, duration))
    if len(candles) != len(expected_opens):
        raise DataGapError(f"insufficient historical coverage for [{page_start}, {page_end})")
    actual_opens = tuple(candle.open_time_ms for candle in candles)
    if actual_opens != expected_opens:
        raise DataGapError(f"gap, duplicate, or out-of-window candle in [{page_start}, {page_end})")
    for candle in candles:
        if (candle.exchange, candle.market, candle.symbol, candle.interval) != (exchange, market, symbol, interval):
            raise DataGapError("candle identity does not match requested historical window")
