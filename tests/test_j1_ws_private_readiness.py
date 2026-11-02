"""OPS13: private read-only readiness, fail-closed and no implicit probes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import OfflineStreamAudit
from crypto_intelligence_agent.j1_ws_private_readiness import read_private_ws_readiness
from scripts.read_j1_ws_private_readiness import main
from test_j1_bybit_closed_stream_cache import DECISION, scope


@unittest.skipUnless(os.name == "posix", "private owner-only POSIX contract")
class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        self.path = self.directory / "ws-confirmed.sqlite"
        self.path.write_bytes(b"PRIVATE_UNTOUCHED_JOURNAL_FIXTURE")
        self.path.chmod(0o600)
        self.reviewed = scope()
        self.clock = DECISION + 4000

    def report(self, *, rows=48, missing=0, gaps=0, when=None):
        audit = OfflineStreamAudit(
            status="offline_fixture_only", persisted_rows=rows,
            observed_symbols=2, journal_digest_sha256="a"*64,
            missing_24h_symbols=missing, complete_24h_symbols=2-missing,
            rank_digest_sha256="b"*64 if missing == 0 else None,
            declared_gap_markers=gaps,
        )
        with patch("crypto_intelligence_agent.j1_ws_private_readiness._read_epoch_chain",
                   return_value=(self.reviewed,)), patch(
                   "crypto_intelligence_agent.j1_ws_private_readiness._audit_epoch_chain",
                   return_value=audit), patch(
                   "crypto_intelligence_agent.j1_ws_private_readiness.read_owner_ws_health",
                   return_value={"status": "health_recent_unverified"}):
            return read_private_ws_readiness(
                self.directory, now_ms=self.clock if when is None else when,
            )

    def test_complete_sample_is_not_live_or_marketwide(self):
        original = self.path.read_bytes()
        got = self.report()
        self.assertEqual(got["status"], "ws_private_sample_complete_not_live")
        self.assertEqual(got["reviewed_contracts"], 2)
        self.assertEqual(got["remaining_rows"], 100000-48)
        self.assertEqual(got["remaining_full_days_at_scope"], (100000-48)//48)
        self.assertFalse(got["low_capacity_warning"])
        for key in ("worker_running_verified", "source_authenticated",
                    "marketwide_top50_verified", "live_trading_authorized",
                    "orders_sent"):
            self.assertFalse(got[key])
        self.assertEqual(got["network_requests"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(got))
        self.assertEqual(self.path.read_bytes(), original)

    def test_missing_hours_and_gap_markers_are_only_aggregates(self):
        got = self.report(rows=200, missing=1, gaps=2)
        self.assertEqual(got["status"], "ws_private_sample_incomplete_abstain")
        self.assertEqual((got["complete_24h_contracts"], got["missing_24h_contracts"]),
                         (1, 1))
        self.assertEqual(got["declared_gap_markers"], 2)
        self.assertNotIn("ETHUSDT", json.dumps(got))

    def test_low_capacity_and_full_limit_warn_without_deletion(self):
        before = self.path.read_bytes()
        got = self.report(rows=100000-48*7)
        self.assertEqual(got["remaining_full_days_at_scope"], 7)
        self.assertTrue(got["low_capacity_warning"])
        full = self.report(rows=100000)
        self.assertEqual(full["remaining_rows"], 0)
        self.assertTrue(full["low_capacity_warning"])
        self.assertEqual(before, self.path.read_bytes())

    def test_wrong_permissions_and_symlink_fail_closed_before_audit(self):
        self.directory.chmod(0o755)
        self.assertEqual(self.report()["status"], "ws_private_readiness_abstain")
        self.directory.chmod(0o700)
        self.path.chmod(0o644)
        self.assertEqual(self.report()["status"], "ws_private_readiness_abstain")
        self.path.chmod(0o600)
        self.path.unlink()
        self.path.symlink_to(self.directory / "missing")
        self.assertEqual(self.report()["status"], "ws_private_readiness_abstain")

    def test_clock_and_untrusted_counters_fail_closed(self):
        self.assertEqual(self.report(when=DECISION)["status"],
                         "ws_private_readiness_abstain")
        self.assertEqual(self.report(when=True)["status"],
                         "ws_private_readiness_abstain")
        self.assertEqual(self.report(rows=100001)["status"],
                         "ws_private_readiness_abstain")
        self.assertEqual(self.report(missing=3)["status"],
                         "ws_private_readiness_abstain")
        self.assertEqual(self.report(gaps=-1)["status"],
                         "ws_private_readiness_abstain")

    def test_cli_defaults_to_no_private_access_and_no_network(self):
        from contextlib import redirect_stdout
        from io import StringIO
        out = StringIO()
        with redirect_stdout(out):
            rc = main(["--directory", "/does-not-exist/private"])
        self.assertEqual(rc, 1)
        data = json.loads(out.getvalue())
        self.assertEqual(data["status"], "ws_private_readiness_abstain")
        self.assertFalse(data["orders_sent"])
        self.assertNotIn("/does-not-exist", out.getvalue())


if __name__ == "__main__":
    unittest.main()
