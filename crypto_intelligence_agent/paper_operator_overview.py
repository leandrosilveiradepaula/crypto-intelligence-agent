"""J5/J6 PRE9: conservative composition of PAPER recovery and selected positions.

Independent read-only snapshots are repeated only to detect OBSERVED drift.
They cannot prove atomicity across AUTO2/AUTO4 or authorize any OPEN.
No enumeration, exchange, orders, financial aggregates or write paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .market_data import DataValidationError
from .paper_position_inspection import (
    PaperPositionInspection, inspect_paper_positions,
)
from .paper_recovery_status import (
    PaperRecoveryState, PaperRecoveryStatus,
    inspect_local_paper_recovery_status,
)
from .synthetic_position_state import _fixture_id


@dataclass(frozen=True)
class PaperOperatorOverview:
    recovery: PaperRecoveryStatus
    selected: tuple[PaperPositionInspection, ...]
    selection_verified: bool
    cross_database_atomic_snapshot_available: bool = False
    native_stop_verified: bool = False
    orders_sent: bool = False
    live_trading_authorized: bool = False
    new_open_authorized: bool = False
    all_positions_enumerated: bool = False
    financial_pnl_available: bool = False


def _unverified(reason: str) -> PaperOperatorOverview:
    return PaperOperatorOverview(
        PaperRecoveryStatus(PaperRecoveryState.UNVERIFIED, reason, None),
        (), False,
    )


def inspect_local_paper_operator_overview(
    order_journal_path: str | Path,
    position_journal_path: str | Path,
    position_ids: tuple[str, ...],
) -> PaperOperatorOverview:
    """Inspect 1..128 EXPLICIT fixture positions in addition to recovery state.

    Position selection is a subset, not a portfolio inventory. The two
    databases cannot offer an atomic cross-file snapshot; any observed
    mismatch rejects all selected data. No attempts to repair/reconcile.
    """
    if (type(position_ids) is not tuple
            or not 1 <= len(position_ids) <= 128
            or any(type(pid) is not str for pid in position_ids)
            or len(set(position_ids)) != len(position_ids)):
        raise DataValidationError("1..128 unique explicit PAPER fixture IDs required")
    for pid in position_ids:
        _fixture_id(pid)

    before = inspect_local_paper_recovery_status(
        order_journal_path, position_journal_path,
    )
    if before.state is PaperRecoveryState.UNVERIFIED:
        return PaperOperatorOverview(before, (), False)
    try:
        selected = inspect_paper_positions(position_journal_path, position_ids)
        after = inspect_local_paper_recovery_status(
            order_journal_path, position_journal_path,
        )
        checked_again = inspect_paper_positions(position_journal_path, position_ids)
    except (DataValidationError, OSError, ValueError):
        return _unverified("paper_selected_positions_unverified")
    if (after.state is PaperRecoveryState.UNVERIFIED
            or before != after or selected != checked_again):
        return _unverified("paper_overview_changed_during_inspection")
    return PaperOperatorOverview(before, selected, True)
