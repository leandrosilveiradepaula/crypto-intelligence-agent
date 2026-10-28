"""J6/PRE4: conservative, read-only multi-journal PAPER recovery visibility.

Independent SQLite reads cannot establish an atomic cross-file snapshot.
This report is diagnostic only and MUST NOT authorize new OPEN reservations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .market_data import DataValidationError
from .paper_open_health import audit_paper_open_health
from .paper_operator_status import PaperOperatorStatus, inspect_local_paper_operator_status
from .paper_position_inspection import _checked_path


class PaperRecoveryState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    BLOCKED = "BLOCKED"
    PAPER_FLAT_HYPOTHETICAL_ONLY = "PAPER_FLAT_HYPOTHETICAL_ONLY"


@dataclass(frozen=True)
class PaperRecoveryStatus:
    state: PaperRecoveryState
    reason: str
    operator: PaperOperatorStatus | None
    cross_database_atomic_snapshot_available: bool = False
    native_stop_verified: bool = False
    orders_sent: bool = False
    live_trading_authorized: bool = False
    new_open_authorized: bool = False


def inspect_local_paper_recovery_status(
    order_journal_path: str | Path,
    position_journal_path: str | Path,
    *,
    decision_at_ms: int | None = None,
) -> PaperRecoveryStatus:
    """Inspect existing fixture files without writing or trusting either as live.

    Invalid journals and races are reported as UNVERIFIED, not promoted to
    a healthy state. This function is never an authorization for OPEN.
    """
    try:
        orders = _checked_path(order_journal_path)
        positions = _checked_path(position_journal_path)
        if orders == positions:
            raise DataValidationError("independent PAPER journals required")
        operator = inspect_local_paper_operator_status(orders)
        health = audit_paper_open_health(
            orders, positions, decision_at_ms=decision_at_ms,
        )
    except (DataValidationError, OSError, ValueError):
        return PaperRecoveryStatus(
            PaperRecoveryState.UNVERIFIED, "paper_journal_unverified", None,
        )
    if operator.new_paper_open_paused:
        return PaperRecoveryStatus(
            PaperRecoveryState.BLOCKED, "paper_operator_paused", operator,
        )
    if operator.pending_or_unresolved_open_count or operator.unknown_open_requires_reconciliation:
        return PaperRecoveryStatus(
            PaperRecoveryState.BLOCKED, "paper_order_reconciliation_required", operator,
        )
    if not health.new_open_allowed:
        return PaperRecoveryStatus(
            PaperRecoveryState.BLOCKED, health.reason, operator,
        )
    if health.closed_flat_paper_only or not health.fills:
        return PaperRecoveryStatus(
            PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY,
            "paper_flat_not_live_verified", operator,
        )
    return PaperRecoveryStatus(
        PaperRecoveryState.UNVERIFIED, "paper_health_unverified", operator,
    )
