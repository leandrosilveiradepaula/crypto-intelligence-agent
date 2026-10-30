"""Regression coverage for J6/PRE6's read-only incident observer."""
from decimal import Decimal as D
from pathlib import Path
import json
import socket
import sqlite3
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.paper_runner_incident_audit import (
    PaperIncidentCode, PaperIncidentSeverity, audit_paper_runner_incident,
)
from crypto_intelligence_agent.paper_runner_journal import start_paper_runner_journal, append_paper_runner_mark
from crypto_intelligence_agent.paper_runner_trailing import PaperRunnerTrailPolicy
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderEventKind
from scripts.audit_paper_runner_incident import main
from test_paper_position_reservations import e, exit_order, T
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
        self.assertEqual(self.audit().code, PaperIncidentCode.RUNNER_CHECKPOINT_SUPERSEDED)
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


if __name__ == "__main__":
    unittest.main()
