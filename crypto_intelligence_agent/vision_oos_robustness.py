"""J3/PRE26: explicit adversarial OOS research screen; never a trading gate.

The screen consumes PRE22 results already computed on immutable OOS decisions.
It cannot turn synthetic scenario bounds into proven PnL or leverage approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json

from .market_data import DataValidationError
from .vision_stress_sensitivity import VisionStressSensitivity

_CTX = Context(prec=512)
_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True)
class OOSRobustnessPolicy:
    min_test_folds: int
    min_exposures_per_fold: int
    max_liquidation_proxy_fraction: Decimal
    max_intrabar_ambiguity_fraction: Decimal
    max_single_bar_loss_over_margin: Decimal
    max_worst_drawdown_quote: Decimal
    require_nonnegative_adverse_fold: bool

    def __post_init__(self) -> None:
        if (type(self.min_test_folds) is not int
                or not 1 <= self.min_test_folds <= 24
                or type(self.min_exposures_per_fold) is not int
                or not 1 <= self.min_exposures_per_fold <= 100_000
                or type(self.require_nonnegative_adverse_fold) is not bool):
            raise DataValidationError("explicit bounded OOS robustness sample policy required")
        for name, upper in (
            ("max_liquidation_proxy_fraction", _ONE),
            ("max_intrabar_ambiguity_fraction", _ONE),
            ("max_single_bar_loss_over_margin", Decimal(1000)),
            ("max_worst_drawdown_quote", Decimal("1000000000000")),
        ):
            x = getattr(self, name)
            if (type(x) is not Decimal or not x.is_finite()
                    or x < _ZERO or x > upper
                    or x.as_tuple().exponent < -12):
                raise DataValidationError("finite bounded explicit OOS robustness threshold required")


@dataclass(frozen=True)
class OOSRobustnessScenario:
    ordinal: int
    leverage_at_intent: int
    exposure_count: int
    fold_failures: tuple[tuple[str, ...], ...]
    rejection_codes: tuple[str, ...]

    def sanitized_report(self) -> dict:
        return {
            "ordinal": self.ordinal,
            "leverage_at_intent": self.leverage_at_intent,
            "exposure_count": self.exposure_count,
            "fold_rejection_codes": [list(x) for x in self.fold_failures],
            "rejection_codes": list(self.rejection_codes),
            "research_only_conditions_met": not self.rejection_codes,
        }


@dataclass(frozen=True)
class OOSRobustnessAudit:
    scenario_reports: tuple[OOSRobustnessScenario, ...]
    digest_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "j3_pre26_oos_robustness_v1",
            "status": "synthetic_oos_robustness_screen_only",
            "all_synthetic_conditions_met": all(
                not row.rejection_codes for row in self.scenario_reports),
            "scenario_count": len(self.scenario_reports),
            "scenarios": [x.sanitized_report() for x in self.scenario_reports],
            "digest_sha256": self.digest_sha256,
            "recommended_leverage": None,
            "financial_backtest_approved": False,
            "net_pnl_verified": False,
            "liquidation_formula_verified": False,
            "marketwide_top50_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def audit_oos_robustness(
    comparison: VisionStressSensitivity, *,
    policy: OOSRobustnessPolicy,
) -> OOSRobustnessAudit:
    """Fail closed on inconsistent counts; reject ANY adverse fold/scenario.

    Ratios are based on strategy exposures, not all-bars LONG observations.
    No ex-post scenario ranking, averaging away risk, or aggregate-only gate.
    """
    if (type(comparison) is not VisionStressSensitivity
            or type(policy) is not OOSRobustnessPolicy
            or not 2 <= len(comparison.scenarios) <= 6):
        raise DataValidationError("typed bounded PRE22 comparison and policy required")
    result = []
    fingerprints = None
    with localcontext(_CTX):
        for s in comparison.scenarios:
            a = s.audit
            if (s.ordinal != len(result) + 1 or not a.fold_reports
                    or a.matched_long is None
                    or type(a.stressed_count) is not int
                    or a.stressed_count < 0
                    or a.matched_long.exposures != a.stressed_count
                    or a.stressed_count != sum(f.strategy_exposures for f in a.fold_reports)
                    or a.abstention_count != sum(f.strategy_abstention_count for f in a.fold_reports)
                    or a.liquidation_possible_count != sum(
                        f.strategy_liquidation_possible_count for f in a.fold_reports)
                    or a.ambiguous_count != sum(f.strategy_ambiguous_count for f in a.fold_reports)):
                raise DataValidationError("inconsistent OOS exposure or fold evidence")
            fp = (
                a.decision_fingerprint_sha256,
                tuple((f.test_month_number, f.bars_scored, f.strategy_exposures,
                       f.strategy_abstention_count, f.decision_fingerprint_sha256)
                      for f in a.fold_reports),
            )
            if fingerprints is None:
                fingerprints = fp
            elif fp != fingerprints:
                raise DataValidationError("OOS robustness compared different decisions")
            failures = []
            for f in a.fold_reports:
                if (f.matched_long is None
                        or f.matched_long.exposures != f.strategy_exposures
                        or f.strategy_exposures < 0 or f.strategy_abstention_count < 0
                        or f.bars_scored != f.strategy_exposures + f.strategy_abstention_count
                        or f.strategy_liquidation_possible_count < 0
                        or f.strategy_ambiguous_count < 0
                        or f.strategy_liquidation_possible_count > f.strategy_exposures
                        or f.strategy_ambiguous_count > f.strategy_exposures
                        or f.test_month_number != len(failures) + 1):
                    raise DataValidationError("invalid OOS fold accounting or matched exposure")
                codes = []
                if f.strategy_exposures < policy.min_exposures_per_fold:
                    codes.append("insufficient_exposures_per_fold")
                if f.strategy_exposures:
                    if (Decimal(f.strategy_liquidation_possible_count) /
                            f.strategy_exposures > policy.max_liquidation_proxy_fraction):
                        codes.append("liquidation_proxy_fraction_exceeded")
                    if (Decimal(f.strategy_ambiguous_count) /
                            f.strategy_exposures > policy.max_intrabar_ambiguity_fraction):
                        codes.append("intrabar_ambiguity_fraction_exceeded")
                if f.strategy_max_single_bar_loss_over_margin > policy.max_single_bar_loss_over_margin:
                    codes.append("single_bar_margin_loss_exceeded")
                if -f.strategy_worst_drawdown_proxy_quote > policy.max_worst_drawdown_quote:
                    codes.append("adverse_drawdown_exceeded")
                if policy.require_nonnegative_adverse_fold and f.strategy_worst_net_quote < _ZERO:
                    codes.append("negative_adverse_fold")
                failures.append(tuple(codes))
            aggregate = []
            if len(a.fold_reports) < policy.min_test_folds:
                aggregate.append("insufficient_oos_folds")
            if not a.stressed_count:
                aggregate.append("no_oos_exposure")
            # Each fold fails independently; never average negative risk away.
            all_codes = tuple(dict.fromkeys(
                aggregate + [code for fold in failures for code in fold]))
            result.append(OOSRobustnessScenario(
                s.ordinal, s.assumptions.margin.leverage_at_intent,
                a.stressed_count, tuple(failures), all_codes))
        payload = {
            "schema": "j3_pre26_oos_robustness_v1",
            "source": comparison.digest_sha256,
            "policy": [(k, str(v) if type(v) is Decimal else v)
                       for k, v in vars(policy).items()],
            "reports": [x.sanitized_report() for x in result],
        }
        digest = sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    return OOSRobustnessAudit(tuple(result), digest)
