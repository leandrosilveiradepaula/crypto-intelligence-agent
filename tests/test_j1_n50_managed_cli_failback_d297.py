"""D297 ensure managed systemd failures trigger OnFailure, never silent exit0."""
from __future__ import annotations
from contextlib import redirect_stdout
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from scripts.run_j1_n50_managed_once import main


class ManagedN50CliFailbackTests(TestCase):
    def test_deferred_and_failed_tick_exit_nonzero(self):
        for status in ("deferred", "blocked", "optin_required"):
            with self.subTest(status=status), patch(
                "scripts.run_j1_n50_managed_once.managed_n50_tick_once",
                return_value={"status":status,"orders_sent":False},
            ) as run:
                output=StringIO()
                with redirect_stdout(output):
                    rc=main(["--root-directory","/nonexistent"])
                self.assertEqual(rc,65)
                self.assertIn('"orders_sent":false',output.getvalue())
                run.assert_called_once()

    def test_successful_epoch_or_writer_returns_zero(self):
        for status in ("epoch_started","epoch_rotated",
                       "research_hour_persisted"):
            with self.subTest(status=status), patch(
                "scripts.run_j1_n50_managed_once.managed_n50_tick_once",
                return_value={"status":status,"orders_sent":False},
            ):
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["--root-directory","/nonexistent"]),0)


if __name__=="__main__":
    from unittest import main as unittest_main
    unittest_main()
