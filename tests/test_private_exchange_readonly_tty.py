"""No-network tests for the AUTH1 hidden TTY credential launcher."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import getpass
import json
import unittest
from unittest.mock import patch

from scripts.run_private_exchange_readonly_tty import main


MODULE = "scripts.run_private_exchange_readonly_tty"
FLAGS = ["--allow-private-read", "--confirm-read-only-key"]


class TtyReadonlyTests(unittest.TestCase):
    def _run(self, venue="bybit", flags=None, secrets=("example_key", "example_secret"),
             provider_status="authenticated_read_only_key_confirmed",
             tty=True, provider_error=None):
        output = StringIO()
        fake_provider = lambda *args, **kwargs: {
            "status": provider_status,
            "venue": venue,
            "orders_sent": False,
            "trading_enabled": False,
            "balances_exported": False,
            "private_account_details_exported": False,
            "source_market_data_verified": False,
        }
        captures = []
        def provider(*args, **kwargs):
            captures.append((args, dict(kwargs)))
            if provider_error:
                raise provider_error
            return fake_provider(*args, **kwargs)

        with patch(f"{MODULE}.sys.stdin.isatty", return_value=tty), \\
             patch(f"{MODULE}.sys.stderr.isatty", return_value=tty), \\
             patch(f"{MODULE}.getpass.getpass", side_effect=secrets) as hidden, \\
             patch(f"{MODULE}.diagnose", side_effect=provider), \\
             redirect_stdout(output):
            code = main(["--venue", venue] + (FLAGS if flags is None else flags))
        return code, json.loads(output.getvalue()), captures, hidden

    def test_no_flags_has_no_key_prompt_and_no_network(self):
        for venue in ("binance", "bybit"):
            for flags in ([], FLAGS[:1], FLAGS[1:]):
                with self.subTest(venue=venue, flags=flags):
                    code, report, calls, hidden = self._run(venue, flags=flags)
                    self.assertEqual(code, 1)
                    self.assertEqual(report["status"], "offline_network_disabled")
                    self.assertFalse(calls)
                    hidden.assert_not_called()

    def test_noninteractive_rejected_before_secret_prompt(self):
        for venue in ("binance", "bybit"):
            code, report, calls, hidden = self._run(venue, tty=False)
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "interactive_tty_required")
            self.assertFalse(calls)
            hidden.assert_not_called()

    def test_bybit_uses_only_explicit_in_memory_mapping_and_sanitized_output(self):
        code, report, calls, hidden = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "authenticated_read_only_key_confirmed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], ("bybit",))
        self.assertTrue(calls[0][1]["allow_private_read"])
        self.assertTrue(calls[0][1]["confirm_read_only_key"])
        # Credential dict is cleared by wrapper after the call.
        self.assertEqual(calls[0][1]["env"], {})
        self.assertEqual(hidden.call_count, 2)
        self.assertNotIn("example_key", str(report))
        self.assertNotIn("example_secret", str(report))
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["balances_exported"])
        self.assertFalse(report["trading_enabled"])

    def test_binance_proves_authentication_not_permissions(self):
        code, report, calls, hidden = self._run(
            "binance", provider_status="authenticated_permissions_not_attested",
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "authenticated_permissions_not_attested")
        self.assertEqual(len(calls), 1)
        self.assertFalse(report["trading_enabled"])

    def test_provider_rejection_keeps_secrets_opaque(self):
        code, report, calls, _ = self._run(
            provider_status="access_or_region_restricted",
        )
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "access_or_region_restricted")
        self.assertEqual(len(calls), 1)

    def test_empty_key_or_secret_rejected_without_network(self):
        for pair in (("", "secret"), ("key", "")):
            with self.subTest(pair=pair):
                code, report, calls, _ = self._run(secrets=pair)
                self.assertEqual(code, 2)
                self.assertEqual(report["status"], "missing_private_credentials")
                self.assertFalse(calls)

    def test_terminal_warnings_or_cancel_fail_closed(self):
        for error in (getpass.GetPassWarning("sensitive"),
                      EOFError("sensitive"),
                      KeyboardInterrupt(),
                      OSError("sensitive")):
            with self.subTest(kind=type(error).__name__):
                output = StringIO()
                with patch(f"{MODULE}.sys.stdin.isatty", return_value=True), \\
                     patch(f"{MODULE}.sys.stderr.isatty", return_value=True), \\
                     patch(f"{MODULE}.getpass.getpass", side_effect=error), \\
                     patch(f"{MODULE}.diagnose") as provider, \\
                     redirect_stdout(output):
                    code = main(["--venue", "bybit"] + FLAGS)
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(output.getvalue())["status"],
                                 "interactive_entry_cancelled")
                self.assertNotIn("sensitive", output.getvalue())
                provider.assert_not_called()

    def test_unexpected_internal_error_does_not_print_exception(self):
        code, report, calls, _ = self._run(
            provider_error=RuntimeError("secret example_key example_secret"),
        )
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "unexpected_diagnostic_failure")
        self.assertNotIn("example_secret", str(report))

    def test_no_secret_arguments_accepted(self):
        output = StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit):
            main(["--venue", "bybit", "--api-key", "user_secret"])
        self.assertNotIn("user_secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
