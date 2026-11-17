"""D402 end-to-end public adapter/PAPER journal, no network or real orders."""
from __future__ import annotations

import json
import shutil
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

    @unittest.skipUnless(shutil.which("node"), "Node required for the mobile JSON contract")
    def test_complete_offline_market_to_auto4_to_mobile_export(self):
        """Use the real D402 producer and real D407 schema, not a copied fixture."""
        for scenario, filled, remaining, reserved, pending in (
            ("closed", "100", "0", "0", False),
            ("unknown", "0", "100", "30", True),
        ):
            with self.subTest(scenario=scenario):
                with patch("socket.create_connection",
                           side_effect=AssertionError("no market network")):
                    result = demonstrate_adapter_to_paper_cycle(
                        scenario=scenario, include_mobile_snapshot=True)
                mobile = result["mobile_snapshot"]
                self.assertEqual(mobile["schema_version"], "paper_positions_snapshot_v1")
                self.assertEqual(len(mobile["positions"]), 1)
                pos = mobile["positions"][0]
                self.assertEqual(pos["filled_exit_units"], filled)
                self.assertEqual(pos["confirmed_remaining_units"], remaining)
                self.assertEqual(pos["reserved_unfilled_units"], reserved)
                self.assertEqual(pos["pending_or_unknown_orders"] > 0, pending)
                self.assertFalse(mobile["orders_sent"])
                self.assertFalse(mobile["financial_pnl_available"])
                self.assertFalse(result["real_market_connected"])
                self.assertFalse(result["real_fills_verified"])
                node = r"""
const fs = require("node:fs");
const assert = require("node:assert/strict");
const data = JSON.parse(fs.readFileSync(0, "utf8"));
const viewer = require("./web/app/persisted-paper.js");
assert.equal(viewer.validateReport(data), data);
assert.equal(data.positions.length, 1);
assert.equal(data.orders_sent, false);
assert.equal(data.financial_pnl_available, false);
console.log("D409_OFFLINE_WS_TO_AUTO4_TO_MOBILE_PASS");
"""
                response = subprocess.run(
                    ["node", "-e", node], input=json.dumps(mobile),
                    text=True, capture_output=True, cwd=ROOT, timeout=15,
                )
                self.assertEqual(response.returncode, 0, response.stderr)
                self.assertIn("D409_OFFLINE_WS_TO_AUTO4_TO_MOBILE_PASS", response.stdout)

    def test_opt_in_is_required_and_legacy_output_does_not_change(self):
        base = demonstrate_adapter_to_paper_cycle(scenario="unknown")
        enriched = demonstrate_adapter_to_paper_cycle(
            scenario="unknown", include_mobile_snapshot=True)
        self.assertNotIn("mobile_snapshot", base)
        self.assertEqual({k: v for k, v in enriched.items() if k != "mobile_snapshot"}, base)
        with self.assertRaises(DataValidationError):
            demonstrate_adapter_to_paper_cycle(
                scenario="closed", include_mobile_snapshot=1)

    def test_cli_exposes_mobile_snapshot_on_explicit_request_only(self):
        for scenario in ("closed", "unknown"):
            with self.subTest(scenario=scenario):
                base = [sys.executable, "-m",
                        "scripts.run_paper_public_adapter_proof_d402",
                        "--scenario", scenario]
                normal = subprocess.run(
                    base, cwd=ROOT, capture_output=True, text=True, timeout=25)
                extra = subprocess.run(
                    base + ["--mobile-snapshot"], cwd=ROOT,
                    capture_output=True, text=True, timeout=25)
                self.assertEqual(normal.returncode, 0, normal.stderr)
                self.assertEqual(extra.returncode, 0, extra.stderr)
                self.assertNotIn("mobile_snapshot", json.loads(normal.stdout))
                self.assertEqual(
                    json.loads(extra.stdout)["mobile_snapshot"]["positions"][0]
                    ["filled_exit_units"], "100" if scenario == "closed" else "0")

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
