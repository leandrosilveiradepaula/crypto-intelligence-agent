"""D389: One PAPER intrahour event -> stop FIRST, then optional target.

There is exactly one existing AUTO4 position journal. This coordinator does
not connect to a venue, generate fills, or imply native protection. Its only
writes are the tested D387/D388 synthetic REDUCE_ONLY reservations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .bybit_public_ticker_state_d385 import BybitTickerQuote
from .market_data import DataValidationError
from .paper_intrahour_emergency_stop_d388 import (
    PaperEmergencyStopRule, PaperEmergencyStopState, PaperEmergencyStopResult,
    step_paper_emergency_stop,
)
from .paper_intrahour_target_step_d387 import (
    PaperIntrahourTargetPolicy, PaperAutoTargetState, PaperAutoTargetStep,
    step_paper_intrahour_target,
)


class PaperIntrahourDecision(str, Enum):
    STOP_RESERVED = "paper_stop_reserved"
    STOP_PENDING = "paper_stop_reconciliation_required"
    STOP_CLOSED = "paper_stop_fill_confirmed"
    STOP_UNRESOLVED = "paper_stop_unresolved"
    STOP_UNAVAILABLE = "paper_stop_data_unavailable"
    STOP_TERMINAL_REVIEW = "paper_stop_terminal_review_required"
    TARGET_RESERVED = "paper_target_reserved"
    TARGET_PENDING = "paper_target_reconciliation_required"
    TARGET_REVIEW = "paper_target_terminal_review_required"
    TARGET_HOLD = "paper_no_new_exit_intent"


_STOP_DECISIONS = {
    PaperEmergencyStopState.RESERVED: PaperIntrahourDecision.STOP_RESERVED,
    PaperEmergencyStopState.PENDING: PaperIntrahourDecision.STOP_PENDING,
    PaperEmergencyStopState.CLOSED: PaperIntrahourDecision.STOP_CLOSED,
    PaperEmergencyStopState.OLDER_ORDER_UNRESOLVED: PaperIntrahourDecision.STOP_UNRESOLVED,
    PaperEmergencyStopState.STALE: PaperIntrahourDecision.STOP_UNAVAILABLE,
    PaperEmergencyStopState.MANUAL_RECONCILIATION: PaperIntrahourDecision.STOP_TERMINAL_REVIEW,
}
_TARGET_DECISIONS = {
    PaperAutoTargetState.RESERVED: PaperIntrahourDecision.TARGET_RESERVED,
    PaperAutoTargetState.PENDING: PaperIntrahourDecision.TARGET_PENDING,
    PaperAutoTargetState.MANUAL_RECONCILIATION: PaperIntrahourDecision.TARGET_REVIEW,
    PaperAutoTargetState.HOLD: PaperIntrahourDecision.TARGET_HOLD,
    PaperAutoTargetState.STALE: PaperIntrahourDecision.STOP_UNAVAILABLE,
    PaperAutoTargetState.SPREAD: PaperIntrahourDecision.TARGET_HOLD,
    PaperAutoTargetState.DONE: PaperIntrahourDecision.TARGET_HOLD,
    PaperAutoTargetState.RUNNER: PaperIntrahourDecision.TARGET_HOLD,
}


@dataclass(frozen=True)
class PaperIntrahourCoordinatedStep:
    decision: PaperIntrahourDecision
    stop: PaperEmergencyStopResult
    target: PaperAutoTargetStep | None

    @property
    def created_intent_id(self) -> str | None:
        if self.target is not None:
            return self.target.intent_id
        return self.stop.created_intent_id

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "paper-intrahour-coordinator-d389-v1",
            "decision": self.decision.value,
            "stop_state": self.stop.state.value,
            "target_state": None if self.target is None else self.target.state.value,
            "stop_evaluated_first": True,
            "target_evaluated": self.target is not None,
            "new_intent_reserved": self.decision in {
                PaperIntrahourDecision.STOP_RESERVED,
                PaperIntrahourDecision.TARGET_RESERVED,
            },
            "real_fill_verified": False,
            "native_stop_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def step_paper_intrahour_coordinated(
    position_path: str | Path,
    position_id: str,
    *,
    stop_rule: PaperEmergencyStopRule,
    target_policy: PaperIntrahourTargetPolicy,
    quote: BybitTickerQuote,
    as_of_ms: int,
) -> PaperIntrahourCoordinatedStep:
    """Give stop absolute priority, including its data/reconciliation gate.

    A HOLD is the ONLY stop state permitting a planned partial target.
    A stale/unavailable stop must NOT fall through to a target even if that
    target sees favorable prices. A prior stop reservation also blocks all
    future targets. Both reserve operations use the existing AUTO4 journal's
    BEGIN IMMEDIATE and quantity checks.
    """
    if (type(stop_rule) is not PaperEmergencyStopRule or
            type(target_policy) is not PaperIntrahourTargetPolicy):
        raise DataValidationError("PAPER coordinator requires explicit policies")
    # Validate each policy before *any* write, including stop reservation.
    if stop_rule.max_quote_age_ms != target_policy.max_quote_age_ms:
        raise DataValidationError("PAPER coordinator age policy mismatch")
    if type(quote) is not BybitTickerQuote:
        raise DataValidationError("PAPER coordinator requires typed Bybit quote")
    stop = step_paper_emergency_stop(
        position_path, position_id,
        rule=stop_rule, quote=quote, as_of_ms=as_of_ms,
    )
    if stop.state is not PaperEmergencyStopState.HOLD:
        return PaperIntrahourCoordinatedStep(
            decision=_STOP_DECISIONS[stop.state], stop=stop, target=None,
        )
    target = step_paper_intrahour_target(
        position_path, position_id,
        policy=target_policy, quote=quote, as_of_ms=as_of_ms,
    )
    return PaperIntrahourCoordinatedStep(
        decision=_TARGET_DECISIONS[target.state], stop=stop, target=target,
    )
