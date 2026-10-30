"""Regression coverage for J6/PRE6's read-only incident observer."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import tempfile
import json
import socket
import sqlite3
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_runner_incident_audit import (
    PaperIncidentCode, PaperIncidentSeverity, audit_paper_runner_incident,
)
from crypto_intelligence_agent.paper_runner_journal import start_paper_runner_journal, append_paper_runner_mark
from crypto_intelligence_agent.paper_runner_trailing import PaperRunnerTrailPolicy
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderEventKind
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from scripts.audit_paper_runner_incident import main
from scripts.inspect_paper_positions import TEMPLATE, render_incident_card_markup, render_paper_positions
from test_paper_position_reservations import e, exit_order, T, opened_order, plan
from test_paper_runner_journal import DurablePaperRunnerTests, policy, tick


class PaperRunnerIncidentAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DurablePaperRunnerTests(methodName="test_restart_replay_preserves_ratchet_and_terminal_trigger")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.position
        self.path = self.fixture.position_path
        self.runner = self.fixture.path
        self.position_id = self.fixture.id

    def audit(self, **kwargs):
        return audit_paper_runner_incident(self.path, self.position_id, **kwargs)

    def test_confirmed_runner_without_runner2_is_explicitly_unprotected(self):
        report = self.audit()
        self.assertEqual(report.code, PaperIncidentCode.RUNNER_UNPROTECTED)
        self.assertEqual(report.severity, PaperIncidentSeverity.REVIEW)
        self.assertIn("native_stop", report.evidence_missing)
        self.assertFalse(report.sanitized_report()["orders_sent"])

    def test_runner2_states_and_sanitized_schema(self):
        start_paper_runner_journal(self.runner, self.path, self.position_id, policy=policy(), first_mark=tick("100", 0), as_of_ms=T + 100)
        report = self.audit(runner_journal_path=self.runner, policy=policy(), as_of_ms=T + 100)
        self.assertEqual(report.code, PaperIncidentCode.TRAILING_NOT_ACTIVATED)
        append_paper_runner_mark(self.runner, self.path, self.position_id, tick("102", 1), policy=policy(), as_of_ms=T + 1100)
        self.assertEqual(self.audit(runner_journal_path=self.runner, policy=policy(), as_of_ms=T + 1100).code, PaperIncidentCode.TRAILING_TRACKING_HYPOTHETICAL)
        append_paper_runner_mark(self.runner, self.path, self.position_id, tick("103", 2), policy=policy(), as_of_ms=T + 2100)
        append_paper_runner_mark(self.runner, self.path, self.position_id, tick("102", 3), policy=policy(), as_of_ms=T + 3100)
        triggered = self.audit(runner_journal_path=self.runner, policy=policy(), as_of_ms=T + 3100)
        self.assertEqual(triggered.code, PaperIncidentCode.TRAILING_TRIGGERED_HYPOTHETICAL)
        payload = triggered.sanitized_report()
        self.assertEqual(payload["schema"], "paper_runner_incident_audit_v1")
        self.assertNotIn("position_id", json.dumps(payload))
        self.assertFalse(payload["native_stop_verified"])

    def test_pending_unknown_cancel_and_partial_are_distinguished(self):
        current = self.store.load(self.position_id)
        intent = exit_order("audit_runner", "6", current.as_of_ms - T, cap="6")
        self.store.reserve_exit(self.position_id, 0, intent, as_of_ms=current.as_of_ms)
        self.assertEqual(self.audit().code, PaperIncidentCode.RUNNER_EXIT_PENDING_RECONCILIATION)
        self.store.append_exit_events(self.position_id, intent.intent_id, (e("audit_unknown", PaperOrderEventKind.UNKNOWN, 5),), as_of_ms=T + 5)
        self.assertEqual(self.audit().code, PaperIncidentCode.RUNNER_EXIT_UNKNOWN_RECONCILIATION)
        self.store.append_exit_events(self.position_id, intent.intent_id, (e("audit_partial", PaperOrderEventKind.FILL, 6, "2"),), as_of_ms=T + 6)
        self.assertEqual(self.audit().code, PaperIncidentCode.RUNNER_EXIT_PARTIALLY_FILLED)
        self.store.append_exit_events(self.position_id, intent.intent_id, (e("audit_cancel", PaperOrderEventKind.CANCELLED, 7),), as_of_ms=T + 7)
        self.assertEqual(self.audit().code, PaperIncidentCode.RUNNER_EXIT_PARTIALLY_FILLED)

    def test_invalid_or_missing_journal_and_digest_fail_closed_as_report(self):
        missing = self.path.parent / "missing.sqlite"
        report = audit_paper_runner_incident(missing, self.position_id)
        self.assertEqual(report.code, PaperIncidentCode.JOURNAL_INVALID_OR_MISSING)
        self.assertEqual(report.severity, PaperIncidentSeverity.BLOCKED)
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE paper_positions SET digest='bad' WHERE position_id=?", (self.position_id,))
        self.assertEqual(self.audit().code, PaperIncidentCode.JOURNAL_INVALID_OR_MISSING)

    def test_read_only_no_network_and_cli_is_sanitized(self):
        before = self.path.read_bytes()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            report = self.audit()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(report.residual_paper_units, D(6))
        # CLI writes only stdout; it has no output-path argument.
        with patch("sys.argv", ["audit", "--position-journal", str(self.path), "--position-id", self.position_id]):
            from io import StringIO
            with patch("sys.stdout", new_callable=StringIO) as out:
                main()
            payload = json.loads(out.getvalue())
        self.assertFalse(payload["live_trading_authorized"])
        self.assertNotIn(str(Path(self.path.parent)), out.getvalue())

    def test_replacement_pending_after_partial_is_not_treated_as_terminal(self):
        current = self.store.load(self.position_id)
        first = exit_order("pre6_first", "6", current.as_of_ms - T, cap="6")
        self.store.reserve_exit(self.position_id, 0, first, as_of_ms=current.as_of_ms)
        self.store.append_exit_events(
            self.position_id, first.intent_id,
            (e("pre6_partial_two", PaperOrderEventKind.FILL, 5, "2"),), as_of_ms=T+5)
        self.store.append_exit_events(
            self.position_id, first.intent_id,
            (e("pre6_partial_cancel", PaperOrderEventKind.CANCELLED, 6),), as_of_ms=T+6)
        second = exit_order("pre6_replacement", "4", 6, cap="4")
        self.store.reserve_exit(self.position_id, 0, second, as_of_ms=T+6)
        pending = self.audit()
        self.assertEqual(pending.code, PaperIncidentCode.RUNNER_EXIT_PENDING_RECONCILIATION)
        self.assertEqual(pending.reserved_units, D(4))
        self.assertEqual(pending.filled_units, D(2))
        self.assertTrue(pending.reconciliation_required)

    def test_rejected_runner_exit_requires_review(self):
        current = self.store.load(self.position_id)
        order = exit_order("pre6_rejected", "6", current.as_of_ms-T, cap="6")
        self.store.reserve_exit(self.position_id, 0, order, as_of_ms=current.as_of_ms)
        self.store.append_exit_events(
            self.position_id, order.intent_id,
            (e("pre6_runner_rejected", PaperOrderEventKind.REJECTED, 5),),
            as_of_ms=T+5)
        report = self.audit()
        self.assertEqual(report.code, PaperIncidentCode.RUNNER_EXIT_CANCELLED_REVIEW)
        self.assertEqual(report.severity, PaperIncidentSeverity.REVIEW)
        self.assertTrue(report.reconciliation_required)

    def test_filled_short_runner_order_cannot_mean_whole_position_closed(self):
        current = self.store.load(self.position_id)
        # A legal REDUCE_ONLY runner order may cover only a subset of the floor.
        intent = exit_order("audit_short_runner", "2", current.as_of_ms - T, cap="6")
        self.store.reserve_exit(self.position_id, 0, intent, as_of_ms=current.as_of_ms)
        self.store.append_exit_events(
            self.position_id, intent.intent_id,
            (e("audit_small_fill", PaperOrderEventKind.FILL, 5, "2"),),
            as_of_ms=T + 5,
        )
        saved = self.store.load(self.position_id)
        self.assertEqual(saved.exit_orders[-1].snapshot.status.value, "FILLED")
        self.assertEqual(saved.confirmed_remaining_units, D(4))
        report = self.audit()
        self.assertEqual(report.code, PaperIncidentCode.RUNNER_EXIT_PARTIALLY_FILLED)
        self.assertEqual(report.severity, PaperIncidentSeverity.REVIEW)
        self.assertTrue(report.reconciliation_required)
        self.assertNotEqual(report.code, PaperIncidentCode.RUNNER_CLOSED_PAPER_ONLY)

    def test_pending_runner_and_superseded_checkpoint_are_distinct(self):
        current = self.store.load(self.position_id)
        intent = exit_order("audit_pending_runner", "6", current.as_of_ms - T, cap="6")
        self.store.reserve_exit(self.position_id, 0, intent, as_of_ms=current.as_of_ms)
        pending = self.audit()
        self.assertEqual(pending.code, PaperIncidentCode.RUNNER_EXIT_PENDING_RECONCILIATION)
        self.assertTrue(pending.reconciliation_required)
        explicit_old_trailing = self.audit(
            runner_journal_path=self.runner, policy=policy(), as_of_ms=T+1100)
        self.assertEqual(explicit_old_trailing.code, PaperIncidentCode.RUNNER_CHECKPOINT_SUPERSEDED)

    def test_invalid_cutoff_or_policy_is_rejected_even_after_runner_reservation(self):
        current = self.store.load(self.position_id)
        intent = exit_order("audit_cutoff_runner", "6", current.as_of_ms - T, cap="6")
        self.store.reserve_exit(self.position_id, 0, intent, as_of_ms=current.as_of_ms)
        with self.assertRaises(DataValidationError):
            self.audit(runner_journal_path=self.runner, policy=policy(), as_of_ms=-1)
        with self.assertRaises(DataValidationError):
            self.audit(runner_journal_path=self.runner, policy=object(), as_of_ms=T+1100)

    def test_runner2_cross_database_drift_blocks_stale_report(self):
        self.fixture.start()
        selected = inspect_paper_position(self.path, self.position_id)
        newer = replace(selected, balance=replace(selected.balance, as_of_ms=selected.balance.as_of_ms+1))
        original_inspect = inspect_paper_position
        calls = 0
        def changing_reader(path, position_id):
            nonlocal calls
            calls += 1
            if calls == 2:
                return newer
            return original_inspect(path, position_id)
        with patch("crypto_intelligence_agent.paper_runner_incident_audit.inspect_paper_position",
                   side_effect=changing_reader):
            report = self.audit(
                runner_journal_path=self.runner, policy=policy(), as_of_ms=T+100)
        self.assertEqual(report.severity, PaperIncidentSeverity.BLOCKED)
        self.assertEqual(report.code, PaperIncidentCode.INSUFFICIENT_EVIDENCE)
        self.assertIn("stable_auto4_checkpoint", report.evidence_missing)

    def test_failure_reasons_never_expose_private_path_or_identifier(self):
        private = "/private/secret/account/fixture_private"
        with patch("crypto_intelligence_agent.paper_runner_incident_audit.inspect_paper_position",
                   side_effect=DataValidationError(private)):
            report = self.audit()
        self.assertEqual(report.severity, PaperIncidentSeverity.BLOCKED)
        self.assertNotIn(private, json.dumps(report.sanitized_report()))
        self.fixture.start()
        with patch("crypto_intelligence_agent.paper_runner_incident_audit.load_paper_runner_journal",
                   side_effect=DataValidationError(private)):
            report = self.audit(
                runner_journal_path=self.runner, policy=policy(), as_of_ms=T+100)
        self.assertEqual(report.severity, PaperIncidentSeverity.BLOCKED)
        self.assertNotIn(private, json.dumps(report.sanitized_report()))

    def test_pending_partial_tranche_is_blocked_before_runner(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pending.sqlite"
            journal = SQLitePaperPositionJournal(path)
            current = journal.create_position(
                position_id="fixture_pre6_pending_partial",
                opening_intent=opened_order(),
                opening_events=(e("pre6_open", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=plan(), plan_version="fixture_pre6_v1",
                synthetic_lot_step_units=D(1), as_of_ms=T+1)
            order = exit_order("pre6_pending", "50", 1)
            journal.reserve_exit(current.position_id, 1, order, as_of_ms=T+1)
            report = audit_paper_runner_incident(path, current.position_id)
            self.assertEqual(report.code, PaperIncidentCode.PARTIALS_INCOMPLETE)
            self.assertEqual(report.severity, PaperIncidentSeverity.BLOCKED)
            self.assertTrue(report.reconciliation_required)

    def test_existing_mobile_view_renders_incident_without_trading_controls(self):
        report = self.audit()
        markup = render_incident_card_markup(report)
        self.assertIn('data-incident-code="RUNNER_UNPROTECTED"', markup)
        self.assertIn("stop nativo não verificado", markup)
        self.assertNotIn("<script", markup.lower())
        from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
        html = render_paper_positions(
            (inspect_paper_position(self.path, self.position_id),),
            TEMPLATE.read_text(encoding="utf-8"), incident_report=report)
        self.assertIn('data-incident-code="RUNNER_UNPROTECTED"', html)
        self.assertIn("default-src 'none'", html)


if __name__ == "__main__":
    unittest.main()
