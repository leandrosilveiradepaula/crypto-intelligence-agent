"""J1 #319: research-only ranking by 24 *closed* UTC-hour Bybit turnovers.

Unlike ticker turnover24h this sums the exact documented quote-USDT turnover
from 24 completed 1h bars for every currently eligible independently reviewed
crypto base. Pre/post full exchange catalog scans must match to detect
membership/metadata drift during a slow 2s/GET multiasset capture.

Offline and pure. Input dictionaries may be untrusted; no network, SQLite,
account credentials or order endpoints. The resulting rank is only inside the
EXPLICITLY REVIEWED registry, never the marketwide Top50 until the whole
crypto identity universe is demonstrably covered.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, Context, localcontext
from hashlib import sha256
import json
from typing import Mapping

from .bybit_linear_candle_research import stage_bybit_linear_kline
from .bybit_paginated_universe_research import (
    scan_bybit_linear_instruments_offline, _response,
)
from .bybit_top50_coverage_census import census_bybit_top50_identity_coverage
from .market_data import DataGapError, DataValidationError

HOUR_MS = 3_600_000
WINDOW_HOURS = 24
TOP_N = 50
# The 2s minimum safe GET spacing requires >120s for 52 single-asset
# kline windows. Six minutes is bounded and restricted to this research
# endpoint, not the strict 30s/120s small-sample capture contracts.
MAX_BATCH_DURATION_MS = 360_000
RESPONSE_FRESHNESS_MS = 30_000


@dataclass(frozen=True)
class ReviewedClosedMember:
    rank: int
    symbol: str
    base: str
    turnover_24_closed_hours_usdt: Decimal


@dataclass(frozen=True)
class BybitReviewedClosedRanking:
    observed_at_ms: int
    closed_hour_decision_ms: int
    registry_sha256: str
    reviewed_eligible_contracts: int
    reviewed_insufficient_listing_history: int
    verified_24h_window_count: int
    complete_catalog_instrument_rows: int
    unreviewed_plausible_contracts: int
    ranked: tuple[ReviewedClosedMember, ...]
    instrument_pages_scanned: int = 1

    def sanitized_report(self, *, include_public_symbols: bool = False) -> dict:
        canonical = json.dumps(
            [(m.rank, m.symbol, format(m.turnover_24_closed_hours_usdt, "f"))
             for m in self.ranked],
            separators=(",", ":"), ensure_ascii=True,
        )
        report = {
            "status": (
                "j1_reviewed_50_closed_24h_rank_verified_not_marketwide"
                if len(self.ranked) >= TOP_N
                else "j1_reviewed_closed_24h_rank_below_50_not_marketwide"
            ),
            "observed_at_ms": self.observed_at_ms,
            "closed_hour_decision_ms": self.closed_hour_decision_ms,
            "registry_sha256": self.registry_sha256,
            "full_catalog_pre_and_post_scan_matched": True,
            "complete_catalog_instrument_rows":
                self.complete_catalog_instrument_rows,
            "reviewed_eligible_contracts": self.reviewed_eligible_contracts,
            "reviewed_insufficient_listing_history":
                self.reviewed_insufficient_listing_history,
            "reviewed_complete_closed_24h_windows":
                self.verified_24h_window_count,
            "ranked_contracts_with_closed_24h_turnover": len(self.ranked),
            "top_n_reviewed_count": min(TOP_N, len(self.ranked)),
            "unreviewed_plausible_contracts":
                self.unreviewed_plausible_contracts,
            "reviewed_rank_digest_sha256":
                sha256(canonical.encode("ascii")).hexdigest(),
            "turnover_quote_currency": "USDT",
            "rolling_ticker_used_for_rank": False,
            "historical_pit_marketwide_top50_verified": False,
            "marketwide_top50_verified": False,
            "canonical_ohlcv_approved": False,
            "rights_for_live_authorized": False,
            "orders_sent": False,
            "network_requests_by_offline_rank": 0,
        }
        if include_public_symbols:
            report["public_reviewed_ranked_contract_identifiers_only"] = [
                member.symbol for member in self.ranked[:TOP_N]
            ]
        return report


def rank_bybit_reviewed_closed_24h_pit(
    *,
    before_instrument_pages: tuple[dict, ...],
    before_requested_cursors: tuple[str | None, ...],
    before_page_received_at_ms: tuple[int, ...],
    after_instrument_pages: tuple[dict, ...],
    after_requested_cursors: tuple[str | None, ...],
    after_page_received_at_ms: tuple[int, ...],
    kline_pages: Mapping[str, dict],
    kline_page_received_at_ms: Mapping[str, int],
    observed_at_ms: int,
    decision_at_ms: int,
    registry_variant: str = "expanded-52",
) -> BybitReviewedClosedRanking:
    """Require complete 24 closed 1h bars for ALL reviewed eligible assets.

    Never fill missing contracts with zero, backdate the new registry, reuse
    ticker rolling turnover or silently omit a missing 24h window.
    """
    if (type(observed_at_ms) is not int or type(decision_at_ms) is not int
            or decision_at_ms <= 0 or decision_at_ms % HOUR_MS
            or observed_at_ms <= decision_at_ms + 999
            or observed_at_ms >= decision_at_ms + HOUR_MS
            or type(registry_variant) is not str
            or registry_variant != "expanded-52"
            or not isinstance(kline_pages, dict)
            or not isinstance(kline_page_received_at_ms, dict)
            or type(before_page_received_at_ms) is not tuple
            or type(after_page_received_at_ms) is not tuple
            or not before_page_received_at_ms
            or not after_page_received_at_ms
            or observed_at_ms - before_page_received_at_ms[0] >
                MAX_BATCH_DURATION_MS
            or before_page_received_at_ms[-1] >=
                after_page_received_at_ms[0]):
        raise DataValidationError("closed24h PIT capture clocks/registry/budget rejected")

    before = scan_bybit_linear_instruments_offline(
        instrument_pages=before_instrument_pages,
        requested_cursors=before_requested_cursors,
        page_received_at_ms=before_page_received_at_ms,
        observed_at_ms=observed_at_ms,
        registry_variant=registry_variant,
    )
    after = scan_bybit_linear_instruments_offline(
        instrument_pages=after_instrument_pages,
        requested_cursors=after_requested_cursors,
        page_received_at_ms=after_page_received_at_ms,
        observed_at_ms=observed_at_ms,
        registry_variant=registry_variant,
    )
    pre_census = census_bybit_top50_identity_coverage(
        instrument_pages=before_instrument_pages,
        requested_cursors=before_requested_cursors,
        page_received_at_ms=before_page_received_at_ms,
        observed_at_ms=observed_at_ms,
        registry_variant=registry_variant,
    )
    post_census = census_bybit_top50_identity_coverage(
        instrument_pages=after_instrument_pages,
        requested_cursors=after_requested_cursors,
        page_received_at_ms=after_page_received_at_ms,
        observed_at_ms=observed_at_ms,
        registry_variant=registry_variant,
    )
    def contracts(rows):
        return tuple(sorted(
            (m.symbol, m.base_coin, m.quote_coin, m.settle_coin,
             m.launch_time_ms, m.max_leverage, m.tick_size, m.quantity_step)
            for m in rows
        ))
    if (contracts(before.instruments) != contracts(after.instruments)
            or pre_census.plausible_candidate_symbol_digest_sha256 !=
                post_census.plausible_candidate_symbol_digest_sha256
            or pre_census.scanned_rows != post_census.scanned_rows
            or before.registry_sha256 != after.registry_sha256
            or before.registry_sha256 != pre_census.registry_sha256
            or pre_census.registry_sha256 != post_census.registry_sha256):
        raise DataValidationError("pre/post reviewed market membership drift")

    eligible = tuple(m for m in before.instruments if
                     m.launch_time_ms <= decision_at_ms - 24 * HOUR_MS)
    expected = {m.symbol for m in eligible}
    if (not expected
            or set(kline_pages) != expected
            or set(kline_page_received_at_ms) != expected):
        raise DataGapError("every listed reviewed crypto perp needs 24 closed hours")
    if (any(type(when) is not int
            or when < before_page_received_at_ms[-1]
            or when > after_page_received_at_ms[0]
            or when <= decision_at_ms + 999
            for when in kline_page_received_at_ms.values())):
        raise DataValidationError("kline receipt before close or after post-scan")
    if (observed_at_ms - before_page_received_at_ms[0] >
            MAX_BATCH_DURATION_MS):
        raise DataValidationError("closed24h capture exceeded six-minute budget")
    values: list[tuple[str, str, Decimal]] = []
    with localcontext(Context(prec=72)):
        for member in eligible:
            payload = kline_pages[member.symbol]
            received = kline_page_received_at_ms[member.symbol]
            # Bybit V5 supplies a server response time, separately verified
            # against the actual receipt of every 24-hour kline GET.
            _response(
                payload, label="Bybit 24 closed 1h research bars",
                at_ms=received, age_ms=RESPONSE_FRESHNESS_MS,
            )
            page = stage_bybit_linear_kline(
                payload,
                symbol=member.symbol,
                quote_currency="USDT",
                contract_type="LinearPerpetual",
                contract_status="Trading",
                contract_observed_at_ms=member.observed_at_ms,
                observed_at_ms=received,
                max_contract_age_ms=MAX_BATCH_DURATION_MS,
                interval="1h",
                start_open_ms=decision_at_ms - WINDOW_HOURS * HOUR_MS,
                end_open_ms=decision_at_ms,
                close_safety_ms=1000,
                max_candles=WINDOW_HOURS,
            )
            total = sum(
                (bar.documented_quote_turnover for bar in page.candles),
                Decimal(0),
            )
            if not total.is_finite() or total < 0:
                raise DataValidationError("nonfinite 24h quote turnover")
            values.append((member.symbol, member.base_coin, total))
        values.sort(key=lambda x: (-x[2], x[0]))
    ranked = tuple(
        ReviewedClosedMember(i, symbol, base, total)
        for i, (symbol, base, total) in enumerate(values[:TOP_N], start=1)
    )
    return BybitReviewedClosedRanking(
        observed_at_ms=observed_at_ms,
        closed_hour_decision_ms=decision_at_ms,
        registry_sha256=before.registry_sha256,
        reviewed_eligible_contracts=len(before.instruments),
        reviewed_insufficient_listing_history=(
            len(before.instruments) - len(eligible)
        ),
        verified_24h_window_count=len(eligible),
        complete_catalog_instrument_rows=pre_census.scanned_rows,
        unreviewed_plausible_contracts=pre_census.plausible_unreviewed_usdt_perpetuals,
        ranked=ranked,
        instrument_pages_scanned=len(before_instrument_pages),
    )
