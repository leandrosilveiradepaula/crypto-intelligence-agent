"""J1/D309 CLI contract: no private data by default, no raw diagnostics."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts.inspect_j1_n50_24h_witness_once import main


class CLIWitnessTests(unittest.TestCase):
    def run_cli(self, arguments, status):
        out = StringIO()
        with patch(
            "scripts.inspect_j1_n50_24h_witness_once.observe_n50_24h_witness",
            return_value={"status": status, "closed_24h_pit_verified": False,
                          "orders_sent": False},
        ) as audited, redirect_stdout(out):
            code = main(arguments)
        return code, json.loads(out.getvalue()), audited.call_args.kwargs

    def test_default_disables_all_private_read_and_witness(self):
        code, report, options = self.run_cli([], "owner_optin_required")
        self.assertEqual(code, 65)
        self.assertEqual(report["status"], "owner_optin_required")
        self.assertFalse(options["allow_private_readonly_audit"])
        self.assertFalse(options["enable_closed24h_witness"])

    def test_24hour_witness_requires_both_flags(self):
        code, report, options = self.run_cli(
            ["--allow-private-readonly-audit", "--enable-closed24h-witness"],
            "accumulating_24_closed_hours",
        )
        self.assertEqual(code, 0)
        self.assertTrue(options["allow_private_readonly_audit"])
        self.assertTrue(options["enable_closed24h_witness"])
        self.assertFalse(report["closed_24h_pit_verified"])

    def test_failback_exit_is_nonzero_and_no_raw_data(self):
        code, report, options = self.run_cli(
            ["--allow-private-readonly-audit", "--enable-closed24h-witness"],
            "failback_to_n2_observed",
        )
        self.assertEqual(code, 65)
        self.assertEqual(report["orders_sent"], False)
        self.assertNotIn("USDT", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
