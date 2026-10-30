"""J3/ROBUST1: bounded offline OOS stress sensitivity; never executable PnL.

These alternate assumptions are NOT observed funding settlements, venue mark
prices, a statistical confidence interval, or a liquidation-price equation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json

from .market_data import DataValidationError
from .synthetic_cost_scenarios import _rate
from .vision_intrabar_stress import VisionStressAssumptions
from .vision_stress_oos import VisionStressOOS, audit_costed_vision_intrabar_oos

_CTX = Context(prec=512)
_ZERO = Decimal(0)


@dataclass(frozen=True)
class VisionRiskShocks:
    extra_entry_fee_bps: Decimal
    extra_exit_fee_bps: Decimal
    extra_entry_slippage_bps: Decimal
    extra_exit_slippage_bps: Decimal
    extra_maintenance_bps: Decimal
    funding_shock_bps: Decimal

    def __post_init__(self) -> None:
        for name in vars(self):
            _rate(getattr(self, name), name, signed=False)
        # Requiring a meaningful adverse scenario avoids a misleading
        # duplicate baseline dressed up as a distinct stress test.
        if not any(getattr(self, name) > _ZERO for name in vars(self)):
            raise DataValidationError("at least one explicit sensitivity shock required")


@dataclass(frozen=True)
class VisionRiskSensitivity:
    baseline: VisionStressOOS
    adverse_costs: VisionStressOOS
    funding_plus: VisionStressOOS
    funding_minus: VisionStressOOS
    digest_sha256: str

    def sanitized_report(self) -> dict:
        reports = (
            ("baseline", self.baseline),
            ("adverse_costs", self.adverse_costs),
            ("funding_plus", self.funding_plus),
            ("funding_minus", self.funding_minus),
        )
        return {
            "status": "offline_conditional_oos_sensitivity_only",
            "scenarios": {
                name: {
                    "strategy_exposures": audit.stressed_count,
                    "benchmark_exposures": sum(f.benchmark_exposures for f in audit.fold_reports),
                    "liquidation_possible_count": audit.liquidation_possible_count,
                    "benchmark_liquidation_possible_count": audit.benchmark_liquidation_possible_count,
                    "worst_net_quote": str(audit.worst_net_quote),
                    "best_net_quote": str(audit.best_net_quote),
                    "worst_drawdown_proxy_quote": str(audit.worst_drawdown_proxy_quote),
                    "best_drawdown_proxy_quote": str(audit.best_drawdown_proxy_quote),
                    "benchmark_worst_net_quote": str(audit.benchmark_worst_net_quote),
                    "benchmark_best_net_quote": str(audit.benchmark_best_net_quote),
                    "strategy_max_single_bar_loss_over_margin":
                        str(audit.strategy_max_single_bar_loss_over_margin),
                    "benchmark_max_single_bar_loss_over_margin":
                        str(audit.benchmark_max_single_bar_loss_over_margin),
                    "digest_sha256": audit.digest_sha256,
                } for name, audit in reports
            },
            "worst_conditional_strategy_quote": str(min(
                r.worst_net_quote for _, r in reports)),
            "research_digest_sha256": self.digest_sha256,
            "marketwide_top50_verified": False,
            "source_authenticated": False,
            "financial_backtest_approved": False,
            "funding_schedule_verified": False,
            "liquidation_formula_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def audit_vision_risk_sensitivity(
    month_groups: tuple[tuple, ...], *, as_of_ms: int,
    cost_bps_per_side: Decimal, assumptions: VisionStressAssumptions,
    shocks: VisionRiskShocks,
) -> VisionRiskSensitivity:
    if type(assumptions) is not VisionStressAssumptions or type(shocks) is not VisionRiskShocks:
        raise DataValidationError("typed explicit OOS stress terms and shocks required")
    if assumptions.margin.quote_currency != "SYNTHETIC_USDT":
        raise DataValidationError("USDT synthetic research assumptions only")
    with localcontext(_CTX):
        additions = {
            "entry_fee_bps": shocks.extra_entry_fee_bps,
            "exit_fee_bps": shocks.extra_exit_fee_bps,
            "entry_slippage_bps": shocks.extra_entry_slippage_bps,
            "exit_slippage_bps": shocks.extra_exit_slippage_bps,
            "maintenance_bps": shocks.extra_maintenance_bps,
        }
        stressed_terms = {}
        for name, increment in additions.items():
            x = getattr(assumptions, name) + increment
            _rate(x, name, signed=False)
            stressed_terms[name] = x
        adverse_assumptions = replace(assumptions, **stressed_terms)
        paid_rate = adverse_assumptions.signed_funding_bps + shocks.funding_shock_bps
        received_rate = adverse_assumptions.signed_funding_bps - shocks.funding_shock_bps
        _rate(paid_rate, "funding_plus", signed=True)
        _rate(received_rate, "funding_minus", signed=True)
        terms = (
            assumptions,
            adverse_assumptions,
            replace(adverse_assumptions, signed_funding_bps=paid_rate),
            replace(adverse_assumptions, signed_funding_bps=received_rate),
        )
        results = tuple(
            audit_costed_vision_intrabar_oos(
                month_groups, as_of_ms=as_of_ms,
                cost_bps_per_side=cost_bps_per_side, assumptions=term)
            for term in terms)
        base, adverse = results[:2]
        # Only cost/maintenance shocks with unchanged funding have a
        # directional risk claim. Funding +/- can help one side and hurt
        # the other, so NEVER impose monotonicity on those comparisons.
        if (base.stressed_count != adverse.stressed_count
                or len(base.fold_reports) != len(adverse.fold_reports)
                or sum(f.benchmark_exposures for f in base.fold_reports)
                   != sum(f.benchmark_exposures for f in adverse.fold_reports)
                or adverse.worst_net_quote > base.worst_net_quote
                or adverse.best_net_quote > base.best_net_quote
                or adverse.benchmark_worst_net_quote > base.benchmark_worst_net_quote
                or adverse.benchmark_best_net_quote > base.benchmark_best_net_quote):
            raise DataValidationError("adverse assumptions improved or changed OOS exposure")
        if any(
            (r.stressed_count != base.stressed_count
             or len(r.fold_reports) != len(base.fold_reports)
             or any(a.bars_scored != b.bars_scored
                    or a.strategy_exposures != b.strategy_exposures
                    for a, b in zip(r.fold_reports, base.fold_reports)))
            for r in results[1:]
        ):
            raise DataValidationError("sensitivity scenarios changed frozen OOS selection")
        digest = sha256(json.dumps({
            "schema": "vision-risk-sensitivity-v1",
            "baseline_parameters": [
                str(getattr(assumptions, key)) for key in (
                    "maintenance_bps", "entry_fee_bps", "exit_fee_bps",
                    "entry_slippage_bps", "exit_slippage_bps", "signed_funding_bps")
            ],
            "shocks": [str(getattr(shocks, name)) for name in vars(shocks)],
            "evaluations": [r.digest_sha256 for r in results],
        }, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
        return VisionRiskSensitivity(*results, digest)
