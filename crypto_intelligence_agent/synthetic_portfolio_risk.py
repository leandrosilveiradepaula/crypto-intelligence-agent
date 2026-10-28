"""J3/PRE17: synchronized isolated-bucket PAPER research risk, never PnL.

All input paths are explicit synthetic marks/trades. No cross margin,
portfolio liquidation formula, netting or inferred market correlations.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import re

from .market_data import DataValidationError
from .synthetic_cost_scenarios import SyntheticFundingEvent
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_mark_replay import (
    SyntheticMarkReplayPlan, SyntheticMarkReplayResult, SyntheticMarkTick,
    SyntheticReplayState, replay_synthetic_mark_path,
)

_CTX = Context(prec=512, rounding=ROUND_HALF_EVEN)
_ID = re.compile(r"fixture_[A-Za-z0-9_-]{1,56}")
_SYMBOL = re.compile(r"[A-Z0-9]{4,25}")
MAX_POSITIONS = 16


@dataclass(frozen=True)
class SyntheticPortfolioTrack:
    position_id: str
    symbol: str
    plan: SyntheticMarkReplayPlan
    ticks: tuple[SyntheticMarkTick, ...]
    funding_events: tuple[SyntheticFundingEvent, ...] = ()

    def __post_init__(self) -> None:
        if (type(self.position_id) is not str
                or _ID.fullmatch(self.position_id) is None
                or type(self.symbol) is not str or _SYMBOL.fullmatch(self.symbol) is None
                or type(self.plan) is not SyntheticMarkReplayPlan
                or type(self.ticks) is not tuple
                or type(self.funding_events) is not tuple):
            raise DataValidationError("typed fixture track identity and input required")


@dataclass(frozen=True)
class SyntheticPortfolioSnapshot:
    at_ms: int
    gross_entry_notional_quote: Decimal
    signed_mark_notional_quote: Decimal
    gross_mark_notional_quote: Decimal
    requested_margin_quote: Decimal
    sum_isolated_mark_equity_quote: Decimal
    sum_isolated_maintenance_quote: Decimal
    insolvent_bucket_ids: tuple[str, ...]
    simultaneous_terminal_ids: tuple[str, ...]
    adverse_mark_bucket_ids: tuple[str, ...]
    affected_symbols: tuple[str, ...]


@dataclass(frozen=True)
class SyntheticPortfolioRiskReport:
    snapshots: tuple[SyntheticPortfolioSnapshot, ...]
    first_terminal_at_ms: int | None
    first_terminal_states: tuple[tuple[str, SyntheticReplayState], ...]
    first_terminal_includes_liquidation_condition: bool
    max_symbol_entry_concentration_fraction: Decimal
    position_count: int
    symbol_count: int

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def net_pnl_verified(self) -> bool:
        return False

    @property
    def portfolio_liquidation_verified(self) -> bool:
        return False

    @property
    def correlation_estimated(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False


def replay_synthetic_portfolio_risk(
    tracks: tuple[SyntheticPortfolioTrack, ...], *, as_of_ms: int,
) -> SyntheticPortfolioRiskReport:
    """Describe synchronized positions up to first terminal tick only.

    An isolated bucket's maintenance failure cannot be offset by another
    bucket's positive equity. Track order does not affect output.
    """
    if (type(tracks) is not tuple or not 2 <= len(tracks) <= MAX_POSITIONS
            or any(type(t) is not SyntheticPortfolioTrack for t in tracks)):
        raise DataValidationError("portfolio requires 2..16 typed fixture tracks")
    ordered = tuple(sorted(tracks, key=lambda t: t.position_id))
    if len({t.position_id for t in ordered}) != len(ordered):
        raise DataValidationError("duplicate position identity")
    initial = ordered[0]
    clock = tuple(t.at_ms for t in initial.ticks)
    if not clock:
        raise DataValidationError("portfolio requires explicit ticks")
    for track in ordered:
        if (track.plan.entry_at_ms != initial.plan.entry_at_ms
                or track.plan.margin.quote_currency != initial.plan.margin.quote_currency
                or tuple(t.at_ms for t in track.ticks) != clock):
            raise DataValidationError("all portfolio tracks need same entry time, quote and tick clock")

    results: tuple[SyntheticMarkReplayResult, ...] = tuple(
        replay_synthetic_mark_path(
            track.plan, track.ticks, track.funding_events, as_of_ms=as_of_ms,
        ) for track in ordered
    )
    terminals = [result.first_trigger_at_ms for result in results
                 if result.first_trigger_at_ms is not None]
    first_terminal = min(terminals) if terminals else None
    horizon = clock.index(first_terminal) + 1 if first_terminal is not None else len(clock)
    with localcontext(_CTX):
        gross_entry = sum((t.plan.margin.entry_notional_quote for t in ordered), Decimal(0))
        margin_total = sum((t.plan.margin.requested_margin_quote for t in ordered), Decimal(0))
        by_symbol: dict[str, Decimal] = {}
        for track in ordered:
            by_symbol[track.symbol] = by_symbol.get(track.symbol, Decimal(0)) + track.plan.margin.entry_notional_quote
        max_concentration = max(by_symbol.values()) / gross_entry
        snapshots = []
        prev_marks: dict[str, Decimal] = {}
        for i in range(horizon):
            items = [(track, result.observations[i]) for track, result in zip(ordered, results)]
            gross_mark = Decimal(0)
            signed_mark = Decimal(0)
            equity = Decimal(0)
            maintenance = Decimal(0)
            insolvent = []
            terminal_ids = []
            adverse = []
            affected = set()
            for track, obs in items:
                p = track.plan
                notion = obs.mark_price * p.quantity_base
                sign = Decimal(1) if p.direction is ResearchDirection.LONG else Decimal(-1)
                gross_mark += notion
                signed_mark += sign * notion
                equity += obs.equity_at_mark_quote
                maintenance += obs.maintenance_requirement_quote
                if obs.state is SyntheticReplayState.LIQUIDATION_CONDITION:
                    insolvent.append(track.position_id)
                if obs.state is not SyntheticReplayState.OPEN_UNRESOLVED:
                    terminal_ids.append(track.position_id)
                last = prev_marks.get(track.position_id)
                if last is not None and sign * (obs.mark_price - last) < 0:
                    adverse.append(track.position_id)
                    affected.add(track.symbol)
                prev_marks[track.position_id] = obs.mark_price
            snapshots.append(SyntheticPortfolioSnapshot(
                at_ms=clock[i], gross_entry_notional_quote=gross_entry,
                signed_mark_notional_quote=signed_mark,
                gross_mark_notional_quote=gross_mark,
                requested_margin_quote=margin_total,
                sum_isolated_mark_equity_quote=equity,
                sum_isolated_maintenance_quote=maintenance,
                insolvent_bucket_ids=tuple(insolvent),
                simultaneous_terminal_ids=tuple(terminal_ids),
                adverse_mark_bucket_ids=tuple(adverse),
                affected_symbols=tuple(sorted(affected)),
            ))
    terminal_states = tuple(
        (t.position_id, result.state)
        for t, result in zip(ordered, results)
        if first_terminal is not None and result.first_trigger_at_ms == first_terminal
    )
    return SyntheticPortfolioRiskReport(
        tuple(snapshots), first_terminal, terminal_states,
        any(state is SyntheticReplayState.LIQUIDATION_CONDITION
            for _, state in terminal_states),
        max_concentration, len(ordered), len(by_symbol),
    )
