"""J1/EXIT: deterministic point-in-time Bybit perpetual research selection.

Uses existing validated complete paginated instrument scan and official V5
closed-1h kline quote turnover (USDT). No network, cache, licensing grant,
historical market-wide Top50 assertion, canonical feed or order execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
from typing import Mapping

from .bybit_linear_candle_research import stage_bybit_linear_kline
from .bybit_paginated_universe_research import scan_bybit_linear_instruments_offline
from .market_data import DataValidationError

HOUR_MS = 3_600_000
WINDOW_HOURS = 24
# Strict offline/one-shot freshness stays at 30s. The only permitted longer
# case is an owner-captured, individually timestamped paginated PIT batch:
# pacing a reviewed multiasset ranking can exceed 30s while all bars remain
# closed at one UTC decision cutoff. This is NOT a live trading data contract.
DEFAULT_CONTRACT_MAX_AGE_MS = 30_000
MAX_PIT_BATCH_CONTRACT_AGE_MS = 120_000
_CONTEXT = Context(prec=256)


@dataclass(frozen=True)
class BybitPITMember:
    rank_in_reviewed_sample: int
    symbol: str
    base_unit: str
    quote_unit: str
    observed_turnover_24h_usdt: Decimal


@dataclass(frozen=True)
class BybitPITResearchSelection:
    observed_at_ms: int
    decision_at_ms: int
    registry_sha256: str
    instrument_page_count: int
    all_instrument_row_count: int
    reviewed_contract_count: int
    insufficient_listing_history_count: int
    candidates_with_full_24h_count: int
    ranked: tuple[BybitPITMember, ...]

    def __post_init__(self) -> None:
        if (type(self.observed_at_ms) is not int
                or type(self.decision_at_ms) is not int
                or self.decision_at_ms <= 0
                or self.decision_at_ms % HOUR_MS
                or not self.decision_at_ms + 1000 <= self.observed_at_ms
                       < self.decision_at_ms + HOUR_MS
                or type(self.registry_sha256) is not str
                or len(self.registry_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.registry_sha256)
                or any(type(v) is not int or v < 0 for v in (
                    self.instrument_page_count, self.all_instrument_row_count,
                    self.reviewed_contract_count,
                    self.insufficient_listing_history_count,
                    self.candidates_with_full_24h_count))
                or self.instrument_page_count < 1
                or self.all_instrument_row_count < self.reviewed_contract_count
                or self.reviewed_contract_count != (
                    self.insufficient_listing_history_count
                    + self.candidates_with_full_24h_count)
                or type(self.ranked) is not tuple
                or not 1 <= len(self.ranked) <= 50
                or len(self.ranked) > self.candidates_with_full_24h_count):
            raise DataValidationError("invalid research PIT selection identity or bounds")
        seen = set()
        amounts = []
        for index, member in enumerate(self.ranked):
            if (type(member) is not BybitPITMember
                    or type(member.rank_in_reviewed_sample) is not int
                    or member.rank_in_reviewed_sample != index + 1
                    or type(member.symbol) is not str
                    or not member.symbol.isascii()
                    or not member.symbol.endswith("USDT")
                    or not member.symbol.isupper()
                    or member.symbol in seen
                    or type(member.base_unit) is not str
                    or member.symbol != member.base_unit + "USDT"
                    or member.quote_unit != "USDT"
                    or type(member.observed_turnover_24h_usdt) is not Decimal
                    or not member.observed_turnover_24h_usdt.is_finite()
                    or member.observed_turnover_24h_usdt < 0):
                raise DataValidationError("invalid reviewed-sample PIT ranking member")
            seen.add(member.symbol)
            amounts.append((member.observed_turnover_24h_usdt, member.symbol))
        if amounts != sorted(amounts, key=lambda x: (-x[0], x[1])):
            raise DataValidationError("PIT rank must be monotonic and deterministic")

    @property
    def quote_turnover_unit(self) -> str:
        return "USDT_not_USD"

    @property
    def historical_universe_complete(self) -> bool:
        return False

    @property
    def verified_market_top50(self) -> bool:
        return False

    @property
    def point_in_time_source_authenticated(self) -> bool:
        return False

    @property
    def rights_for_live_authorized(self) -> bool:
        return False

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    def canonical_json(self) -> str:
        """Stable immutable research claim; no provenance attestation."""
        return json.dumps({
            "schema_version": "j1-bybit-pit-reviewed-sample-v1",
            "observed_at_ms": self.observed_at_ms,
            "decision_at_ms": self.decision_at_ms,
            "registry_sha256": self.registry_sha256,
            "instrument_page_count": self.instrument_page_count,
            "all_instrument_row_count": self.all_instrument_row_count,
            "reviewed_contract_count": self.reviewed_contract_count,
            "insufficient_listing_history_count": self.insufficient_listing_history_count,
            "candidates_with_full_24h_count": self.candidates_with_full_24h_count,
            "ranked": [{
                "rank": m.rank_in_reviewed_sample,
                "symbol": m.symbol,
                "base": m.base_unit,
                "quote": m.quote_unit,
                "turnover_24h_usdt": format(m.observed_turnover_24h_usdt, "f"),
            } for m in self.ranked],
            "market_wide_top50_verified": False,
            "source_authenticated": False,
            "rights_for_live_authorized": False,
        }, separators=(",", ":"), sort_keys=True, ensure_ascii=True)

    @property
    def content_sha256(self) -> str:
        return sha256(self.canonical_json().encode("ascii")).hexdigest()


def select_bybit_reviewed_sample_pit(
    *,
    instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    kline_pages: Mapping[str, dict],
    observed_at_ms: int,
    decision_at_ms: int,
    registry_variant: str = "expanded-13",
    max_candidates: int = 50,
    instrument_page_received_at_ms: tuple[int, ...] | None = None,
    max_contract_age_ms: int = DEFAULT_CONTRACT_MAX_AGE_MS,
) -> BybitPITResearchSelection:
    """Rank FULL 24 hours of closed candles for every reviewed eligible base.

    A reviewed crypto identity registry is necessarily incomplete (currently 13
    bases). We do not pretend this is the historical top 50 of the exchange.
    All required klines must exist or the whole observation fails closed.
    """
    if (type(observed_at_ms) is not int or type(decision_at_ms) is not int
            or observed_at_ms <= 0 or type(max_candidates) is not int
            or not 1 <= max_candidates <= 50
            or decision_at_ms % HOUR_MS
            or decision_at_ms != (observed_at_ms // HOUR_MS) * HOUR_MS
            or observed_at_ms - decision_at_ms < 1000
            or type(kline_pages) is not dict
            or type(max_contract_age_ms) is not int
            or not 0 <= max_contract_age_ms <= MAX_PIT_BATCH_CONTRACT_AGE_MS
            or (max_contract_age_ms > DEFAULT_CONTRACT_MAX_AGE_MS
                and (type(instrument_page_received_at_ms) is not tuple
                     or not instrument_page_received_at_ms))):
        raise DataValidationError("invalid point-in-time observed clock/candidate budget")
    scan = scan_bybit_linear_instruments_offline(
        instrument_pages=instrument_pages,
        requested_cursors=requested_cursors, observed_at_ms=observed_at_ms,
        registry_variant=registry_variant,
        page_received_at_ms=instrument_page_received_at_ms,
    )
    # A larger freshness allowance is justified only by a bounded REAL
    # sequence of per-page receipt clocks, not by adjusting a stale offline
    # fixture or inventing a receipt timestamp for an old server response.
    if (max_contract_age_ms > DEFAULT_CONTRACT_MAX_AGE_MS
            and observed_at_ms - instrument_page_received_at_ms[0]
                > MAX_PIT_BATCH_CONTRACT_AGE_MS):
        raise DataValidationError("PIT paginated capture batch exceeds 120s")
    eligible = tuple(
        item for item in scan.instruments
        if item.launch_time_ms <= decision_at_ms - WINDOW_HOURS * HOUR_MS
    )
    expected = {item.symbol for item in eligible}
    if (not expected or set(kline_pages) != expected
            or any(type(s) is not str or type(page) is not dict
                   for s, page in kline_pages.items())):
        raise DataValidationError("full reviewed-sample closed-kline coverage required")

    totals: list[tuple[str, str, Decimal]] = []
    with localcontext(_CONTEXT):
        for item in eligible:
            page = stage_bybit_linear_kline(
                kline_pages[item.symbol],
                symbol=item.symbol,
                quote_currency=item.quote_coin,
                contract_type="LinearPerpetual",
                contract_status="Trading",
                contract_observed_at_ms=item.observed_at_ms,
                observed_at_ms=observed_at_ms,
                max_contract_age_ms=max_contract_age_ms,
                interval="1h",
                start_open_ms=decision_at_ms - WINDOW_HOURS * HOUR_MS,
                end_open_ms=decision_at_ms,
                close_safety_ms=1000,
                max_candles=WINDOW_HOURS,
            )
            if len(page.candles) != WINDOW_HOURS:
                raise DataValidationError("missing closed hourly kline")
            total = sum((c.documented_quote_turnover for c in page.candles), Decimal(0))
            if not total.is_finite() or total < 0:
                raise DataValidationError("invalid quote turnover")
            totals.append((item.symbol, item.base_coin, total))
        totals.sort(key=lambda x: (-x[2], x[0]))
    members = tuple(BybitPITMember(
        i + 1, sym, base, "USDT", total,
    ) for i, (sym, base, total) in enumerate(totals[:max_candidates]))
    return BybitPITResearchSelection(
        observed_at_ms=observed_at_ms,
        decision_at_ms=decision_at_ms,
        registry_sha256=scan.registry_sha256,
        instrument_page_count=scan.page_count,
        all_instrument_row_count=scan.instrument_row_count,
        reviewed_contract_count=len(scan.instruments),
        insufficient_listing_history_count=len(scan.instruments) - len(eligible),
        candidates_with_full_24h_count=len(eligible),
        ranked=members,
    )
