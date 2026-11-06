"""J3/PRE28: causal, direction-adjusted correlation risk for synthetic portfolios.

No external market data, order path, storage, or trading authorization.
This opt-in research-only layer reuses PRE20 risk and PRE19 mark replays.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json

from .market_data import DataValidationError
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_mark_replay import SyntheticReplayState, replay_synthetic_mark_path
from .synthetic_portfolio_replay import SyntheticPortfolioLeg
from .synthetic_portfolio_risk_limits import (
    SyntheticPortfolioRiskLimits, audit_synthetic_portfolio_risk,
)

_CTX = Context(prec=512)
_ZERO = Decimal(0)
_ONE = Decimal(1)
MAX_CORRELATION_TICKS = 256


@dataclass(frozen=True)
class SyntheticCorrelationGate:
    """Explicit research guard; no default is silently enabled."""
    max_positive_signed_return_correlation: Decimal
    minimum_return_samples: int

    def __post_init__(self) -> None:
        value = self.max_positive_signed_return_correlation
        if (type(value) is not Decimal or not value.is_finite()
                or not _ZERO <= value <= _ONE
                or len(value.as_tuple().digits) > 40
                or value.as_tuple().exponent < -18
                or type(self.minimum_return_samples) is not int
                or not 3 <= self.minimum_return_samples <= 128):
            raise DataValidationError("bounded causal correlation gate required")


@dataclass(frozen=True)
class SyntheticCorrelationCheckpoint:
    tick_number: int
    state: str
    evaluated_pairs: int
    unmeasurable_pairs: int
    max_signed_pair_correlation: Decimal | None
    new_position_research_allowed: bool

    def sanitized_report(self) -> dict:
        return {
            "tick_number": self.tick_number,
            "state": self.state,
            "evaluated_pairs": self.evaluated_pairs,
            "unmeasurable_pairs": self.unmeasurable_pairs,
            "max_signed_pair_correlation": (
                str(self.max_signed_pair_correlation)
                if self.max_signed_pair_correlation is not None else None
            ),
            "new_position_research_allowed": self.new_position_research_allowed,
        }


@dataclass(frozen=True)
class SyntheticCorrelationAudit:
    checkpoints: tuple[SyntheticCorrelationCheckpoint, ...]
    aggregate_state: str
    new_position_research_allowed: bool
    digest_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "status": "synthetic_causal_correlation_risk_only",
            "checkpoints": [c.sanitized_report() for c in self.checkpoints],
            "aggregate_state": self.aggregate_state,
            "new_position_research_allowed": self.new_position_research_allowed,
            "digest_sha256": self.digest_sha256,
            "correlation_predicts_liquidation": False,
            "financial_backtest_approved": False,
            "net_pnl_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def audit_synthetic_causal_correlation(
    legs: tuple[SyntheticPortfolioLeg, ...], *,
    risk_limits: SyntheticPortfolioRiskLimits,
    correlation_gate: SyntheticCorrelationGate,
    as_of_ms: int,
    max_tick_gap_ms: int,
    max_risk_snapshot_age_ms: int | None = None,
) -> SyntheticCorrelationAudit:
    """Bounded past-only Pearson on open legs' direction-signed mark returns.

    A pair is counted only while both legs remain hypothetically OPEN.
    Insufficient paired returns or constant prices are not evidence of safety.
    Breaches and unknown-liquidation status never reset in this replay.
    """
    if type(correlation_gate) is not SyntheticCorrelationGate:
        raise DataValidationError("explicit synthetic correlation policy required")
    if (type(legs) is not tuple or not 1 <= len(legs) <= 16
            or any(type(x) is not SyntheticPortfolioLeg for x in legs)
            or not 1 <= len(legs[0].ticks) <= MAX_CORRELATION_TICKS):
        raise DataValidationError("bounded typed correlation portfolio required")
    with localcontext(_CTX):
        base = audit_synthetic_portfolio_risk(
            legs, limits=risk_limits, as_of_ms=as_of_ms,
            max_tick_gap_ms=max_tick_gap_ms,
            max_risk_snapshot_age_ms=max_risk_snapshot_age_ms,
        )
        ordered = tuple(sorted(legs, key=lambda leg: leg.position_id))
        replays = tuple(replay_synthetic_mark_path(
            leg.plan, leg.ticks, leg.funding_events, as_of_ms=as_of_ms,
            risk_snapshots=leg.risk_snapshots,
            funding_calendar=leg.funding_calendar,
            max_tick_gap_ms=max_tick_gap_ms,
            max_risk_snapshot_age_ms=(max_risk_snapshot_age_ms
                if leg.risk_snapshots is not None else None),
        ) for leg in ordered)
        n = len(legs)
        # O(pairs) streaming state, never full-future correlation at a prefix.
        # Each entry is [sample count, sum(x), sum(y), sum(x*x), sum(y*y), sum(x*y)].
        stats = {(i, j): [0, _ZERO, _ZERO, _ZERO, _ZERO, _ZERO]
                 for i in range(n) for j in range(i+1, n)}
        prior_breach = False
        unknown_liquidation = False
        checkpoints: list[SyntheticCorrelationCheckpoint] = []
        for tick_index, risk_row in enumerate(base.checkpoints):
            active = tuple(
                tick_index < len(replay.observations)
                and replay.observations[tick_index].state is SyntheticReplayState.OPEN_UNRESOLVED
                for replay in replays
            )
            active_pairs = [(i, j) for i in range(n) for j in range(i+1, n)
                            if active[i] and active[j]]
            max_corr = None
            valid_pairs = unmeasurable = 0
            for i, j in active_pairs:
                accumulator = stats[(i, j)]
                if tick_index > 0 and all(
                    tick_index-1 < len(replays[k].observations)
                    and replays[k].observations[tick_index-1].state is
                        SyntheticReplayState.OPEN_UNRESOLVED
                    for k in (i, j)
                ):
                    left, right = ordered[i], ordered[j]
                    x = (left.ticks[tick_index].mark_price /
                         left.ticks[tick_index-1].mark_price - _ONE)
                    y = (right.ticks[tick_index].mark_price /
                         right.ticks[tick_index-1].mark_price - _ONE)
                    if left.plan.direction is ResearchDirection.SHORT:
                        x = -x
                    if right.plan.direction is ResearchDirection.SHORT:
                        y = -y
                    accumulator[0] += 1
                    accumulator[1] += x
                    accumulator[2] += y
                    accumulator[3] += x*x
                    accumulator[4] += y*y
                    accumulator[5] += x*y
                count, sx, sy, sxx, syy, sxy = accumulator
                if count < correlation_gate.minimum_return_samples:
                    unmeasurable += 1
                    continue
                q = Decimal(count)
                vx, vy = q*sxx - sx*sx, q*syy - sy*sy
                if vx <= 0 or vy <= 0:
                    unmeasurable += 1
                    continue
                rho = (q*sxy-sx*sy) / (vx*vy).sqrt()
                rho = max(-_ONE, min(_ONE, rho))
                max_corr = rho if max_corr is None else max(max_corr, rho)
                valid_pairs += 1
                if rho > correlation_gate.max_positive_signed_return_correlation:
                    prior_breach = True

            if risk_row.state == "unknown_due_to_liquidation":
                unknown_liquidation = True
            if unknown_liquidation:
                state = "unknown_liquidation_abstain"
            elif risk_row.state != "within_limits":
                state = "existing_portfolio_risk_block"
            elif prior_breach:
                state = "positive_correlation_limit_exceeded"
            elif unmeasurable:
                state = "insufficient_or_flat_pair_history_abstain"
            elif not active_pairs:
                state = "no_open_pair"
            else:
                state = "within_correlation_limit"
            checkpoints.append(SyntheticCorrelationCheckpoint(
                tick_index+1, state, valid_pairs, unmeasurable, max_corr,
                state in ("no_open_pair", "within_correlation_limit"),
            ))
        terminal = checkpoints[-1]
        digest = sha256(json.dumps({
            "schema": "synthetic-causal-correlation-v1",
            "portfolio_risk": base.digest_sha256,
            "cap": str(correlation_gate.max_positive_signed_return_correlation),
            "minimum_samples": correlation_gate.minimum_return_samples,
            "rows": [x.sanitized_report() for x in checkpoints],
        }, separators=(",", ":"), sort_keys=True).encode("ascii")).hexdigest()
        return SyntheticCorrelationAudit(
            tuple(checkpoints), terminal.state,
            terminal.new_position_research_allowed, digest,
        )
