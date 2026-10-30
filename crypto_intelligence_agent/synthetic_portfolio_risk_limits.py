"""J3/PRE20: read-only global limits for synthetic portfolio research.

The gate neither orders nor reallocates collateral. All equity, prices, margin
and funding are synthetic. Unknown liquidation exposure blocks new research.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json

from .market_data import DataValidationError
from .synthetic_cost_scenarios import _amount
from .synthetic_portfolio_replay import (
    SyntheticPortfolioLeg, SyntheticPortfolioReplay, replay_synthetic_portfolio,
)

_CTX = Context(prec=512)
_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True)
class SyntheticPortfolioRiskLimits:
    max_allocated_margin_quote: Decimal
    max_margin_per_position_quote: Decimal
    max_entry_gross_notional_quote: Decimal
    max_open_gross_notional_quote: Decimal
    max_abs_open_net_notional_quote: Decimal
    max_open_notional_per_instrument_quote: Decimal
    max_open_concentration_fraction: Decimal
    max_known_prefix_drawdown_quote: Decimal
    max_leverage_at_entry: int

    def __post_init__(self) -> None:
        for name in (
            "max_allocated_margin_quote",
            "max_margin_per_position_quote",
            "max_entry_gross_notional_quote",
            "max_open_gross_notional_quote",
            "max_abs_open_net_notional_quote",
            "max_open_notional_per_instrument_quote",
            "max_known_prefix_drawdown_quote",
        ):
            _amount(getattr(self, name), name)
        ratio = self.max_open_concentration_fraction
        if (type(ratio) is not Decimal or not ratio.is_finite()
                or not _ZERO < ratio <= _ONE
                or len(ratio.as_tuple().digits) > 40
                or ratio.as_tuple().exponent < -18):
            raise DataValidationError("bounded exact concentration fraction in (0,1] required")
        if (type(self.max_leverage_at_entry) is not int
                or not 1 <= self.max_leverage_at_entry <= 200):
            raise DataValidationError("explicit leverage cap 1..200 required")


@dataclass(frozen=True)
class SyntheticPortfolioRiskCheckpoint:
    tick_number: int
    state: str
    violation_codes: tuple[str, ...]
    new_position_research_allowed: bool

    def sanitized_report(self) -> dict:
        return {
            "tick_number": self.tick_number,
            "state": self.state,
            "violation_codes": list(self.violation_codes),
            "new_position_research_allowed": self.new_position_research_allowed,
        }


@dataclass(frozen=True)
class SyntheticPortfolioRiskAudit:
    initial_violation_codes: tuple[str, ...]
    checkpoints: tuple[SyntheticPortfolioRiskCheckpoint, ...]
    aggregate_state: str
    new_position_research_allowed: bool
    digest_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "status": "synthetic_portfolio_risk_limits_only",
            "initial_violation_codes": list(self.initial_violation_codes),
            "checkpoints": [r.sanitized_report() for r in self.checkpoints],
            "aggregate_state": self.aggregate_state,
            "new_position_research_allowed": self.new_position_research_allowed,
            "digest_sha256": self.digest_sha256,
            "financial_backtest_approved": False,
            "net_pnl_verified": False,
            "liquidation_formula_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def audit_synthetic_portfolio_risk(
    legs: tuple[SyntheticPortfolioLeg, ...], *,
    limits: SyntheticPortfolioRiskLimits,
    as_of_ms: int,
    max_tick_gap_ms: int,
    max_risk_snapshot_age_ms: int | None = None,
) -> SyntheticPortfolioRiskAudit:
    if type(limits) is not SyntheticPortfolioRiskLimits:
        raise DataValidationError("explicit typed portfolio risk limits required")
    # Do not pre-empt replay validation; its clock/PIT/funding conditions are
    # mandatory even for an initially disallowed hypothetical portfolio.
    with localcontext(_CTX):
        portfolio = replay_synthetic_portfolio(
            legs, as_of_ms=as_of_ms, max_tick_gap_ms=max_tick_gap_ms,
            max_risk_snapshot_age_ms=max_risk_snapshot_age_ms)
        allocated = sum((leg.plan.margin.requested_margin_quote for leg in legs), _ZERO)
        entry_gross = sum((leg.plan.margin.entry_notional_quote for leg in legs), _ZERO)
        initial = set()
        if allocated > limits.max_allocated_margin_quote:
            initial.add("allocated_margin_exceeded")
        if any(leg.plan.margin.requested_margin_quote > limits.max_margin_per_position_quote
               for leg in legs):
            initial.add("margin_per_position_exceeded")
        if entry_gross > limits.max_entry_gross_notional_quote:
            initial.add("entry_gross_notional_exceeded")
        if any(leg.plan.margin.entry_notional_quote >
               limits.max_open_notional_per_instrument_quote for leg in legs):
            initial.add("entry_notional_per_instrument_exceeded")
        if any(leg.plan.margin.leverage_at_intent > limits.max_leverage_at_entry
               for leg in legs):
            initial.add("opening_leverage_exceeded")
        prior_violations = set(initial)
        unknown = False
        rows = []
        peak = allocated
        prefix_drawdown = _ZERO
        for checkpoint in portfolio.checkpoints:
            if checkpoint.unresolved_liquidation_count:
                unknown = True
            if not unknown:
                codes = set(prior_violations)
                gross = checkpoint.gross_open_notional_quote
                net = checkpoint.signed_open_notional_quote
                max_single = checkpoint.max_open_notional_quote
                concentration = checkpoint.max_open_concentration
                if gross is None or net is None or max_single is None:
                    raise DataValidationError("defined portfolio checkpoint lacks exposure")
                if gross > limits.max_open_gross_notional_quote:
                    codes.add("open_gross_notional_exceeded")
                if abs(net) > limits.max_abs_open_net_notional_quote:
                    codes.add("open_abs_net_notional_exceeded")
                if max_single > limits.max_open_notional_per_instrument_quote:
                    codes.add("open_notional_per_instrument_exceeded")
                if (concentration is not None and
                        concentration > limits.max_open_concentration_fraction):
                    codes.add("open_concentration_exceeded")
                equity = checkpoint.hypothetical_equity_quote
                if equity is None:
                    raise DataValidationError("known checkpoint requires defined equity")
                peak = max(peak, equity)
                prefix_drawdown = min(prefix_drawdown, equity-peak)
                if -prefix_drawdown > limits.max_known_prefix_drawdown_quote:
                    codes.add("known_prefix_drawdown_exceeded")
                state = "limits_exceeded" if codes else "within_limits"
                prior_violations = codes
            else:
                codes = set(prior_violations)
                codes.add("unresolved_liquidation")
                state = "unknown_due_to_liquidation"
                prior_violations = codes
            rows.append(SyntheticPortfolioRiskCheckpoint(
                checkpoint.tick_number, state, tuple(sorted(codes)),
                state == "within_limits"))
        if prefix_drawdown != portfolio.known_prefix_drawdown_quote:
            raise DataValidationError("portfolio prefix drawdown disagreement")
        final_state = ("unknown_due_to_liquidation" if unknown
                       else "limits_exceeded" if prior_violations else "within_limits")
        # Research eligibility is retrospective and advisory only. It cannot
        # authorize, prepare, or send an order in any trading environment.
        digest = sha256(json.dumps({
            "schema": "synthetic-portfolio-risk-v1",
            "portfolio": portfolio.digest_sha256,
            "limits": [str(getattr(limits, name)) for name in vars(limits)],
            "initial": sorted(initial),
            "states": [(r.tick_number,r.state,r.violation_codes) for r in rows],
        }, separators=(",", ":"), sort_keys=True).encode("ascii")).hexdigest()
        return SyntheticPortfolioRiskAudit(
            tuple(sorted(initial)), tuple(rows), final_state,
            final_state == "within_limits", digest)
