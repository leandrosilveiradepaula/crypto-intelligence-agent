"""J6/PRE10: bounded, deterministic local PAPER transition alerts.

No network, file writes, clocks, account values or trading actions here.
Comparing observational snapshots never proves cross-journal atomicity.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from .market_data import DataValidationError
from .paper_operator_overview import PaperOperatorOverview
from .paper_position_inspection import PaperPositionInspection
from .paper_recovery_status import PaperRecoveryState, PaperRecoveryStatus


class PaperAlertKind(str, Enum):
    INITIAL = "INITIAL"
    STATUS_CHANGED = "STATUS_CHANGED"
    SELECTED_POSITIONS_CHANGED = "SELECTED_POSITIONS_CHANGED"


class PaperAlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO_HYPOTHETICAL_ONLY = "INFO_HYPOTHETICAL_ONLY"


@dataclass(frozen=True)
class PaperAlert:
    sample: int
    kind: PaperAlertKind
    severity: PaperAlertSeverity
    state: PaperRecoveryState
    reason: str


@dataclass(frozen=True)
class PaperAlertReport:
    sample_count: int
    events: tuple[PaperAlert, ...]
    final: PaperRecoveryStatus
    final_selected: tuple[PaperPositionInspection, ...] | None
    had_degraded_state: bool
    cross_database_atomic_snapshot_available: bool = False
    orders_sent: bool = False
    new_open_authorized: bool = False
    native_stop_verified: bool = False
    live_trading_authorized: bool = False
    financial_pnl_available: bool = False
    all_positions_enumerated: bool = False


def _verified_observation(
    observation: PaperRecoveryStatus | PaperOperatorOverview,
) -> tuple[PaperRecoveryStatus, tuple[PaperPositionInspection, ...] | None, tuple]:
    if type(observation) is PaperRecoveryStatus:
        status = observation
        selected = None
    elif type(observation) is PaperOperatorOverview:
        status = observation.recovery
        selected = observation.selected
        if (type(status) is not PaperRecoveryStatus
                or type(observation.selection_verified) is not bool
                or type(selected) is not tuple or len(selected) > 128
                or any(type(item) is not PaperPositionInspection for item in selected)
                or any(item.orders_sent or item.live_trading_authorized
                       or item.approved_for_live_use for item in selected)
                or any(getattr(observation, field) is not False for field in (
                    "cross_database_atomic_snapshot_available", "native_stop_verified",
                    "orders_sent", "new_open_authorized", "live_trading_authorized",
                    "financial_pnl_available", "all_positions_enumerated",
                ))
                or (not observation.selection_verified and selected)
                or (observation.selection_verified and len(selected) == 0)
                or (status.state is not PaperRecoveryState.UNVERIFIED
                    and not observation.selection_verified)):
            raise DataValidationError("invalid PAPER selected-position observation")
    else:
        raise DataValidationError("validated PAPER recovery observation required")

    if (type(status) is not PaperRecoveryStatus
            or type(status.state) is not PaperRecoveryState
            or type(status.reason) is not str
            or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", status.reason) is None
            or any(getattr(status, field) is not False for field in (
                "cross_database_atomic_snapshot_available", "native_stop_verified",
                "orders_sent", "live_trading_authorized", "new_open_authorized",
            ))
            or (status.state is PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY
                and (status.operator is None
                     or not status.operator.durable_cursor_present))
            or (status.state is PaperRecoveryState.UNVERIFIED and selected)):
        raise DataValidationError("untrusted PAPER recovery observation")

    # Internal equality only; never export IDs, symbols, balance quantities,
    # event timestamps, account data or hashes in the alert output.
    balances = tuple((
        item.balance.position_id,
        item.balance.initial_confirmed_units,
        item.balance.filled_exit_units,
        item.balance.reserved_unfilled_units,
        item.balance.confirmed_remaining_units,
        item.balance.unreserved_units,
        item.balance.runner_floor_units,
        tuple((
            order.snapshot.status,
            order.snapshot.filled_total_units,
            order.reserved_unfilled_units,
        ) for order in item.balance.exit_orders),
    ) for item in (selected or ()))
    return status, selected, balances


def summarize_paper_observations(
    observations: tuple[PaperRecoveryStatus | PaperOperatorOverview, ...],
) -> PaperAlertReport:
    """Collapse repeated identical risks; change of cursor alone is not an alert.

    Exactly one alert for the first sample, then at most one per changed
    state/reason or selected-position risk signature. No all-clear claim.
    """
    if type(observations) is not tuple or not 1 <= len(observations) <= 16:
        raise DataValidationError("1..16 bounded PAPER observations required")
    alerts: list[PaperAlert] = []
    prior_status: tuple[PaperRecoveryState, str] | None = None
    prior_balances: tuple | None = None
    degraded = False
    last_status = None
    last_selected = None
    for sample, raw in enumerate(observations, 1):
        status, selected, balance_signature = _verified_observation(raw)
        current_status = (status.state, status.reason)
        degraded |= status.state is not PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY
        kind = (
            PaperAlertKind.INITIAL if sample == 1 else
            PaperAlertKind.STATUS_CHANGED if current_status != prior_status else
            PaperAlertKind.SELECTED_POSITIONS_CHANGED
            if balance_signature != prior_balances else None
        )
        if kind is not None:
            severity = (
                PaperAlertSeverity.CRITICAL
                if status.state is PaperRecoveryState.UNVERIFIED
                else PaperAlertSeverity.WARNING
                if status.state is PaperRecoveryState.BLOCKED
                else PaperAlertSeverity.INFO_HYPOTHETICAL_ONLY
            )
            alerts.append(PaperAlert(sample, kind, severity, status.state, status.reason))
        prior_status = current_status
        prior_balances = balance_signature
        last_status = status
        last_selected = selected
    assert last_status is not None
    return PaperAlertReport(
        len(observations), tuple(alerts), last_status, last_selected, degraded,
    )
