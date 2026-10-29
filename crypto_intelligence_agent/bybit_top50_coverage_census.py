"""J1 #319: independently reviewable *coverage gap*, NEVER a Top50 grant.

A full Bybit linear instrument list includes USDC, expiring futures, premarket
and TradFi/stock-derived products. Contract labels alone cannot authenticate
independent cryptocurrency identities. The positive reviewed registry remains
the only admission rule to downstream J1 research.

All inputs are caller-provided (offline); no network, storage, new privileges,
market turnover or financial-order calculations. Output deliberately excludes
all raw symbols, prices, volumes and private addresses.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .bybit_paginated_universe_research import (
    scan_bybit_linear_instruments_offline,
)
from .market_data import DataValidationError
from .research_registry_catalog import load_reviewed_registry

_SYMBOL = re.compile(r"^[A-Z0-9]{2,24}USDT$")
_BASE = re.compile(r"^[A-Z0-9]{2,24}$")
MAX_RESEARCH_TOP = 50


@dataclass(frozen=True)
class BybitMarketwideCoverageCensus:
    observed_at_ms: int
    registry_sha256: str
    scanned_pages: int
    scanned_rows: int
    reviewed_crypto_registry_bases: int
    reviewed_eligible_usdt_perpetuals: int
    plausible_unreviewed_usdt_perpetuals: int
    excluded_other_or_tradfi_rows: int
    reviewed_but_noneligible_rows: int
    plausible_candidate_symbol_digest_sha256: str

    @property
    def top50_capacity_gap(self) -> int:
        return max(0, MAX_RESEARCH_TOP - self.reviewed_eligible_usdt_perpetuals)

    def sanitized_report(self) -> dict:
        # The 24h rolling ticker is not equal to 24 CLOSED hourly candles.
        # No volume ranking is attempted here, so marketwide cannot pass.
        return {
            "status": "j1_top50_marketwide_identity_coverage_incomplete",
            "observed_at_ms": self.observed_at_ms,
            "registry_sha256": self.registry_sha256,
            "instrument_pages_scanned": self.scanned_pages,
            "instrument_rows_scanned": self.scanned_rows,
            "reviewed_crypto_registry_bases": self.reviewed_crypto_registry_bases,
            "reviewed_eligible_usdt_perpetuals":
                self.reviewed_eligible_usdt_perpetuals,
            "plausible_unreviewed_usdt_perpetuals":
                self.plausible_unreviewed_usdt_perpetuals,
            "excluded_other_or_tradfi_rows":
                self.excluded_other_or_tradfi_rows,
            "reviewed_but_noneligible_rows":
                self.reviewed_but_noneligible_rows,
            "positive_registry_top50_capacity_gap": self.top50_capacity_gap,
            "plausible_candidate_symbol_digest_sha256":
                self.plausible_candidate_symbol_digest_sha256,
            "full_paginated_catalog_observed_from_caller": True,
            "full_closed_24h_turnover_rank_verified": False,
            "historical_pit_marketwide_top50_verified": False,
            "marketwide_top50_verified": False,
            "crypto_identity_for_unreviewed_candidates_verified": False,
            "canonical_ohlcv_approved": False,
            "public_or_commercial_rights_authorized": False,
            "orders_sent": False,
            "network_requests_by_census": 0,
        }


def census_bybit_top50_identity_coverage(
    *, instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    observed_at_ms: int,
    page_received_at_ms: tuple[int, ...] | None = None,
    registry_variant: str = "expanded-13",
) -> BybitMarketwideCoverageCensus:
    """Count reviewed + unreviewed, without silently promoting the latter.

    A row enters the unreviewed plausible group only if all of the Bybit
    crypto-shaped perpetual guards pass. This is an identity REVIEW QUEUE,
    not crypto-only evidence or Top50. Duplicates of *plausible* symbols across
    the complete cursor chain fail closed, as do duplicates of reviewed ones.
    """
    scan = scan_bybit_linear_instruments_offline(
        instrument_pages=instrument_pages,
        requested_cursors=requested_cursors,
        observed_at_ms=observed_at_ms,
        page_received_at_ms=page_received_at_ms,
        registry_variant=registry_variant,
    )
    registry = load_reviewed_registry(registry_variant, as_of_ms=observed_at_ms)
    known = {asset.symbol for asset in scan.instruments}
    plausible_unreviewed: set[str] = set()
    considered: set[str] = set()
    excluded, noneligible_reviewed = 0, 0
    for page in instrument_pages:
        for row in page["result"]["list"]:
            symbol = row["symbol"]
            base = row.get("baseCoin")
            crypto_shaped = (
                type(base) is str and _BASE.fullmatch(base) is not None
                and type(symbol) is str and _SYMBOL.fullmatch(symbol) is not None
                and symbol == base + "USDT"
                and row.get("contractType") == "LinearPerpetual"
                and row.get("status") == "Trading"
                and row.get("quoteCoin") == "USDT"
                and row.get("settleCoin") == "USDT"
                and row.get("deliveryTime") == "0"
                and row.get("symbolType") == ""
                and row.get("marketRegion", "") == ""
                and row.get("underlyingTicker", "") == ""
                and row.get("tags") == []
                and row.get("isPreListing") is False
                and row.get("preListingInfo") is None
            )
            if not crypto_shaped:
                if type(base) is str and base in registry.verified_crypto_bases:
                    noneligible_reviewed += 1
                else:
                    excluded += 1
                continue
            if symbol in considered:
                raise DataValidationError(
                    "Bybit plausible reviewed/unreviewed instrument repeated"
                )
            considered.add(symbol)
            if base not in registry.verified_crypto_bases:
                plausible_unreviewed.add(symbol)
            elif symbol not in known:
                # A known base with invalid fields is not automatically accepted.
                noneligible_reviewed += 1
    if known - considered:
        raise DataValidationError(
            "Bybit independently reviewed candidate lost from census"
        )
    digest = sha256(
        "\n".join(sorted(plausible_unreviewed)).encode("ascii")
    ).hexdigest()
    return BybitMarketwideCoverageCensus(
        observed_at_ms=observed_at_ms,
        registry_sha256=scan.registry_sha256,
        scanned_pages=scan.page_count,
        scanned_rows=scan.instrument_row_count,
        reviewed_crypto_registry_bases=len(registry.verified_crypto_bases),
        reviewed_eligible_usdt_perpetuals=len(known),
        plausible_unreviewed_usdt_perpetuals=len(plausible_unreviewed),
        excluded_other_or_tradfi_rows=excluded,
        reviewed_but_noneligible_rows=noneligible_reviewed,
        plausible_candidate_symbol_digest_sha256=digest,
    )
