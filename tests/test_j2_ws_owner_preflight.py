"""#656: read-only J2/J3 owner preflight contracts and fail-closed gates."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent import j2_ws_owner_preflight as preflight
from crypto_intelligence_agent import j2_ws_prospective_ledger as ledger
from crypto_intelligence_agent.market_data import DataValidationError


END = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
NOW = END + 240_000


class ReadOnlyPreflightContracts(unittest.TestCase):
    def test_no_optin_rejects_before_owner_clock_and_source(self):
        with patch.object(ledger, "_owner_guard", side_effect=AssertionError("owner")), \
             patch.object(preflight, "_os_ntp_synchronized",
                          side_effect=AssertionError("clock")), \
             patch.object(ledger, "_private_source",
                          side_effect=AssertionError("source")):
            result = preflight.preflight_owner_ws_decision_once()
        self.assertEqual(result["status"], "owner_read_optin_required")
        self.assertFalse(result["capture_eligible_now"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["database_mutation_statements"], 0)

    def test_os_clock_probe_is_bounded_and_exact(self):
        with patch.object(preflight.subprocess, "run",
                          return_value=Mock(returncode=0, stdout="yes\n")) as run:
            self.assertTrue(preflight._os_ntp_synchronized())
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertFalse(run.call_args.kwargs["check"])
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/timedatectl")
        with patch.object(preflight.subprocess, "run",
                          return_value=Mock(returncode=0, stdout="unknown\n")):
            self.assertFalse(preflight._os_ntp_synchronized())
        with patch.object(preflight.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("timedatectl", 3)):
            self.assertFalse(preflight._os_ntp_synchronized())

    def test_cli_is_optin_only_and_reports_sanitized_status(self):
        from scripts.research_j2_ws_prospective_once import main
        with patch("scripts.research_j2_ws_prospective_once.preflight_owner_ws_decision_once",
                   return_value={"status": "owner_read_optin_required",
                                 "orders_sent": False}) as fn, \
             redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["preflight"]), 65)
        fn.assert_called_once_with(allow_private_readonly_research=False)
        self.assertNotIn("BTCUSDT", output.getvalue())
        with patch("scripts.research_j2_ws_prospective_once.preflight_owner_ws_decision_once",
                   return_value={"status": "owner_preflight_ready_no_capture",
                                 "orders_sent": False}) as fn, \
             redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["preflight", "--allow-private-readonly-research"]), 0)
        fn.assert_called_once_with(allow_private_readonly_research=True)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "owner_preflight_ready_no_capture")


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0,
                     "owner-only preflight requires unprivileged POSIX process")
class OwnerPreflightFixtures(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="j2-preflight-fixture-")
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.root = self.parent / "decisions"
        fixture = patch.object(ledger, "LEDGER_ROOT", self.root)
        fixture.start()
        self.addCleanup(fixture.stop)

    def _run(self, *, now=NOW, later=None, source=None, sync=True):
        if source is None:
            source = ({"latest_closed_end_ms": now-now%HOUR_MS}, {})
        if later is None:
            later = now
        with patch.object(preflight, "_os_ntp_synchronized", return_value=sync), \
             patch.object(preflight.time, "time_ns",
                          side_effect=[now*1_000_000, later*1_000_000]), \
             patch.object(ledger, "_private_source", return_value=source) as reader:
            result = preflight.preflight_owner_ws_decision_once(
                allow_private_readonly_research=True)
        return result, reader

    def test_fully_ready_no_side_effect_no_symbol_and_only_one_replay(self):
        with patch("socket.create_connection",
                   side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen",
                   side_effect=AssertionError("http")), \
             patch("os.mkdir", side_effect=AssertionError("mkdir")), \
             patch("sqlite3.connect", side_effect=AssertionError("new database")):
            result, source = self._run()
        self.assertEqual(result["status"], "owner_preflight_ready_no_capture")
        self.assertTrue(result["capture_eligible_now"])
        self.assertTrue(result["owner_ws_50x24_readonly_replayed"])
        self.assertTrue(result["owner_ledger_parent_dac_verified"])
        self.assertFalse(result["ledger_directory_exists"])
        self.assertFalse(self.root.exists())
        self.assertEqual(result["reference_utc_closed_end_ms"], END)
        self.assertEqual(result["score_horizons_hours"], [1, 4, 8])
        self.assertFalse(result["prospective_registration_independently_verified"])
        self.assertFalse(result["approved_for_signals"])
        self.assertFalse(result["live_trading_authorized"])
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["database_mutation_statements"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))
        source.assert_called_once_with(NOW)

    def test_existing_0700_ledger_remains_unchanged(self):
        self.root.mkdir(mode=0o700)
        private_file = self.root / "decision-existing.json"
        private_file.write_bytes(b"fixture")
        private_file.chmod(0o600)
        before = private_file.read_bytes()
        result, source = self._run()
        self.assertEqual(result["status"], "owner_preflight_ready_no_capture")
        self.assertTrue(result["ledger_directory_exists"])
        self.assertEqual(private_file.read_bytes(), before)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        source.assert_called_once_with(NOW)

    def test_clock_unsynchronized_refuses_before_source(self):
        result, source = self._run(sync=False)
        self.assertEqual(result["status"], "owner_os_clock_sync_unverified")
        self.assertFalse(result["capture_eligible_now"])
        source.assert_not_called()

    def test_closed_capture_windows_are_not_replayed(self):
        for now in (END+179_999, END+HOUR_MS-60_000, END+HOUR_MS-1):
            with self.subTest(now=now):
                result, source = self._run(now=now)
                self.assertEqual(result["status"], "owner_capture_window_closed")
                self.assertFalse(result["capture_eligible_now"])
                source.assert_not_called()

    def test_clock_jump_and_scope_change_abstain(self):
        for later in (NOW-1, END+HOUR_MS-59_000):
            with self.subTest(later=later):
                result, source = self._run(later=later)
                self.assertEqual(result["status"], "owner_clock_or_epoch_shift_abstain")
                source.assert_called_once_with(NOW)
        result, source = self._run(source=({"latest_closed_end_ms": END-HOUR_MS}, {}))
        self.assertEqual(result["status"], "owner_clock_or_epoch_shift_abstain")
        source.assert_called_once_with(NOW)

    def test_unready_50x24_is_fail_closed(self):
        with patch.object(ledger, "_private_source",
                          side_effect=DataValidationError("sensitive symbol BTCUSDT")), \
             patch.object(preflight, "_os_ntp_synchronized", return_value=True), \
             patch.object(preflight.time, "time_ns", return_value=NOW*1_000_000):
            result = preflight.preflight_owner_ws_decision_once(
                allow_private_readonly_research=True)
        self.assertEqual(result["status"], "owner_ws_50x24_unavailable")
        self.assertFalse(result["capture_eligible_now"])
        self.assertNotIn("BTCUSDT", json.dumps(result))

    def test_insecure_ledger_or_parent_rejects_without_read(self):
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o755)
        result, source = self._run()
        self.assertEqual(result["status"], "owner_preflight_dac_abstain")
        source.assert_not_called()
        self.root.chmod(0o700)
        self.root.rmdir()
        self.root.symlink_to(self.parent)
        result, source = self._run()
        self.assertEqual(result["status"], "owner_preflight_dac_abstain")
        source.assert_not_called()
        self.root.unlink()
        self.parent.chmod(0o777)
        try:
            result, source = self._run()
            self.assertEqual(result["status"], "owner_preflight_dac_abstain")
            source.assert_not_called()
        finally:
            self.parent.chmod(0o700)

    def test_owner_gate_failure_rejects_without_snapshot(self):
        with patch.object(ledger, "_owner_guard",
                          side_effect=DataValidationError("untrusted owner")), \
             patch.object(ledger, "_private_source",
                          side_effect=AssertionError("must not read")):
            result = preflight.preflight_owner_ws_decision_once(
                allow_private_readonly_research=True)
        self.assertEqual(result["status"], "owner_preflight_dac_abstain")
        self.assertFalse(result["capture_eligible_now"])


if __name__ == "__main__":
    unittest.main()
