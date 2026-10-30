"""J1 #351: offline review order, NOT ranking or identity approval.

Caller-supplied snapshots only; rolling ticker values are unverified proxies.
No network, persistence, marketwide ranking, rights or trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json

from .bybit_paginated_universe_research import (
    _response, _quantity, _SYMBOL, MAX_TICKERS,
)
from .bybit_top50_coverage_census import _census_with_review_candidates
from .market_data import DataValidationError

MAX_REVIEW = 50
MAX_CAPTURE_AGE_MS = 30_000


@dataclass(frozen=True)
class OfflineIdentityReviewQueue:
    reviewed_count: int
    unreviewed_count: int
    ranked_unreviewed_count: int
    omitted_zero_turnover_count: int
    review_queue_digest_sha256: str
    review_symbols: tuple[str, ...]

    def sanitized_report(self, *, include_public_symbols: bool = False) -> dict:
        if type(include_public_symbols) is not bool:
            raise DataValidationError("public-symbol opt-in must be boolean")
        output = {
            "status": "offline_unreviewed_identity_priority_only",
            "reviewed_eligible_count": self.reviewed_count,
            "plausible_unreviewed_count": self.unreviewed_count,
            "ranked_unreviewed_count": self.ranked_unreviewed_count,
            "omitted_zero_turnover_count": self.omitted_zero_turnover_count,
            "priority_digest_sha256": self.review_queue_digest_sha256,
            "marketwide_top50_verified": False,
            "closed_24h_rank_verified": False,
            "ticker_unit_verified": False,
            "crypto_identity_verified_for_queue": False,
            "rights_for_live_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
        }
        if include_public_symbols:
            output["review_symbols_public_only"] = list(self.review_symbols)
        return output


def prioritize_unreviewed_bybit_identities_offline(
    *, instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    page_received_at_ms: tuple[int, ...],
    tickers_payload: dict,
    observed_at_ms: int,
    registry_variant: str = "expanded-52",
    max_review: int = MAX_REVIEW,
) -> OfflineIdentityReviewQueue:
    """Pure offline triage; every plausible candidate must have a fresh ticker."""
    if (type(max_review) is not int or not 1 <= max_review <= MAX_REVIEW
            or type(observed_at_ms) is not int or observed_at_ms <= 0):
        raise DataValidationError("review size or observation clock invalid")
    census, known, unreviewed = _census_with_review_candidates(
        instrument_pages=instrument_pages,
        requested_cursors=requested_cursors,
        page_received_at_ms=page_received_at_ms,
        observed_at_ms=observed_at_ms, registry_variant=registry_variant,
    )
    _, result, ticker_ms = _response(
        tickers_payload, label="Bybit review tickers",
        at_ms=observed_at_ms, age_ms=MAX_CAPTURE_AGE_MS,
    )
    if (ticker_ms < max(page["time"] for page in instrument_pages)
            or ticker_ms < page_received_at_ms[-1] - MAX_CAPTURE_AGE_MS):
        raise DataValidationError("review ticker predates catalog")
    raw = result.get("list")
    if type(raw) is not list or not 1 <= len(raw) <= MAX_TICKERS:
        raise DataValidationError("review ticker list incomplete or oversized")
    targets = set(unreviewed)
    seen: set[str] = set()
    amounts: dict[str, Decimal] = {}
    for row in raw:
        if type(row) is not dict:
            raise DataValidationError("review ticker row is not object")
        symbol = row.get("symbol")
        if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
                or symbol in seen):
            raise DataValidationError("review ticker malformed or duplicate")
        seen.add(symbol)
        if symbol in targets:
            turnover = _quantity(row.get("turnover24h"), "turnover24h")
            volume = _quantity(row.get("volume24h"), "volume24h")
            if (turnover == 0) != (volume == 0):
                raise DataValidationError("review ticker volume inconsistent")
            amounts[symbol] = turnover
    if targets - set(amounts):
        raise DataValidationError("unreviewed candidate missing ticker")
    ordered = sorted(
        ((sym, value) for sym, value in amounts.items() if value > 0),
        key=lambda item: (-item[1], item[0]),
    )
    queue = tuple(sym for sym, _ in ordered[:max_review])
    digest = sha256(json.dumps(
        [[sym, format(v, "f")] for sym, v in ordered],
        separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")).hexdigest()
    return OfflineIdentityReviewQueue(
        reviewed_count=len(known),
        unreviewed_count=len(unreviewed),
        ranked_unreviewed_count=len(ordered),
        omitted_zero_turnover_count=len(unreviewed) - len(ordered),
        review_queue_digest_sha256=digest,
        review_symbols=queue,
    )
