"""J1/PIT1: descriptive multiasset Vision research sample at a past UTC hour.

No exchange listing registry, historical eligible universe, authenticated data,
USD conversion, trading signal, account, persistence, or network is provided.
Candidate ordering is restricted to the supplied local USDT-quote sample.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .market_data import DataValidationError
from .offline_vision_month import OfflineVisionMonth
from .offline_vision_series import assemble_offline_vision_months

_HOUR_MS = 3_600_000
_LOOKBACK_HOURS = 24
_MAX_SYMBOLS = 50
_CTX = Context(prec=256, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class ObservedVisionResearchMember:
    """Not a verified perpetual contract or a real Top50 rank."""

    rank_within_supplied_sample: int
    symbol: str
    observed_quote_volume_24h_usdt: Decimal


@dataclass(frozen=True)
class ObservedVisionResearchWindow:
    decision_at_ms: int
    window_first_open_ms: int
    window_end_open_exclusive_ms: int
    observed_symbol_count: int
    observed_closed_bars_per_symbol: int
    ranked: tuple[ObservedVisionResearchMember, ...]

    @property
    def ranking_basis(self) -> str:
        return "last_24_fully_closed_1h_quote_volumes_usdt_in_supplied_sample"

    @property
    def research_only(self) -> bool:
        return True

    @property
    def sample_is_full_eligible_market(self) -> bool:
        return False

    @property
    def historical_listing_eligibility_verified(self) -> bool:
        return False

    @property
    def historical_top50_verified(self) -> bool:
        return False

    @property
    def usd_comparable_volume_verified(self) -> bool:
        return False

    @property
    def source_authenticated(self) -> bool:
        return False

    @property
    def dataset_rights_authorized_for_live(self) -> bool:
        return False

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def ready_for_trading(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def rank_observed_vision_quote_volume(
    month_groups: tuple[tuple[OfflineVisionMonth, ...], ...], *,
    as_of_ms: int,
    decision_at_ms: int,
    max_candidates: int = 50,
) -> ObservedVisionResearchWindow:
    """Rank only supplied, aligned local research series using PAST 24 closed bars.

    Each group must pass the existing full chronological/month/Decimal
    validation. Timestamp checks guard against using the decision candle or
    future data in volume. A past market listing or full eligible Top50 universe
    CANNOT be inferred from archives that happen to exist in hindsight.
    """
    if (type(month_groups) is not tuple or not 2 <= len(month_groups) <= _MAX_SYMBOLS
            or any(type(group) is not tuple for group in month_groups)
            or type(as_of_ms) is not int or type(decision_at_ms) is not int
            or type(max_candidates) is not int
            or not 1 <= max_candidates <= _MAX_SYMBOLS):
        raise DataValidationError("bounded multiasset research inputs required")
    series = tuple(assemble_offline_vision_months(group, as_of_ms=as_of_ms)
                   for group in month_groups)
    first = series[0]
    signature = (first.first_open_ms, first.end_open_exclusive_ms, len(first.candles),
                 len(first.month_names))
    if (len({item.symbol for item in series}) != len(series)
            or any((item.first_open_ms, item.end_open_exclusive_ms,
                    len(item.candles), len(item.month_names)) != signature
                   or item.interval != "1h" or not item.symbol.endswith("USDT")
                   for item in series)):
        raise DataValidationError("unaligned, duplicate or mixed-quote research universe")
    if (decision_at_ms % _HOUR_MS != 0
            or not first.first_open_ms + _LOOKBACK_HOURS * _HOUR_MS
            <= decision_at_ms <= first.end_open_exclusive_ms):
        raise DataValidationError("decision must have exactly 24 prior closed research bars")
    index = (decision_at_ms - first.first_open_ms) // _HOUR_MS
    with localcontext(_CTX):
        totals: list[tuple[str, Decimal]] = []
        for item in series:
            window = item.candles[index - _LOOKBACK_HOURS:index]
            if (len(window) != _LOOKBACK_HOURS
                    or window[-1].close_time_ms >= decision_at_ms):
                raise DataValidationError("lookahead or incomplete research window")
            observed = sum((bar.documented_quote_volume for bar in window), Decimal(0))
            if not observed.is_finite() or observed < 0:
                raise DataValidationError("invalid research quote turnover")
            totals.append((item.symbol, observed))
        totals.sort(key=lambda pair: (-pair[1], pair[0]))
    ranked = tuple(ObservedVisionResearchMember(
        rank_within_supplied_sample=i + 1, symbol=symbol,
        observed_quote_volume_24h_usdt=amount,
    ) for i, (symbol, amount) in enumerate(totals[:max_candidates]))
    return ObservedVisionResearchWindow(
        decision_at_ms=decision_at_ms,
        window_first_open_ms=decision_at_ms - _LOOKBACK_HOURS * _HOUR_MS,
        window_end_open_exclusive_ms=decision_at_ms,
        observed_symbol_count=len(series),
        observed_closed_bars_per_symbol=_LOOKBACK_HOURS,
        ranked=ranked,
    )
