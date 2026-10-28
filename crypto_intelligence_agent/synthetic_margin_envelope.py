"""J3/PRE15: conditional downside versus requested SYNTHETIC margin.

Consumes PRE6 results; never assigns an intrabar ordering or trade probability.
No venue mark, maintenance margin, fills, account equity, or live permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .market_data import DataValidationError
from .synthetic_financial_scenarios import ConditionalFinancialResult
from .synthetic_intrabar_barriers import SyntheticBarrier

_EXACT = Context(prec=512, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class SyntheticMarginBasis:
    """Hypothetical requested collateral, not a venue-maintained balance."""

    requested_margin_quote: Decimal
    leverage_at_intent: int
    entry_notional_quote: Decimal
    quote_currency: str

    def __post_init__(self) -> None:
        for value in (self.requested_margin_quote, self.entry_notional_quote):
            if (type(value) is not Decimal or not value.is_finite()
                    or value <= 0 or len(value.as_tuple().digits) > 40
                    or value.as_tuple().exponent < -18
                    or value.adjusted() > 24):
                raise DataValidationError("margin basis needs bounded exact positive Decimal")
        if type(self.leverage_at_intent) is not int or not 1 <= self.leverage_at_intent <= 200:
            raise DataValidationError("leverage must be an explicit bounded integer")
        if (type(self.quote_currency) is not str
                or self.quote_currency not in ("SYNTHETIC_QUOTE", "SYNTHETIC_USDT", "SYNTHETIC_USDC")):
            raise DataValidationError("synthetic quote currency required; no FX conversion")
        with localcontext(_EXACT):
            if self.requested_margin_quote * self.leverage_at_intent != self.entry_notional_quote:
                raise DataValidationError("requested margin times leverage differs from entry notional")


@dataclass(frozen=True)
class ConditionalMarginEnvelope:
    """Bounds across mutually exclusive PRE6 alternatives, NOT realized PnL."""

    worst_barrier: SyntheticBarrier
    best_barrier: SyntheticBarrier
    worst_conditional_net_quote: Decimal
    best_conditional_net_quote: Decimal
    hypothetical_max_downside_over_margin: Decimal
    conditional_margin_exhaustion_possible: bool
    favorable_branch_not_sufficient_for_safety: bool
    hypothetical_liquidation_branch_present: bool
    branch_count: int

    @property
    def quality(self) -> str:
        return "synthetic_conditional_margin_envelope_only"

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def out_of_sample_results_validated(self) -> bool:
        return False

    @property
    def net_pnl_verified(self) -> bool:
        return False

    @property
    def liquidation_formula_verified(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False


def evaluate_conditional_margin_envelope(
    results: tuple[ConditionalFinancialResult, ...],
    *, margin: SyntheticMarginBasis,
) -> ConditionalMarginEnvelope:
    """Compare PRE6 alternatives without summing mutually exclusive outcomes."""
    if type(margin) is not SyntheticMarginBasis:
        raise DataValidationError("explicit synthetic margin terms required")
    if (type(results) is not tuple or not 1 <= len(results) <= 16
            or any(type(row) is not ConditionalFinancialResult for row in results)):
        raise DataValidationError("verified typed PRE6 alternatives required")
    barriers = [row.assumed_barrier for row in results]
    if len(set(barriers)) != len(barriers):
        raise DataValidationError("duplicated conditional barrier")
    if (any(row.quote_currency != margin.quote_currency for row in results)
            or any(row.ambiguity_branch_count != len(results) for row in results)):
        raise DataValidationError("margin quote or scenario branch count mismatch")
    for row in results:
        if (type(row.conditional_net_quote_units) is not Decimal
                or not row.conditional_net_quote_units.is_finite()
                or row.financial_backtest_approved or row.net_pnl_verified):
            raise DataValidationError("untrusted conditional financial result")
    # Never turn a favorable target into the chosen fill. Deterministic tie
    # breaks use barrier value, not supplied ordering or a probabilistic weight.
    ordered = sorted(results, key=lambda row: (row.conditional_net_quote_units, row.assumed_barrier.value))
    worst, best = ordered[0], ordered[-1]
    with localcontext(_EXACT):
        ratio = max(Decimal(0), -worst.conditional_net_quote_units) / margin.requested_margin_quote
    return ConditionalMarginEnvelope(
        worst_barrier=worst.assumed_barrier,
        best_barrier=best.assumed_barrier,
        worst_conditional_net_quote=worst.conditional_net_quote_units,
        best_conditional_net_quote=best.conditional_net_quote_units,
        hypothetical_max_downside_over_margin=ratio,
        conditional_margin_exhaustion_possible=ratio >= 1,
        favorable_branch_not_sufficient_for_safety=(
            best.conditional_net_quote_units > 0
            and worst.conditional_net_quote_units < 0
        ),
        hypothetical_liquidation_branch_present=(
            SyntheticBarrier.HYPOTHETICAL_LIQUIDATION in barriers
        ),
        branch_count=len(results),
    )
