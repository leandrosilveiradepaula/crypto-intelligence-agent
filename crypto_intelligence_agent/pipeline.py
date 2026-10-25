"""Read-only orchestration with durable collection provenance and strict failure handling.

This module calls the previously validated adapter, checkpointed backfill, and
storage contracts. It cannot authenticate or place orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Callable, Protocol, Sequence

from .backfill import HistoricalBackfill
from .market_data import (
    BinanceFuturesPublicAdapter, ClosedCandle, DataValidationError,
    UniverseSnapshot, interval_duration_ms, interval_open_aligned,
)
from .storage import CollectionEvent, MarketDataStore


CONTRACTS_ENDPOINT = "GET /fapi/v1/exchangeInfo"
UNIVERSE_ENDPOINT = "GET /fapi/v1/exchangeInfo + GET /fapi/v1/ticker/24hr"
CANDLES_ENDPOINT = "GET /fapi/v1/klines"


@dataclass(frozen=True)
class SymbolSummary:
    symbol: str
    pages_committed: int
    candles_committed: int
    expected_candles: int
    persisted_candles: int
    missing_open_times_ms: tuple[int, ...]
    complete: bool


@dataclass(frozen=True)
class CollectionSummary:
    mode: str
    source: str
    exchange: str
    selection_rule_version: str
    contracts_observed_at_ms: int
    universe_observed_at_ms: int
    selected_symbols: tuple[str, ...]
    excluded: dict[str, str]
    window_start_ms: int
    window_end_ms: int
    interval: str
    results: tuple[SymbolSummary, ...]
    endpoints: tuple[str, ...]
    synthetic: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CandleReader(Protocol):
    def closed_candles(
        self, symbol: str, interval: str, *, observed_at_ms: int,
        start_time_ms: int | None = None, end_time_ms: int | None = None,
        limit: int = 500,
    ) -> tuple[ClosedCandle, ...]: ...


class _ProvenanceCandleReader:
    """Mark offline fixture rows explicitly so they cannot be mistaken for exchange data."""

    def __init__(self, source: CandleReader, *, synthetic: bool):
        self._source = source
        self._synthetic = synthetic

    def closed_candles(
        self, symbol: str, interval: str, *, observed_at_ms: int,
        start_time_ms: int | None = None, end_time_ms: int | None = None,
        limit: int = 500,
    ) -> tuple[ClosedCandle, ...]:
        rows = self._source.closed_candles(
            symbol, interval, observed_at_ms=observed_at_ms,
            start_time_ms=start_time_ms, end_time_ms=end_time_ms, limit=limit,
        )
        if self._synthetic:
            return tuple(replace(row, quality="synthetic_fixture") for row in rows)
        return rows


class ReadOnlyCollectionPipeline:
    """Capture current metadata/universe, backfill only closed candles and report QA.

    Clock is injectable; recorded metadata timestamps reflect response-completion
    time rather than a caller-supplied historical instant. The two REST endpoints
    are NOT an atomic quote and must not be treated as a historical universe.
    """

    def __init__(
        self,
        adapter: BinanceFuturesPublicAdapter,
        store: MarketDataStore,
        *,
        clock_ms: Callable[[], int],
        mode: str,
        source_name: str,
        selection_rule_version: str = "j1-wu3-v1",
    ):
        if mode not in {"offline", "live"}:
            raise ValueError("collection mode must be offline or live")
        if not source_name or not selection_rule_version:
            raise ValueError("source name and selection version are required")
        self._adapter = adapter
        self._store = store
        self._clock_ms = clock_ms
        self._mode = mode
        self._source_name = source_name
        self._version = selection_rule_version

    def _clock(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or value < 0:
            raise DataValidationError("collection clock must return a nonnegative UTC millisecond integer")
        return value

    def _record(
        self, *, endpoint: str, status: str, detail: str, start_ms: int,
        symbol: str | None = None, interval: str | None = None,
        pages: int = 0, candles: int = 0,
    ) -> None:
        self._store.record_collection_event(CollectionEvent(
            observed_start_ms=start_ms, observed_end_ms=self._clock(),
            mode=self._mode, source=self._source_name, exchange="binance",
            endpoint=endpoint, selection_rule_version=self._version,
            symbol=symbol, interval=interval, status=status, detail=detail,
            pages_committed=pages, candles_committed=candles,
        ))

    def run(
        self, *, interval: str, start_open_ms: int, end_open_ms: int,
        max_symbols: int = 1, page_size: int = 2,
        min_onboard_age_ms: int = 0,
        required_symbols: Sequence[str] = (),
    ) -> CollectionSummary:
        duration = interval_duration_ms(interval)
        if (type(start_open_ms) is not int or type(end_open_ms) is not int
                or start_open_ms < 0 or end_open_ms <= start_open_ms
                or not interval_open_aligned(interval, start_open_ms)
                or not interval_open_aligned(interval, end_open_ms)):
            raise ValueError("historical window must be nonempty and UTC interval-aligned")
        if (type(max_symbols) is not int or not 1 <= max_symbols <= 50
                or type(page_size) is not int or not 1 <= page_size <= 1_500
                or type(min_onboard_age_ms) is not int or min_onboard_age_ms < 0):
            raise ValueError("limits must be integers: symbols 1-50, page size 1-1500, min age >= 0")
        if end_open_ms > self._clock():
            raise DataValidationError("historical window extends beyond the observation clock")
        if len(set(required_symbols)) != len(required_symbols):
            raise ValueError("required_symbols must not contain duplicates")

        contracts_start = self._clock()
        try:
            contracts = self._adapter.contracts(observed_at_ms=contracts_start)
            contracts_end = self._clock()
            normalized_contracts = tuple(
                replace(contract, observed_at_ms=contracts_end, source=self._source_name)
                for contract in contracts
            )
            self._store.save_contracts(normalized_contracts)
            self._record(
                endpoint=CONTRACTS_ENDPOINT, status="success", start_ms=contracts_start,
                detail=f"contracts={len(normalized_contracts)}; response-completion timestamp",
            )
        except Exception as exc:
            self._record(
                endpoint=CONTRACTS_ENDPOINT, status="failure", start_ms=contracts_start,
                detail=type(exc).__name__,
            )
            raise

        universe_start = self._clock()
        try:
            universe = self._adapter.universe(
                observed_at_ms=universe_start, max_symbols=max_symbols,
                min_onboard_age_ms=min_onboard_age_ms,
                selection_rule_version=self._version,
            )
            universe_end = self._clock()
            normalized = replace(
                universe, observed_at_ms=universe_end, source=self._source_name,
            )
            self._store.save_universe_snapshot(normalized)
            self._record(
                endpoint=UNIVERSE_ENDPOINT, status="success", start_ms=universe_start,
                detail=f"eligible={len(normalized.eligible)}; not historical point-in-time",
            )
        except Exception as exc:
            self._record(
                endpoint=UNIVERSE_ENDPOINT, status="failure", start_ms=universe_start,
                detail=type(exc).__name__,
            )
            raise

        eligible = {member.symbol for member in normalized.eligible}
        required = tuple(required_symbols)
        if required and (any(symbol not in eligible for symbol in required) or len(required) > max_symbols):
            self._record(
                endpoint=UNIVERSE_ENDPOINT, status="failure",
                detail="required_symbol_not_in_ranked_universe", start_ms=universe_start,
            )
            raise DataValidationError("required symbol is absent from the currently eligible ranked universe")
        selected = required if required else tuple(m.symbol for m in normalized.eligible)
        if not selected:
            self._record(
                endpoint=UNIVERSE_ENDPOINT, status="failure",
                detail="empty_eligible_universe", start_ms=universe_start,
            )
            raise DataValidationError("eligible universe is empty; no historical data collected")

        reader = _ProvenanceCandleReader(self._adapter, synthetic=self._mode == "offline")
        backfill = HistoricalBackfill(
            reader, self._store, page_size=page_size, contract_version=self._version,
        )
        results: list[SymbolSummary] = []
        for symbol in selected:
            began = self._clock()
            try:
                result = backfill.run(
                    exchange="binance", market="linear_perpetual", symbol=symbol,
                    interval=interval, start_open_ms=start_open_ms,
                    end_open_ms=end_open_ms, observed_at_ms=began,
                    source_name=self._source_name,
                )
                quality = self._store.quality_report(
                    exchange="binance", market="linear_perpetual", symbol=symbol,
                    interval=interval, start_open_ms=start_open_ms,
                    end_open_ms=end_open_ms,
                )
                if not quality.complete:
                    raise DataValidationError(f"quality is incomplete for {symbol}")
                results.append(SymbolSummary(
                    symbol=symbol, pages_committed=result.pages_committed,
                    candles_committed=result.candles_committed,
                    expected_candles=quality.expected_candles,
                    persisted_candles=quality.persisted_candles,
                    missing_open_times_ms=quality.missing_open_times_ms,
                    complete=quality.complete,
                ))
                self._record(
                    endpoint=CANDLES_ENDPOINT, status="success", detail="complete",
                    symbol=symbol, interval=interval, start_ms=began,
                    pages=result.pages_committed, candles=result.candles_committed,
                )
            except Exception as exc:
                self._record(
                    endpoint=CANDLES_ENDPOINT, status="failure",
                    detail=type(exc).__name__, symbol=symbol, interval=interval,
                    start_ms=began,
                )
                raise

        return CollectionSummary(
            mode=self._mode, source=self._source_name, exchange="binance",
            selection_rule_version=self._version,
            contracts_observed_at_ms=contracts_end,
            universe_observed_at_ms=universe_end,
            selected_symbols=tuple(selected), excluded=dict(normalized.excluded),
            window_start_ms=start_open_ms, window_end_ms=end_open_ms,
            interval=interval, results=tuple(results),
            endpoints=(CONTRACTS_ENDPOINT, UNIVERSE_ENDPOINT, CANDLES_ENDPOINT),
            synthetic=self._mode == "offline",
        )
