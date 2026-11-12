"""D308 CLI: opt-in and privacy gates, synthetic offline only."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts.observe_j2_n50_watchlist_once import main


class CliTests(unittest.TestCase):
    def _run(self, args):
        output = StringIO()
        with redirect_stdout(output):
            rc = main(args)
        return rc, json.loads(output.getvalue())

    def test_no_flags_never_read_private_data(self):
        with patch(
            "scripts.observe_j2_n50_watchlist_once.observe_private_n50_watchlist",
            return_value={"status": "owner_optin_required"},
        ) as reader:
            code, payload = self._run([])
        self.assertEqual(code, 65)
        self.assertEqual(payload["status"], "owner_optin_required")
        self.assertFalse(reader.call_args.kwargs["allow_private_readonly_audit"])
        self.assertFalse(reader.call_args.kwargs["enable_descriptive_watchlist"])
        self.assertFalse(reader.call_args.kwargs["include_private_symbols"])

    def test_explicit_private_output_requires_both_flags(self):
        with patch(
            "scripts.observe_j2_n50_watchlist_once.observe_private_n50_watchlist",
            return_value={"status": "private_symbol_output_not_approved"},
        ) as reader:
            code, payload = self._run([
                "--allow-private-readonly-audit",
                "--enable-descriptive-watchlist",
                "--include-private-symbols",
            ])
        self.assertEqual(code, 65)
        self.assertTrue(reader.call_args.kwargs["include_private_symbols"])
        self.assertFalse(
            reader.call_args.kwargs["confirm_private_symbol_output"]
        )
        self.assertEqual(payload["status"], "private_symbol_output_not_approved")

    def test_approved_count_summary(self):
        safe = {
            "status": "descriptive_watchlist_ready", "audited_assets": 50,
            "up_breakout_watchlist": [], "down_breakout_watchlist": [],
            "orders_sent": False, "approved_for_live_use": False,
        }
        with patch(
            "scripts.observe_j2_n50_watchlist_once.observe_private_n50_watchlist",
            return_value=safe,
        ) as reader:
            code, payload = self._run([
                "--allow-private-readonly-audit", "--enable-descriptive-watchlist",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(payload["audited_assets"], 50)
        self.assertFalse(reader.call_args.kwargs["include_private_symbols"])
        self.assertFalse(payload["orders_sent"])


if __name__ == "__main__":
    unittest.main()
