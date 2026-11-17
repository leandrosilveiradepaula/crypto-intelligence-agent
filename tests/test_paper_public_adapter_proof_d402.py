"""D402 end-to-end public adapter/PAPER journal, no network or real orders."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_intelligence_agent.paper_public_adapter_proof_d402 import (
    demonstrate_adapter_to_paper_cycle,
)
from crypto_intelligence_agent.market_data import DataValidationError

ROOT = Path(__file__).resolve().parents[1]


class PaperPublicAdapterProofTests(unittest.TestCase):
    def test_all_three_market_sessions_drive_full_paper_cycle(self):
        with patch("socket.create_connection",
                   side_effect=AssertionError("no network in D402")):
            result = demonstrate_adapter_to_paper_cycle(scenario="closed")
        self.assertEqual(result["status"], "synthetic_cycle_closed")
        self.assertEqual(result["post_ack_quotes"], 3)
        self.assertEqual(result["subscription_sessions"], 3)
        self.assertEqual([s["minute_of_hour"] for s in result["steps"]],
                         [12, 19, 27])
        self.assertEqual([s["exit_intents"] for s in result["steps"]],
                         [1, 2, 3])
        self.assertEqual(result["final_filled_units"], "100")
        self.assertEqual(result["final_reserved_units"], "0")
        self.assertEqual(result["final_remaining_units"], "0")
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["real_market_connected"])
        self.assertFalse(result["real_fills_verified"])
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn("fixture_d402", json.dumps(result))

    def test_unknown_does_not_create_second_or_stop_intent(self):
        result = demonstrate_adapter_to_paper_cycle(scenario="unknown")
        self.assertEqual(result["status"], "unknown_requires_reconciliation")
        self.assertEqual([s["exit_intents"] for s in result["steps"]],
                         [1, 1, 1])
        self.assertEqual(result["final_filled_units"], "0")
        self.assertEqual(result["final_reserved_units"], "30")
        self.assertEqual(result["final_remaining_units"], "100")
        self.assertTrue(result["reconciliation_required"])
        self.assertFalse(result["orders_sent"])

    def test_invalid_scenario_refused_without_any_market_or_db(self):
        with self.assertRaises(DataValidationError):
            demonstrate_adapter_to_paper_cycle(scenario="live")

    def test_cli_runs_real_adapters_offline_and_prints_sanitized_report(self):
        for scenario in ("closed", "unknown"):
            with self.subTest(scenario=scenario):
                result = subprocess.run(
                    [sys.executable, "-m",
                     "scripts.run_paper_public_adapter_proof_d402",
                     "--scenario", scenario],
                    cwd=ROOT, capture_output=True, text=True, timeout=25,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                obj = json.loads(result.stdout)
                self.assertEqual(obj["scenario"], scenario)
                self.assertFalse(obj["approved_for_live_use"])
                self.assertFalse(obj["orders_sent"])
                self.assertTrue(obj["fills_are_explicit_fixtures_only"])


if __name__ == "__main__":
    unittest.main()
