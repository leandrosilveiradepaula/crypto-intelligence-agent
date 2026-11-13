"""J2/CONFLUENCE1: causal fixture-only agreement between existing J2 hypotheses.

Composes BTC/relative-strength breakout screen (PRE4) and prior-trend
pullback-resumption research without reimplementing indicators. No score,
calibrated probability, venue eligibility, live signal, margin or orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_btc_breakout_screen import (
    MAX_RESEARCH_ASSETS, ScreenDisposition, SyntheticScreenConfig,
    SyntheticScreenItem, SyntheticScreenResult, screen_synthetic_btc_breakouts,
)
from .synthetic_btc_relative_regime import SyntheticBtcRelativeObservation
from .synthetic_entry_hypotheses import (
    STRATEGY_ID as BREAKOUT_STRATEGY_ID, SyntheticEntryCandidate,
)
from .synthetic_position_state import SyntheticSide
from .synthetic_trend_pullback import (
    STRATEGY_ID as PULLBACK_STRATEGY_ID, TrendPullbackCandidate,
    TrendPullbackConfig, TrendPullbackResearch,
    research_synthetic_trend_pullbacks,
)


class ConfluenceDisposition(str, Enum):
    CONFLUENT_RESEARCH_ONLY = "confluent_research_only"
    NO_PULLBACK_CONFIRMATION = "no_pullback_confirmation"
    BTC_OR_BREAKOUT_VETO = "btc_or_breakout_veto"
    DIRECTION_CONFLICT_ABSTAIN = "direction_conflict_abstain"


@dataclass(frozen=True)
class SyntheticConfluenceConfig:
    """Explicit compatibility gate, not a new parametrized entry strategy."""

    screen: SyntheticScreenConfig
    pullback: TrendPullbackConfig

    def __post_init__(self) -> None:
        if (type(self.screen) is not SyntheticScreenConfig
                or type(self.pullback) is not TrendPullbackConfig
                or self.screen.breakout.features != self.pullback.features):
            raise DataValidationError(
                "BTC, breakout and pullback must use identical causal feature definitions"
            )


@dataclass(frozen=True)
class SyntheticConfluenceItem:
    symbol: str
    disposition: ConfluenceDisposition
    btc_breakout_disposition: ScreenDisposition
    breakout_side: SyntheticSide | None
    pullback_side: SyntheticSide | None
    breakout_research_rank: int | None
    confluence_research_rank: int | None

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


@dataclass(frozen=True)
class SyntheticConfluenceResearch:
    exchange: str
    interval: str
    last_closed_at_ms: int
    decision_at_ms: int
    evaluated_asset_count: int
    items: tuple[SyntheticConfluenceItem, ...]
    confluence_symbols: tuple[str, ...]

    @property
    def quality(self) -> str:
        return "synthetic_multistrategy_confluence_research_only"

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    def sanitized_report(self) -> dict[str, object]:
        """Aggregate research counts only; no symbol, price, ID or order."""
        counts = {
            disposition.value: sum(
                item.disposition is disposition for item in self.items
            )
            for disposition in ConfluenceDisposition
        }
        return {
            "status": self.quality,
            "evaluated_asset_count": self.evaluated_asset_count,
            "confluence_count": len(self.confluence_symbols),
            "disposition_counts": counts,
            "last_closed_at_ms": self.last_closed_at_ms,
            "decision_at_ms": self.decision_at_ms,
            "probabilities_calibrated": False,
            "returns_backtested": False,
            "marketwide_top50_verified": False,
            "approved_for_signals": False,
            "approved_for_live_use": False,
            "order_capable": False,
            "orders_sent": False,
            "network_requests": 0,
        }


def _validated_screen(
    screen: SyntheticScreenResult,
) -> dict[str, SyntheticScreenItem]:
    if (type(screen) is not SyntheticScreenResult
            or type(screen.items) is not tuple
            or not 1 <= len(screen.items) <= MAX_RESEARCH_ASSETS
            or type(screen.ranked_symbols) is not tuple
            or type(screen.exchange) is not str or not screen.exchange
            or type(screen.interval) is not str or not screen.interval
            or type(screen.last_closed_at_ms) is not int
            or type(screen.decision_at_ms) is not int
            or not 0 < screen.last_closed_at_ms < screen.decision_at_ms):
        raise DataValidationError("typed bounded closed BTC breakout screen required")
    result: dict[str, SyntheticScreenItem] = {}
    for item in screen.items:
        if (type(item) is not SyntheticScreenItem
                or type(item.symbol) is not str or not item.symbol
                or item.symbol in result
                or type(item.disposition) is not ScreenDisposition
                or type(item.context) is not SyntheticBtcRelativeObservation):
            raise DataValidationError("unique validated BTC screen items required")
        ctx = item.context
        if (ctx.btc_symbol != "BTCUSDT"
                or ctx.asset_symbol != item.symbol
                or ctx.exchange != screen.exchange
                or ctx.interval != screen.interval
                or ctx.closed_at_ms != screen.last_closed_at_ms
                or ctx.decision_at_ms != screen.decision_at_ms
                or type(ctx.earliest_research_at_ms) is not int
                or not ctx.closed_at_ms < ctx.earliest_research_at_ms <= screen.decision_at_ms):
            raise DataValidationError("BTC-relative context must be current and causal")
        candidate = item.candidate
        if candidate is not None:
            if (type(candidate) is not SyntheticEntryCandidate
                    or candidate.strategy_id != BREAKOUT_STRATEGY_ID
                    or candidate.exchange != screen.exchange
                    or candidate.symbol != item.symbol
                    or candidate.interval != screen.interval
                    or type(candidate.side) is not SyntheticSide
                    or candidate.closed_at_ms != screen.last_closed_at_ms
                    or type(candidate.earliest_research_at_ms) is not int
                    or not candidate.closed_at_ms <
                        candidate.earliest_research_at_ms <= screen.decision_at_ms):
                raise DataValidationError("breakout must be current, typed and closed")
        is_ranked = item.disposition is ScreenDisposition.RANKED_HYPOTHESIS
        if ((candidate is None and is_ranked)
                or (item.disposition is ScreenDisposition.NO_CURRENT_BREAKOUT
                    and candidate is not None)
                or (is_ranked and (
                    type(item.rank) is not int or item.rank <= 0
                    or ctx.relative_strength is None))
                or (not is_ranked and item.rank is not None)):
            raise DataValidationError("BTC veto and breakout ranking contradict")
        result[item.symbol] = item
    ordered = tuple(
        item.symbol
        for item in sorted(
            (x for x in result.values() if x.rank is not None),
            key=lambda x: x.rank,
        )
    )
    ranks = sorted(x.rank for x in result.values() if x.rank is not None)
    if (ordered != screen.ranked_symbols
            or ranks != list(range(1, len(ranks) + 1))):
        raise DataValidationError("BTC screen ranks must be complete and deterministic")
    return result


def _current_pullback_by_symbol(
    trends: tuple[TrendPullbackResearch, ...],
    screen: SyntheticScreenResult,
    required_symbols: set[str],
) -> dict[str, TrendPullbackCandidate | None]:
    if (type(trends) is not tuple or len(trends) != len(required_symbols)
            or any(type(t) is not TrendPullbackResearch for t in trends)):
        raise DataValidationError("exactly one typed pullback research per asset required")
    found: dict[str, TrendPullbackCandidate | None] = {}
    for trend in trends:
        if (type(trend.symbol) is not str or trend.symbol not in required_symbols
                or trend.symbol in found
                or trend.strategy_id != PULLBACK_STRATEGY_ID
                or trend.exchange != screen.exchange
                or trend.interval != screen.interval
                or type(trend.evaluated_candle_count) is not int
                or not 1 <= trend.evaluated_candle_count <= 10_000
                or type(trend.candidates) is not tuple
                or len(trend.candidates) > trend.evaluated_candle_count):
            raise DataValidationError("pullback context mismatched or duplicated")
        previous = 0
        current: TrendPullbackCandidate | None = None
        for candidate in trend.candidates:
            if (type(candidate) is not TrendPullbackCandidate
                    or candidate.strategy_id != PULLBACK_STRATEGY_ID
                    or candidate.exchange != screen.exchange
                    or candidate.symbol != trend.symbol
                    or candidate.interval != screen.interval
                    or type(candidate.side) is not SyntheticSide
                    or type(candidate.trigger_closed_at_ms) is not int
                    or type(candidate.earliest_research_at_ms) is not int
                    or not previous < candidate.trigger_closed_at_ms <= screen.last_closed_at_ms
                    or not candidate.trigger_closed_at_ms <
                        candidate.earliest_research_at_ms <= screen.decision_at_ms):
                raise DataValidationError("pullback candle cannot be duplicate, stale or future")
            previous = candidate.trigger_closed_at_ms
            if candidate.trigger_closed_at_ms == screen.last_closed_at_ms:
                current = candidate
        found[trend.symbol] = current
    if set(found) != required_symbols:
        raise DataValidationError("missing or unexpected pullback research asset")
    return found


def arbitrate_synthetic_entry_confluence(
    screen: SyntheticScreenResult,
    trends: tuple[TrendPullbackResearch, ...],
) -> SyntheticConfluenceResearch:
    """Arbitrate only the *same last closed bar*; never promote stale votes."""
    items = _validated_screen(screen)
    pullbacks = _current_pullback_by_symbol(trends, screen, set(items))
    yes: set[str] = set()
    provisional: dict[str, tuple[ConfluenceDisposition, SyntheticSide | None]] = {}
    for symbol, breakout in items.items():
        trend = pullbacks[symbol]
        if breakout.disposition is not ScreenDisposition.RANKED_HYPOTHESIS:
            disposition = ConfluenceDisposition.BTC_OR_BREAKOUT_VETO
        elif trend is None:
            disposition = ConfluenceDisposition.NO_PULLBACK_CONFIRMATION
        elif trend.side is not breakout.candidate.side:
            disposition = ConfluenceDisposition.DIRECTION_CONFLICT_ABSTAIN
        else:
            disposition = ConfluenceDisposition.CONFLUENT_RESEARCH_ONLY
            yes.add(symbol)
        provisional[symbol] = (disposition, trend.side if trend else None)

    # Do not invent a second score: retain the already-computed BTC screen order.
    eligible = tuple(symbol for symbol in screen.ranked_symbols if symbol in yes)
    confluence_rank = {symbol: i + 1 for i, symbol in enumerate(eligible)}
    result_items = tuple(
        SyntheticConfluenceItem(
            symbol=symbol,
            disposition=provisional[symbol][0],
            btc_breakout_disposition=items[symbol].disposition,
            breakout_side=(items[symbol].candidate.side if items[symbol].candidate else None),
            pullback_side=provisional[symbol][1],
            breakout_research_rank=items[symbol].rank,
            confluence_research_rank=confluence_rank.get(symbol),
        )
        for symbol in sorted(items)
    )
    return SyntheticConfluenceResearch(
        exchange=screen.exchange, interval=screen.interval,
        last_closed_at_ms=screen.last_closed_at_ms,
        decision_at_ms=screen.decision_at_ms,
        evaluated_asset_count=len(result_items),
        items=result_items,
        confluence_symbols=eligible,
    )


def research_synthetic_entry_confluence(
    btc_candles: Sequence[ClosedCandle],
    asset_series: Sequence[Sequence[ClosedCandle]],
    *,
    config: SyntheticConfluenceConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
) -> SyntheticConfluenceResearch:
    """Compose existing causal engines, using precisely the same source bars.

    No 50-position target, market feed adapter, signal approval or risk sizing.
    The screen validators reject future, gapped, non-fixture and mixed data;
    every pullback uses that very same input/decision clock.
    """
    if type(config) is not SyntheticConfluenceConfig:
        raise DataValidationError("explicit compatible synthetic research config required")
    screen = screen_synthetic_btc_breakouts(
        btc_candles, asset_series, config=config.screen,
        decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
    )
    trends = tuple(
        research_synthetic_trend_pullbacks(
            bars, config=config.pullback, decision_at_ms=decision_at_ms,
            close_safety_ms=close_safety_ms,
        )
        for bars in asset_series
    )
    return arbitrate_synthetic_entry_confluence(screen, trends)
