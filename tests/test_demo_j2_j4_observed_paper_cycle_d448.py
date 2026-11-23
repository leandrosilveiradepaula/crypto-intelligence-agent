"""D448 end-to-end executable demonstration, hermetic and owner-only."""
import os
from decimal import Decimal
import unittest
from unittest.mock import patch

from scripts.demo_j2_j4_observed_paper_cycle_d448 import run


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "POSIX nonroot owner required")
class ObservedFullPaperCycleDemoTests(unittest.TestCase):
    def test_long_and_short_full_d436_j2_j3_auto2_auto4_j5_cycle(self):
        for side in ("LONG", "SHORT"):
            with self.subTest(side=side), patch(
                "socket.create_connection",
                side_effect=AssertionError("D448 demo cannot open network"),
            ):
                report = run(side=side)
                self.assertEqual(report["status"], "offline_full_paper_path_demonstrated")
                self.assertEqual(report["side"], side)
                self.assertEqual(report["confirmed_ws_close_history_replayed"], 25)
                self.assertEqual(report["observed_j2_hypotheses"], 1)
                self.assertEqual(report["durable_hypothetical_open_fills"], 1)
                self.assertEqual(report["persisted_auto4_positions"], 1)
                self.assertEqual(report["partial_exit_intents_reserved"], 1)
                self.assertEqual(report["hypothetical_partial_exit_fills_recorded"], 1)
                self.assertGreater(Decimal(report["hypothetical_partial_exit_units"]), 0)
                self.assertEqual(report["duplicate_hypothetical_exit_fills"], 0)
                self.assertTrue(report["conditional_pnl_before_funding_available"])
                self.assertFalse(report["funding_settlement_verified"])
                self.assertEqual(report["duplicate_open_fills_after_restart"], 0)
                self.assertTrue(report["position_visible_in_j5"])
                for field in (
                    "financial_returns_validated", "native_stop_installed",
                    "real_fill_verified", "public_market_session_observed",
                    "j1_accessed", "orders_sent", "approved_for_live_use",
                ):
                    self.assertIs(report[field], False)
                self.assertEqual(report["network_requests"], 0)


if __name__ == "__main__":
    unittest.main()
