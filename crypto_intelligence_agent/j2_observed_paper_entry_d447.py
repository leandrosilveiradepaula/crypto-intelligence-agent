"""D447: observed Bybit J2 -> J3 cost screening -> durable PAPER OPEN.

Only local PENDING AUTO2 intentions. No FILL, AUTO4 position, authenticated
trading signal, exchange order, private API, or change to J1.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path

from .bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from .j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from .j2_observed_bybit_research import evaluate_observed_bybit_research
from .market_data import DataValidationError
from .paper_margin_preflight import PaperMarginPreflightRequest, assess_paper_margin_open
from .paper_order_store import SQLitePaperOrderJournal
from .paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from .synthetic_cost_scenarios import (
    BPS_DENOMINATOR, SyntheticCostScenario, _amount, _rate, evaluate_synthetic_costs,
)
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from .synthetic_position_state import SyntheticSide


@dataclass(frozen=True)
class ObservedPaperEntryPolicy:
    """Explicit assumptions; a successful screen never certifies liquidation."""

    target_distance_bps: Decimal
    stop_distance_bps: Decimal
    first_tranche_fraction: Decimal
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_adverse_slippage_bps: Decimal
    exit_adverse_slippage_bps: Decimal
    max_signal_age_ms: int = 120_000
    max_quote_age_ms: int = 3_000

    def __post_init__(self) -> None:
        for name in (
            "target_distance_bps", "stop_distance_bps",
            "entry_fee_bps", "exit_fee_bps",
            "entry_adverse_slippage_bps", "exit_adverse_slippage_bps",
        ):
            value = getattr(self, name)
            _rate(value, name, signed=False)
            if value > Decimal("1000"):
                raise DataValidationError("D447 cost/distance bound exceeded")
        if self.target_distance_bps <= 0 or self.stop_distance_bps <= 0:
            raise DataValidationError("D447 positive target and stop required")
        fraction = self.first_tranche_fraction
        if (type(fraction) is not Decimal or not fraction.is_finite()
                or not 0 < fraction <= 1 or fraction.as_tuple().exponent < -6):
            raise DataValidationError("D447 bounded first tranche required")
        if (type(self.max_signal_age_ms) is not int
                or not 1 <= self.max_signal_age_ms <= 600_000
                or type(self.max_quote_age_ms) is not int
                or not 100 <= self.max_quote_age_ms <= 3_000):
            raise DataValidationError("D447 bounded causal ages required")


@dataclass(frozen=True)
class ObservedPaperEntryResult:
    """Only a PENDING intent; no explicit/implicit execution anywhere."""

    status: str
    intent_id: str | None = None
    closed_at_ms: int | None = None
    hypothetical_first_target_net_quote: Decimal | None = None
    hypothetical_stop_margin_buffer_quote: Decimal | None = None

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "j2-j3-paper-entry-d447-v1",
            "status": self.status,
            "source_quality": "public_bybit_observed_unverified_paper_intent_only",
            "hypothetical_intent_id": self.intent_id,
            "hypothesis_closed_at_ms": self.closed_at_ms,
            "hypothetical_first_target_net_quote": (
                None if self.hypothetical_first_target_net_quote is None
                else format(self.hypothetical_first_target_net_quote, "f")
            ),
            "hypothetical_stop_margin_buffer_quote": (
                None if self.hypothetical_stop_margin_buffer_quote is None
                else format(self.hypothetical_stop_margin_buffer_quote, "f")
            ),
            "paper_intent_pending_only": self.status == "paper_open_intent_reserved_only",
            "fills_created": 0, "positions_created": 0,
            "market_data_authenticated": False,
            "venue_fees_funding_liquidation_verified": False,
            "financial_backtest_approved": False,
            "approved_for_signals": False, "approved_for_live_use": False,
            "orders_sent": False, "j1_accessed": False,
        }


def _cost_screen(
    quote: BybitTickerQuote, units: Decimal, margin_quote: Decimal,
    side: SyntheticSide, policy: ObservedPaperEntryPolicy, at_ms: int,
) -> tuple[Decimal, Decimal]:
    """Spread-inclusive hypothetical barriers; necessary, NEVER sufficient."""
    with localcontext(_EXACT_CONTEXT):
        long = side is SyntheticSide.LONG
        mark = quote.mark_price
        entry = quote.ask_price if long else quote.bid_price
        target = mark * (
            1 + policy.target_distance_bps / BPS_DENOMINATOR if long
            else 1 - policy.target_distance_bps / BPS_DENOMINATOR
        )
        stop = mark * (
            1 - policy.stop_distance_bps / BPS_DENOMINATOR if long
            else 1 + policy.stop_distance_bps / BPS_DENOMINATOR
        )
        if target <= 0 or stop <= 0:
            raise DataValidationError("D447 hypothetical brackets invalid")
        target_move = target - entry if long else entry - target
        stop_move = entry - stop if long else stop - entry
        if target_move <= 0 or stop_move <= 0:
            return Decimal("-1"), Decimal("-1")
        direction = ResearchDirection.LONG if long else ResearchDirection.SHORT

        def assumed_cost(qty: Decimal, exit_price: Decimal) -> Decimal:
            return evaluate_synthetic_costs(SyntheticCostScenario(
                direction=direction, entry_at_ms=at_ms, exit_at_ms=at_ms + 1,
                entry_hypothetical_notional_quote_units=qty * entry,
                exit_hypothetical_notional_quote_units=qty * exit_price,
                entry_fee_bps=policy.entry_fee_bps, exit_fee_bps=policy.exit_fee_bps,
                entry_adverse_slippage_bps=policy.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=policy.exit_adverse_slippage_bps,
            )).total_signed_cost_units

        tranche = units * policy.first_tranche_fraction
        net_target = tranche * target_move - assumed_cost(tranche, target)
        stop_buffer = margin_quote - units * stop_move - assumed_cost(units, stop)
        return net_target, stop_buffer


def reserve_observed_paper_entry(
    series: BybitClosedResearchSeries, *,
    config: CompressionBreakoutConfig,
    quote: BybitTickerQuote,
    observation: PaperRiskObservation,
    limits: PaperRiskLimits,
    margin: PaperMarginPreflightRequest,
    policy: ObservedPaperEntryPolicy,
    requested_units: Decimal,
    journal: SQLitePaperOrderJournal,
    position_journal_path: str | Path,
    now_ms: int,
    allow_hypothetical_paper_open: bool = False,
    allow_causal_rest_ws_warmup: bool = False,
) -> ObservedPaperEntryResult:
    """Causal entry PAPER; never reclassifies public candles as synthetic."""
    if (type(allow_hypothetical_paper_open) is not bool
            or type(allow_causal_rest_ws_warmup) is not bool):
        raise DataValidationError("D447 PAPER research opt-ins must be boolean")
    if type(allow_hypothetical_paper_open) is not bool:
        raise DataValidationError("D447 opt-in must be boolean")
    if not allow_hypothetical_paper_open:
        return ObservedPaperEntryResult("hypothetical_paper_open_optin_required")
    if (type(series) is not BybitClosedResearchSeries
            or type(config) is not CompressionBreakoutConfig
            or type(quote) is not BybitTickerQuote
            or type(observation) is not PaperRiskObservation
            or type(limits) is not PaperRiskLimits
            or type(margin) is not PaperMarginPreflightRequest
            or type(policy) is not ObservedPaperEntryPolicy
            or type(journal) is not SQLitePaperOrderJournal
            or not isinstance(position_journal_path, (str, Path))
            or not series.candles):
        raise DataValidationError("D447 typed observed J2/PAPER inputs required")
    units = _amount(requested_units, "D447 PAPER requested units")
    now = _utc_ms(now_ms, "D447 decision clock")
    close_at = series.candles[-1].close_time_ms
    research = evaluate_observed_bybit_research(
        series, config=config, decision_at_ms=close_at + 1, close_safety_ms=1,
        allow_causal_rest_ws_warmup=allow_causal_rest_ws_warmup,
    )
    if not research.hypotheses:
        return ObservedPaperEntryResult(
            "no_current_observed_hypothesis", closed_at_ms=close_at,
        )
    hypothesis = research.hypotheses[0]
    symbol = series.candles[-1].symbol
    if (quote.source != SOURCE or quote.symbol != symbol
            or observation.venue is not PaperVenue.BYBIT_V5
            or observation.symbol != symbol or observation.quote_currency != "USDT"
            or margin.contract.venue is not PaperVenue.BYBIT_V5
            or margin.contract.symbol != symbol
            or margin.contract.quote_currency != "USDT"):
        raise DataValidationError("D447 exact public Bybit/PAPER identity required")
    if (type(quote.exchange_at_ms) is not int
            or type(quote.received_at_ms) is not int
            or quote.exchange_at_ms < close_at + 1
            or quote.received_at_ms < quote.exchange_at_ms
            or quote.received_at_ms > now
            or now - (close_at + 1) > policy.max_signal_age_ms
            or quote.received_at_ms - quote.exchange_at_ms > policy.max_quote_age_ms
            or now - quote.exchange_at_ms > policy.max_quote_age_ms
            or now - quote.received_at_ms > policy.max_quote_age_ms):
        return ObservedPaperEntryResult(
            "observed_ticker_or_signal_stale", closed_at_ms=close_at,
        )
    for name in (
        "mark_price", "last_price", "index_price", "bid_price",
        "ask_price", "bid_size", "ask_size",
    ):
        _amount(getattr(quote, name), "D447 " + name)
    if (not quote.has_positive_book_depth
            or quote.bid_price > quote.ask_price
            or observation.observed_at_ms != quote.received_at_ms
            or observation.mark_price_quote != quote.mark_price):
        raise DataValidationError("D447 fresh independent PAPER mark/BBO required")
    # One ID per symbol+closed bar, not per mutable user policy or side.
    token = sha256((
        "d447-observed-compression-bybit-v1|" + symbol + "|" + str(close_at)
    ).encode("ascii")).hexdigest()[:24]
    intent = PaperOrderIntent(
        intent_id="fixture_observed_open_" + token,
        fixture_signal_id="fixture_observed_signal_" + token,
        venue=PaperVenue.BYBIT_V5, symbol=symbol,
        position_side=hypothesis.side,
        side=PaperOrderSide.BUY if hypothesis.side is SyntheticSide.LONG
             else PaperOrderSide.SELL,
        effect=PaperOrderEffect.OPEN, requested_units=units, created_at_ms=now,
    )
    first_net, buffer = _cost_screen(
        quote, units, margin.margin_quote, hypothesis.side, policy, now,
    )
    measures = {
        "closed_at_ms": close_at,
        "hypothetical_first_target_net_quote": first_net,
        "hypothetical_stop_margin_buffer_quote": buffer,
    }
    if first_net <= 0:
        return ObservedPaperEntryResult("hypothetical_target_cost_veto", **measures)
    if buffer <= 0:
        return ObservedPaperEntryResult("hypothetical_stop_margin_veto", **measures)
    assessment = assess_paper_margin_open(
        intent, margin.settings, margin.margin_quote, margin.contract,
        limits, observation, decision_at_ms=now,
        max_contract_age_ms=margin.max_contract_age_ms,
    )
    if not assessment.allowed_for_paper_research_only:
        return ObservedPaperEntryResult(
            "paper_margin_denied_" + assessment.reason.value, **measures,
        )
    health, receipt = journal.reserve_open_if_paper_risk_with_health(
        intent, limits, observation, decision_at_ms=now,
        position_journal_path=position_journal_path, margin_assessment=assessment,
    )
    if not health.new_open_allowed:
        return ObservedPaperEntryResult(
            "paper_health_denied_" + health.reason, **measures,
        )
    if receipt is None or not receipt.decision.allowed_for_paper_only:
        if receipt is not None and receipt.entry is not None:
            raise DataValidationError("D447 risk-denied PAPER OPEN inserted")
        return ObservedPaperEntryResult(
            "paper_risk_denied_" + (
                receipt.decision.reason.value if receipt is not None
                else "missing_decision"
            ), **measures,
        )
    entry = receipt.entry
    if (entry is None or entry.intent != intent or entry.events
            or entry.snapshot.status is not PaperOrderStatus.PENDING
            or entry.snapshot.filled_total_units != Decimal(0)):
        raise DataValidationError("D447 expected only a pending PAPER intent")
    return ObservedPaperEntryResult(
        "paper_open_intent_reserved_only", intent_id=intent.intent_id, **measures,
    )
