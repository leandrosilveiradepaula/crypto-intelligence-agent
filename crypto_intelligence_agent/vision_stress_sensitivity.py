"""J3/PRE22: bounded, OOS-fixed hypothetical finance sensitivity.

This is a READ-ONLY research comparison of the *same* monthly OOS decisions,
not parameter tuning, exchange-risk approval, trade prediction or realized PnL.
Every scenario delegates all financial arithmetic to vision_stress_oos.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json

from .market_data import DataValidationError
from .vision_intrabar_stress import VisionStressAssumptions
from .vision_stress_oos import VisionStressOOS, audit_costed_vision_intrabar_oos


@dataclass(frozen=True)
class VisionSensitivityScenario:
    ordinal: int
    assumptions: VisionStressAssumptions
    audit: VisionStressOOS

    def sanitized_report(self) -> dict:
        margin = self.assumptions.margin
        a = self.audit
        return {
            "ordinal": self.ordinal,
            "leverage_at_intent": margin.leverage_at_intent,
            "hypothetical_margin_quote": str(margin.requested_margin_quote),
            "hypothetical_entry_notional_quote": str(margin.entry_notional_quote),
            "test_fold_count": len(a.fold_reports),
            "strategy_exposures": a.stressed_count,
            "strategy_abstentions": a.abstention_count,
            "strategy_liquidation_proxy_count": a.liquidation_possible_count,
            "strategy_ambiguous_count": a.ambiguous_count,
            "strategy_stop_touched_count": a.stop_touched_count,
            "strategy_target_touched_count": a.target_touched_count,
            "strategy_worst_conditional_net_quote": str(a.worst_net_quote),
            "strategy_best_conditional_net_quote": str(a.best_net_quote),
            "strategy_worst_cumulative_net_over_margin": str(
                a.strategy_worst_cumulative_net_over_margin),
            "strategy_best_cumulative_net_over_margin": str(
                a.strategy_best_cumulative_net_over_margin),
            "benchmark_exposures": sum(f.benchmark_exposures for f in a.fold_reports),
            "benchmark_liquidation_proxy_count": a.benchmark_liquidation_possible_count,
            "benchmark_ambiguous_count": a.benchmark_ambiguous_count,
            "benchmark_worst_conditional_net_quote": str(a.benchmark_worst_net_quote),
            "benchmark_best_conditional_net_quote": str(a.benchmark_best_net_quote),
            "benchmark_worst_cumulative_net_over_margin": str(
                a.benchmark_worst_cumulative_net_over_margin),
            "benchmark_best_cumulative_net_over_margin": str(
                a.benchmark_best_cumulative_net_over_margin),
            "folds": [
                {
                    "test_month_number": f.test_month_number,
                    "bars_scored": f.bars_scored,
                    "strategy_exposures": f.strategy_exposures,
                    "strategy_abstentions": f.strategy_abstention_count,
                    "strategy_liquidation_proxy_count": f.strategy_liquidation_possible_count,
                    "strategy_ambiguous_count": f.strategy_ambiguous_count,
                    "strategy_stop_touched_count": f.strategy_stop_touched_count,
                    "strategy_target_touched_count": f.strategy_target_touched_count,
                    "strategy_worst_conditional_net_quote": str(f.strategy_worst_net_quote),
                    "strategy_best_conditional_net_quote": str(f.strategy_best_net_quote),
                    "strategy_worst_cumulative_net_over_margin": str(
                        f.strategy_worst_cumulative_net_over_margin),
                    "strategy_best_cumulative_net_over_margin": str(
                        f.strategy_best_cumulative_net_over_margin),
                    "benchmark_exposures": f.benchmark_exposures,
                    "benchmark_liquidation_proxy_count": f.benchmark_liquidation_possible_count,
                    "benchmark_worst_conditional_net_quote": str(f.benchmark_worst_net_quote),
                    "benchmark_best_conditional_net_quote": str(f.benchmark_best_net_quote),
                }
                for f in a.fold_reports
            ],
            "research_digest_sha256": a.digest_sha256,
        }


@dataclass(frozen=True)
class VisionStressSensitivity:
    scenarios: tuple[VisionSensitivityScenario, ...]
    digest_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "j3_pre22_oos_sensitivity_v1",
            "status": "offline_hypothetical_oos_sensitivity_only",
            "scenario_count": len(self.scenarios),
            "selection_fixed_across_scenarios": True,
            "scenarios_with_liquidation_proxy": sum(
                s.audit.liquidation_possible_count > 0 for s in self.scenarios),
            "scenarios_with_adverse_conditional_net_negative": sum(
                s.audit.worst_net_quote < 0 for s in self.scenarios),
            "scenarios_with_zero_strategy_exposures": sum(
                s.audit.stressed_count == 0 for s in self.scenarios),
            "scenarios": [s.sanitized_report() for s in self.scenarios],
            "digest_sha256": self.digest_sha256,
            "marketwide_top50_verified": False,
            "source_authenticated": False,
            "financial_backtest_approved": False,
            "net_pnl_verified": False,
            "liquidation_formula_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def compare_costed_vision_oos_stress_scenarios(
    month_groups: tuple[tuple, ...], *,
    as_of_ms: int,
    cost_bps_per_side: Decimal,
    assumptions_grid: tuple[VisionStressAssumptions, ...],
) -> VisionStressSensitivity:
    """Evaluate 2..6 hypotheses with the SAME training and OOS decisions.

    Retains the input grid's order; ordinals are *not* recommendation ranks.
    Every per-bar/net/margin/liquidation calculation is delegated to PRE21.
    """
    if (type(assumptions_grid) is not tuple
            or not 2 <= len(assumptions_grid) <= 6
            or any(type(t) is not VisionStressAssumptions for t in assumptions_grid)
            or len(set(assumptions_grid)) != len(assumptions_grid)):
        raise DataValidationError("2..6 distinct typed OOS finance assumptions required")
    # Quote-valued conditional outcomes cannot be meaningfully compared
    # without an FX basis; do not silently mix SYNTHETIC_USDT / USDC / QUOTE.
    if len({case.margin.quote_currency for case in assumptions_grid}) != 1:
        raise DataValidationError("sensitivity scenarios require one synthetic quote currency")

    cases: list[VisionSensitivityScenario] = []
    reference: tuple | None = None
    for i, assumptions in enumerate(assumptions_grid, start=1):
        report = audit_costed_vision_intrabar_oos(
            month_groups, as_of_ms=as_of_ms,
            cost_bps_per_side=cost_bps_per_side,
            assumptions=assumptions,
        )
        # Count comparisons do not depend on ex-post price moves, risk costs,
        # funding or leverage. Any mismatch means the scenarios did not use
        # the same OOS selection. Fail closed rather than ranking them.
        coverage = tuple(
            (fold.test_month_number, fold.bars_scored,
             fold.strategy_exposures, fold.strategy_abstention_count,
             fold.benchmark_exposures)
            for fold in report.fold_reports
        )
        if reference is None:
            reference = coverage
        elif coverage != reference:
            raise DataValidationError("sensitivity grid changed frozen OOS decisions")
        cases.append(VisionSensitivityScenario(i, assumptions, report))

    digest_payload = {
        "schema": "j3_pre22_oos_sensitivity_v1",
        "scenario_digests": [x.audit.digest_sha256 for x in cases],
        "cost_bps_per_side": str(cost_bps_per_side),
        "coverage": reference,
    }
    digest = sha256(json.dumps(
        digest_payload, separators=(",", ":"), sort_keys=True).encode("ascii")).hexdigest()
    return VisionStressSensitivity(tuple(cases), digest)
