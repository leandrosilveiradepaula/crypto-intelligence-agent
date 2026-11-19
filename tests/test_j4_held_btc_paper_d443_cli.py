"""D443 CLI: opt-in and finite-budget fail before owner/network access."""
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts.run_j4_held_btc_paper_d443_once import main


class D443CLIResearchTests(unittest.TestCase):
    def test_no_optins_does_not_touch_private_ledger_or_network(self):
        with patch("scripts.run_j4_held_btc_paper_d443_once.observe_existing_btc_paper_once",
                   side_effect=AssertionError("unexpected IO")):
            output = StringIO()
            with redirect_stdout(output):
                code = main(["--private-paper-directory", "/owner/never-read"])
        self.assertEqual(code, 77)
        data = json.loads(output.getvalue())
        self.assertFalse(data["private_paper_journal_accessed"])
        self.assertFalse(data["network_attempted"])
        self.assertFalse(data["orders_sent"])

    def test_excessive_budget_does_not_open_network_or_paper(self):
        flags = [
            "--private-paper-directory", "/owner/never-read",
            "--allow-public-network", "--allow-public-websocket",
            "--confirm-personal-readonly-research", "--confirm-region-eligible",
            "--allow-private-paper-reservations",
            "--seconds", "120",
        ]
        with patch("scripts.run_j4_held_btc_paper_d443_once.observe_existing_btc_paper_once",
                   side_effect=AssertionError("unexpected IO")):
            out = StringIO()
            with redirect_stdout(out):
                code = main(flags)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "held_btc_paper_budget_invalid_before_io")
        self.assertFalse(json.loads(out.getvalue())["network_attempted"])
        self.assertFalse(json.loads(out.getvalue())["private_paper_journal_accessed"])
        self.assertFalse(json.loads(out.getvalue())["orders_sent"])
