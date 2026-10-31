"""J6/PRE8: bounded all-or-nothing incident triage of selected PAPER positions.

Uses ONE validated AUTO4 snapshot through the pre-existing batch inspector.
It never discovers positions or journals, sums units across instruments, writes
SQLite, or equates fixture evidence with exchange safety or order execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .market_data import DataValidationError
from .paper_position_inspection import inspect_paper_positions
from .paper_runner_incident_audit import (
    PaperIncidentCode, PaperIncidentSeverity, PaperRunnerIncidentReport,
    classify_inspected_paper_runner_incident,
)
from .synthetic_manual_exit_replay import _utc_ms


_MAX_AGE_MS = 604_800_000  # Maximum accepted operator observation window: seven days.


@dataclass(frozen=True)
class PaperPortfolioIncidentSlot:
    ordinal: int
    incident: PaperRunnerIncidentReport

    def sanitized_report(self) -> dict[str, object]:
        evidence = self.incident.sanitized_report()
        return {
            "ordinal": self.ordinal,
            "incident_code": evidence["incident_code"],
            "severity": evidence["severity"],
            "checkpoint_ms": evidence["as_of_ms"],
            "reconciliation_required": evidence["reconciliation_required"],
            "residual_paper_units": evidence["residual_paper_units"],
            "reserved_units": evidence["reserved_units"],
            "filled_units": evidence["filled_units"],
            "evidence_available": evidence["evidence_available"],
            "evidence_missing": evidence["evidence_missing"],
            "reason": evidence["reason"],
        }


@dataclass(frozen=True)
class PaperPortfolioIncidentReport:
    as_of_ms: int
    max_checkpoint_age_ms: int
    selected_count: int
    slots: tuple[PaperPortfolioIncidentSlot, ...]
    batch_block_code: str | None = None

    @property
    def severity(self) -> PaperIncidentSeverity:
        if self.batch_block_code is not None:
            return PaperIncidentSeverity.BLOCKED
        if any(s.incident.severity is PaperIncidentSeverity.BLOCKED for s in self.slots):
            return PaperIncidentSeverity.BLOCKED
        if any(s.incident.severity is PaperIncidentSeverity.REVIEW for s in self.slots):
            return PaperIncidentSeverity.REVIEW
        return PaperIncidentSeverity.INFO

    def sanitized_report(self) -> dict[str, object]:
        count = lambda severity: sum(s.incident.severity is severity for s in self.slots)
        return {
            "schema_version": "paper_portfolio_incidents_v1",
            "mode": "offline_paper",
            "as_of_ms": self.as_of_ms,
            "max_checkpoint_age_ms": self.max_checkpoint_age_ms,
            "selected_count": self.selected_count,
            "observed_count": len(self.slots),
            "severity": self.severity.value,
            "batch_block_code": self.batch_block_code,
            "info_count": count(PaperIncidentSeverity.INFO),
            "review_count": count(PaperIncidentSeverity.REVIEW),
            "blocked_count": count(PaperIncidentSeverity.BLOCKED),
            "positions": [s.sanitized_report() for s in self.slots],
            "same_auto4_snapshot": self.batch_block_code is None,
            "native_stop_verified": False,
            "orders_sent": False,
            "live_trading_authorized": False,
            "approved_for_live_use": False,
            "financial_pnl_available": False,
            "exchange_reconciliation_confirmed": False,
            "portfolio_financial_totals_available": False,
        }


def audit_selected_paper_portfolio_incidents(
    position_journal_path: str | Path,
    position_ids: tuple[str, ...],
    *,
    as_of_ms: int,
    max_checkpoint_age_ms: int,
    opening_order_path: str | Path | None = None,
) -> PaperPortfolioIncidentReport:
    """Single snapshot of 1-128 *explicit* IDs; no partial result on bad data.

    Checkpoints outside the requested UTC age window block their slot. The
    optional AUTO2 cross-check is performed by the existing fail-closed reader.
    This remains a descriptive local PAPER audit, not a trade permission gate.
    """
    _utc_ms(as_of_ms, "portfolio incident cutoff")
    if (type(max_checkpoint_age_ms) is not int
            or not 1 <= max_checkpoint_age_ms <= _MAX_AGE_MS):
        raise DataValidationError("bounded positive PAPER checkpoint age required")
    if (type(position_ids) is not tuple
            or not 1 <= len(position_ids) <= 128
            or any(type(x) is not str for x in position_ids)
            or len(set(position_ids)) != len(position_ids)):
        raise DataValidationError("1-128 unique explicitly selected fixture IDs required")
    try:
        inspections = inspect_paper_positions(
            position_journal_path, position_ids,
            opening_order_path=opening_order_path,
        )
    except DataValidationError:
        return PaperPortfolioIncidentReport(
            as_of_ms, max_checkpoint_age_ms, len(position_ids), (),
            "INVALID_OR_INCONSISTENT_SELECTED_JOURNALS",
        )

    slots = []
    for ordinal, item in enumerate(inspections, start=1):
        b = item.balance
        if b.as_of_ms > as_of_ms or as_of_ms - b.as_of_ms > max_checkpoint_age_ms:
            incident = PaperRunnerIncidentReport(
                PaperIncidentCode.INSUFFICIENT_EVIDENCE, PaperIncidentSeverity.BLOCKED,
                b.as_of_ms, None, None, None, True,
                ("verified_auto4_snapshot",),
                ("causal_fresh_checkpoint",),
                "Checkpoint PAPER futuro ou antigo para o cutoff escolhido; observação bloqueada.",
            )
        else:
            incident = classify_inspected_paper_runner_incident(item)
            if incident is None:
                raise DataValidationError("non-RUNNER2 PAPER classification missing")
        slots.append(PaperPortfolioIncidentSlot(ordinal, incident))
    return PaperPortfolioIncidentReport(
        as_of_ms, max_checkpoint_age_ms, len(position_ids), tuple(slots),
    )
