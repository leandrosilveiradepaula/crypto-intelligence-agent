"""J3/D305: fixed owner archive summary cannot leak symbols or enable trading."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts.evaluate_j3_n50_halted_archive_once import main


class J3ArchivedHaltCliTests(unittest.TestCase):
    @staticmethod
    def execute(*args):
        out=StringIO()
        with redirect_stdout(out):
            exit_code=main(list(args))
        return exit_code,json.loads(out.getvalue())

    def test_neither_flag_or_partial_flag_reads_any_private_data(self):
        with patch(
            "scripts.evaluate_j3_n50_halted_archive_once.evaluate_n50_expost_marks",
            side_effect=AssertionError("no private journal read"),
        ):
            for args in ((),("--allow-private-readonly-audit",),
                         ("--enable-archived-halted-research",)):
                rc,report=self.execute(*args)
                self.assertEqual(rc,65)
                self.assertEqual(report["status"],"optin_required")
                self.assertFalse(report["orders_sent"])
                self.assertEqual(report["audited_contracts"],0)

    def test_verified_halted_archive_is_rounded_and_count_only(self):
        data={
            "status":"archived_halted_expost_reference_only",
            "halted_archive_source_verified":True,
            "audited_contracts":50,
            "prior_closed_end_ms":1_800_000_000_000,
            "outcome_closed_end_ms":1_800_003_600_000,
            "orders_sent":False,
            "network_requests":0,
            "database_mutation_statements":0,
            "financial_backtest_approved":False,
            "out_of_sample_results_validated":False,
            "hypothetical_notional_per_asset_quote":"100",
            "hypothetical_total_cost_per_asset_quote":"0.180000",
            "top_tail_long_expost_net_mark_sum_quote":"24.720999",
            "bottom_tail_short_expost_net_mark_sum_quote":"-5.194132",
            "all50_long_expost_net_mark_sum_quote":"12.999205",
            "private_mark_observations":[{"symbol":"BTCUSDT","close":"300000"}],
        }
        with patch(
            "scripts.evaluate_j3_n50_halted_archive_once.evaluate_n50_expost_marks",
            return_value=data,
        ) as evaluate:
            rc,report=self.execute("--allow-private-readonly-audit",
                                   "--enable-archived-halted-research")
        self.assertEqual(rc,0)
        self.assertEqual(report["status"],"archived_halted_expost_reference_only")
        self.assertTrue(report["archived_halt_source_verified"])
        self.assertEqual(report["top_five_long_net_mark_sum_quote"],"24.72")
        self.assertEqual(report["bottom_five_short_net_mark_sum_quote"],"-5.19")
        self.assertEqual(report["all_fifty_long_net_mark_sum_quote"],"13.00")
        self.assertFalse(report["trading_enabled"])
        self.assertFalse(report["financial_backtest_approved"])
        self.assertNotIn("BTCUSDT",json.dumps(report))
        self.assertNotIn("300000",json.dumps(report))
        evaluate.assert_called_once_with(
            allow_private_readonly_audit=True,
            allow_archived_halted_research=True,
            include_private_symbols=False,
        )

    def test_unverified_archive_cannot_report_mark_results(self):
        data={"status":"unverified_halted_archive","orders_sent":False}
        with patch(
            "scripts.evaluate_j3_n50_halted_archive_once.evaluate_n50_expost_marks",
            return_value=data,
        ):
            rc,report=self.execute("--allow-private-readonly-audit",
                                   "--enable-archived-halted-research")
        self.assertEqual(rc,65)
        self.assertEqual(report["status"],"unverified_halted_archive")
        self.assertIsNone(report["all_fifty_long_net_mark_sum_quote"])
        self.assertFalse(report["archived_halt_source_verified"])


if __name__=="__main__":
    unittest.main()
