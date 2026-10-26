"""J4/AUTO3: fail-closed quantitative preflight for hypothetical PAPER intents.

No provider tiers, financial-market API, private account data, order signing,
live execution or PnL accounting. Inputs are UNTRUSTED simulated fixtures.
Passing this gate never authorizes exchange orders or proves future returns.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
import re

from .market_data import DataValidationError
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperVenue,
)


_SYMBOL = re.compile(r"[A-Z0-9]{4,25}")
_QUOTE = frozenset({"USDT", "USDC"})


def _quote(value: Decimal, field: str, *, allow_zero: bool) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise DataValidationError(f"{field} must be finite exact Decimal, never float")
    if value < 0 or (not allow_zero and value == 0):
        raise DataValidationError(f"{field} must be positive or permitted zero")
    t = value.as_tuple()
    if len(t.digits) > 35 or t.exponent < -18 or value.adjusted() > 24:
        raise DataValidationError(f"{field} exceeds bounded quote precision/range")
    return value


@dataclass(frozen=True)
class PaperRiskLimits:
    """Explicit limits, all in ONE fixture quote currency; no defaults."""

    max_order_notional_quote: Decimal
    max_symbol_exposure_quote: Decimal
    max_portfolio_exposure_quote: Decimal
    max_realized_loss_today_quote: Decimal
    max_pending_open_orders: int
    max_market_age_ms: int

    def __post_init__(self) -> None:
        for field in (
            "max_order_notional_quote", "max_symbol_exposure_quote",
            "max_portfolio_exposure_quote", "max_realized_loss_today_quote",
        ):
            _quote(getattr(self, field), field, allow_zero=False)
        if not (self.max_order_notional_quote
                <= self.max_symbol_exposure_quote
                <= self.max_portfolio_exposure_quote):
            raise DataValidationError("paper order/symbol/portfolio limits are inconsistent")
        if (type(self.max_pending_open_orders) is not int
                or not 1 <= self.max_pending_open_orders <= 100_000):
            raise DataValidationError("positive bounded pending-open limit required")
        if (type(self.max_market_age_ms) is not int
                or not 0 <= self.max_market_age_ms <= 604_800_000):
            raise DataValidationError("paper observation age must be bounded UTC-ms")


@dataclass(frozen=True)
class PaperRiskObservation:
    """A declared paper snapshot; not an authenticated venue exposure or price."""

    venue: PaperVenue
    symbol: str
    quote_currency: str
    observed_at_ms: int
    mark_price_quote: Decimal
    symbol_exposure_quote: Decimal
    portfolio_exposure_quote: Decimal
    realized_loss_today_quote: Decimal
    pending_open_orders: int
    unresolved_open_exists: bool
    kill_switch_active: bool

    def __post_init__(self) -> None:
        if type(self.venue) is not PaperVenue:
            raise DataValidationError("paper venue must use explicit enum")
        if type(self.symbol) is not str or _SYMBOL.fullmatch(self.symbol) is None:
            raise DataValidationError("paper risk symbol invalid")
        if (type(self.quote_currency) is not str
                or self.quote_currency not in _QUOTE
                or not self.symbol.endswith(self.quote_currency)
                or (self.venue is PaperVenue.BINANCE_USDM
                    and self.quote_currency != "USDT")):
            raise DataValidationError("paper quote/contract/venue mismatch")
        _utc_ms(self.observed_at_ms, "observed_at_ms")
        _quote(self.mark_price_quote, "mark_price_quote", allow_zero=False)
        for field in (
            "symbol_exposure_quote", "portfolio_exposure_quote",
            "realized_loss_today_quote",
        ):
            _quote(getattr(self, field), field, allow_zero=True)
        if self.portfolio_exposure_quote < self.symbol_exposure_quote:
            raise DataValidationError("symbol exposure exceeds declared portfolio exposure")
        if type(self.pending_open_orders) is not int or not 0 <= self.pending_open_orders <= 100_000:
            raise DataValidationError("paper pending count must be bounded integer")
        if (type(self.unresolved_open_exists) is not bool
                or type(self.kill_switch_active) is not bool):
            raise DataValidationError("paper safety controls require explicit booleans")

    @property
    def quality(self) -> str:
        return "synthetic_fixture_only"

    @property
    def account_and_market_data_verified(self) -> bool:
        return False


class PaperRiskReason(str, Enum):
    OPEN_ALLOWED_PAPER_ONLY = "open_allowed_paper_only"
    PROTECTIVE_EXIT_PAPER_ONLY = "protective_exit_paper_only"
    KILL_SWITCH = "kill_switch_active"
    UNRESOLVED_OPEN = "unresolved_open_requires_reconciliation"
    PENDING_LIMIT = "pending_open_limit_reached"
    LOSS_LIMIT = "daily_loss_limit_reached"
    STALE_FEED = "paper_market_observation_stale"
    ORDER_NOTIONAL = "paper_order_notional_exceeded"
    SYMBOL_EXPOSURE = "paper_symbol_exposure_exceeded"
    PORTFOLIO_EXPOSURE = "paper_portfolio_exposure_exceeded"


@dataclass(frozen=True)
class PaperRiskDecision:
    """Allowed for simulation only, with no transferable live authority."""

    allowed_for_paper_only: bool
    reason: PaperRiskReason
    hypothetical_notional_quote: Decimal
    observed_age_ms: int

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def quality(self) -> str:
        return "synthetic_risk_assessment_only"


def evaluate_paper_risk(
    intent: PaperOrderIntent,
    limits: PaperRiskLimits,
    observation: PaperRiskObservation,
    *,
    decision_at_ms: int,
) -> PaperRiskDecision:
    """Never auto-submit; only classify a fictitious order using supplied values.

    OPEN is blocked on kill switch, UNKNOWN, stale data and hard caps.
    An explicitly bounded REDUCE_ONLY *paper intent* remains a hypothetical
    protective exit when new entries are paused; it installs no real stop.
    """
    if (type(intent) is not PaperOrderIntent
            or type(limits) is not PaperRiskLimits
            or type(observation) is not PaperRiskObservation):
        raise DataValidationError("validated paper intent/limits/observation required")
    now = _utc_ms(decision_at_ms, "decision_at_ms")
    if (now < intent.created_at_ms
            or observation.observed_at_ms > now):
        raise DataValidationError("paper decision cannot use future information")
    if intent.venue is not observation.venue or intent.symbol != observation.symbol:
        raise DataValidationError("paper risk observation does not describe order venue/symbol")
    age = now - observation.observed_at_ms
    with localcontext(_EXACT_CONTEXT):
        notional = intent.requested_units * observation.mark_price_quote
        # Protectively reduce-only may be prepared while opening is paused.
        # This does not certify native reduceOnly semantics or actual positions.
        if intent.effect is PaperOrderEffect.REDUCE_ONLY:
            reason = PaperRiskReason.PROTECTIVE_EXIT_PAPER_ONLY
        elif observation.kill_switch_active:
            reason = PaperRiskReason.KILL_SWITCH
        elif observation.unresolved_open_exists:
            reason = PaperRiskReason.UNRESOLVED_OPEN
        elif observation.pending_open_orders >= limits.max_pending_open_orders:
            reason = PaperRiskReason.PENDING_LIMIT
        elif observation.realized_loss_today_quote >= limits.max_realized_loss_today_quote:
            reason = PaperRiskReason.LOSS_LIMIT
        elif age > limits.max_market_age_ms:
            reason = PaperRiskReason.STALE_FEED
        elif notional > limits.max_order_notional_quote:
            reason = PaperRiskReason.ORDER_NOTIONAL
        elif observation.symbol_exposure_quote + notional > limits.max_symbol_exposure_quote:
            reason = PaperRiskReason.SYMBOL_EXPOSURE
        elif observation.portfolio_exposure_quote + notional > limits.max_portfolio_exposure_quote:
            reason = PaperRiskReason.PORTFOLIO_EXPOSURE
        else:
            reason = PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY

    return PaperRiskDecision(
        allowed_for_paper_only=reason in (
            PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY,
            PaperRiskReason.PROTECTIVE_EXIT_PAPER_ONLY,
        ),
        reason=reason,
        hypothetical_notional_quote=notional,
        observed_age_ms=age,
    )
