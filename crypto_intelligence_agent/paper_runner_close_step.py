"""J6/PRE4: one causal PAPER-only runner-close step; never broker execution.

The trigger belongs to RUNNER2's local synthetic replay. The reservation is
only AUTO4's existing transactional REDUCE_ONLY PAPER intent. There are no
exchange transports, price fills, asynchronous tasks, or real order senders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .market_data import DataValidationError
from .paper_position_inspection import inspect_paper_position
from .paper_position_reservations import PaperPositionBalance, SQLitePaperPositionJournal
from .paper_runner_close_preview import preview_paper_runner_close
from .paper_runner_trailing import PaperRunnerTrailPolicy
from .synthetic_manual_exit_replay import _utc_ms
from .synthetic_order_lifecycle import PaperOrderStatus


class PaperRunnerCloseStepState(str, Enum):
    RESERVED_PAPER_ONLY = "reserved_paper_only"
    PENDING_RECONCILIATION_PAPER_ONLY = "pending_reconciliation_paper_only"
    CLOSED_PAPER_ONLY = "closed_paper_only"
    TERMINAL_MANUAL_REVIEW_REQUIRED = "terminal_manual_review_required"


@dataclass(frozen=True)
class PaperRunnerCloseStepResult:
    state: PaperRunnerCloseStepState
    position_id: str
    runner_filled_units: Decimal
    runner_reserved_unfilled_units: Decimal
    runner_unallocated_units: Decimal
    runner_order_count: int
    created_intent_id: str | None

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def native_stop_verified(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    def sanitized_report(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "runner_filled_units": str(self.runner_filled_units),
            "runner_reserved_unfilled_units": str(self.runner_reserved_unfilled_units),
            "runner_unallocated_units": str(self.runner_unallocated_units),
            "runner_order_count": self.runner_order_count,
            "orders_sent": False,
            "native_stop_verified": False,
            "approved_for_live_use": False,
            "order_submission_enabled": False,
            "hypothetical_paper_only": True,
        }


def _existing_runner_state(
    balance: PaperPositionBalance,
) -> PaperRunnerCloseStepResult | None:
    if type(balance) is not PaperPositionBalance:
        raise DataValidationError("validated PAPER position balance required")
    runner_orders = tuple(x for x in balance.exit_orders if x.tranche_step == 0)
    if not runner_orders:
        return None
    if (balance.runner_floor_units <= 0 or
            balance.runner_filled_units + balance.runner_reserved_unfilled_units +
            balance.runner_unallocated_units != balance.runner_floor_units):
        raise DataValidationError("inconsistent runner reservation balance")
    unresolved = any(x.snapshot.requires_reconciliation for x in runner_orders)
    if unresolved or balance.runner_reserved_unfilled_units != 0:
        state = PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY
    elif (balance.runner_filled_units == balance.runner_floor_units
            and balance.confirmed_remaining_units == 0
            and all(x.snapshot.status is PaperOrderStatus.FILLED or
                    x.snapshot.status in (PaperOrderStatus.CANCELLED, PaperOrderStatus.REJECTED)
                    for x in runner_orders)):
        state = PaperRunnerCloseStepState.CLOSED_PAPER_ONLY
    else:
        # Never auto-retry a cancelled/rejected/partially-filled runner exit.
        state = PaperRunnerCloseStepState.TERMINAL_MANUAL_REVIEW_REQUIRED
    return PaperRunnerCloseStepResult(
        state=state,
        position_id=balance.position_id,
        runner_filled_units=balance.runner_filled_units,
        runner_reserved_unfilled_units=balance.runner_reserved_unfilled_units,
        runner_unallocated_units=balance.runner_unallocated_units,
        runner_order_count=len(runner_orders),
        created_intent_id=None,
    )


def step_durable_paper_runner_close(
    runner_path: str | Path,
    position_path: str | Path,
    position_id: str,
    *,
    policy: PaperRunnerTrailPolicy,
    as_of_ms: int,
) -> PaperRunnerCloseStepResult:
    """Persist at most one residual PAPER intent; no ACK, fill or exchange call.

    If any runner exit already exists, use AUTO4 as sole durable source and do
    NOT replay stale RUNNER2 after checkpoint drift. Cancellation, UNKNOWN and
    partial fills require reconciliation/manual review; no automatic retry.
    """
    cutoff = _utc_ms(as_of_ms, "PAPER runner-close step cutoff")
    before = inspect_paper_position(position_path, position_id)
    existing = _existing_runner_state(before.balance)
    if existing is not None:
        return existing
    candidate = preview_paper_runner_close(
        runner_path, position_path, position_id,
        policy=policy, as_of_ms=cutoff,
    )
    if candidate.source_checkpoint_ms != before.balance.as_of_ms:
        raise DataValidationError("runner position changed during step preview")
    # The already-existing PAPER journal is mandatory. No schema migration or
    # second order writer; reserve_exit uses BEGIN IMMEDIATE and checks all
    # quantities/other reservations before recording the intent.
    reserved = SQLitePaperPositionJournal(position_path).reserve_exit(
        position_id, 0, candidate.intent, as_of_ms=cutoff,
    )
    after = inspect_paper_position(position_path, position_id)
    if reserved != after.balance:
        raise DataValidationError("PAPER reservation differed from durable replay")
    selected = tuple(
        x for x in after.balance.exit_orders
        if x.tranche_step == 0 and x.intent.intent_id == candidate.intent.intent_id
    )
    if (len(selected) != 1 or
            selected[0].snapshot.status is not PaperOrderStatus.PENDING or
            selected[0].events or
            after.balance.runner_reserved_unfilled_units != candidate.intent.requested_units):
        raise DataValidationError("runner PAPER reservation not reproducible")
    return PaperRunnerCloseStepResult(
        state=PaperRunnerCloseStepState.RESERVED_PAPER_ONLY,
        position_id=position_id,
        runner_filled_units=after.balance.runner_filled_units,
        runner_reserved_unfilled_units=after.balance.runner_reserved_unfilled_units,
        runner_unallocated_units=after.balance.runner_unallocated_units,
        runner_order_count=1,
        created_intent_id=candidate.intent.intent_id,
    )
