"""D395: one Bybit PAPER tick -> stop FIRST, targets, then durable runner.

This composes, rather than replaces, D389 / RUNNER2 / RUNNER3 / PRE4 / AUTO4.
Runner marks belong to RUNNER2's existing independent research journal; the
only order reservations belong to AUTO4. No fills, venue orders, live mode,
credentials or new financial ledger are created here.

The bridge deliberately refuses to arm the runner until every planned tranche
has an explicit confirmed PAPER fill and no reservations remain. The static
stop always has first priority. Missing/unusable data NEVER arms a trailing
order, and a trigger only reserves a hypothetical REDUCE_ONLY intention.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from .market_data import DataGapError, DataValidationError
from .paper_intrahour_coordinator_d389 import (
    PaperIntrahourCoordinatedStep, PaperIntrahourDecision,
    step_paper_intrahour_coordinated,
)
from .paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from .paper_intrahour_target_step_d387 import (
    PaperIntrahourTargetPolicy, PaperAutoTargetState,
)
from .paper_position_inspection import inspect_paper_position
from .paper_runner_trailing import (
    PaperRunnerTrailPolicy, PaperRunnerMark, PaperRunnerTrailReport,
    PaperRunnerTrailState,
)
from .paper_runner_journal import (
    start_paper_runner_journal, append_paper_runner_mark,
)
from .paper_runner_close_step import (
    PaperRunnerCloseStepResult, PaperRunnerCloseStepState,
    step_durable_paper_runner_close,
)
from .synthetic_manual_exit_replay import _utc_ms
from .synthetic_order_lifecycle import PaperOrderStatus, PaperVenue


class PaperRunnerTickDecision(str, Enum):
    SKIPPED = "paper_trailing_not_eligible"
    ARMED = "paper_trailing_armed"
    TRACKING = "paper_trailing_tracking"
    EXIT_RESERVED = "paper_runner_close_reserved"
    EXIT_PENDING = "paper_runner_close_pending"
    EXIT_CLOSED = "paper_runner_close_confirmed"
    EXIT_REVIEW = "paper_runner_close_manual_review"


_CLOSE_STATES = {
    PaperRunnerCloseStepState.RESERVED_PAPER_ONLY:
        PaperRunnerTickDecision.EXIT_RESERVED,
    PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY:
        PaperRunnerTickDecision.EXIT_PENDING,
    PaperRunnerCloseStepState.CLOSED_PAPER_ONLY:
        PaperRunnerTickDecision.EXIT_CLOSED,
    PaperRunnerCloseStepState.TERMINAL_MANUAL_REVIEW_REQUIRED:
        PaperRunnerTickDecision.EXIT_REVIEW,
}


@dataclass(frozen=True)
class PaperIntrahourRunnerStep:
    coordinated: PaperIntrahourCoordinatedStep
    runner_decision: PaperRunnerTickDecision
    trail: PaperRunnerTrailReport | None = None
    runner_close: PaperRunnerCloseStepResult | None = None

    @property
    def created_intent_id(self) -> str | None:
        if self.runner_close is not None and self.runner_close.created_intent_id:
            return self.runner_close.created_intent_id
        return self.coordinated.created_intent_id

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "paper-intrahour-runner-bridge-d395-v1",
            "stop_first_decision": self.coordinated.decision.value,
            "runner_decision": self.runner_decision.value,
            "runner_trail_state": (
                None if self.trail is None else self.trail.state.value
            ),
            "runner_close_state": (
                None if self.runner_close is None
                else self.runner_close.state.value
            ),
            "runner_mark_count": (
                0 if self.trail is None else self.trail.observed_tick_count
            ),
            "runner_exit_reserved": (
                self.runner_decision is PaperRunnerTickDecision.EXIT_RESERVED
            ),
            "runner_live_protection_verified": False,
            "fills_verified": False,
            "native_stop_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def step_paper_intrahour_with_runner(
    position_path: str | Path,
    runner_path: str | Path,
    position_id: str,
    *,
    stop_rule: PaperEmergencyStopRule,
    target_policy: PaperIntrahourTargetPolicy,
    runner_policy: PaperRunnerTrailPolicy,
    quote: BybitTickerQuote,
    as_of_ms: int,
) -> PaperIntrahourRunnerStep:
    """Drive existing AUTO4 + RUNNER2 in the strictly causal safety order.

    STOP -> TARGET -> RUNNER is the exclusive order of evaluation.
    The mark at exchange UTC-ms is used for the runner. A fresh and validated
    quote cannot be replayed backwards to repaint runner highs/lows.
    Once a runner order is reserved, never append fresh marks nor retry it:
    the durable AUTO4 ledger drives PENDING/CLOSED/REVIEW instead.

    Fail-closed journal mismatches/clock gaps raise DataValidationError and do
    NOT create a second trailing journal or new exit order.
    """
    if (type(stop_rule) is not PaperEmergencyStopRule
            or type(target_policy) is not PaperIntrahourTargetPolicy
            or type(runner_policy) is not PaperRunnerTrailPolicy
            or type(quote) is not BybitTickerQuote
            or quote.source != SOURCE):
        raise DataValidationError("D395 requires typed public PAPER policies and quote")
    cutoff = _utc_ms(as_of_ms, "D395 cutoff")
    if (stop_rule.max_quote_age_ms != target_policy.max_quote_age_ms
            or runner_policy.max_last_tick_age_ms < target_policy.max_quote_age_ms):
        raise DataValidationError("D395 incompatible quote staleness budgets")

    coordinated = step_paper_intrahour_coordinated(
        position_path, position_id,
        stop_rule=stop_rule, target_policy=target_policy,
        quote=quote, as_of_ms=cutoff,
    )
    def outcome(
        decision: PaperRunnerTickDecision = PaperRunnerTickDecision.SKIPPED,
        trail: PaperRunnerTrailReport | None = None,
        close: PaperRunnerCloseStepResult | None = None,
    ) -> PaperIntrahourRunnerStep:
        return PaperIntrahourRunnerStep(coordinated, decision, trail, close)

    # A static mark stop, stale feed, UNKNOWN/partial older order, or a new
    # target reservation takes priority over *all* trailing decisions.
    if (coordinated.decision is not PaperIntrahourDecision.TARGET_HOLD
            or coordinated.target is None
            or coordinated.target.state not in (
                PaperAutoTargetState.DONE, PaperAutoTargetState.RUNNER,
            )):
        return outcome()
    b = inspect_paper_position(position_path, position_id).balance
    if (b.venue is not PaperVenue.BYBIT_V5
            or b.symbol != quote.symbol
            or b.plan_version != target_policy.plan_version
            or b.confirmed_remaining_units != b.runner_floor_units
            or b.runner_floor_units <= 0
            or any(t.filled_units != t.target_units
                   or t.reserved_unfilled_units != 0
                   or t.unallocated_units != 0 for t in b.tranches)):
        return outcome()
    runner_orders = tuple(o for o in b.exit_orders if o.tranche_step == 0)
    if len(runner_orders) > 1:
        raise DataValidationError("D395 multiple runner exit orders not supported")
    if runner_orders:
        # Subsequent ticks must never re-arm/re-trigger the journal.
        close = step_durable_paper_runner_close(
            runner_path, position_path, position_id,
            policy=runner_policy, as_of_ms=cutoff,
        )
        return outcome(_CLOSE_STATES[close.state], close=close)
    if (b.reserved_unfilled_units != 0
            or any(o.snapshot.requires_reconciliation for o in b.exit_orders)
            or any(o.snapshot.status in (
                PaperOrderStatus.CANCELLED, PaperOrderStatus.REJECTED,
            ) for o in b.exit_orders)):
        return outcome()

    if (cutoff < quote.received_at_ms
            or quote.received_at_ms - quote.exchange_at_ms < 0
            or quote.received_at_ms - quote.exchange_at_ms >
                runner_policy.max_last_tick_age_ms
            or cutoff - quote.received_at_ms > target_policy.max_quote_age_ms
            or quote.exchange_at_ms < b.as_of_ms
            or quote.mark_price <= 0
            or not quote.has_positive_book_depth):
        raise DataGapError("D395 missing causal fresh runner observation")
    mark = PaperRunnerMark(quote.symbol, quote.exchange_at_ms, quote.mark_price)
    path = Path(runner_path)
    if path.is_file():
        trail = append_paper_runner_mark(
            path, position_path, position_id, mark,
            policy=runner_policy, as_of_ms=cutoff,
        )
    else:
        # RUNNER2 uses O_EXCL and refuses a symlink or invalid path.
        trail = start_paper_runner_journal(
            path, position_path, position_id,
            policy=runner_policy, first_mark=mark, as_of_ms=cutoff,
        )
    if trail.state is PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY:
        close = step_durable_paper_runner_close(
            path, position_path, position_id,
            policy=runner_policy, as_of_ms=cutoff,
        )
        return outcome(_CLOSE_STATES[close.state], trail, close)
    return outcome(
        PaperRunnerTickDecision.ARMED
        if trail.state is PaperRunnerTrailState.NOT_ACTIVATED
        else PaperRunnerTickDecision.TRACKING,
        trail,
    )
