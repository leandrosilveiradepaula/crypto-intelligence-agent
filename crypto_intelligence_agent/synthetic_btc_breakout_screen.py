"""J2/PRE4: pure synthetic multi-asset breakout + BTC-context triage.

This is a research-only ranking of same-UTC *last-closed* synthetic fixtures.
It does not issue signals or orders, authenticate a venue, or validate returns.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_btc_relative_regime import (
    BtcRelativeConfig, HypotheticalBtcRegime,
    SyntheticBtcRelativeObservation, research_synthetic_btc_relative_regime,
)
from .synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, SyntheticEntryCandidate,
    research_synthetic_compression_breakouts,
)
from .synthetic_feature_engine import _numeric
from .synthetic_position_state import SyntheticSide

MAX_RESEARCH_ASSETS = 1_000


class ScreenDisposition(str, Enum):
    RANKED_HYPOTHESIS = "ranked_hypothesis"
    NO_CURRENT_BREAKOUT = "no_current_breakout"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    BTC_VOLATILITY_STRESS = "btc_volatility_stress"
    BTC_SIDEWAYS = "btc_sideways"
    AGAINST_BTC_REGIME = "against_btc_regime"
    WEAK_RELATIVE_STRENGTH = "weak_relative_strength"


@dataclass(frozen=True)
class SyntheticScreenConfig:
    breakout: CompressionBreakoutConfig
    context: BtcRelativeConfig
    min_absolute_relative_strength: Decimal

    def __post_init__(self) -> None:
        if type(self.breakout) is not CompressionBreakoutConfig:
            raise DataValidationError("explicit breakout research configuration required")
        if type(self.context) is not BtcRelativeConfig:
            raise DataValidationError("explicit BTC context research configuration required")
        if self.breakout.features != self.context.features:
            raise DataValidationError("BTC and breakout feature definitions must agree")
        _numeric(self.min_absolute_relative_strength, "min_absolute_relative_strength",
                 strictly_positive=False)
        if self.min_absolute_relative_strength > Decimal(1):
            raise DataValidationError("relative strength research threshold must not exceed 1")


@dataclass(frozen=True)
class SyntheticScreenItem:
    symbol: str
    disposition: ScreenDisposition
    candidate: SyntheticEntryCandidate | None
    context: SyntheticBtcRelativeObservation
    rank: int | None

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False


@dataclass(frozen=True)
class SyntheticScreenResult:
    exchange: str
    interval: str
    last_closed_at_ms: int
    decision_at_ms: int
    items: tuple[SyntheticScreenItem, ...]
    ranked_symbols: tuple[str, ...]

    @property
    def quality(self) -> str:
        return "synthetic_fixture_hypothesis_only"

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def screen_synthetic_btc_breakouts(
    btc_candles: Sequence[ClosedCandle],
    asset_series: Sequence[Sequence[ClosedCandle]],
    *,
    config: SyntheticScreenConfig,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
) -> SyntheticScreenResult:
    """Rank eligible synthetic hypotheses; every other asset abstains explicitly.

    No truncation to a target count: protective 1000 input-series cap is NOT
    a target for position count or number of research results.
    """
    if type(config) is not SyntheticScreenConfig:
        raise DataValidationError("explicit synthetic screen configuration required")
    if type(asset_series) not in (list, tuple) or not 1 <= len(asset_series) <= MAX_RESEARCH_ASSETS:
        raise DataValidationError("expected bounded research asset series")
    if type(btc_candles) not in (list, tuple) or not btc_candles:
        raise DataValidationError("BTC candles must be a nonempty ordered sequence")

    seen: set[str] = set()
    entries: list[tuple[str, ScreenDisposition, SyntheticEntryCandidate | None,
                        SyntheticBtcRelativeObservation]] = []
    last_close: int | None = None
    venue: str | None = None
    interval: str | None = None

    for candles in asset_series:
        if type(candles) not in (list, tuple) or not candles or type(candles[0]) is not ClosedCandle:
            raise DataValidationError("invalid asset series in synthetic batch")
        symbol = candles[0].symbol
        if symbol in seen:
            raise DataValidationError("duplicate asset in synthetic research batch")
        seen.add(symbol)
        # Run both existing validators BEFORE even considering a hypothesis.
        context = research_synthetic_btc_relative_regime(
            btc_candles, candles, config=config.context,
            decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
        )
        breakout = research_synthetic_compression_breakouts(
            candles, config=config.breakout,
            decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
        )
        if last_close is None:
            last_close = context.closed_at_ms
            venue = context.exchange
            interval = context.interval
        elif (last_close != context.closed_at_ms or venue != context.exchange
              or interval != context.interval):
            raise DataValidationError("research batch must share same UTC epoch/venue/interval")
        current = [x for x in breakout.candidates if x.closed_at_ms == context.closed_at_ms]
        if len(current) > 1:
            raise DataValidationError("ambiguous duplicate current-bar hypotheses")
        candidate = current[0] if current else None
        if candidate is None:
            disposition = ScreenDisposition.NO_CURRENT_BREAKOUT
        elif context.regime == HypotheticalBtcRegime.INSUFFICIENT_HISTORY:
            disposition = ScreenDisposition.INSUFFICIENT_CONTEXT
        elif context.regime == HypotheticalBtcRegime.VOLATILITY_STRESS:
            disposition = ScreenDisposition.BTC_VOLATILITY_STRESS
        elif context.regime == HypotheticalBtcRegime.SIDEWAYS:
            disposition = ScreenDisposition.BTC_SIDEWAYS
        elif ((candidate.side == SyntheticSide.LONG and context.regime != HypotheticalBtcRegime.UPTREND)
              or (candidate.side == SyntheticSide.SHORT and context.regime != HypotheticalBtcRegime.DOWNTREND)):
            disposition = ScreenDisposition.AGAINST_BTC_REGIME
        elif context.relative_strength is None:
            disposition = ScreenDisposition.INSUFFICIENT_CONTEXT
        elif ((candidate.side == SyntheticSide.LONG
               and context.relative_strength < config.min_absolute_relative_strength)
              or (candidate.side == SyntheticSide.SHORT
                  and context.relative_strength > -config.min_absolute_relative_strength)):
            disposition = ScreenDisposition.WEAK_RELATIVE_STRENGTH
        else:
            disposition = ScreenDisposition.RANKED_HYPOTHESIS
        entries.append((symbol, disposition, candidate, context))

    winners = [item for item in entries if item[1] == ScreenDisposition.RANKED_HYPOTHESIS]
    # For SHORT, larger rank-score means stronger underperformance.
    def key(item: tuple):
        symbol, _, candidate, context = item
        assert candidate is not None and context.relative_strength is not None
        strength = (context.relative_strength if candidate.side == SyntheticSide.LONG
                    else -context.relative_strength)
        return (-strength, -candidate.volume_to_prior_mean, symbol)
    winners.sort(key=key)
    rank_by_symbol = {item[0]: i + 1 for i, item in enumerate(winners)}
    items = tuple(
        SyntheticScreenItem(symbol=symbol, disposition=status,
                            candidate=candidate, context=context,
                            rank=rank_by_symbol.get(symbol))
        for symbol, status, candidate, context in sorted(entries, key=lambda x: x[0])
    )
    assert venue is not None and interval is not None and last_close is not None
    return SyntheticScreenResult(
        exchange=venue, interval=interval, last_closed_at_ms=last_close,
        decision_at_ms=decision_at_ms, items=items,
        ranked_symbols=tuple(item[0] for item in winners),
    )
