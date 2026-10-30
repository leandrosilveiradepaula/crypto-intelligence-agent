"""J6/PRE7 regression tests for the finite incident evidence matrix."""
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.paper_incident_matrix import run_paper_incident_matrix
from scripts.demo_paper_incident_matrix import main


class PaperIncidentMatrixTests(unittest.TestCase):
    def test_matrix_is_deterministic_sanitized_and_has_no_failures(self):
        first = run_paper_incident_matrix().sanitized_report()
        second = run_paper_incident_matrix().sanitized_report()
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "paper_incident_matrix_v1")
        self.assertEqual(first["scenario_count"], 8)
        self.assertEqual(first["failure_count"], 0)
        self.assertEqual(first["pass_count"], 4)
        self.assertEqual(first["blocked_expected_count"], 4)
        self.assertTrue(first["temporary_journals_removed"])
        self.assertNotIn("BTCUSDT", json.dumps(first))
        for scenario in first["scenarios"]:
            self.assertIn(scenario["validation_status"], ("PASS", "BLOCKED_EXPECTED"))
            self.assertFalse(scenario["orders_sent"])
            self.assertFalse(scenario["native_stop_verified"])

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
