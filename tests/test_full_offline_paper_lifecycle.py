"""PRE9: integrated deterministic signal -> position -> runner PAPER fixture."""
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts.demo_full_offline_paper_lifecycle import (
    main, run_full_offline_paper_lifecycle,
)


class FullOfflinePaperLifecycleTests(unittest.TestCase):
    def test_all_causal_stages_match_and_are_repeatable_without_network(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            first = run_full_offline_paper_lifecycle()
            second = run_full_offline_paper_lifecycle()
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "j6_full_offline_paper_lifecycle_v1")
        self.assertEqual(first["mode"], "offline_paper")
        self.assertEqual(first["stages"], [
            "j2_risk_open_intent_reserved_without_fill",
            "explicit_fixture_open_fill_crosschecked_on_restart",
            "three_explicit_fixture_partial_fills",
            "runner2_hypothetical_trigger",
            "runner_reduce_only_pending_recovered_without_fill",
            "explicit_fixture_runner_fill_and_pre8_audit",
        ])
        checks = first["interruption_checks"]
        self.assertEqual([x["checkpoint"] for x in checks], [
            "pending_open_without_fill",
            "future_open_fill_rejected_at_prior_cutoff",
            "filled_open_without_auto4_position",
            "isolated_auto4_mismatched_fill_identity",
            "auto4_open_confirmed_no_native_stop",
            "partial_exits_leave_runner",
            "pending_runner_after_restart",
            "future_runner_fill_rejected_at_prior_cutoff",
            "fully_flat_after_runner_fill",
        ])
        self.assertTrue(checks[0]["pending_auto6_gate_required"])
        self.assertTrue(checks[0]["health_new_open_allowed_paper_only"])
        self.assertEqual(checks[1]["recovery_state"], "UNVERIFIED")
        self.assertFalse(checks[2]["health_new_open_allowed_paper_only"])
        self.assertFalse(checks[3]["health_new_open_allowed_paper_only"])
        self.assertEqual(checks[3]["portfolio_batch_block_code"],
                         "INVALID_OR_INCONSISTENT_SELECTED_JOURNALS")
        self.assertEqual(checks[6]["incident_code"],
                         "RUNNER_EXIT_PENDING_RECONCILIATION")
        self.assertEqual(checks[7]["recovery_state"], "UNVERIFIED")
        self.assertEqual(checks[8]["incident_code"], "RUNNER_CLOSED_PAPER_ONLY")
        self.assertTrue(checks[8]["health_new_open_allowed_paper_only"])
        for row in checks:
            self.assertFalse(row["native_stop_verified"])
            self.assertFalse(row["orders_sent"])
            self.assertFalse(row["live_trading_authorized"])
            self.assertNotIn("position_id", row)
        outage = first["stop_outage_research"]
        self.assertEqual(outage["checkpoint"],
                         "conditional_stop_unavailable_worsens_loss")
        self.assertEqual(outage["path_count"], 4)
        self.assertTrue(outage["worse_than_assumed_stop"])
        self.assertTrue(outage["hypothetical_only"])
        for flag in ("native_stop_verified", "orders_sent", "live_trading_authorized"):
            self.assertFalse(outage[flag])
        self.assertNotIn("conditional_net_quote", str(outage))
        self.assertEqual(first["strategy_open_intent_count"], 1)
        self.assertEqual(first["opening_units"], "2")
        self.assertEqual(first["partial_exit_units"], "1.88")
        self.assertEqual(first["runner_exit_units"], "0.12")
        self.assertEqual(first["confirmed_remaining_units"], "0")
        self.assertTrue(first["crosschecked_auto2_auto4_opening"])
        self.assertTrue(first["synthetic_open_fill_injected_explicitly"])
        self.assertTrue(first["synthetic_runner_fill_injected_explicitly"])
        self.assertEqual(first["synthetic_partial_fills_injected_explicitly"], 3)
        self.assertEqual(first["restart_duplicate_orders"], 0)
        self.assertFalse(first["persistent_files_retained"])
        self.assertFalse(first["market_data_real"])
        for flag in ("orders_sent", "native_stop_verified", "live_trading_authorized",
                     "approved_for_live_use", "financial_pnl_available"):
            self.assertFalse(first[flag])

    def test_forged_healthy_audit_cannot_silently_pass(self):
        from crypto_intelligence_agent.paper_open_health import PaperOpenHealth
        with patch("scripts.demo_full_offline_paper_lifecycle.audit_paper_open_health",
                   return_value=PaperOpenHealth((), True, "no_filled_open_or_position_requires_protection")):
            with self.assertRaisesRegex(Exception, "PAPER interruption health"):
                run_full_offline_paper_lifecycle()

    def test_cli_stdout_is_sanitized_and_disallows_operational_arguments(self):
        out = StringIO()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with redirect_stdout(out):
                main([])
        result = json.loads(out.getvalue())
        self.assertEqual(result["portfolio_positions_observed"], 1)
        self.assertEqual(result["network_requests"], 0)
        for forbidden in ("BTCUSDT", "fixture_pre9", "sqlite", "http", "cia_pre9_", "api-key"):
            self.assertNotIn(forbidden, out.getvalue().lower())
        with self.assertRaises(SystemExit):
            main(["--enable-live"])


if __name__ == "__main__":
    unittest.main()
