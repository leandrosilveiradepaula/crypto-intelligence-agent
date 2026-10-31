"""J6/PRE7 deterministic, finite incident matrix for existing PAPER contracts.

This laboratory creates disposable AUTO4/RUNNER2 fixtures and invokes the real
reservation, replay and PRE6 audit code.  It is intentionally not a scheduler,
exchange simulator, order sender or prospective paper session.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
import tempfile
import sqlite3
from unittest.mock import patch

from .market_data import DataValidationError
from .paper_position_reservations import SQLitePaperPositionJournal
from .paper_runner_close_step import PaperRunnerCloseStepState, step_durable_paper_runner_close
from . import paper_runner_incident_audit as _incident_module
from .paper_runner_incident_audit import (
    PaperIncidentCode, PaperRunnerIncidentReport, audit_paper_runner_incident,
)
from .paper_runner_journal import append_paper_runner_mark, start_paper_runner_journal
from .paper_runner_trailing import PaperRunnerMark, PaperRunnerTrailPolicy
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperVenue,
)
from .synthetic_partial_exits import ExitBasis, SyntheticExitPlan, SyntheticExitTranche
from .synthetic_position_state import SyntheticSide

D = Decimal
_T = 1_793_100_000_000
_POLICY = PaperRunnerTrailPolicy(D(100), D(50), 5_000, 5_000)


@dataclass(frozen=True)
class PaperIncidentScenarioResult:
    scenario_id: str
    expected_outcome: str
    observed_outcome: str
    validation_status: str
    incident_code: str
    severity: str
    checkpoint_ms: int | None
    reconciliation_required: bool
    reason: str

    def sanitized_report(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "expected_outcome": self.expected_outcome,
            "observed_outcome": self.observed_outcome,
            "validation_status": self.validation_status,
            "incident_code": self.incident_code,
            "severity": self.severity,
            "checkpoint_ms": self.checkpoint_ms,
            "reconciliation_required": self.reconciliation_required,
            "reason": self.reason,
            "orders_sent": False,
            "native_stop_verified": False,
            "live_trading_authorized": False,
            "approved_for_live_use": False,
            "financial_pnl_available": False,
        }


@dataclass(frozen=True)
class PaperIncidentMatrixReport:
    scenarios: tuple[PaperIncidentScenarioResult, ...]

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "paper_incident_matrix_v1",
            "mode": "offline_paper",
            "deterministic_fixture_clock": True,
            "temporary_journals_removed": True,
            "scenario_count": len(self.scenarios),
            "pass_count": sum(x.validation_status == "PASS" for x in self.scenarios),
            "blocked_expected_count": sum(x.validation_status == "BLOCKED_EXPECTED" for x in self.scenarios),
            "failure_count": sum(x.validation_status == "FAIL" for x in self.scenarios),
            "scenarios": [x.sanitized_report() for x in self.scenarios],
            "j6_readiness": _j6_readiness_matrix(self.scenarios),
            "orders_sent": False,
            "native_stop_verified": False,
            "live_trading_authorized": False,
            "approved_for_live_use": False,
            "financial_pnl_available": False,
        }


def _j6_readiness_matrix(scenarios: tuple[PaperIncidentScenarioResult, ...]) -> list[dict[str, str]]:
    """Release gates cannot be marked proven if their local scenarios failed."""
    passed = {x.scenario_id for x in scenarios if x.validation_status in ("PASS", "BLOCKED_EXPECTED")}
    # Integrity failures elsewhere in the same run invalidate aggregate
    # readiness claims even when a narrower fixture happened to pass.
    complete_run = bool(scenarios) and all(
        x.validation_status in ("PASS", "BLOCKED_EXPECTED") for x in scenarios)
    def evidence_state(*ids: str) -> str:
        return ("COMPROVADO_OFFLINE" if complete_run and all(x in passed for x in ids)
                else "NAO_COMPROVADO_NESTA_EXECUCAO")
    return [
        {"criterion": "persistencia_e_recovery_paper", "state": evidence_state("healthy_restart_fill", "before_reservation"), "evidence": "AUTO4/RUNNER2 replay e matriz finita"},
        {"criterion": "idempotencia_e_reserva_local", "state": evidence_state("healthy_restart_fill", "concurrent_single_reservation"), "evidence": "lock SQLite e cenarios concorrentes"},
        {"criterion": "unknown_parcial_cancelamento", "state": evidence_state("unknown_blocks_reconciliation", "partial_cancel_requires_review"), "evidence": "auditor fail-closed"},
        {"criterion": "feed_prospectivo_e_paper_24h", "state": "PENDENTE", "evidence": "requer dados reais validados"},
        {"criterion": "reconciliacao_exchange_e_stop_nativo", "state": "BLOQUEADO", "evidence": "sem conta, credencial ou gate de venue"},
        {"criterion": "funding_slippage_liquidacao_reais", "state": "PENDENTE", "evidence": "J3 e contratos de venue nao homologados"},
        {"criterion": "testnet_e_live", "state": "BLOQUEADO", "evidence": "autorizacao humana e gates de producao ausentes"},
    ]


def _plan() -> SyntheticExitPlan:
    return SyntheticExitPlan(D(100), tuple(SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(x)) for x in ("50", "60", "70")), D(6))


def _report(scenario_id: str, expected: str, audit: PaperRunnerIncidentReport,
            *, invariants_hold: bool = True) -> PaperIncidentScenarioResult:
    """Only evidence AND independent ledger invariants can satisfy an expectation."""
    is_blocked = expected.startswith("BLOCKED:")
    expected_code = expected.split(":", 1)[1] if is_blocked else expected
    correct_code = audit.code.value == expected_code
    if is_blocked:
        valid = (correct_code and audit.severity.value == "BLOCKED"
                 and audit.reconciliation_required and invariants_hold)
        status = "BLOCKED_EXPECTED" if valid else "FAIL"
    else:
        # Exact severity/reconciliation expectations prevent a benign-looking
        # classification from satisfying an incident gate by code alone.
        expected_flags = {
            PaperIncidentCode.RUNNER_CLOSED_PAPER_ONLY.value: ("INFO", False),
            PaperIncidentCode.TRAILING_TRIGGERED_HYPOTHETICAL.value: ("REVIEW", False),
            PaperIncidentCode.RUNNER_EXIT_PARTIALLY_FILLED.value: ("REVIEW", True),
            PaperIncidentCode.RUNNER_CHECKPOINT_SUPERSEDED.value: ("REVIEW", True),
        }
        expected_severity, expected_reconcile = expected_flags.get(expected_code, (None, None))
        valid = (correct_code and expected_severity is not None
                 and audit.severity.value == expected_severity
                 and audit.reconciliation_required is expected_reconcile
                 and invariants_hold)
        status = "PASS" if valid else "FAIL"
    return PaperIncidentScenarioResult(scenario_id, expected, audit.code.value, status,
                                       audit.code.value, audit.severity.value, audit.as_of_ms,
                                       audit.reconciliation_required, audit.reason)


def _fixture(root: Path, suffix: str) -> tuple[SQLitePaperPositionJournal, Path, Path, str]:
    positions, runner = root / (suffix + "-positions.sqlite"), root / (suffix + "-runner.sqlite")
    store = SQLitePaperPositionJournal(positions)
    position_id = "fixture_pre7_" + suffix
    opening = PaperOrderIntent("fixture_pre7_open_" + suffix, "fixture_pre7_signal_" + suffix,
                              PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
                              PaperOrderSide.BUY, PaperOrderEffect.OPEN, D(100), _T)
    current = store.create_position(position_id=position_id, opening_intent=opening,
                                    opening_events=(PaperOrderEvent("fixture_pre7_open_fill_" + suffix, PaperOrderEventKind.FILL, _T + 1, D(100)),),
                                    exit_plan=_plan(), plan_version="fixture_pre7_v1",
                                    synthetic_lot_step_units=D(1), as_of_ms=_T + 1)
    for i, units in enumerate((50, 30, 14), 1):
        intent = PaperOrderIntent("fixture_pre7_exit_%s_%s" % (suffix, i), "fixture_pre7_exit_signal_%s_%s" % (suffix, i),
                                  opening.venue, opening.symbol, SyntheticSide.LONG, PaperOrderSide.SELL,
                                  PaperOrderEffect.REDUCE_ONLY, D(units), current.as_of_ms,
                                  max_reducible_units=current.confirmed_remaining_units)
        current = store.reserve_exit(position_id, i, intent, as_of_ms=current.as_of_ms)
        current = store.append_exit_events(position_id, intent.intent_id,
                                           (PaperOrderEvent("fixture_pre7_fill_%s_%s" % (suffix, i), PaperOrderEventKind.FILL, current.as_of_ms + 1, D(units)),),
                                           as_of_ms=current.as_of_ms + 1)
    return store, positions, runner, position_id


def _trigger(runner: Path, positions: Path, position_id: str) -> None:
    start_paper_runner_journal(runner, positions, position_id, policy=_POLICY,
                               first_mark=PaperRunnerMark("BTCUSDT", _T + 100, D(100)), as_of_ms=_T + 100)
    for n, price in enumerate((D(102), D(103), D(102)), 1):
        append_paper_runner_mark(runner, positions, position_id, PaperRunnerMark("BTCUSDT", _T + 100 + 1000 * n, price), policy=_POLICY, as_of_ms=_T + 100 + 1000 * n)


def _concurrent_reservation(runner: Path, positions: Path, position_id: str) -> PaperRunnerCloseStepState | None:
    """A stale preview is an expected losing race, never a laboratory failure."""
    try:
        return step_durable_paper_runner_close(runner, positions, position_id,
                                               policy=_POLICY, as_of_ms=_T + 3100).state
    except DataValidationError:
        return None


def run_paper_incident_matrix() -> PaperIncidentMatrixReport:
    """Run isolated fixtures; mismatches become FAIL, unexpected errors fail closed."""
    results: list[PaperIncidentScenarioResult] = []
    with tempfile.TemporaryDirectory(prefix="cia_j6_pre7_") as directory:
        root = Path(directory)
        # Healthy trigger/reservation/restart/fill chain.
        store, pos, runner, pid = _fixture(root, "healthy")
        _trigger(runner, pos, pid)
        first = step_durable_paper_runner_close(runner, pos, pid, policy=_POLICY, as_of_ms=_T + 3100)
        replay = step_durable_paper_runner_close(runner, pos, pid, policy=_POLICY, as_of_ms=_T + 3200)
        pending = store.load(pid)
        pending_ok = (first.state is PaperRunnerCloseStepState.RESERVED_PAPER_ONLY
                      and replay.state is PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY
                      and replay.created_intent_id is None and first.created_intent_id is not None
                      and pending.runner_reserved_unfilled_units == D(6)
                      and pending.runner_filled_units == 0
                      and len([o for o in pending.exit_orders if o.tranche_step == 0]) == 1)
        store.append_exit_events(pid, first.created_intent_id, (PaperOrderEvent("fixture_pre7_runner_fill", PaperOrderEventKind.FILL, _T + 3201, D(6)),), as_of_ms=_T + 3201)
        complete = store.load(pid)
        results.append(_report("healthy_restart_fill", PaperIncidentCode.RUNNER_CLOSED_PAPER_ONLY.value,
                               audit_paper_runner_incident(pos, pid),
                               invariants_hold=(pending_ok and complete.confirmed_remaining_units == 0
                                   and complete.filled_exit_units == D(100)
                                   and complete.runner_filled_units == D(6)
                                   and complete.runner_reserved_unfilled_units == 0)))

        # A pre-commit failure leaves no runner order; retry can safely reserve once.
        store, pos, runner, pid = _fixture(root, "precommit")
        _trigger(runner, pos, pid)
        untouched = store.load(pid)
        results.append(_report("before_reservation", PaperIncidentCode.TRAILING_TRIGGERED_HYPOTHETICAL.value,
                               audit_paper_runner_incident(pos, pid, runner_journal_path=runner, policy=_POLICY, as_of_ms=_T + 3100),
                               invariants_hold=(untouched.runner_filled_units == 0
                                                and untouched.runner_reserved_unfilled_units == 0
                                                and not any(o.tranche_step == 0 for o in untouched.exit_orders))))

        store, pos, runner, pid = _fixture(root, "unknown")
        _trigger(runner, pos, pid)
        reserved = step_durable_paper_runner_close(runner, pos, pid, policy=_POLICY, as_of_ms=_T + 3100)
        store.append_exit_events(pid, reserved.created_intent_id, (PaperOrderEvent("fixture_pre7_unknown", PaperOrderEventKind.UNKNOWN, _T + 3101),), as_of_ms=_T + 3101)
        uncertain = store.load(pid)
        results.append(_report("unknown_blocks_reconciliation", "BLOCKED:" + PaperIncidentCode.RUNNER_EXIT_UNKNOWN_RECONCILIATION.value,
                               audit_paper_runner_incident(pos, pid),
                               invariants_hold=(uncertain.runner_reserved_unfilled_units == D(6)
                                                and uncertain.runner_filled_units == 0)))

        store, pos, runner, pid = _fixture(root, "partial")
        _trigger(runner, pos, pid)
        reserved = step_durable_paper_runner_close(runner, pos, pid, policy=_POLICY, as_of_ms=_T + 3100)
        store.append_exit_events(pid, reserved.created_intent_id, (PaperOrderEvent("fixture_pre7_partial", PaperOrderEventKind.FILL, _T + 3101, D(2)), PaperOrderEvent("fixture_pre7_cancel", PaperOrderEventKind.CANCELLED, _T + 3102)), as_of_ms=_T + 3102)
        partial = store.load(pid)
        results.append(_report("partial_cancel_requires_review", PaperIncidentCode.RUNNER_EXIT_PARTIALLY_FILLED.value,
                               audit_paper_runner_incident(pos, pid),
                               invariants_hold=(partial.runner_filled_units == D(2)
                                                and partial.runner_reserved_unfilled_units == 0
                                                and partial.runner_unallocated_units == D(4)
                                                and partial.confirmed_remaining_units == D(4))))

        store, pos, runner, pid = _fixture(root, "concurrent")
        _trigger(runner, pos, pid)
        with ThreadPoolExecutor(max_workers=2) as pool:
            states = tuple(pool.map(lambda _: _concurrent_reservation(runner, pos, pid), range(2)))
        audit = audit_paper_runner_incident(pos, pid, runner_journal_path=runner, policy=_POLICY, as_of_ms=_T + 3200)
        concurrent = store.load(pid)
        runner_orders = [o for o in concurrent.exit_orders if o.tranche_step == 0]
        # Both callers can legitimately return RESERVED on the SAME
        # deterministic intent (AUTO4 idempotent replay). Require one unique
        # durable reservation, not exactly one API return value.
        one_reservation = (
            PaperRunnerCloseStepState.RESERVED_PAPER_ONLY in states
            and all(state in (
                None, PaperRunnerCloseStepState.RESERVED_PAPER_ONLY,
                PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY,
            ) for state in states)
            and concurrent.runner_reserved_unfilled_units == D(6)
            and concurrent.runner_filled_units == 0
            and concurrent.confirmed_remaining_units == D(6)
            and len(runner_orders) == 1
            and runner_orders[0].intent.requested_units == D(6)
            and runner_orders[0].snapshot.filled_total_units == 0
            and runner_orders[0].events == ())
        results.append(_report("concurrent_single_reservation", PaperIncidentCode.RUNNER_CHECKPOINT_SUPERSEDED.value,
                               audit, invariants_hold=one_reservation))

        store, pos, runner, pid = _fixture(root, "incompatible")
        _trigger(runner, pos, pid)
        wrong = PaperRunnerTrailPolicy(D(200), D(50), 5_000, 5_000)
        results.append(_report("policy_incompatible", "BLOCKED:" + PaperIncidentCode.INSUFFICIENT_EVIDENCE.value,
                               audit_paper_runner_incident(pos, pid, runner_journal_path=runner, policy=wrong, as_of_ms=_T + 3100)))

        store, pos, runner, pid = _fixture(root, "corrupt")
        with closing(sqlite3.connect(pos)) as con, con:
            con.execute("UPDATE paper_positions SET digest='bad' WHERE position_id=?", (pid,))
        results.append(_report("corrupt_auto4_digest", "BLOCKED:" + PaperIncidentCode.JOURNAL_INVALID_OR_MISSING.value,
                               audit_paper_runner_incident(pos, pid)))

        # A real trigger journal becomes stale when its last mark is too old.
        store, pos, runner, pid = _fixture(root, "stale")
        _trigger(runner, pos, pid)
        stale = audit_paper_runner_incident(
            pos, pid, runner_journal_path=runner, policy=_POLICY, as_of_ms=_T + 10_000)
        results.append(_report("stale_runner2_cutoff",
                               "BLOCKED:" + PaperIncidentCode.INSUFFICIENT_EVIDENCE.value,
                               stale, invariants_hold=not any(
                                   o.tranche_step == 0 for o in store.load(pid).exit_orders)))

        # No RUNNER2 file is created implicitly by a read-only audit.
        store, pos, runner, pid = _fixture(root, "missingrunner")
        missing_runner = audit_paper_runner_incident(
            pos, pid, runner_journal_path=runner, policy=_POLICY, as_of_ms=_T + 100)
        results.append(_report("missing_runner2_journal",
                               "BLOCKED:" + PaperIncidentCode.INSUFFICIENT_EVIDENCE.value,
                               missing_runner, invariants_hold=not runner.exists()))

        # Deterministically model AUTO4 changing after RUNNER2 replay. The
        # real observer must refuse the torn two-database observation.
        store, pos, runner, pid = _fixture(root, "drift")
        _trigger(runner, pos, pid)
        from .paper_position_inspection import inspect_paper_position
        before = inspect_paper_position(pos, pid)
        changed = replace(before, balance=replace(
            before.balance, as_of_ms=before.balance.as_of_ms + 1))
        original_reader = _incident_module.inspect_paper_position
        reads = 0
        def drift_reader(position_path, position_id):
            nonlocal reads
            reads += 1
            return changed if reads == 2 else original_reader(position_path, position_id)
        with patch.object(_incident_module, "inspect_paper_position",
                          side_effect=drift_reader):
            drift = audit_paper_runner_incident(
                pos, pid, runner_journal_path=runner, policy=_POLICY, as_of_ms=_T + 3100)
        results.append(_report("auto4_drift_during_runner2_read",
                               "BLOCKED:" + PaperIncidentCode.INSUFFICIENT_EVIDENCE.value,
                               drift, invariants_hold=(
                                   "stable_auto4_checkpoint" in drift.evidence_missing
                                   and store.load(pid).runner_reserved_unfilled_units == 0)))

        missing = root / "missing.sqlite"
        results.append(_report("missing_auto4_journal", "BLOCKED:" + PaperIncidentCode.JOURNAL_INVALID_OR_MISSING.value,
                               audit_paper_runner_incident(missing, "fixture_pre7_missing")))
    return PaperIncidentMatrixReport(tuple(results))
