"""Automatic USDT perpetual screening for RESEARCH, not an execution allowlist.

USDT is a quotation/settlement currency, not proof of a crypto underlying.
Provider metadata plus dated known negatives excludes observable TradFi.
The remainder is provisional, with no manual per-token positive registry gate
for research. All inputs are offline. No network, filesystem, orders or API keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import re
from typing import Mapping

from .bybit_paginated_universe_research import (
    _response, _cursor, MAX_PAGES, MAX_ROWS_PER_PAGE, MAX_INSTRUMENT_ROWS,
)
from .bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE
from .market_data import DataValidationError

_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_BAD_NAME = re.compile(
    r"\b(?:brent\s+oil|crude\s+oil|(?:stock|equity|share|shares|etf|index)"
    r"\s+(?:future|perpetual|contract|token)|(?:stock|equity|share|shares|etf)\b)",
    re.IGNORECASE,
)
_HOUR = 3_600_000
_MAX_AGE = 120_000
_MATH = Context(prec=72)


@dataclass(frozen=True)
class AutomaticPerpResearchPool:
    observed_at_ms: int
    scanned_contracts: int
    candidate_symbols: tuple[str, ...]
    excluded_product: int
    excluded_documented_tradfi: int
    excluded_provider_tradfi: int
    excluded_fullname_tradfi: int
    excluded_ambiguous_or_malformed: int
    candidate_missing_optional_markers: int
    catalog_pages: int

    def sanitized_report(self, *, include_public_symbols: bool = False) -> dict:
        if type(include_public_symbols) is not bool:
            raise DataValidationError("explicit boolean symbol opt-in required")
        out = {
            "status": "automatic_usdt_perpetual_research_candidates_only",
            "observed_at_ms": self.observed_at_ms,
            "catalog_pages": self.catalog_pages,
            "catalog_contracts": self.scanned_contracts,
            "possible_crypto_perp_research_candidates": len(self.candidate_symbols),
            "excluded_non_target_products": self.excluded_product,
            "excluded_documented_tradfi": self.excluded_documented_tradfi,
            "excluded_provider_tradfi_markers": self.excluded_provider_tradfi,
            "excluded_clear_tradfi_fullnames": self.excluded_fullname_tradfi,
            "excluded_ambiguous_or_malformed": self.excluded_ambiguous_or_malformed,
            "candidate_missing_optional_markers": self.candidate_missing_optional_markers,
            "candidate_digest_sha256":
                sha256("\n".join(self.candidate_symbols).encode("ascii")).hexdigest(),
            "venue_metadata_is_not_positive_crypto_proof": True,
            "automatic_research_not_trading_allowlist": True,
            "marketwide_top50_verified": False,
            "order_execution_enabled": False,
            "network_requests": 0,
        }
        if include_public_symbols:
            out["research_candidate_symbols_only"] = list(self.candidate_symbols)
        return out


def screen_bybit_usdt_perps_offline(
    *, instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    page_received_at_ms: tuple[int, ...], observed_at_ms: int,
) -> AutomaticPerpResearchPool:
    """Screen a complete, timestamped Bybit V5 linear catalog automatically.

    A row without TradFi indicators remains only a *possible* crypto perp.
    Truncated pagination, duplicated symbols and unsafe inputs fail closed.
    """
    if (type(observed_at_ms) is not int or observed_at_ms <= 0
            or type(instrument_pages) is not tuple
            or not 1 <= len(instrument_pages) <= MAX_PAGES
            or type(requested_cursors) is not tuple
            or len(requested_cursors) != len(instrument_pages)
            or requested_cursors[0] is not None
            or type(page_received_at_ms) is not tuple
            or len(page_received_at_ms) != len(instrument_pages)
            or any(type(t) is not int or not 0 < t <= observed_at_ms
                   for t in page_received_at_ms)
            or any(a > b for a, b in zip(
                page_received_at_ms, page_received_at_ms[1:]))):
        raise DataValidationError("complete causal paginated Bybit catalog required")
    seen = set()
    requested_seen = set()
    expected_cursor = None
    last_server_ms = 0
    candidates = set()
    counts = dict(product=0, documented=0, provider=0, fullname=0,
                  ambiguous=0, optional=0)
    total = 0
    for pidx, payload in enumerate(instrument_pages):
        received = page_received_at_ms[pidx]
        _, result, server_ms = _response(
            payload, label="auto-screen Bybit catalog", at_ms=received,
            age_ms=_MAX_AGE,
        )
        if server_ms + 2_000 < last_server_ms:
            raise DataValidationError("noncausal catalog page timestamps")
        last_server_ms = max(last_server_ms, server_ms)
        requested = requested_cursors[pidx]
        if requested != expected_cursor:
            raise DataValidationError("catalog cursor chain incomplete")
        if requested is not None:
            _cursor(requested, terminal_ok=False)
            if requested in requested_seen:
                raise DataValidationError("repeated catalog request cursor")
            requested_seen.add(requested)
        following = _cursor(result.get("nextPageCursor"), terminal_ok=True)
        if following and (following == requested or following in requested_seen):
            raise DataValidationError("catalog cursor cycle")
        if (pidx == len(instrument_pages) - 1) != (following == ""):
            raise DataValidationError("catalog chain not complete")
        expected_cursor = following or None
        rows = result.get("list")
        if (type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS_PER_PAGE
                or total + len(rows) > MAX_INSTRUMENT_ROWS):
            raise DataValidationError("catalog page resource budget exceeded")
        total += len(rows)
        for row in rows:
            if type(row) is not dict:
                raise DataValidationError("catalog row malformed")
            symbol = row.get("symbol")
            if (type(symbol) is not str or not 1 <= len(symbol) <= 80
                    or not symbol.isascii() or not symbol.isprintable()
                    or any(x.isspace() for x in symbol)
                    or symbol in seen):
                raise DataValidationError("unsafe or duplicate catalog symbol")
            seen.add(symbol)
            if (row.get("contractType") != "LinearPerpetual"
                    or row.get("status") != "Trading"
                    or row.get("quoteCoin") != "USDT"
                    or row.get("settleCoin") != "USDT"):
                counts["product"] += 1
                continue
            base = row.get("baseCoin")
            if (not _SYMBOL.fullmatch(symbol) or type(base) is not str
                    or symbol != base + "USDT"
                    or row.get("deliveryTime", "0") != "0"
                    or row.get("isPreListing", False) is not False
                    or row.get("preListingInfo") is not None):
                counts["ambiguous"] += 1
                continue
            if symbol in NEGATIVE_EVIDENCE:
                counts["documented"] += 1
                continue
            region, underlying = row.get("marketRegion"), row.get("underlyingTicker")
            symbol_type = row.get("symbolType", "")
            name = row.get("fullName", "")
            tags = row.get("tags", [])
            if ((region is not None and
                 (type(region) is not str or len(region) > 80))
                    or (underlying is not None and
                        (type(underlying) is not str or len(underlying) > 80))
                    or type(symbol_type) is not str or len(symbol_type) > 80
                    or type(name) is not str or len(name) > 180
                    or type(tags) is not list or len(tags) > 20
                    or any(type(tag) is not str or len(tag) > 40 for tag in tags)):
                counts["ambiguous"] += 1
                continue
            if region or underlying or symbol_type:
                counts["provider"] += 1
                continue
            if _BAD_NAME.search(name):
                counts["fullname"] += 1
                continue
            if tags:  # unknown special-treatment status: no research admission
                counts["ambiguous"] += 1
                continue
            if region is None or underlying is None:
                counts["optional"] += 1
            candidates.add(symbol)
    return AutomaticPerpResearchPool(
        observed_at_ms=observed_at_ms, scanned_contracts=total,
        candidate_symbols=tuple(sorted(candidates)),
        excluded_product=counts["product"],
        excluded_documented_tradfi=counts["documented"],
        excluded_provider_tradfi=counts["provider"],
        excluded_fullname_tradfi=counts["fullname"],
        excluded_ambiguous_or_malformed=counts["ambiguous"],
        candidate_missing_optional_markers=counts["optional"],
        catalog_pages=len(instrument_pages),
    )


@dataclass(frozen=True)
class Closed24hResearchRanking:
    ranked: tuple[tuple[str, Decimal], ...]
    covered_count: int
    insufficient_count: int
    zero_turnover_count: int
    metadata_near_closed_hour: bool

    def sanitized_report(self, *, include_public_symbols: bool = False) -> dict:
        if type(include_public_symbols) is not bool:
            raise DataValidationError("explicit boolean opt-in required")
        digest = sha256(json.dumps(
            [[s, format(v, "f")] for s, v in self.ranked],
            ensure_ascii=True, separators=(",", ":"),
        ).encode("ascii")).hexdigest()
        out = {
            "status": "auto_candidate_closed24h_research_not_marketwide",
            "complete_closed_24h_candidates": self.covered_count,
            "missing_or_incomplete_candidates": self.insufficient_count,
            "zero_turnover_candidates": self.zero_turnover_count,
            "top50_sample_size": len(self.ranked),
            "rank_digest_sha256": digest,
            "metadata_observed_near_closed_hour_not_pit_proof":
                self.metadata_near_closed_hour,
            "marketwide_top50_verified": False,
            "approved_for_trading": False,
            "orders_sent": False,
        }
        if include_public_symbols:
            out["research_ranked_symbols_only"] = [s for s, _ in self.ranked]
        return out


def rank_auto_candidates_closed24h_offline(
    pool: AutomaticPerpResearchPool, *,
    closed_hour_end_ms: int,
    closed_candle_turnovers: Mapping[str, tuple[tuple[int, Decimal], ...]],
) -> Closed24hResearchRanking:
    """Rank strictly 24 contiguous CLOSED 1h quote-turnover observations.

    No rolling ticker, zero imputation, stale metadata PIT assertion, or
    marketwide/trading grant. Inputs are untrusted offline research data.
    """
    if (type(pool) is not AutomaticPerpResearchPool
            or type(closed_hour_end_ms) is not int
            or closed_hour_end_ms <= 0 or closed_hour_end_ms % _HOUR
            or pool.observed_at_ms < closed_hour_end_ms + 1_000
            or type(closed_candle_turnovers) is not dict
            or set(closed_candle_turnovers) - set(pool.candidate_symbols)):
        raise DataValidationError("invalid closed-hour rank inputs")
    complete = []
    incomplete = zeros = 0
    with localcontext(_MATH):
        for symbol in pool.candidate_symbols:
            bars = closed_candle_turnovers.get(symbol, ())
            if type(bars) is not tuple or len(bars) > 24:
                raise DataValidationError("invalid closed-hour bar collection")
            if len(bars) != 24:
                incomplete += 1
            total = Decimal(0)
            for i, bar in enumerate(bars):
                expected = closed_hour_end_ms - (24 - i) * _HOUR
                if (type(bar) is not tuple or len(bar) != 2
                        or type(bar[0]) is not int or bar[0] != expected
                        or type(bar[1]) is not Decimal
                        or not bar[1].is_finite() or bar[1] < 0
                        or len(bar[1].as_tuple().digits) > 40
                        or bar[1].adjusted() > 35):
                    raise DataValidationError("closed 24h quote turnover row invalid")
                total += bar[1]
            if len(bars) != 24:
                continue
            if total == 0:
                zeros += 1
                continue
            complete.append((symbol, total))
    complete.sort(key=lambda x: (-x[1], x[0]))
    return Closed24hResearchRanking(
        ranked=tuple(complete[:50]), covered_count=len(complete),
        insufficient_count=incomplete, zero_turnover_count=zeros,
        metadata_near_closed_hour=(
            pool.observed_at_ms < closed_hour_end_ms + _HOUR
        ),
    )
