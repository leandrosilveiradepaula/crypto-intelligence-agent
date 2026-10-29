"""J1 #319: prioritize independent crypto identity review using ticker proxy.

The V5 "turnover24h" ticker is a rolling-24h value, NOT the sum of 24
COMPLETED UTC-hour candles. This module NEVER approves a marketwide top 50,
canonical data or trading. A complete crypto-shaped instrument catalog is
the input, but those shape-only candidates remain UNVERIFIED identities.

No HTTP, persistence, user accounts or exchange order requests here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from .bybit_paginated_universe_research import _response, _quantity
from .bybit_top50_coverage_census import (
    BybitMarketwideCoverageCensus, _census_with_review_candidates,
)
from .market_data import DataValidationError

MAX_TICKER_ROWS = 3000
MAX_PRIORITY_RANK = 100
REQUIRED_MARKET_RANK = 50
TICKER_AGE_MS = 30_000


@dataclass(frozen=True)
class BybitTickerReviewPriority:
    """Private symbols are inspectable internally; JSON is sanitized."""

    census: BybitMarketwideCoverageCensus
    ticker_observed_at_ms: int
    ticker_rows_scanned: int
    candidates_with_ticker: int
    candidates_with_positive_proxy: int
    reviewed_in_rolling_proxy_top50: int
    unreviewed_in_rolling_proxy_top50: int
    rolling_proxy_top50_digest_sha256: str
    priority_review_symbols: tuple[str, ...]
    priority_review_symbols_digest_sha256: str
    priority_rank_limit: int

    def sanitized_report(self) -> dict:
        report = self.census.sanitized_report()
        report.update({
            "status": "j1_top50_rolling_ticker_identity_review_priority_only",
            "ticker_observed_at_ms": self.ticker_observed_at_ms,
            "ticker_rows_scanned": self.ticker_rows_scanned,
            "review_candidate_contracts_with_ticker": self.candidates_with_ticker,
            "review_candidate_contracts_with_positive_rolling_proxy":
                self.candidates_with_positive_proxy,
            "reviewed_in_rolling_ticker_top50_proxy":
                self.reviewed_in_rolling_proxy_top50,
            "unreviewed_in_rolling_ticker_top50_proxy":
                self.unreviewed_in_rolling_proxy_top50,
            "rolling_ticker_top50_proxy_digest_sha256":
                self.rolling_proxy_top50_digest_sha256,
            "review_priority_rank_limit": self.priority_rank_limit,
            "unreviewed_in_priority_queue":
                len(self.priority_review_symbols),
            "priority_queue_digest_sha256":
                self.priority_review_symbols_digest_sha256,
            "rolling_24h_ticker_proxy_unit_verified": False,
            "full_closed_24h_turnover_rank_verified": False,
            "historical_pit_marketwide_top50_verified": False,
            "marketwide_top50_verified": False,
            "crypto_identity_for_unreviewed_candidates_verified": False,
            "canonical_ohlcv_approved": False,
            "orders_sent": False,
            "network_requests_by_ranking": 0,
        })
        return report


def _digest_symbols(symbols: tuple[str, ...]) -> str:
    return sha256("\n".join(symbols).encode("ascii")).hexdigest()


def rank_bybit_ticker_identity_review_priority(
    *, instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    page_received_at_ms: tuple[int, ...],
    ticker_payload: dict,
    observed_at_ms: int,
    priority_rank_limit: int = 75,
    registry_variant: str = "expanded-13",
) -> BybitTickerReviewPriority:
    """Provisional ordering only; requires ALL relevant ticker rows.

    Catches missing, duplicate or noncanonical turnover for ANY of the
    catalog's crypto-shaped candidates, not just those in the first 50.
    """
    if (type(priority_rank_limit) is not int
            or not REQUIRED_MARKET_RANK <= priority_rank_limit <= MAX_PRIORITY_RANK):
        raise DataValidationError("invalid ticker review priority rank budget")
    census, known, plausible = _census_with_review_candidates(
        instrument_pages=instrument_pages,
        requested_cursors=requested_cursors,
        page_received_at_ms=page_received_at_ms,
        observed_at_ms=observed_at_ms,
        registry_variant=registry_variant,
    )
    # The ticker endpoint reports its own close-to-now rolling values.
    # Check this server clock individually, not against the first instrument
    # page's timestamp; this is a review proxy, not a shared PIT close.
    _, ticker, _ = _response(
        ticker_payload, label="Bybit ticker review proxy",
        at_ms=observed_at_ms, age_ms=TICKER_AGE_MS,
    )
    rows = ticker.get("list")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_TICKER_ROWS:
        raise DataValidationError("ticker review source row-count/budget invalid")
    all_candidate_symbols = set(known) | set(plausible)
    observed_candidates: dict[str, Decimal] = {}
    for row in rows:
        if type(row) is not dict:
            raise DataValidationError("ticker review row must be an object")
        symbol = row.get("symbol")
        if (type(symbol) is not str or not 1 <= len(symbol) <= 80
                or not symbol.isascii() or not symbol.isprintable()
                or any(c.isspace() for c in symbol)):
            raise DataValidationError("ticker review contains unsafe symbol")
        if symbol not in all_candidate_symbols:
            # Other tradfi/USDC/expiring tickers are immaterial to the
            # positive-or-unreviewed crypto-shaped candidate universe.
            continue
        if symbol in observed_candidates:
            raise DataValidationError("duplicate relevant ticker symbol")
        # Exact finite Decimal, not floating-point. Numeric unit remains
        # explicitly unverified and therefore NOT a canonical quote total.
        observed_candidates[symbol] = _quantity(
            row.get("turnover24h"), "ticker rolling turnover24h",
        )
    if set(observed_candidates) != all_candidate_symbols:
        raise DataValidationError("incomplete crypto-shaped ticker coverage")
    ranked = tuple(sorted(
        (sym for sym, value in observed_candidates.items() if value > 0),
        key=lambda sym: (-observed_candidates[sym], sym),
    ))
    proxy50 = ranked[:REQUIRED_MARKET_RANK]
    known_set = set(known)
    unreviewed_set = set(plausible)
    queue = tuple(
        sym for sym in ranked[:priority_rank_limit] if sym in unreviewed_set
    )
    return BybitTickerReviewPriority(
        census=census,
        ticker_observed_at_ms=observed_at_ms,
        ticker_rows_scanned=len(rows),
        candidates_with_ticker=len(observed_candidates),
        candidates_with_positive_proxy=len(ranked),
        reviewed_in_rolling_proxy_top50=sum(sym in known_set for sym in proxy50),
        unreviewed_in_rolling_proxy_top50=sum(
            sym in unreviewed_set for sym in proxy50
        ),
        rolling_proxy_top50_digest_sha256=_digest_symbols(proxy50),
        priority_review_symbols=queue,
        priority_review_symbols_digest_sha256=_digest_symbols(queue),
        priority_rank_limit=priority_rank_limit,
    )
