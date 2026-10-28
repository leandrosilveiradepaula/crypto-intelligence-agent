"""J4/PRE11: compositional, exact PAPER entry margin preflight.

For explicitly supplied synthetic Binance USD-M / Bybit linear assumptions.
This is not an exchange contract, risk-engine integration, account, collateral,
funding/liquidation model, authentic mark or a proposal to submit an order.

Never silently round quantity, convert USDT/USDC into USD, cap 50x without
user choice, or mutate previously opened positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
import re

from .market_data import DataValidationError
from .paper_risk_gate import (
    PaperRiskLimits, PaperRiskObservation, PaperRiskReason,
    _quote, evaluate_paper_risk,
)
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperVenue,
)
from .synthetic_position_state import SyntheticLeverageSettings

_FIXTURE_VERSION = re.compile(r"fixture_[A-Za-z0-9_-]{1,56}")
_SYMBOL = re.compile(r"[A-Z0-9]{4,25}")
_QUOTES = frozenset(("USDT", "USDC"))
_MAX_RULE_AGE_MS = 604_800_000


@dataclass(frozen=True)
class PaperLinearContractFixture:
    """Unverified contract-size and leverage assumptions, NOT venue rules."""

    venue: PaperVenue
    symbol: str
    quote_currency: str
    observed_at_ms: int
    fixture_version: str
    max_leverage_assumed: int
    price_tick_quote: Decimal
    quantity_step_base: Decimal
    min_quantity_base: Decimal
    min_notional_quote: Decimal
    max_notional_quote: Decimal | None

    def __post_init__(self) -> None:
        if type(self.venue) is not PaperVenue:
            raise DataValidationError("fixture must name exact supported paper venue")
        if (type(self.symbol) is not str
                or _SYMBOL.fullmatch(self.symbol) is None
                or type(self.quote_currency) is not str
                or self.quote_currency not in _QUOTES
                or not self.symbol.endswith(self.quote_currency)
                or (self.venue is PaperVenue.BINANCE_USDM
                    and self.quote_currency != "USDT")
                or not self.symbol[:-len(self.quote_currency)]):
            raise DataValidationError("linear fixture symbol/quote/venue mismatch")
        _utc_ms(self.observed_at_ms, "contract_fixture_observed_at_ms")
        if (type(self.fixture_version) is not str
                or _FIXTURE_VERSION.fullmatch(self.fixture_version) is None):
            raise DataValidationError("contract provenance MUST be fixture-only")
        if (type(self.max_leverage_assumed) is not int
                or not 1 <= self.max_leverage_assumed <= 200):
            raise DataValidationError("hypothetical venue leverage cap invalid")
        # An unverified MARK is not an order limit price. Tick is checked as
        # metadata only; there is no order price to round or validate yet.
        _quote(self.price_tick_quote, "price_tick_quote", allow_zero=False)
        step = _quote(self.quantity_step_base, "quantity_step_base", allow_zero=False)
        minimum = _quote(self.min_quantity_base, "min_quantity_base", allow_zero=False)
        _quote(self.min_notional_quote, "min_notional_quote", allow_zero=False)
        if self.max_notional_quote is not None:
            _quote(self.max_notional_quote, "max_notional_quote", allow_zero=False)
            if self.max_notional_quote < self.min_notional_quote:
                raise DataValidationError("maximum hypothetical notional below minimum")
        with localcontext(_EXACT_CONTEXT):
            if minimum % step != 0:
                raise DataValidationError("fixture minimum quantity must align with step")

    @property
    def provenance(self) -> str:
        return "unverified_synthetic_contract_fixture"

    @property
    def exchange_lot_rules_verified(self) -> bool:
        return False

    @property
    def venue_leverage_tiers_verified(self) -> bool:
        return False

    @property
    def funding_liquidation_verified(self) -> bool:
        return False

    @property
    def executable_price_tick_verified(self) -> bool:
        return False


@dataclass(frozen=True)
class PaperMarginPreflightRequest:
    """Explicit, immutable opt-in for the causal PAPER OPEN preparation path.

    A valid request is still a synthetic assumption, not a venue grant.
    It never changes settings on old positions or authorizes live execution.
    """

    settings: SyntheticLeverageSettings
    margin_quote: Decimal
    contract: PaperLinearContractFixture
    max_contract_age_ms: int

    def __post_init__(self) -> None:
        if (type(self.settings) is not SyntheticLeverageSettings
                or type(self.contract) is not PaperLinearContractFixture
                or type(self.max_contract_age_ms) is not int
                or not 0 <= self.max_contract_age_ms <= _MAX_RULE_AGE_MS):
            raise DataValidationError("typed bounded PAPER margin preflight required")
        _quote(self.margin_quote, "requested_margin_quote", allow_zero=False)

    @property
    def venue_metadata_authenticated(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False


class PaperMarginReason(str, Enum):
    FEASIBLE_PAPER_ONLY = "feasible_paper_only"
    RISK_GATE_BLOCKED = "paper_risk_gate_blocked"
    CONTRACT_FIXTURE_STALE = "hypothetical_contract_fixture_stale"
    LEVERAGE_CAP_EXCEEDED = "hypothetical_leverage_cap_exceeded"
    MARGIN_NOTIONAL_MISMATCH = "margin_notional_exact_match_required"
    QUANTITY_STEP_MISMATCH = "quantity_step_not_exact"
    MIN_QUANTITY = "hypothetical_min_quantity_not_met"
    MIN_NOTIONAL = "hypothetical_min_notional_not_met"
    MAX_NOTIONAL = "hypothetical_max_notional_exceeded"


@dataclass(frozen=True)
class PaperMarginAssessment:
    """One hypothetical new OPEN assessment; not a persisted position record."""

    reason: PaperMarginReason
    risk_reason: PaperRiskReason
    allowed_for_paper_research_only: bool
    leverage_captured_for_new_intent: int
    requested_margin_quote: Decimal
    assumed_notional_quote: Decimal
    actual_intent_notional_quote: Decimal
    requested_units_base: Decimal
    quote_currency: str
    contract_fixture_version: str
    assessed_mark_price_quote: Decimal
    assessed_at_ms: int

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def venue_contract_verified(self) -> bool:
        return False

    @property
    def real_margin_currency_verified(self) -> bool:
        return False

    @property
    def mark_price_authenticated(self) -> bool:
        return False

    @property
    def liquidation_model_verified(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def leverage_persisted_to_position_ledger(self) -> bool:
        return False


def assess_paper_margin_open(
    intent: PaperOrderIntent,
    settings: SyntheticLeverageSettings,
    margin_quote: Decimal,
    contract: PaperLinearContractFixture,
    limits: PaperRiskLimits,
    observation: PaperRiskObservation,
    *, decision_at_ms: int, max_contract_age_ms: int,
) -> PaperMarginAssessment:
    """Compose existing risk gate with exact margin and entry-size constraints.

    No rounding, venue tier inference, quote FX, order creation or persistence.
    On a declined assessment the PAPER risk gate remains authoritative and
    its reason has precedence over min-notional or leverage convenience.
    """
    if (type(intent) is not PaperOrderIntent
            or intent.effect is not PaperOrderEffect.OPEN
            or type(settings) is not SyntheticLeverageSettings
            or type(contract) is not PaperLinearContractFixture
            or type(limits) is not PaperRiskLimits
            or type(observation) is not PaperRiskObservation):
        raise DataValidationError("explicit PAPER OPEN, limits, settings and fixture required")
    if (intent.venue is not contract.venue
            or observation.venue is not contract.venue
            or intent.symbol != contract.symbol
            or observation.symbol != contract.symbol
            or observation.quote_currency != contract.quote_currency):
        raise DataValidationError("paper intent/mark/fixture must match venue, symbol and quote")
    now = _utc_ms(decision_at_ms, "paper_margin_decision_at_ms")
    if (type(max_contract_age_ms) is not int
            or not 0 <= max_contract_age_ms <= _MAX_RULE_AGE_MS
            or contract.observed_at_ms > now):
        raise DataValidationError("invalid or future contract fixture at decision time")
    margin = _quote(margin_quote, "requested_margin_quote", allow_zero=False)

    # Exactly the same risk gate as the existing PAPER entry path.
    risk = evaluate_paper_risk(intent, limits, observation, decision_at_ms=now)
    with localcontext(_EXACT_CONTEXT):
        theoretical = margin * Decimal(settings.for_new_positions)
        actual = intent.requested_units * observation.mark_price_quote
        if not risk.allowed_for_paper_only:
            reason = PaperMarginReason.RISK_GATE_BLOCKED
        elif now - contract.observed_at_ms > max_contract_age_ms:
            reason = PaperMarginReason.CONTRACT_FIXTURE_STALE
        elif settings.for_new_positions > contract.max_leverage_assumed:
            reason = PaperMarginReason.LEVERAGE_CAP_EXCEEDED
        elif theoretical != actual:
            reason = PaperMarginReason.MARGIN_NOTIONAL_MISMATCH
        elif intent.requested_units % contract.quantity_step_base != 0:
            reason = PaperMarginReason.QUANTITY_STEP_MISMATCH
        elif intent.requested_units < contract.min_quantity_base:
            reason = PaperMarginReason.MIN_QUANTITY
        elif actual < contract.min_notional_quote:
            reason = PaperMarginReason.MIN_NOTIONAL
        elif (contract.max_notional_quote is not None
              and actual > contract.max_notional_quote):
            reason = PaperMarginReason.MAX_NOTIONAL
        else:
            reason = PaperMarginReason.FEASIBLE_PAPER_ONLY

    return PaperMarginAssessment(
        reason=reason, risk_reason=risk.reason,
        allowed_for_paper_research_only=reason is PaperMarginReason.FEASIBLE_PAPER_ONLY,
        leverage_captured_for_new_intent=settings.for_new_positions,
        requested_margin_quote=margin,
        assumed_notional_quote=theoretical,
        actual_intent_notional_quote=actual,
        requested_units_base=intent.requested_units,
        quote_currency=contract.quote_currency,
        contract_fixture_version=contract.fixture_version,
        assessed_mark_price_quote=observation.mark_price_quote,
        assessed_at_ms=now,
    )
