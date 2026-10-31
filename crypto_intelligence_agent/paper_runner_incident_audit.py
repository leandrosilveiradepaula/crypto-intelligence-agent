"""J6/PRE6: read-only, fail-closed incident report for one PAPER runner.

This is an observer, not a reconciler or execution engine.  It deliberately
accepts only paths chosen by the caller and a single fixture position identity.
No writer is constructed, no schema is initialised and no network is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .market_data import DataValidationError
from .paper_position_inspection import PaperPositionInspection, inspect_paper_position
from .paper_runner_journal import load_paper_runner_journal
from .paper_runner_trailing import PaperRunnerTrailPolicy, PaperRunnerTrailState
from .synthetic_manual_exit_replay import _utc_ms
from .synthetic_order_lifecycle import PaperOrderStatus


class PaperIncidentSeverity(str, Enum):
    INFO = "INFO"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


class PaperIncidentCode(str, Enum):
    PARTIALS_INCOMPLETE = "PARTIALS_INCOMPLETE"
    RUNNER_UNPROTECTED = "RUNNER_UNPROTECTED"
    TRAILING_NOT_ACTIVATED = "TRAILING_NOT_ACTIVATED"
    TRAILING_TRACKING_HYPOTHETICAL = "TRAILING_TRACKING_HYPOTHETICAL"
    TRAILING_TRIGGERED_HYPOTHETICAL = "TRAILING_TRIGGERED_HYPOTHETICAL"
    RUNNER_EXIT_PENDING_RECONCILIATION = "RUNNER_EXIT_PENDING_RECONCILIATION"
    RUNNER_EXIT_UNKNOWN_RECONCILIATION = "RUNNER_EXIT_UNKNOWN_RECONCILIATION"
    RUNNER_EXIT_PARTIALLY_FILLED = "RUNNER_EXIT_PARTIALLY_FILLED"
    RUNNER_EXIT_CANCELLED_REVIEW = "RUNNER_EXIT_CANCELLED_REVIEW"
    RUNNER_CLOSED_PAPER_ONLY = "RUNNER_CLOSED_PAPER_ONLY"
    RUNNER_CHECKPOINT_SUPERSEDED = "RUNNER_CHECKPOINT_SUPERSEDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    JOURNAL_INVALID_OR_MISSING = "JOURNAL_INVALID_OR_MISSING"


@dataclass(frozen=True)
class PaperRunnerIncidentReport:
    """Sanitised, deterministic local observation; never an exchange fact."""
    code: PaperIncidentCode
    severity: PaperIncidentSeverity
    as_of_ms: int | None
    residual_paper_units: Decimal | None
    reserved_units: Decimal | None
    filled_units: Decimal | None
    reconciliation_required: bool
    evidence_available: tuple[str, ...]
    evidence_missing: tuple[str, ...]
    reason: str

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema": "paper_runner_incident_audit_v1",
            "mode": "offline_paper",
            "incident_code": self.code.value,
            "severity": self.severity.value,
            "as_of_ms": self.as_of_ms,
            "residual_paper_units": None if self.residual_paper_units is None else str(self.residual_paper_units),
            "reserved_units": None if self.reserved_units is None else str(self.reserved_units),
            "filled_units": None if self.filled_units is None else str(self.filled_units),
            "reconciliation_required": self.reconciliation_required,
            "evidence_available": list(self.evidence_available),
            "evidence_missing": list(self.evidence_missing),
            "reason": self.reason,
            "orders_sent": False,
            "native_stop_verified": False,
            "live_trading_authorized": False,
            "approved_for_live_use": False,
            "financial_pnl_available": False,
        }


def _report(code: PaperIncidentCode, severity: PaperIncidentSeverity, *, as_of_ms: int | None,
            residual: Decimal | None, reserved: Decimal | None, filled: Decimal | None,
            reconcile: bool, available: tuple[str, ...], missing: tuple[str, ...], reason: str) -> PaperRunnerIncidentReport:
    return PaperRunnerIncidentReport(code, severity, as_of_ms, residual, reserved, filled,
                                     reconcile, available, missing, reason)


def classify_inspected_paper_runner_incident(
    inspection: "PaperPositionInspection", *, runner_journal_selected: bool = False,
) -> PaperRunnerIncidentReport | None:
    """Pure classification of an ALREADY verified AUTO4 position snapshot.

    None means only that an explicit RUNNER2 observation still needs replay.
    Never fetches journals and never implies stop/native order confirmation.
    """
    if type(inspection) is not PaperPositionInspection or type(runner_journal_selected) is not bool:
        raise DataValidationError("verified PAPER inspection required")
    balance = inspection.balance
    base = ("auto4_position_replay", "synthetic_fixture_only")
    runner_orders = tuple(order for order in balance.exit_orders if order.tranche_step == 0)
    if runner_orders:
        latest = runner_orders[-1]
        if (balance.confirmed_remaining_units == 0
                and balance.runner_filled_units == balance.runner_floor_units
                and balance.runner_reserved_unfilled_units == 0
                and not any(o.snapshot.requires_reconciliation for o in runner_orders)):
            return _report(PaperIncidentCode.RUNNER_CLOSED_PAPER_ONLY, PaperIncidentSeverity.INFO,
                           as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                           reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                           reconcile=False, available=base + ("runner_exit_fill_fixture",), missing=("exchange_fill_confirmation",),
                           reason="Runner encerrado somente por eventos fictícios no diário PAPER.")
        if (latest.snapshot.status is PaperOrderStatus.CANCELLED
                and latest.snapshot.filled_total_units > 0):
            return _report(PaperIncidentCode.RUNNER_EXIT_PARTIALLY_FILLED, PaperIncidentSeverity.REVIEW,
                           as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                           reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                           reconcile=True, available=base + ("runner_exit_partial_fill_fixture", "runner_exit_cancel"), missing=("terminal_reconciliation",),
                           reason="Saída residual parcialmente preenchida e cancelada; não há reenvio automático.")
        if latest.snapshot.status in (PaperOrderStatus.CANCELLED, PaperOrderStatus.REJECTED):
            return _report(PaperIncidentCode.RUNNER_EXIT_CANCELLED_REVIEW, PaperIncidentSeverity.REVIEW,
                           as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                           reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                           reconcile=True, available=base + ("runner_exit_terminal_cancel",), missing=("reconciliation",),
                           reason="Saída residual cancelada; não há reenvio automático.")
        if latest.snapshot.status is PaperOrderStatus.UNKNOWN:
            return _report(PaperIncidentCode.RUNNER_EXIT_UNKNOWN_RECONCILIATION, PaperIncidentSeverity.BLOCKED,
                           as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                           reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                           reconcile=True, available=base + ("runner_exit_unknown",), missing=("reconciliation",),
                           reason="Estado UNKNOWN não prova rejeição nem preenchimento.")
        if (balance.runner_reserved_unfilled_units > 0
                and latest.snapshot.filled_total_units == 0
                and balance.runner_filled_units > 0):
            return _report(PaperIncidentCode.RUNNER_EXIT_PENDING_RECONCILIATION, PaperIncidentSeverity.REVIEW,
                           as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                           reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                           reconcile=True, available=base + ("auto4_runner_replacement_pending",),
                           missing=("reconciliation",),
                           reason="Saldo runner parcialmente preenchido tem nova reserva pendente; nao reenviar.")
        if balance.runner_filled_units > 0:
            return _report(PaperIncidentCode.RUNNER_EXIT_PARTIALLY_FILLED, PaperIncidentSeverity.REVIEW,
                           as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                           reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                           reconcile=True, available=base + ("runner_exit_partial_fill_fixture",), missing=("terminal_reconciliation",),
                           reason="Saída residual parcialmente preenchida apenas na simulação.")
        if runner_journal_selected:
            return _report(PaperIncidentCode.RUNNER_CHECKPOINT_SUPERSEDED, PaperIncidentSeverity.REVIEW,
                           as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                           reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                           reconcile=True, available=base + ("auto4_runner_reservation",),
                           missing=("reconciliation",),
                           reason="Reserva AUTO4 superou o checkpoint RUNNER2; não rearmar nem reenviar.")
        return _report(PaperIncidentCode.RUNNER_EXIT_PENDING_RECONCILIATION, PaperIncidentSeverity.REVIEW,
                       as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                       reserved=balance.runner_reserved_unfilled_units, filled=balance.runner_filled_units,
                       reconcile=True, available=base + ("auto4_runner_reservation",), missing=("reconciliation",),
                       reason="Saída runner PENDING/ACKNOWLEDGED no diário PAPER; requer reconciliação.")

    if any(order.snapshot.requires_reconciliation for order in balance.exit_orders):
        return _report(PaperIncidentCode.PARTIALS_INCOMPLETE, PaperIncidentSeverity.BLOCKED,
                       as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                       reserved=balance.reserved_unfilled_units, filled=balance.filled_exit_units,
                       reconcile=True, available=base + ("pending_partial_exit",), missing=("reconciled_partial_exit",),
                       reason="Saída parcial PAPER pendente, incerta ou não reconciliada.")
    if balance.confirmed_remaining_units == 0:
        return _report(PaperIncidentCode.RUNNER_CLOSED_PAPER_ONLY, PaperIncidentSeverity.INFO,
                       as_of_ms=balance.as_of_ms, residual=Decimal(0), reserved=Decimal(0), filled=balance.runner_filled_units,
                       reconcile=False, available=base, missing=("exchange_position_confirmation",),
                       reason="Posição encerrada somente no diário PAPER.")
    if balance.runner_floor_units == 0:
        return _report(PaperIncidentCode.PARTIALS_INCOMPLETE, PaperIncidentSeverity.INFO,
                       as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                       reserved=balance.reserved_unfilled_units, filled=balance.filled_exit_units,
                       reconcile=balance.reserved_unfilled_units > 0, available=base, missing=("runner_configuration",),
                       reason="Não existe runner residual configurado para esta posição fictícia.")
    if balance.confirmed_remaining_units > balance.runner_floor_units:
        return _report(PaperIncidentCode.PARTIALS_INCOMPLETE, PaperIncidentSeverity.REVIEW,
                       as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                       reserved=balance.reserved_unfilled_units, filled=balance.filled_exit_units,
                       reconcile=balance.reserved_unfilled_units > 0, available=base, missing=("confirmed_partial_exits",),
                       reason="Parciais ainda não confirmam o saldo residual do runner.")
    if not runner_journal_selected:
        return _report(PaperIncidentCode.RUNNER_UNPROTECTED, PaperIncidentSeverity.REVIEW,
                       as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                       reserved=Decimal(0), filled=balance.runner_filled_units,
                       reconcile=False, available=base + ("confirmed_runner",), missing=("runner2_observation", "native_stop"),
                       reason="Runner confirmado, sem observação RUNNER2 e sem proteção nativa comprovada.")
    return None


def audit_paper_runner_incident(
    position_journal_path: str | Path, position_id: str, *,
    runner_journal_path: str | Path | None = None,
    policy: PaperRunnerTrailPolicy | None = None,
    as_of_ms: int | None = None,
) -> PaperRunnerIncidentReport:
    """Audit exactly one selected PAPER position without writing either journal.

    A RUNNER2 journal needs both its pinned policy and an explicit cutoff.  Once
    AUTO4 contains a runner reservation, RUNNER2's old fingerprint is expected
    to be stale; it is reported as superseded and is never re-armed or replayed.
    """
    if ((runner_journal_path is None) != (policy is None)
            or (runner_journal_path is None) != (as_of_ms is None)):
        raise DataValidationError("RUNNER2 audit requires journal, policy and explicit cutoff together")
    if runner_journal_path is not None:
        if type(policy) is not PaperRunnerTrailPolicy:
            raise DataValidationError("typed RUNNER2 policy required")
        _utc_ms(as_of_ms, "RUNNER2 audit cutoff")
    try:
        inspection = inspect_paper_position(position_journal_path, position_id)
    except DataValidationError:
        return _report(PaperIncidentCode.JOURNAL_INVALID_OR_MISSING, PaperIncidentSeverity.BLOCKED,
                       as_of_ms=None, residual=None, reserved=None, filled=None, reconcile=True,
                       available=(), missing=("valid_auto4_position_journal",),
                       reason="AUTO4 local indisponível, ausente ou inválido; nenhum estado confiável pode ser inferido.")

    if as_of_ms is not None and inspection.balance.as_of_ms > as_of_ms:
        return _report(
            PaperIncidentCode.INSUFFICIENT_EVIDENCE,
            PaperIncidentSeverity.BLOCKED,
            as_of_ms=None, residual=None, reserved=None, filled=None,
            reconcile=True, available=(),
            missing=("causal_auto4_checkpoint",),
            reason="Checkpoint AUTO4 futuro; estado PAPER nao observavel neste cutoff.",
        )
    classified = classify_inspected_paper_runner_incident(
        inspection, runner_journal_selected=runner_journal_path is not None)
    if classified is not None:
        return classified
    balance = inspection.balance
    base = ("auto4_position_replay", "synthetic_fixture_only")
    try:
        trail = load_paper_runner_journal(runner_journal_path, position_journal_path, position_id,
                                          policy=policy, as_of_ms=as_of_ms)
    except DataValidationError:
        return _report(PaperIncidentCode.INSUFFICIENT_EVIDENCE, PaperIncidentSeverity.BLOCKED,
                       as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                       reserved=Decimal(0), filled=balance.runner_filled_units, reconcile=True,
                       available=base + ("confirmed_runner",), missing=("valid_runner2_journal",),
                       reason="RUNNER2 local indisponível, corrompido, stale ou incompatível; verificação bloqueada.")
    try:
        refreshed = inspect_paper_position(position_journal_path, position_id)
    except DataValidationError:
        return _report(PaperIncidentCode.JOURNAL_INVALID_OR_MISSING, PaperIncidentSeverity.BLOCKED,
                       as_of_ms=None, residual=None, reserved=None, filled=None,
                       reconcile=True, available=(), missing=("stable_auto4_position_journal",),
                       reason="AUTO4 local inválido durante a segunda leitura da auditoria.")
    if refreshed != inspection:
        return _report(PaperIncidentCode.INSUFFICIENT_EVIDENCE, PaperIncidentSeverity.BLOCKED,
                       as_of_ms=None, residual=None, reserved=None, filled=None,
                       reconcile=True, available=base, missing=("stable_auto4_checkpoint",),
                       reason="Posição PAPER mudou durante a leitura dos journals; tentar nova auditoria.")
    mapping = {
        PaperRunnerTrailState.NOT_ACTIVATED: (PaperIncidentCode.TRAILING_NOT_ACTIVATED, PaperIncidentSeverity.INFO, "Trailing fictício ainda não ativado."),
        PaperRunnerTrailState.TRACKING: (PaperIncidentCode.TRAILING_TRACKING_HYPOTHETICAL, PaperIncidentSeverity.INFO, "Trailing fictício em acompanhamento; não é stop nativo."),
        PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY: (PaperIncidentCode.TRAILING_TRIGGERED_HYPOTHETICAL, PaperIncidentSeverity.REVIEW, "Gatilho observado apenas em marks fictícias; não houve ordem real."),
    }
    code, severity, reason = mapping.get(trail.state, (PaperIncidentCode.INSUFFICIENT_EVIDENCE, PaperIncidentSeverity.BLOCKED, "Estado RUNNER2 não classificável."))
    return _report(code, severity, as_of_ms=balance.as_of_ms, residual=balance.confirmed_remaining_units,
                   reserved=Decimal(0), filled=balance.runner_filled_units, reconcile=severity is PaperIncidentSeverity.BLOCKED,
                   available=base + ("runner2_replay",), missing=("native_stop", "exchange_confirmation"), reason=reason)
