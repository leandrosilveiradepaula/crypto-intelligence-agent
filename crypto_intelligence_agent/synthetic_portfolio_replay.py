"""J3/PRE19: offline, no-fill synthetic portfolio reconciliation.

No data access, exchange schedule inference, execution, or real profitability.
An unresolved liquidation makes the aggregate equity unknowable, not zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import re

from .market_data import DataValidationError
from .synthetic_cost_scenarios import SyntheticFundingEvent
from .synthetic_funding_calendar import SyntheticFundingCalendar
from .synthetic_mark_replay import (
    SyntheticMarkReplayPlan, SyntheticMarkTick, SyntheticReplayState,
    replay_synthetic_mark_path,
)
from .synthetic_risk_tiers import SyntheticRiskSnapshot
from .synthetic_intrabar_barriers import ResearchDirection

_CTX = Context(prec=512)
_ID = re.compile(r"fixture_[A-Za-z0-9_-]{1,48}\Z")
_ZERO = Decimal(0)
_MAX_LEGS = 16


@dataclass(frozen=True)
class SyntheticPortfolioLeg:
    position_id: str
    plan: SyntheticMarkReplayPlan
    ticks: tuple[SyntheticMarkTick, ...]
    funding_events: tuple[SyntheticFundingEvent, ...] = ()
    funding_calendar: SyntheticFundingCalendar | None = None
    risk_snapshots: tuple[SyntheticRiskSnapshot, ...] | None = None

    def __post_init__(self) -> None:
        if (type(self.position_id) is not str or _ID.fullmatch(self.position_id) is None
                or type(self.plan) is not SyntheticMarkReplayPlan
                or type(self.ticks) is not tuple or not self.ticks
                or any(type(t) is not SyntheticMarkTick for t in self.ticks)
                or type(self.funding_events) is not tuple
                or any(type(x) is not SyntheticFundingEvent for x in self.funding_events)
                or (self.funding_calendar is not None
                    and type(self.funding_calendar) is not SyntheticFundingCalendar)
                or (self.risk_snapshots is not None
                    and (type(self.risk_snapshots) is not tuple or
                         any(type(x) is not SyntheticRiskSnapshot for x in self.risk_snapshots)))):
            raise DataValidationError("typed synthetic portfolio fixture leg required")
        if self.plan.margin.quote_currency != "SYNTHETIC_USDT":
            raise DataValidationError("synthetic USDT only; no currency conversion")


@dataclass(frozen=True)
class SyntheticPortfolioCheckpoint:
    tick_number: int
    hypothetical_equity_quote: Decimal | None
    conditional_net_from_entry_quote: Decimal | None
    gross_open_notional_quote: Decimal | None
    signed_open_notional_quote: Decimal | None
    max_open_concentration: Decimal | None
    max_open_notional_quote: Decimal | None
    signed_funding_paid_quote: Decimal
    open_count: int
    closed_conditional_count: int
    unresolved_liquidation_count: int

    def sanitized_report(self) -> dict:
        return {k: str(v) if type(v) is Decimal else v
                for k, v in vars(self).items()}


@dataclass(frozen=True)
class SyntheticPortfolioReplay:
    checkpoints: tuple[SyntheticPortfolioCheckpoint, ...]
    known_prefix_drawdown_quote: Decimal
    complete_equity_path: bool
    pairwise_mark_return_correlation_min: Decimal | None
    pairwise_mark_return_correlation_max: Decimal | None
    digest_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "status": "synthetic_portfolio_conditional_only",
            "checkpoint_count": len(self.checkpoints),
            "leg_count": (self.checkpoints[0].open_count +
                          self.checkpoints[0].closed_conditional_count +
                          self.checkpoints[0].unresolved_liquidation_count),
            "checkpoints": [c.sanitized_report() for c in self.checkpoints],
            "known_prefix_drawdown_quote": str(self.known_prefix_drawdown_quote),
            "complete_equity_path": self.complete_equity_path,
            "pairwise_mark_return_correlation_min": (
                str(self.pairwise_mark_return_correlation_min)
                if self.pairwise_mark_return_correlation_min is not None else None),
            "pairwise_mark_return_correlation_max": (
                str(self.pairwise_mark_return_correlation_max)
                if self.pairwise_mark_return_correlation_max is not None else None),
            "digest_sha256": self.digest_sha256,
            "financial_backtest_approved": False,
            "net_pnl_verified": False,
            "liquidation_formula_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def _corr(x: tuple[Decimal, ...], y: tuple[Decimal, ...]) -> Decimal | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    n = Decimal(len(x))
    xm, ym = sum(x, _ZERO) / n, sum(y, _ZERO) / n
    dx = tuple(a-xm for a in x)
    dy = tuple(b-ym for b in y)
    sx = sum((a*a for a in dx), _ZERO)
    sy = sum((b*b for b in dy), _ZERO)
    if sx == 0 or sy == 0:
        return None
    result = sum((a*b for a,b in zip(dx,dy)), _ZERO) / (sx*sy).sqrt()
    return max(Decimal(-1), min(Decimal(1), result))


def replay_synthetic_portfolio(
    legs: tuple[SyntheticPortfolioLeg, ...], *,
    as_of_ms: int,
    max_tick_gap_ms: int,
    max_risk_snapshot_age_ms: int | None = None,
) -> SyntheticPortfolioReplay:
    if (type(legs) is not tuple or not 1 <= len(legs) <= _MAX_LEGS
            or any(type(leg) is not SyntheticPortfolioLeg for leg in legs)):
        raise DataValidationError("1..16 immutable synthetic legs required")
    if (type(max_tick_gap_ms) is not int
            or not 1 <= max_tick_gap_ms <= 86_400_000):
        raise DataValidationError("explicit bounded mark observation gap required")
    first = legs[0]
    clock = tuple(t.at_ms for t in first.ticks)
    if (len(set(leg.position_id for leg in legs)) != len(legs)
            or len(set(leg.plan.instrument_id for leg in legs)) != len(legs)
            or any(leg.plan.entry_at_ms != first.plan.entry_at_ms
                   or tuple(t.at_ms for t in leg.ticks) != clock
                   for leg in legs)):
        raise DataValidationError("unique instruments and common UTC mark clock required")
    # Sorting removes accidental dependence on input order. Return no identities.
    sorted_legs = tuple(sorted(legs, key=lambda leg: leg.position_id))
    with localcontext(_CTX):
        results = tuple(replay_synthetic_mark_path(
            leg.plan, leg.ticks, leg.funding_events, as_of_ms=as_of_ms,
            risk_snapshots=leg.risk_snapshots,
            funding_calendar=leg.funding_calendar,
            max_tick_gap_ms=max_tick_gap_ms,
            max_risk_snapshot_age_ms=(max_risk_snapshot_age_ms
                if leg.risk_snapshots is not None else None))
            for leg in sorted_legs)
        # No pretense that collateral is reusable or netted across positions.
        initial_margin = sum((l.plan.margin.requested_margin_quote for l in sorted_legs), _ZERO)
        rows = []
        peak = initial_margin
        worst_drawdown = _ZERO
        known = True
        for k, at in enumerate(clock):
            equity = _ZERO
            gross = signed = _ZERO
            open_sizes = []
            funding = _ZERO
            open_n = closed_n = liquidated_n = 0
            for leg, result in zip(sorted_legs, results):
                end_index = len(result.observations)-1
                terminal = result.state is not SyntheticReplayState.OPEN_UNRESOLVED
                # A conditional close is carried unchanged after its trigger.
                if terminal and k > end_index:
                    state = result.state
                    observation = result.observations[-1]
                else:
                    observation = result.observations[k]
                    state = observation.state
                funding += observation.signed_funding_paid_quote
                if state is SyntheticReplayState.LIQUIDATION_CONDITION:
                    liquidated_n += 1
                    known = False
                    continue
                if state in (SyntheticReplayState.CONDITIONAL_TARGET,
                             SyntheticReplayState.CONDITIONAL_STOP):
                    closed_n += 1
                    if result.conditional_net_quote is None:
                        raise DataValidationError("closed fixture without conditional outcome")
                    equity += leg.plan.margin.requested_margin_quote + result.conditional_net_quote
                    continue
                if not known:
                    open_n += 1
                    continue
                open_n += 1
                equity += observation.equity_at_mark_quote
                mark_size = observation.mark_price * leg.plan.quantity_base
                gross += mark_size
                signed += (mark_size if leg.plan.direction is ResearchDirection.LONG
                           else -mark_size)
                open_sizes.append(mark_size)
            if known:
                peak = max(peak, equity)
                worst_drawdown = min(worst_drawdown, equity-peak)
                concentration = (max(open_sizes)/gross if gross > 0 else None)
                row = SyntheticPortfolioCheckpoint(
                    k+1, equity, equity-initial_margin, gross, signed,
                    concentration, max(open_sizes) if open_sizes else _ZERO,
                    funding, open_n, closed_n, liquidated_n)
            else:
                row = SyntheticPortfolioCheckpoint(
                    k+1, None, None, None, None, None, None,
                    funding, open_n, closed_n, liquidated_n)
            rows.append(row)
        # Correlations are descriptive, on overlapping OPEN prefixes only.
        pair_correlations = []
        series = []
        for leg, result in zip(sorted_legs, results):
            count = (len(result.observations) if
                     result.state is SyntheticReplayState.OPEN_UNRESOLVED
                     else max(0, len(result.observations)-1))
            marks = tuple(t.mark_price for t in leg.ticks[:count])
            series.append(tuple(marks[i]/marks[i-1]-1
                                for i in range(1,len(marks))))
        for i in range(len(series)):
            for j in range(i+1,len(series)):
                overlap = min(len(series[i]), len(series[j]))
                c = _corr(series[i][:overlap], series[j][:overlap])
                if c is not None:
                    pair_correlations.append(c)
        digest = sha256(json.dumps({
            "schema":"synthetic-portfolio-v1",
            "legs":[(leg.position_id,leg.plan.instrument_id,
                     str(leg.plan.margin.requested_margin_quote),
                     result.state.value,str(result.conditional_net_quote),
                     [(o.at_ms,str(o.mark_price),str(o.equity_at_mark_quote),
                       o.state.value) for o in result.observations])
                    for leg,result in zip(sorted_legs,results)],
            "rows":[r.sanitized_report() for r in rows],
        },sort_keys=True,separators=(",",":")).encode("ascii")).hexdigest()
        return SyntheticPortfolioReplay(
            tuple(rows),worst_drawdown,known,
            min(pair_correlations) if pair_correlations else None,
            max(pair_correlations) if pair_correlations else None,digest)
