"""J4/AUTO7: causal J2 hypothesis -> atomic PAPER risk reservation, OFFLINE.

This is a fixture-only research bridge. It never consumes an ex-post PRE5/PRE7
label, performs a market request, invents a fill, or authorizes an exchange.
Paper journal rows are hypothetical intents, never broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .paper_order_store import PaperOpenRiskReservation, SQLitePaperOrderJournal
from .paper_open_health import PaperOpenHealth
from .paper_margin_preflight import (
    PaperMarginAssessment, PaperMarginPreflightRequest, assess_paper_margin_open,
)
from .paper_risk_gate import PaperRiskLimits, PaperRiskObservation, PaperRiskReason
from .synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, SyntheticEntryCandidate,
    research_synthetic_compression_breakouts,
)
from .synthetic_manual_exit_replay import _fixture_units, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from .synthetic_position_state import SyntheticSide


MAX_CLOSE_SAFETY_MS = 86_400_000


@dataclass(frozen=True)
class CausalPaperOpening:
    """One synthetic decision; rejected or PENDING, never a confirmed fill."""

    decision_at_ms: int
    candidate: SyntheticEntryCandidate | None
    intent: PaperOrderIntent | None
    reservation: PaperOpenRiskReservation | None
    health: PaperOpenHealth | None
    reason: str
    margin_assessment: PaperMarginAssessment | None = None

    @property
    def mode(self) -> str:
        return "offline_paper"

    @property
    def quality(self) -> str:
        return "synthetic_fixture_only"

    @property
    def paper_intent_reserved(self) -> bool:
        return self.reservation is not None and self.reservation.entry is not None

    @property
    def paper_intent_count(self) -> int:
        return int(self.paper_intent_reserved)

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
    def market_data_verified(self) -> bool:
        return False

    @property
    def real_pnl_available(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False


def _fixture_signal_key(candidate: SyntheticEntryCandidate) -> str:
    """Stable across the two candidate venues and parameter tweaks.

    Deliberately does not encode config, mark price, quantity or exchange
    execution venue: one source+strategy+candle+side is ONE PAPER hypothesis.
    Collisions between changed research parameters are safely deduplicated.
    """
    identity = "|".join((
        candidate.strategy_id, candidate.exchange, candidate.symbol,
        candidate.interval, candidate.side.value, str(candidate.closed_at_ms),
    ))
    return sha256(identity.encode("ascii")).hexdigest()[:24]


def prepare_causal_paper_open(
    candles: Sequence[ClosedCandle],
    *,
    strategy: CompressionBreakoutConfig,
    venue: PaperVenue,
    requested_units: Decimal,
    limits: PaperRiskLimits,
    observation: PaperRiskObservation,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
    margin_preflight: PaperMarginPreflightRequest | None = None,
) -> CausalPaperOpening:
    """Recompute a J2 hypothesis from the closed prefix, WITHOUT reserving.

    Only a hypothesis on the LAST closed candle is eligible. The decision
    clock must be exactly its close+safety. The independent PAPER risk
    observation explicitly supplies the fictional mark and exposures; the
    J2 candidate close is NEVER passed as a verified mark, fill, or notional.
    Reservation is deliberately deferred so a durable caller can hold ONE
    AUTO2 transaction across the risk gate and its PAPER cursor.
    """
    if (type(strategy) is not CompressionBreakoutConfig
            or type(venue) is not PaperVenue
            or type(limits) is not PaperRiskLimits
            or type(observation) is not PaperRiskObservation):
        raise DataValidationError("typed J2, PAPER venue and risk observation are required")
    if (margin_preflight is not None
            and type(margin_preflight) is not PaperMarginPreflightRequest):
        raise DataValidationError("PAPER margin preflight requires typed opt-in request")
    if type(requested_units) is not Decimal:
        raise DataValidationError("explicit Decimal PAPER requested units required")
    _fixture_units(requested_units)
    if type(close_safety_ms) is not int or not 0 <= close_safety_ms <= MAX_CLOSE_SAFETY_MS:
        raise DataValidationError("close safety must be bounded integer UTC-ms")
    now = _utc_ms(decision_at_ms, "decision_at_ms")
    cs = tuple(candles)
    if not cs or type(cs[-1]) is not ClosedCandle:
        raise DataValidationError("closed synthetic candle prefix required")
    if now != cs[-1].close_time_ms + close_safety_ms:
        raise DataValidationError("PAPER decision must use latest closed candle exact availability")
    # Validate the risk snapshot's identity even for a no-signal decision.
    # The research exchange is a fixture origin, not a venue eligibility proof.
    if observation.venue is not venue or observation.symbol != cs[-1].symbol:
        raise DataValidationError("PAPER risk observation venue/symbol mismatch")
    if observation.observed_at_ms > now:
        raise DataValidationError("future PAPER risk observations are prohibited")

    research = research_synthetic_compression_breakouts(
        cs, config=strategy, decision_at_ms=now,
        close_safety_ms=close_safety_ms,
    )
    fresh = tuple(
        candidate for candidate in research.candidates
        if candidate.closed_at_ms == cs[-1].close_time_ms
    )
    if len(fresh) > 1:
        raise DataValidationError("multiple hypotheses for latest closed candle")
    if not fresh:
        return CausalPaperOpening(now, None, None, None, None, "no_fresh_synthetic_hypothesis")
    candidate = fresh[0]
    if (candidate.earliest_research_at_ms != now
            or candidate.symbol != observation.symbol
            or candidate.side not in (SyntheticSide.LONG, SyntheticSide.SHORT)):
        raise DataValidationError("causal candidate differs from latest PAPER decision")

    token = _fixture_signal_key(candidate)
    intent = PaperOrderIntent(
        intent_id=f"fixture_open_{venue.value}_{token}",
        fixture_signal_id=f"fixture_signal_{token}",
        venue=venue, symbol=candidate.symbol, position_side=candidate.side,
        side=(PaperOrderSide.BUY if candidate.side is SyntheticSide.LONG
              else PaperOrderSide.SELL),
        effect=PaperOrderEffect.OPEN,
        requested_units=requested_units,
        created_at_ms=now,
    )
    assessment = None
    if margin_preflight is not None:
        # Only AFTER a latest-candle hypothesis produces an OPEN intent. All
        # checks are pure and occur before the AUTO2 reservation transaction.
        # The journal repeats its own health and PAPER RiskGate under lock.
        assessment = assess_paper_margin_open(
            intent, margin_preflight.settings, margin_preflight.margin_quote,
            margin_preflight.contract, limits, observation,
            decision_at_ms=now,
            max_contract_age_ms=margin_preflight.max_contract_age_ms,
        )
        if not assessment.allowed_for_paper_research_only:
            return CausalPaperOpening(
                now, candidate, None, None, None,
                "paper_margin_denied_" + assessment.reason.value,
                assessment,
            )
    return CausalPaperOpening(
        now, candidate, intent, None, None, "candidate_pending_paper_risk_gate",
        assessment,
    )


def _finish_causal_paper_open(
    prepared: CausalPaperOpening,
    health: PaperOpenHealth,
    receipt: PaperOpenRiskReservation | None,
) -> CausalPaperOpening:
    """Reuse AUTO7 response checks for legacy and durable atomic reservation."""
    if (type(prepared) is not CausalPaperOpening
            or prepared.intent is None
            or type(health) is not PaperOpenHealth):
        raise DataValidationError("invalid prepared PAPER reservation result")
    now, candidate, intent = (
        prepared.decision_at_ms, prepared.candidate, prepared.intent,
    )
    if not health.new_open_allowed:
        if receipt is not None:
            raise DataValidationError("health-denied PAPER OPEN must not reserve")
        return CausalPaperOpening(
            now, candidate, None, None, health,
            "paper_open_health_denied_" + health.reason,
            prepared.margin_assessment,
        )
    if receipt is None:
        raise DataValidationError("health allowed without PAPER risk decision")
    if not receipt.decision.allowed_for_paper_only:
        if receipt.entry is not None:
            raise DataValidationError("risk denied but PAPER journal reserved OPEN")
        return CausalPaperOpening(
            now, candidate, intent, receipt, health,
            "paper_risk_denied_" + receipt.decision.reason.value,
            prepared.margin_assessment,
        )
    if (receipt.decision.reason is not PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY
            or receipt.entry is None
            or receipt.entry.intent != intent
            or receipt.entry.events
            or receipt.entry.snapshot.status is not PaperOrderStatus.PENDING
            or receipt.entry.snapshot.filled_total_units != Decimal(0)):
        raise DataValidationError("unexpected PAPER reservation/fill state")
    return CausalPaperOpening(
        now, candidate, intent, receipt, health, "paper_open_intent_reserved_only",
        prepared.margin_assessment,
    )


def reserve_causal_paper_open(
    candles: Sequence[ClosedCandle], *,
    strategy: CompressionBreakoutConfig,
    venue: PaperVenue,
    requested_units: Decimal,
    limits: PaperRiskLimits,
    observation: PaperRiskObservation,
    journal: SQLitePaperOrderJournal,
    position_journal_path: str | Path,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
    margin_preflight: PaperMarginPreflightRequest | None = None,
) -> CausalPaperOpening:
    """Legacy AUTO7 entry point; health, risk and OPEN share AUTO2 lock."""
    if type(journal) is not SQLitePaperOrderJournal:
        raise DataValidationError("typed PAPER journal required")
    prepared = prepare_causal_paper_open(
        candles, strategy=strategy, venue=venue,
        requested_units=requested_units, limits=limits,
        observation=observation, decision_at_ms=decision_at_ms,
        close_safety_ms=close_safety_ms,
        margin_preflight=margin_preflight,
    )
    if prepared.intent is None:
        return prepared
    health, receipt = journal.reserve_open_if_paper_risk_with_health(
        prepared.intent, limits, observation,
        decision_at_ms=prepared.decision_at_ms,
        position_journal_path=position_journal_path,
    )
    return _finish_causal_paper_open(prepared, health, receipt)
