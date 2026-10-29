"""J1/WU49: offline ONLY Bybit V5 paginated-universe research admission.

Consumes caller-supplied response-shaped dictionaries, NEVER fetches them.
Complete cursor chaining and crypto/USDT filtering are necessary but NOT
sufficient to prove actual exchange capture, access, historical membership,
rights, perpetual Top50 coverage or permission to trade.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any

from .bybit_instrument_volume_contract import (
    BybitLinearInstrumentResearch, validate_bybit_linear_instrument,
)
from .market_data import DataValidationError
from .research_registry_catalog import load_reviewed_registry

MAX_PAGES = 20
# Bounded jitter permitted ONLY when each real page has its own receive clock.
MAX_RECEIVED_PAGE_SERVER_JITTER_MS = 2_000
MAX_ROWS_PER_PAGE = 1000
MAX_INSTRUMENT_ROWS = 10_000
MAX_TICKERS = 10_000
_MAX_CAPTURE_AGE_MS = 30_000
_SYMBOL = re.compile(r"[A-Z0-9]{5,40}")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,22})(?:\.[0-9]{1,20})?")


@dataclass(frozen=True)
class BybitResearchUniverseMember:
    """Numeric research proxy. Ticker 24h fields have no proven economic unit."""

    rank: int
    symbol: str
    base_coin: str
    turnover24h_raw_unverified: Decimal
    volume24h_raw_unverified: Decimal
    quote_contract_currency: str = "USDT"


@dataclass(frozen=True)
class BybitPaginatedUniverseResearch:
    """Only shape/selection checks; all authority and production gates are OFF."""

    observed_at_ms: int
    registry_sha256: str
    instrument_page_count: int
    instrument_row_count: int
    candidate_contract_count: int
    ticker_row_count: int
    selected: tuple[BybitResearchUniverseMember, ...]

    @property
    def source_quality(self) -> str:
        return "unverified_caller_supplied_offline_payload"

    @property
    def ranking_basis(self) -> str:
        return "raw_ticker_turnover24h_numeric_proxy_unit_unverified"

    @property
    def cursor_chain_complete_as_asserted(self) -> bool:
        # Validates only the caller's declared cursor chain, not the HTTP log.
        return True

    @property
    def live_source_verified(self) -> bool:
        return False

    @property
    def canonical_ohlcv_ready(self) -> bool:
        return False

    @property
    def verified_top50_coverage(self) -> bool:
        return False

    @property
    def rights_verified(self) -> bool:
        return False

    @property
    def usd_comparable_volume_verified(self) -> bool:
        return False

    @property
    def ticker_turnover_unit_verified(self) -> bool:
        return False

    @property
    def ticker_volume_unit_verified(self) -> bool:
        return False

    @property
    def point_in_time_history_verified(self) -> bool:
        return False

    @property
    def automatic_trading_authorized(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def _response(payload: Any, *, label: str, at_ms: int, age_ms: int) -> tuple[dict, dict, int]:
    if type(payload) is not dict or type(payload.get("retCode")) is not int or payload["retCode"] != 0:
        raise DataValidationError(label + " API status/shape unverified")
    obj = payload.get("result")
    server_ms = payload.get("time")
    if (type(obj) is not dict or obj.get("category") != "linear"
            or type(server_ms) is not int
            or not 0 < server_ms <= at_ms or at_ms - server_ms > age_ms):
        raise DataValidationError(label + " category or capture clock is invalid")
    return payload, obj, server_ms


def _cursor(value: Any, *, terminal_ok: bool) -> str:
    if (type(value) is not str or len(value) > 300
            or (not terminal_ok and value == "")
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise DataValidationError("Bybit pagination cursor is missing or unsafe")
    return value


def _quantity(value: Any, field: str) -> Decimal:
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        raise DataValidationError(field + " must be canonical finite Decimal string")
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise DataValidationError(field + " is invalid")
    return number



@dataclass(frozen=True)
class BybitInstrumentScanResearch:
    """Full asserted cursor traversal, restricted to reviewed crypto bases."""

    observed_at_ms: int
    registry_sha256: str
    page_count: int
    instrument_row_count: int
    last_server_time_ms: int
    instruments: tuple[BybitLinearInstrumentResearch, ...]

    @property
    def historical_top50_verified(self) -> bool:
        return False

    @property
    def provider_authenticated(self) -> bool:
        return False

    @property
    def rights_authorized(self) -> bool:
        return False


def scan_bybit_linear_instruments_offline(
    *, instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    observed_at_ms: int,
    registry_variant: str = "expanded-13",
    max_capture_age_ms: int = _MAX_CAPTURE_AGE_MS,
    page_received_at_ms: tuple[int, ...] | None = None,
) -> BybitInstrumentScanResearch:
    """Validate all pages/cursors once; no ticker-unit inference or network."""
    if (type(observed_at_ms) is not int or observed_at_ms <= 0
            or type(max_capture_age_ms) is not int
            or not 0 <= max_capture_age_ms <= _MAX_CAPTURE_AGE_MS):
        raise DataValidationError("invalid Bybit instrument scan clock/budget")
    if (type(instrument_pages) is not tuple
            or not 1 <= len(instrument_pages) <= MAX_PAGES
            or type(requested_cursors) is not tuple
            or len(requested_cursors) != len(instrument_pages)
            or requested_cursors[0] is not None):
        raise DataValidationError("complete instrument page chain required")
    if page_received_at_ms is not None:
        if (type(page_received_at_ms) is not tuple
                or len(page_received_at_ms) != len(instrument_pages)
                or any(type(t) is not int or t <= 0 or t > observed_at_ms
                       for t in page_received_at_ms)
                or any(a > b for a, b in zip(
                    page_received_at_ms, page_received_at_ms[1:]))):
            raise DataValidationError("invalid ordered per-page receive timestamps")
    registry = load_reviewed_registry(registry_variant, as_of_ms=observed_at_ms)
    expected_cursor: str | None = None
    seen_cursors: set[str] = set()
    seen_instruments: set[str] = set()
    accepted: dict[str, BybitLinearInstrumentResearch] = {}
    previous_server_time = 0
    total_rows = 0
    for page_index, page in enumerate(instrument_pages):
        # Each GET has its own receive time: measuring all pages against the
        # final scan clock spuriously rejects valid paginated responses when a
        # scan takes >30s. Legacy offline callers retain their strict behavior.
        received_at = (observed_at_ms if page_received_at_ms is None
                       else page_received_at_ms[page_index])
        _, result, server_ms = _response(
            page, label="Bybit instruments", at_ms=received_at,
            age_ms=max_capture_age_ms,
        )
        jitter = (0 if page_received_at_ms is None
                  else MAX_RECEIVED_PAGE_SERVER_JITTER_MS)
        if server_ms + jitter < previous_server_time:
            raise DataValidationError("Bybit pagination server timestamps are noncausal")
        previous_server_time = max(previous_server_time, server_ms)
        requested = requested_cursors[page_index]
        if requested != expected_cursor:
            raise DataValidationError("Bybit instrument page cursor chain is incomplete")
        if requested is not None:
            _cursor(requested, terminal_ok=False)
            if requested in seen_cursors:
                raise DataValidationError("Bybit repeated pagination request cursor")
            seen_cursors.add(requested)
        next_cursor = _cursor(result.get("nextPageCursor"), terminal_ok=True)
        if next_cursor and (next_cursor in seen_cursors or next_cursor == requested):
            raise DataValidationError("Bybit pagination cursor cycle")
        rows = result.get("list")
        if (type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS_PER_PAGE
                or total_rows + len(rows) > MAX_INSTRUMENT_ROWS):
            raise DataValidationError("Bybit instrument page size/budget invalid")
        total_rows += len(rows)
        if page_index == len(instrument_pages) - 1:
            if next_cursor != "":
                raise DataValidationError("Bybit final instrument page not terminal")
        elif next_cursor == "":
            raise DataValidationError("Bybit instrument pages were supplied after termination")
        expected_cursor = next_cursor or None

        for row in rows:
            if type(row) is not dict:
                raise DataValidationError("Bybit instrument row must be an object")
            symbol = row.get("symbol")
            if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
                    or symbol in seen_instruments):
                raise DataValidationError("Bybit instrument symbol malformed or duplicated")
            seen_instruments.add(symbol)
            if not symbol.endswith("USDT"):
                continue  # No USDC->USDT or USD normalization, ever.
            base = symbol[:-4]
            if base not in registry.verified_crypto_bases:
                continue
            # Reuse the existing strict single-instrument contract, using a
            # local subview of the SAME untrusted page (not a fabricated GET).
            row_view = {
                "retCode": page["retCode"],
                "time": server_ms,
                "result": {"category": "linear", "nextPageCursor": "", "list": [row]},
            }
            try:
                checked = validate_bybit_linear_instrument(
                    row_view, symbol=symbol, observed_at_ms=server_ms,
                    registry_variant=registry_variant,
                )
            except DataValidationError:
                continue  # Non-trading/TradFi/invalid contract is NOT eligible.
            accepted[checked.symbol] = checked

    return BybitInstrumentScanResearch(
        observed_at_ms, registry.sha256_digest, len(instrument_pages),
        total_rows, previous_server_time,
        tuple(accepted[key] for key in sorted(accepted)),
    )


def audit_bybit_linear_universe_offline(
    *,
    instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    tickers_payload: dict,
    observed_at_ms: int,
    registry_variant: str = "expanded-13",
    max_symbols: int = 50,
    max_capture_age_ms: int = _MAX_CAPTURE_AGE_MS,
) -> BybitPaginatedUniverseResearch:
    """Rank RAW ticker turnover values for USDT-quoted crypto perps in fixtures.

    A second/subsequent page is accepted only when the caller supplies the
    exact prior returned cursor. The terminal page MUST expose an empty
    nextPageCursor. Cursors and timestamps are *claims*, not server proof.
    The ticker endpoint documents raw 24h turnover but NOT its unit; the
    separate kline endpoint\'s explicit quote units do NOT transfer to it.
    Never promote returned members into a validated Top50 universe or OHLCV.
    """
    if (type(observed_at_ms) is not int or observed_at_ms <= 0
            or type(max_symbols) is not int or not 1 <= max_symbols <= 50
            or type(max_capture_age_ms) is not int
            or not 0 <= max_capture_age_ms <= _MAX_CAPTURE_AGE_MS):
        raise DataValidationError("Bybit universe UTC decision and resource limits invalid")
    if (type(instrument_pages) is not tuple or not 1 <= len(instrument_pages) <= MAX_PAGES
            or type(requested_cursors) is not tuple
            or len(requested_cursors) != len(instrument_pages)
            or requested_cursors[0] is not None):
        raise DataValidationError("all Bybit instrument pages and first cursor are required")

    scan = scan_bybit_linear_instruments_offline(
        instrument_pages=instrument_pages,
        requested_cursors=requested_cursors,
        observed_at_ms=observed_at_ms,
        registry_variant=registry_variant,
        max_capture_age_ms=max_capture_age_ms,
    )
    candidate_bases = {item.symbol: item.base_coin for item in scan.instruments}
    previous_server_time = scan.last_server_time_ms
    total_rows = scan.instrument_row_count

    _, tickers, ticker_time = _response(
        tickers_payload, label="Bybit tickers", at_ms=observed_at_ms,
        age_ms=max_capture_age_ms,
    )
    if ticker_time < previous_server_time:
        raise DataValidationError("Bybit ticker snapshot predates final instrument page")
    ticker_rows = tickers.get("list")
    if type(ticker_rows) is not list or not 1 <= len(ticker_rows) <= MAX_TICKERS:
        raise DataValidationError("Bybit ticker list is missing, empty or over resource budget")
    observed_tickers: set[str] = set()
    turnover_by_symbol: dict[str, tuple[Decimal, Decimal]] = {}
    for row in ticker_rows:
        if type(row) is not dict:
            raise DataValidationError("Bybit ticker row is not an object")
        symbol = row.get("symbol")
        if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
                or symbol in observed_tickers):
            raise DataValidationError("Bybit ticker has malformed/duplicate symbol")
        observed_tickers.add(symbol)
        if symbol not in candidate_bases:
            continue
        turnover = _quantity(row.get("turnover24h"), "turnover24h")
        volume = _quantity(row.get("volume24h"), "volume24h")
        if (turnover == 0) != (volume == 0):
            raise DataValidationError("Bybit quote turnover/base volume consistency is unknown")
        turnover_by_symbol[symbol] = (turnover, volume)
    missing = set(candidate_bases) - set(turnover_by_symbol)
    if missing:
        raise DataValidationError("Bybit crypto instrument missing contemporaneous ticker")

    ranked = sorted(
        ((symbol, values) for symbol, values in turnover_by_symbol.items()
         if values[0] > 0),
        key=lambda pair: (-pair[1][0], pair[0]),
    )
    selected = tuple(
        BybitResearchUniverseMember(
            rank=i + 1, symbol=symbol, base_coin=candidate_bases[symbol],
            turnover24h_raw_unverified=values[0],
            volume24h_raw_unverified=values[1],
        )
        for i, (symbol, values) in enumerate(ranked[:max_symbols])
    )
    return BybitPaginatedUniverseResearch(
        observed_at_ms=observed_at_ms,
        registry_sha256=scan.registry_sha256,
        instrument_page_count=scan.page_count,
        instrument_row_count=total_rows,
        candidate_contract_count=len(candidate_bases),
        ticker_row_count=len(ticker_rows),
        selected=selected,
    )


def classify_bybit_instrument_scan_failure(exc: DataValidationError) -> str:
    """Stable, raw-data-free rejection category for private owner diagnostics.

    A provider payload, symbol or URL must never appear in this result.
    Only parser-controlled message fragments can authorize a category.
    """
    if not isinstance(exc, DataValidationError):
        return "unclassified"
    description = str(exc)
    if "registry" in description or "revision" in description or "history" in description:
        return "crypto_registry_or_asof"
    if "noncausal" in description:
        return "cross_page_server_clock"
    if "timestamp" in description or "clock" in description or "stale" in description:
        return "page_capture_clock"
    if "cursor" in description or "pagination" in description or "terminal" in description:
        return "cursor_chain"
    if "duplicated" in description:
        return "duplicate_instrument"
    if "symbol malformed" in description:
        return "malformed_symbol"
    if "page size" in description or "page chain" in description:
        return "page_size_or_budget"
    if "category" in description or "shape" in description:
        return "response_category_or_schema"
    return "other_schema_rejection"
