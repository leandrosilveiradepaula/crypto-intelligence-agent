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
