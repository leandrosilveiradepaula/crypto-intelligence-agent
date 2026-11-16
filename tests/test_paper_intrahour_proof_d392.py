"""Offline D392 end-to-end scenarios, using only synthetic Bybit events."""
from __future__ import annotations

import json
from hashlib import sha256
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    demonstrate_paper_intrahour_cycle,
)


class PaperIntrahourProofD392Tests(unittest.TestCase):
    def test_long_cycle_closes_with_three_paper_exit_intents(self):
        r = demonstrate_paper_intrahour_cycle(side="LONG")
        self.assertEqual(r["status"], "fixture_cycle_closed")
        self.assertEqual(
            [(x["minute_of_same_hour"], x["decision"]) for x in r["timeline"]],
            [
                (12, "paper_target_reserved"),
                (19, "paper_target_reserved"),
                (27, "paper_stop_reserved"),
            ],
        )
        self.assertEqual(
            [x["confirmed_remaining_units"] for x in r["timeline"]],
            ["100", "70", "50"],
        )
        self.assertEqual(r["final_filled_exit_units"], "100")
        self.assertEqual(r["final_remaining_units"], "0")
        self.assertEqual(r["final_reserved_unfilled_units"], "0")
        self.assertEqual(r["planned_residual_units"], "50")
        self.assertEqual(r["recorded_exit_intents"], 3)
        self.assertEqual(r["fixture_fill_event_count"], 4)
        self.assertFalse(r["entry_signal_computed"])
        self.assertFalse(r["real_fills_verified"])
        self.assertFalse(r["leverage_at_open_verified"])
        self.assertFalse(r["net_pnl_verified"])
        self.assertFalse(r["order_submission_enabled"])
        self.assertFalse(r["orders_sent"])

    def test_short_cycle_uses_buy_to_cover_price_and_mark_stop(self):
        r = demonstrate_paper_intrahour_cycle(side="SHORT")
        self.assertEqual(r["status"], "fixture_cycle_closed")
        self.assertEqual(
            [x["decision"] for x in r["timeline"]],
            ["paper_target_reserved", "paper_target_reserved", "paper_stop_reserved"],
        )
        self.assertEqual(r["final_filled_exit_units"], "100")
        self.assertEqual(r["final_remaining_units"], "0")

    def test_unknown_blocks_later_target_and_stop_without_false_fill(self):
        r = demonstrate_paper_intrahour_cycle(
            scenario="unknown_blocks_stop",
        )
        self.assertEqual(
            [x["decision"] for x in r["timeline"]],
            [
                "paper_target_reserved",
                "paper_target_reconciliation_required",
                "paper_stop_unresolved",
            ],
        )
        self.assertEqual(r["recorded_exit_intents"], 1)
        self.assertEqual(r["final_filled_exit_units"], "0")
        self.assertEqual(r["final_reserved_unfilled_units"], "30")
        self.assertEqual(r["final_remaining_units"], "100")
        self.assertTrue(r["reconciliation_required"])
        self.assertFalse(r["native_stop_verified"])

    def test_short_unknown_also_abstains(self):
        r = demonstrate_paper_intrahour_cycle(
            scenario="unknown_blocks_stop", side="SHORT",
        )
        self.assertEqual(r["status"], "fixture_unknown_requires_reconciliation")
        self.assertEqual(r["final_reserved_unfilled_units"], "30")

    def test_report_is_deterministic_and_contains_no_market_prices_or_ids(self):
        first = demonstrate_paper_intrahour_cycle()
        self.assertEqual(first, demonstrate_paper_intrahour_cycle())
        raw = json.dumps(first, sort_keys=True, separators=(",", ":"))
        for forbidden in (
            "BTCUSDT", "fixture_d392_open_position", "fixture_d392_fill",
            "101.02", "103.02", "98.02",
        ):
            self.assertNotIn(forbidden, raw)
        copied = dict(first)
        digest = copied.pop("fixture_report_sha256")
        self.assertEqual(
            sha256(json.dumps(copied, sort_keys=True,
                              separators=(",", ":")).encode("ascii")).hexdigest(),
            digest,
        )
        self.assertEqual(len(digest), 64)

    def test_real_cli_process_emits_auditable_json_for_all_scenarios(self):
        import subprocess
        import sys

        cases = [
            ("LONG", "two_targets_then_stop", "fixture_cycle_closed"),
            ("SHORT", "two_targets_then_stop", "fixture_cycle_closed"),
            ("LONG", "unknown_blocks_stop",
             "fixture_unknown_requires_reconciliation"),
        ]
        for side, scenario, expected in cases:
            with self.subTest(side=side, scenario=scenario):
                run = subprocess.run(
                    [sys.executable, "-m",
                     "scripts.run_paper_intrahour_proof_d392",
                     "--side", side, "--scenario", scenario],
                    check=True, capture_output=True, text=True, timeout=30,
                )
                report = json.loads(run.stdout)
                self.assertEqual(report["status"], expected)
                self.assertEqual(report["position_side"], side)
                self.assertEqual(len(report["timeline"]), 3)
                self.assertFalse(report["orders_sent"])
                self.assertFalse(report["net_pnl_verified"])
                self.assertEqual(run.stderr, "")

    def test_invalid_fixture_options_fail_without_any_broker(self):
        with self.assertRaises(DataValidationError):
            demonstrate_paper_intrahour_cycle(scenario="live_trading")
        with self.assertRaises(DataValidationError):
            demonstrate_paper_intrahour_cycle(side="HEDGE")


if __name__ == "__main__":
    unittest.main()
