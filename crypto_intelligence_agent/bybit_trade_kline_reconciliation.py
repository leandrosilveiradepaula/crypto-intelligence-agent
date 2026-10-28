"""J1 #256: offline-only comparison of unverified trade hours vs V5 schema.

The V5 reference comes from the existing STRICT offline parser and is NOT
independent evidence of a 2020 venue contract or rights to store market data.
Never return prices, volumes, per-hour differences, signals or trading output.
"""
from __future__ import annotations

from dataclasses import dataclass

from .bybit_linear_candle_research import (
    BybitLinearCandlePageResearch, SOURCE as V5_RESEARCH_SOURCE,
)
from .bybit_trade_hourly_research import WeeklyTradeHourResearch
from .market_data import DataValidationError

HOUR_MS = 3_600_000
WEEK_HOURS = 168


@dataclass(frozen=True)
class BybitHourlyReconciliation:
    reference_hours: int
    hours_without_trades_observed: int
    hours_with_trades_observed: int
    ambiguous_boundary_hours: int
    fully_comparable_ohlc_hours: int
    fully_equal_ohlc_hours: int
    divergent_ohlc_hours: int
    open_compared: int
    open_divergent: int
    high_compared: int
    high_divergent: int
    low_compared: int
    low_divergent: int
    close_compared: int
    close_divergent: int
    quote_volume_compared: int = 0
    volume_units_verified: bool = False
    source_authenticated: bool = False
    rights_authorized: bool = False
    canonical_ohlcv_approved: bool = False
    historical_top50_approved: bool = False
    financial_backtest_approved: bool = False
    live_trading_authorized: bool = False
    orders_sent: bool = False


def reconcile_weekly_trades_with_v5_kline(
    trade_week: WeeklyTradeHourResearch,
    reference: BybitLinearCandlePageResearch,
) -> BybitHourlyReconciliation:
    """Count exact OHLC agreements; ambiguous and missing hours never pass.

    A full 168-hour reference is required, with the strict original reverse
    sequence already validated by stage_bybit_linear_kline. No fetch here.
    """
    if (not isinstance(trade_week, WeeklyTradeHourResearch)
            or not isinstance(reference, BybitLinearCandlePageResearch)
            or reference.source != V5_RESEARCH_SOURCE
            or reference.interval != "1h"
            or reference.symbol != "BTCUSDT"
            or reference.quote_currency != "USDT"
            or type(reference.start_open_ms) is not int
            or type(reference.end_open_ms) is not int
            or reference.start_open_ms < 0
            or reference.start_open_ms % HOUR_MS != 0
            or reference.end_open_ms != reference.start_open_ms + WEEK_HOURS * HOUR_MS
            or len(reference.candles) != WEEK_HOURS
            or len(trade_week.hours) > WEEK_HOURS
            or len(trade_week.missing_hour_open_ms) > WEEK_HOURS):
        raise DataValidationError("research-only week/reference contract mismatch")
    start = reference.start_open_ms
    expected = tuple(start + i * HOUR_MS for i in range(WEEK_HOURS))
    if any(c.open_time_ms != t or c.interval != "1h"
           or c.symbol != "BTCUSDT" or c.quote_currency != "USDT"
           for c, t in zip(reference.candles, expected)):
        raise DataValidationError("reference window or contract shifted")
    observed = tuple(h.open_time_ms for h in trade_week.hours)
    missing = trade_week.missing_hour_open_ms
    all_open = sorted(observed + missing)
    if (len(all_open) != WEEK_HOURS or tuple(all_open) != expected
            or len(set(observed)) != len(observed)
            or len(set(missing)) != len(missing)
            or tuple(sorted(observed)) != observed
            or tuple(sorted(missing)) != missing):
        raise DataValidationError("trade hour calendar is not exact UTC partition")
    by_open = {h.open_time_ms: h for h in trade_week.hours}
    counters = {
        "open_compared": 0, "open_divergent": 0,
        "high_compared": 0, "high_divergent": 0,
        "low_compared": 0, "low_divergent": 0,
        "close_compared": 0, "close_divergent": 0,
    }
    fully_equal = fully_divergent = ambiguous = 0
    for ref in reference.candles:
        item = by_open.get(ref.open_time_ms)
        if item is None:
            continue
        if (item.open_boundary_ambiguous != (item.open_price is None)
                or item.close_boundary_ambiguous != (item.close_price is None)
                or item.trade_count <= 0 or item.high_price < item.low_price):
            raise DataValidationError("inconsistent trade-derived boundary provenance")
        is_ambiguous = item.open_boundary_ambiguous or item.close_boundary_ambiguous
        if is_ambiguous:
            ambiguous += 1
        fields = [
            ("high", item.high_price, ref.high, True),
            ("low", item.low_price, ref.low, True),
            ("open", item.open_price, ref.open, not item.open_boundary_ambiguous),
            ("close", item.close_price, ref.close, not item.close_boundary_ambiguous),
        ]
        equal = True
        for label, actual, expected_price, comparable in fields:
            if not comparable:
                continue
            counters[label + "_compared"] += 1
            if actual != expected_price:
                counters[label + "_divergent"] += 1
                equal = False
        if not is_ambiguous:
            fully_equal += int(equal)
            fully_divergent += int(not equal)
    if fully_equal + fully_divergent + ambiguous != len(trade_week.hours):
        raise DataValidationError("unreconciled trade-derived research hours")
    return BybitHourlyReconciliation(
        reference_hours=WEEK_HOURS,
        hours_without_trades_observed=len(missing),
        hours_with_trades_observed=len(trade_week.hours),
        ambiguous_boundary_hours=ambiguous,
        fully_comparable_ohlc_hours=fully_equal + fully_divergent,
        fully_equal_ohlc_hours=fully_equal,
        divergent_ohlc_hours=fully_divergent,
        **counters,
    )
