"""J4/AUTO5: the entire automatic PAPER journey is synthetic and offline."""
from contextlib import redirect_stdout
from decimal import Decimal
import io
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from scripts.demo_automated_paper_cycle import (
    main, simulate_automatic_paper_cycle,
)


class EndToEndPaperDemoTests(unittest.TestCase):
    def test_binance_candidate_fixture_has_reproducible_conservation(self):
        run = simulate_automatic_paper_cycle(PaperVenue.BINANCE_USDM)
        self.assertEqual(run["mode"], "offline_paper")
        self.assertEqual(run["quality"], "synthetic_fixture_only")
        self.assertEqual(run["venue_candidate"], "binance_usdm")
        self.assertFalse(run["venue_selected_for_live"])
        self.assertEqual(run["paper_risk_result"], "open_allowed_paper_only")
        self.assertEqual(run["entry_status"], "FILLED")
        self.assertEqual(run["initial_confirmed_units"], "100")
        self.assertEqual([x["filled_units"] for x in run["exit_steps"]],
                         ["50", "30", "14"])
        self.assertEqual([x["basis"] for x in run["exit_steps"]],
                         ["REMAINING_BALANCE"] * 3)
        self.assertEqual([x["status"] for x in run["exit_steps"]],
                         ["FILLED"] * 3)
        self.assertEqual(run["filled_exit_units"], "94")
        self.assertEqual(run["residual_units"], "6")
        self.assertEqual(run["residual_percent_of_initial"], "6")
        self.assertEqual(Decimal(run["filled_exit_units"]) +
                         Decimal(run["residual_units"]),
                         Decimal(run["initial_confirmed_units"]))
        self.assertTrue(run["unknown_resolved_by_explicit_fixture_fill"])
        self.assertTrue(run["recovery_consistent_after_restart"])
        self.assertEqual(run["database_retention"], "temporary_files_discarded")

    def test_bybit_is_independent_candidate_not_selected(self):
        run = simulate_automatic_paper_cycle(PaperVenue.BYBIT_V5)
        self.assertEqual(run["venue_candidate"], "bybit_v5")
        self.assertFalse(run["venue_selected_for_live"])
        self.assertEqual(run["symbol_fixture"], "BTCUSDT")
        self.assertEqual(run["quote_currency_fixture"], "USDT")
        self.assertEqual(run["filled_exit_units"], "94")
        self.assertEqual(run["residual_units"], "6")
        self.assertEqual(run["paper_risk_result"], "open_allowed_paper_only")
        self.assertTrue(run["unknown_resolved_by_explicit_fixture_fill"])

    def test_does_not_infer_financial_profits_or_approve_trading(self):
        for venue in PaperVenue:
            with self.subTest(venue=venue):
                run = simulate_automatic_paper_cycle(venue)
                self.assertFalse(run["orders_sent"])
                self.assertFalse(run["live_trading_authorized"])
                self.assertFalse(run["approved_for_live_use"])
                self.assertFalse(run["real_financial_pnl_available"])
                self.assertEqual(
                    run["signal_source"],
                    "predefined_test_fixture_not_a_validated_strategy",
                )
                self.assertEqual(
                    run["market_data_source"],
                    "invented_unit_test_values_not_exchange_data",
                )
                self.assertNotIn("profit_percent", run)
                self.assertNotIn("accuracy", run)

    def test_wrong_venue_input_is_not_silently_accepted(self):
        for value in (None, True, "binance_usdm", "live", 0, {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                simulate_automatic_paper_cycle(value)

    def test_stdout_json_is_deterministic_and_contains_both_venues(self):
        a = io.StringIO()
        b = io.StringIO()
        with redirect_stdout(a):
            main()
        with redirect_stdout(b):
            main()
        self.assertEqual(a.getvalue(), b.getvalue())
        data = json.loads(a.getvalue())
        self.assertEqual(data["demo"], "two_independent_synthetic_candidate_venues")
        self.assertEqual(data["mode"], "offline_paper")
        self.assertEqual([x["venue_candidate"] for x in data["results"]],
                         ["binance_usdm", "bybit_v5"])
        self.assertFalse(data["live_trading_authorized"])
        self.assertFalse(data["orders_sent"])
        self.assertEqual([x["residual_units"] for x in data["results"]], ["6", "6"])

    def test_cannot_access_network_during_end_to_end_paper_flow(self):
        with patch("urllib.request.urlopen",
                   side_effect=AssertionError("network attempted")):
            with patch("socket.create_connection",
                       side_effect=AssertionError("network attempted")):
                for venue in PaperVenue:
                    self.assertFalse(
                        simulate_automatic_paper_cycle(venue)["orders_sent"]
                    )


if __name__ == "__main__":
    unittest.main()
