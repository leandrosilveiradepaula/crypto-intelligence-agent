"""J3/PRE6: explicit conditional financial scenarios on synthetic fixtures.

This module never derives a fill, liquidation price, or intrabar ordering from
OHLC.  Every entry/exit price and any liquidation loss is a declared fixture.
It composes PRE1 observations and PRE2 cost arithmetic without promoting either
to a financial backtest or an order authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
import re
from typing import Sequence

from .market_data import DataValidationError
from .synthetic_cost_scenarios import (
    SyntheticCostBreakdown, SyntheticCostScenario, SyntheticFundingEvent,
    evaluate_synthetic_costs,
)
from .synthetic_feature_engine import validate_synthetic_research_price
from .synthetic_intrabar_barriers import (
    ObservationKind, ResearchDirection, SyntheticBarrierObservation,
)


_EXACT = Context(prec=512, rounding=ROUND_HALF_EVEN)
_ID = re.compile(r"fixture_financial_[A-Za-z0-9_-]{1,40}")
_SOURCE_ID = re.compile(r"fixture_source_[A-Za-z0-9_-]{1,40}")


class ScenarioResolution(str, Enum):
    EXPLICIT_EXIT = "explicit_exit"
    EXPLICIT_LIQUIDATION_LOSS = "explicit_liquidation_loss"


@dataclass(frozen=True)
class FundingProvenance:
    """Identity, sign convention and abstract currency for a fixture event."""

    event: SyntheticFundingEvent
    source_id: str
    quote_currency: str
    positive_rate_means: str = "LONG_PAYS_SHORT_RECEIVES"

    def __post_init__(self) -> None:
        if type(self.event) is not SyntheticFundingEvent:
            raise DataValidationError("funding provenance requires synthetic funding event")
        if type(self.source_id) is not str or _SOURCE_ID.fullmatch(self.source_id) is None:
            raise DataValidationError("funding source requires fixture-only identity")
        if type(self.quote_currency) is not str or not self.quote_currency.startswith("SYNTHETIC_"):
            raise DataValidationError("funding quote currency must be declared synthetic unit")
        if self.positive_rate_means != "LONG_PAYS_SHORT_RECEIVES":
            raise DataValidationError("funding sign convention must be explicit and supported")


@dataclass(frozen=True)
class ConditionalFinancialScenario:
    """One branch with explicit fixture-only fills or an explicit loss amount."""

    scenario_id: str
    exchange: str
    symbol: str
    interval: str
    direction: ResearchDirection
    entry_price: Decimal
    quantity_base_units: Decimal
    resolution: ScenarioResolution
    exit_price: Decimal | None
    hypothetical_liquidation_loss_quote_units: Decimal | None
    quote_currency: str
    costs: SyntheticCostScenario
    funding_provenance: tuple[FundingProvenance, ...] = ()

    def __post_init__(self) -> None:
        if type(self.scenario_id) is not str or _ID.fullmatch(self.scenario_id) is None:
            raise DataValidationError("financial scenario ID must be fixture-only bounded ASCII")
        if any(type(value) is not str or not value for value in (self.exchange, self.symbol, self.interval)):
            raise DataValidationError("scenario market identity must be explicit")
        if type(self.direction) is not ResearchDirection or type(self.resolution) is not ScenarioResolution:
            raise DataValidationError("scenario direction and resolution require explicit enums")
        validate_synthetic_research_price(self.entry_price, "entry_price")
        if type(self.quantity_base_units) is not Decimal or not self.quantity_base_units.is_finite() or self.quantity_base_units <= 0:
            raise DataValidationError("quantity_base_units requires positive finite Decimal")
        if type(self.quote_currency) is not str or not self.quote_currency.startswith("SYNTHETIC_"):
            raise DataValidationError("quote currency must be declared synthetic unit")
        if type(self.costs) is not SyntheticCostScenario or self.costs.direction is not self.direction:
            raise DataValidationError("scenario requires matching explicit synthetic cost scenario")
        if type(self.funding_provenance) is not tuple or any(type(item) is not FundingProvenance for item in self.funding_provenance):
            raise DataValidationError("funding provenance requires immutable declared tuple")
        declared = tuple(item.event for item in self.funding_provenance)
        if declared != self.costs.funding_events or any(item.quote_currency != self.quote_currency for item in self.funding_provenance):
            raise DataValidationError("every funding event needs matching source, currency and sign declaration")
        if len({item.event.event_id for item in self.funding_provenance}) != len(self.funding_provenance):
            raise DataValidationError("funding provenance cannot duplicate event identity")
        if self.resolution is ScenarioResolution.EXPLICIT_EXIT:
            validate_synthetic_research_price(self.exit_price, "exit_price")
            if self.hypothetical_liquidation_loss_quote_units is not None:
                raise DataValidationError("exit branch cannot also assert liquidation loss")
        else:
            if self.exit_price is not None:
                raise DataValidationError("liquidation branch cannot infer an exit price")
            if (type(self.hypothetical_liquidation_loss_quote_units) is not Decimal
                    or not self.hypothetical_liquidation_loss_quote_units.is_finite()
                    or self.hypothetical_liquidation_loss_quote_units <= 0):
                raise DataValidationError("liquidation branch needs explicit positive loss Decimal")


@dataclass(frozen=True)
class ConditionalFinancialResult:
    scenario_id: str
    resolution: ScenarioResolution
    quote_currency: str
    gross_price_movement_quote_units: Decimal
    hypothetical_liquidation_loss_quote_units: Decimal | None
    costs: SyntheticCostBreakdown
    conditional_net_quote_units: Decimal
    ambiguity_branch_count: int

    @property
    def quality(self) -> str:
        return "conditional_synthetic_explicit_assumptions_only"

    @property
    def intrabar_path_verified(self) -> bool:
        return False

    @property
    def fill_price_verified(self) -> bool:
        return False

    @property
    def liquidation_formula_verified(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def evaluate_conditional_financial_scenarios(
    observation: SyntheticBarrierObservation,
    scenarios: Sequence[ConditionalFinancialScenario],
) -> tuple[ConditionalFinancialResult, ...]:
    """Evaluate explicit branches; refuse an unresolved OHLC ambiguity alone."""
    if type(observation) is not SyntheticBarrierObservation:
        raise DataValidationError("PRE1 synthetic barrier observation required")
    if type(scenarios) not in (tuple, list) or not scenarios:
        raise DataValidationError("at least one explicit conditional scenario is required")
    rows = tuple(scenarios)
    if any(type(row) is not ConditionalFinancialScenario for row in rows):
        raise DataValidationError("conditional scenarios must use the typed contract")
    if len({row.scenario_id for row in rows}) != len(rows):
        raise DataValidationError("conditional scenario identities must be unique")
    if observation.kind is ObservationKind.MULTIPLE_LEVELS_UNORDERED and len(rows) < 2:
        raise DataValidationError("unordered intrabar levels require explicit alternative scenarios")
    if observation.kind is ObservationKind.NO_LEVEL_REACHED:
        raise DataValidationError("no observed barrier leaves no conditional exit premise")
    for row in rows:
        if (row.exchange, row.symbol, row.interval) != (observation.exchange, observation.symbol, observation.interval):
            raise DataValidationError("scenario identity does not match PRE1 observation")
        if row.costs.entry_at_ms < observation.plan_created_at_ms:
            raise DataValidationError("financial assumption predates its synthetic barrier plan")
    with localcontext(_EXACT):
        results: list[ConditionalFinancialResult] = []
        for row in rows:
            cost = evaluate_synthetic_costs(row.costs)
            if row.resolution is ScenarioResolution.EXPLICIT_EXIT:
                movement = (row.exit_price - row.entry_price) * row.quantity_base_units
                if row.direction is ResearchDirection.SHORT:
                    movement = -movement
                loss = None
            else:
                loss = row.hypothetical_liquidation_loss_quote_units
                movement = -loss
            results.append(ConditionalFinancialResult(
                scenario_id=row.scenario_id, resolution=row.resolution, quote_currency=row.quote_currency,
                gross_price_movement_quote_units=movement, hypothetical_liquidation_loss_quote_units=loss,
                costs=cost, conditional_net_quote_units=movement - cost.total_signed_cost_units,
                ambiguity_branch_count=len(rows),
            ))
    return tuple(results)
