"""J6/PRE7 regression tests for the finite incident evidence matrix."""
from dataclasses import replace
from decimal import Decimal as D
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.paper_incident_matrix import (
    PaperIncidentMatrixReport, _report, run_paper_incident_matrix,
)
from crypto_intelligence_agent.paper_runner_incident_audit import (
    PaperIncidentCode, PaperIncidentSeverity, PaperRunnerIncidentReport,
)
from scripts.demo_paper_incident_matrix import main


class PaperIncidentMatrixTests(unittest.TestCase):
    def test_matrix_is_deterministic_sanitized_and_has_no_failures(self):
        first = run_paper_incident_matrix().sanitized_report()
        second = run_paper_incident_matrix().sanitized_report()
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "paper_incident_matrix_v1")
        self.assertEqual(first["scenario_count"], 11)
        self.assertEqual(first["failure_count"], 0)
        self.assertEqual(first["pass_count"], 4)
        self.assertEqual(first["blocked_expected_count"], 7)
        self.assertTrue(first["temporary_journals_removed"])
        self.assertEqual(len({x["scenario_id"] for x in first["scenarios"]}), 11)
        self.assertTrue(all(x["validation_status"] != "FAIL" for x in first["scenarios"]))
        self.assertNotIn("BTCUSDT", json.dumps(first))
        for scenario in first["scenarios"]:
            self.assertIn(scenario["validation_status"], ("PASS", "BLOCKED_EXPECTED"))
            self.assertFalse(scenario["orders_sent"])
            self.assertFalse(scenario["native_stop_verified"])

    def test_false_positive_guards_check_severity_reconciliation_and_ledger(self):
        valid = PaperRunnerIncidentReport(
            PaperIncidentCode.RUNNER_EXIT_UNKNOWN_RECONCILIATION,
            PaperIncidentSeverity.BLOCKED, 1793100000100, D("6"), D("6"), D("0"),
            True, ("auto4_position_replay",), ("reconciliation",),
            "Estado de fixture incerto",
        )
        expected = "BLOCKED:RUNNER_EXIT_UNKNOWN_RECONCILIATION"
        self.assertEqual(_report("unknown_blocks_reconciliation", expected, valid).validation_status,
                         "BLOCKED_EXPECTED")
        self.assertEqual(_report("unknown_blocks_reconciliation", expected, valid,
                                 invariants_hold=False).validation_status, "FAIL")
        self.assertEqual(_report("unknown_blocks_reconciliation", expected,
                                 replace(valid, severity=PaperIncidentSeverity.REVIEW)
                                 ).validation_status, "FAIL")
        self.assertEqual(_report("unknown_blocks_reconciliation", expected,
                                 replace(valid, reconciliation_required=False)
                                 ).validation_status, "FAIL")

    def test_readiness_is_not_proven_when_scenario_fails(self):
        original = run_paper_incident_matrix()
        broken = tuple(replace(x, validation_status="FAIL")
                       if x.scenario_id == "concurrent_single_reservation" else x
                       for x in original.scenarios)
        output = PaperIncidentMatrixReport(broken).sanitized_report()
        gates = {x["criterion"]: x["state"] for x in output["j6_readiness"]}
        self.assertEqual(output["failure_count"], 1)
        self.assertEqual(gates["idempotencia_e_reserva_local"],
                         "NAO_COMPROVADO_NESTA_EXECUCAO")
        self.assertEqual(gates["testnet_e_live"], "BLOQUEADO")

    def test_no_network_and_cli_stdout_are_safe(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            report = run_paper_incident_matrix().sanitized_report()
        self.assertFalse(report["live_trading_authorized"])
        from io import StringIO
        with patch("sys.stdout", new_callable=StringIO) as out:
            main([])
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["failure_count"], 0)
        self.assertNotIn("cia_j6_pre7_", out.getvalue())
        self.assertNotIn("BTCUSDT", out.getvalue())

    def test_cli_rejects_operational_arguments(self):
        with self.assertRaises(SystemExit):
            main(["--api-key", "not-allowed"])


if __name__ == "__main__":
    unittest.main()
