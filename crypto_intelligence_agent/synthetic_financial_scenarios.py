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
    evaluate_synthetic_costs, _amount,
)
from .synthetic_feature_engine import validate_synthetic_research_price
from .synthetic_intrabar_barriers import (
    ObservationKind, ResearchDirection, SyntheticBarrier, SyntheticBarrierPlan,
    SyntheticBarrierObservation,
)


_EXACT = Context(prec=512, rounding=ROUND_HALF_EVEN)
_ID = re.compile(r"fixture_financial_[A-Za-z0-9_-]{1,40}")
_SOURCE_ID = re.compile(r"fixture_source_[A-Za-z0-9_-]{1,40}")
_QUOTE_ID = re.compile(r"SYNTHETIC_[A-Z0-9_]{1,32}")
MAX_SCENARIOS = 16


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
        if type(self.quote_currency) is not str or _QUOTE_ID.fullmatch(self.quote_currency) is None:
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
    assumed_barrier: SyntheticBarrier
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
        if type(self.assumed_barrier) is not SyntheticBarrier:
            raise DataValidationError("scenario requires an explicit observed barrier")
        validate_synthetic_research_price(self.entry_price, "entry_price")
        _amount(self.quantity_base_units, "quantity_base_units")
        if type(self.quote_currency) is not str or _QUOTE_ID.fullmatch(self.quote_currency) is None:
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
            if self.assumed_barrier is SyntheticBarrier.HYPOTHETICAL_LIQUIDATION:
                raise DataValidationError("liquidation barrier needs explicit liquidation loss")
            validate_synthetic_research_price(self.exit_price, "exit_price")
            if self.hypothetical_liquidation_loss_quote_units is not None:
                raise DataValidationError("exit branch cannot also assert liquidation loss")
        else:
            if self.assumed_barrier is not SyntheticBarrier.HYPOTHETICAL_LIQUIDATION:
                raise DataValidationError("liquidation loss requires liquidation barrier")
            if self.exit_price is not None:
                raise DataValidationError("liquidation branch cannot infer an exit price")
            _amount(self.hypothetical_liquidation_loss_quote_units, "liquidation loss")
        # Preserve a single economic basis across quantity, price and fee notionals.
        # Liquidation exit notional is necessarily a separate explicit assumption.
        with localcontext(_EXACT):
            if self.costs.entry_hypothetical_notional_quote_units != self.entry_price * self.quantity_base_units:
                raise DataValidationError("entry cost notional must equal declared entry price times quantity")
            if (self.resolution is ScenarioResolution.EXPLICIT_EXIT
                    and self.costs.exit_hypothetical_notional_quote_units != self.exit_price * self.quantity_base_units):
                raise DataValidationError("exit cost notional must equal declared exit price times quantity")


@dataclass(frozen=True)
class ConditionalFinancialResult:
    scenario_id: str
    assumed_barrier: SyntheticBarrier
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
    def net_pnl_verified(self) -> bool:
        return False

    @property
    def out_of_sample_results_validated(self) -> bool:
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
    *,
    barrier_plan: SyntheticBarrierPlan,
) -> tuple[ConditionalFinancialResult, ...]:
    """Evaluate only explicit branches tied to actually observed PRE1 levels.

    The event time must be within PRE1's first hit candle, but a hypothetical
    price/fee never becomes a verified fill. The matching synthetic plan binds
    direction and entry assumptions, not authenticated market evidence.
    """
    if type(observation) is not SyntheticBarrierObservation:
        raise DataValidationError("PRE1 synthetic barrier observation required")
    if type(barrier_plan) is not SyntheticBarrierPlan:
        raise DataValidationError("explicit matching PRE1 barrier plan required")
    if observation.plan_created_at_ms != barrier_plan.plan_created_at_ms:
        raise DataValidationError("PRE1 observation does not match barrier plan")
    if type(observation.kind) is not ObservationKind:
        raise DataValidationError("invalid PRE1 observation kind")
    if observation.kind is ObservationKind.NO_LEVEL_REACHED:
        raise DataValidationError("no observed barrier leaves no conditional exit premise")
    levels = observation.levels_reached
    if (type(levels) is not tuple or not levels
            or any(type(level) is not SyntheticBarrier for level in levels)
            or len(set(levels)) != len(levels)):
        raise DataValidationError("PRE1 observation requires unique typed reached barriers")
    if observation.kind is ObservationKind.MULTIPLE_LEVELS_UNORDERED and len(levels) < 2:
        raise DataValidationError("unordered intrabar observation must identify multiple barriers")
    if observation.kind is ObservationKind.SINGLE_LEVEL_RANGE and len(levels) != 1:
        raise DataValidationError("single-level observation cannot contain multiple barriers")
    if (SyntheticBarrier.HYPOTHETICAL_LIQUIDATION in levels
            and barrier_plan.hypothetical_liquidation_level is None):
        raise DataValidationError("liquidation barrier not declared in PRE1 plan")
    opened = observation.first_candidate_open_time_ms
    closed = observation.first_candidate_close_time_ms
    if (type(opened) is not int or type(closed) is not int
            or type(observation.as_of_ms) is not int
            or type(observation.first_candidate_index) is not int
            or observation.first_candidate_index < 0
            or not barrier_plan.plan_created_at_ms <= opened <= closed <= observation.as_of_ms):
        raise DataValidationError("invalid PRE1 event timestamp bounds")

    if type(scenarios) not in (tuple, list) or not 1 <= len(scenarios) <= MAX_SCENARIOS:
        raise DataValidationError("one to sixteen explicit conditional scenarios required")
    rows = tuple(scenarios)
    if any(type(row) is not ConditionalFinancialScenario for row in rows):
        raise DataValidationError("conditional scenarios must use the typed contract")
    if len({row.scenario_id for row in rows}) != len(rows):
        raise DataValidationError("conditional scenario identities must be unique")
    # Renaming a target scenario does not cover an unordered stop/target hit.
    if (len(rows) != len(levels)
            or {row.assumed_barrier for row in rows} != set(levels)):
        raise DataValidationError(
            "explicit alternatives must cover each observed barrier exactly once"
        )
    # All alternatives represent the SAME already-open hypothetical position.
    # Varying quantity/currency/entry costs by exit branch would make the
    # conditional net outcomes economically incomparable (and may hide risk).
    # Exit prices, exit fees and funding accrued AFTER entry may legitimately
    # vary between explicit hypothetical outcomes.
    first = rows[0]
    shared_entry = (
        first.quote_currency, first.quantity_base_units,
        first.costs.entry_at_ms,
        first.costs.entry_hypothetical_notional_quote_units,
        first.costs.entry_fee_bps, first.costs.entry_adverse_slippage_bps,
    )
    for row in rows[1:]:
        row_entry = (
            row.quote_currency, row.quantity_base_units,
            row.costs.entry_at_ms,
            row.costs.entry_hypothetical_notional_quote_units,
            row.costs.entry_fee_bps, row.costs.entry_adverse_slippage_bps,
        )
        if row_entry != shared_entry:
            raise DataValidationError(
                "alternative financial branches must share the same "
                "position quantity, currency, entry time, notional and entry costs"
            )
    for row in rows:
        if (row.exchange, row.symbol, row.interval) != (observation.exchange, observation.symbol, observation.interval):
            raise DataValidationError("scenario identity does not match PRE1 observation")
        if row.direction is not barrier_plan.side or row.entry_price != barrier_plan.hypothetical_entry_price:
            raise DataValidationError("scenario side/entry differs from PRE1 barrier plan")
        # A candle's observed range may have touched a barrier before an entry
        # placed partway through that candle. The position must already exist
        # at its open; otherwise the range cannot support this exit premise.
        if not barrier_plan.plan_created_at_ms <= row.costs.entry_at_ms <= opened:
            raise DataValidationError(
                "synthetic position entry must be at or before first-hit candle open"
            )
        if not opened <= row.costs.exit_at_ms <= closed:
            raise DataValidationError("explicit exit event outside observed synthetic barrier candle")
    # Alternative exits refer to one position. A settlement before the
    # earliest hypothetical exit cannot disappear or change its event identity
    # merely because STOP/TARGET/LIQUIDATION is selected afterwards. The
    # notional itself may vary with an explicitly assumed intrabar mark path.
    earliest_exit_at_ms = min(row.costs.exit_at_ms for row in rows)

    def shared_funding_schedule(row: ConditionalFinancialScenario) -> tuple:
        return tuple(
            (source.event.event_id, source.event.event_at_ms,
             source.event.signed_funding_rate_bps, source.source_id,
             source.quote_currency, source.positive_rate_means)
            for source in row.funding_provenance
            if source.event.event_at_ms < earliest_exit_at_ms
        )

    # Funding events are a time-ordered ledger, not an unordered set.
    # Canonicalize declared event order before comparing alternative paths,
    # without changing the event amounts or PRE2 arithmetic.
    def ordered_shared_funding_schedule(row: ConditionalFinancialScenario) -> tuple:
        return tuple(sorted(shared_funding_schedule(row), key=lambda event: (event[1], event[0])))

    schedule = ordered_shared_funding_schedule(rows[0])
    if any(ordered_shared_funding_schedule(row) != schedule for row in rows[1:]):
        raise DataValidationError(
            "alternative financial branches must share funding event identity, "
            "time, rate and source before their earliest exit"
        )
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
                scenario_id=row.scenario_id, assumed_barrier=row.assumed_barrier,
                resolution=row.resolution, quote_currency=row.quote_currency,
                gross_price_movement_quote_units=movement,
                hypothetical_liquidation_loss_quote_units=loss,
                costs=cost, conditional_net_quote_units=movement - cost.total_signed_cost_units,
                ambiguity_branch_count=len(rows),
            ))
    return tuple(results)
