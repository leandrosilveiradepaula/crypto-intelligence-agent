"""J1 #310: real-history-preserving hourly resume, entirely offline.

All HTTP is injected and simulated; none of these tests contact Bybit.
No real user symbols/market data, credentials, orders, deploy or paid services.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
)
from scripts.audit_private_bybit_j1_progress import (
    audit_private_bybit_j1_progress,
)
from scripts.capture_private_bybit_j1 import owner_private_j1_capture
from scripts.resume_private_bybit_j1 import owner_resume_private_j1
from test_j1_private_bybit_capture import FakeFeed, H


@unittest.skipUnless(os.name == "posix", "private research 0700/0600 requires POSIX")
class ResumePreservedBybitHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name)
        self.private.chmod(0o700)
        self.db = self.private / "bybit.sqlite"
        self.feed = FakeFeed()

    def clock(self):
        return self.feed.now()

    def sleep(self, seconds):
        self.feed.observed += int(seconds * 1000) + 100

    def initial_capture(self):
        first = owner_private_j1_capture(
            database=self.db, max_assets=2, two_hourly_updates=False,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            client=BoundedBybitPublicClient(transport=self.feed.get),
            clock_ms=self.clock,
        )
        self.assertEqual(first["closed_candles"], 1440)
        return self.audit()

    def audit(self):
        return audit_private_bybit_j1_progress(
            database=self.db, allow_private_readonly_audit=True,
        )

    def later(self, initial, *, hours=3):
        self.feed.observed = initial["last_pit_decision_ms"] + hours * H + 60_000

    def run_resume(self, *, getter=None, events=None):
        return owner_resume_private_j1(
            database=self.db, max_assets=2,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            client=BoundedBybitPublicClient(transport=getter or self.feed.get),
            clock_ms=self.clock, sleep=self.sleep,
            progress=events.append if events is not None else None,
        )

    def test_30d_preserved_no_historical_pit_fabrication_two_future_hours(self):
        initial = self.initial_capture()
        self.later(initial, hours=3)
        initial_sha = initial["initial_snapshot_digest_sha256"]
        requested_incremental_starts = []
        ranking_24h_requests = 0
        events = []

        def track(url, limit):
            nonlocal ranking_24h_requests
            if "/kline" in url:
                params = parse_qs(urlsplit(url).query)
                start = int(params["start"][0])
                if params["limit"] == ["24"]:
                    # A fresh 24h PIT turnover ranking re-reads overlapping
                    # closed bars; that is NOT the 720h research backfill.
                    ranking_24h_requests += 1
                else:
                    requested_incremental_starts.append(start)
            return self.feed.get(url, limit)

        with patch("socket.create_connection",
                   side_effect=AssertionError("no real network permitted")):
            report = self.run_resume(getter=track, events=events)
        self.assertEqual(report["status"],
                         "private_j1_two_consecutive_updates_verified_not_top50")
        self.assertEqual(report["sample_assets"], 2)
        self.assertEqual(report["stored_closed_candles"], 1450)
        self.assertEqual(report["immutable_pit_snapshots"], 4)
        self.assertEqual(report["consecutive_hourly_updates_at_end"], 2)
        self.assertGreater(ranking_24h_requests, 0)
        self.assertTrue(requested_incremental_starts)
        self.assertTrue(all(
            start >= initial["last_pit_decision_ms"]
            for start in requested_incremental_starts
        ))
        self.assertTrue(report["sqlite_integrity"])
        self.assertTrue(report["old_720h_history_preserved"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(report["first_pit_digest_sha256"], initial_sha)
        self.assertEqual(
            [e["phase"] for e in events],
            ["current_pit_verified", "waiting_for_next_closed_hour",
             "hourly_pit_verified", "waiting_for_next_closed_hour",
             "hourly_pit_verified"],
        )
        # A 3h historical catch-up adds ONLY one PIT at its actual receipt
        # time; it does NOT forge PITs for the missing two past hours.
        self.assertEqual(self.audit()["immutable_pit_snapshots"], 4)

    def test_retry_after_failure_preserves_old_pit_and_does_not_start_over(self):
        initial = self.initial_capture()
        self.later(initial, hours=2)
        failure_hour = initial["last_pit_decision_ms"] + 3 * H

        def fail_future(url, limit):
            if (self.feed.observed >= failure_hour
                    and "/instruments-info" in url
                    and "symbol=" not in url):
                return b'{"retCode":10006,"retMsg":"REDACTED_DO_NOT_LOG"}'
            return self.feed.get(url, limit)

        with self.assertRaisesRegex(J1BybitCaptureError,
                                     "provider_rate_limit_no_retry"):
            self.run_resume(getter=fail_future)
        state = self.audit()
        self.assertEqual(state["stored_closed_candle_rows"], 1444)
        self.assertEqual(state["immutable_pit_snapshots"], 2)
        self.assertEqual(state["consecutive_snapshots_at_end"], 0)
        self.assertEqual(
            state["initial_snapshot_digest_sha256"],
            initial["initial_snapshot_digest_sha256"],
        )
        # Resume from the last TRUE observation. Two future hourly
        # snapshots now finish the missing consecutive proof.
        completed = self.run_resume()
        self.assertEqual(completed["consecutive_hourly_updates_at_end"], 2)
        self.assertEqual(completed["stored_closed_candles"], 1448)
        self.assertEqual(completed["immutable_pit_snapshots"], 4)

    def test_completed_resume_is_idempotent_without_any_network(self):
        initial = self.initial_capture()
        self.later(initial, hours=1)
        completed = self.run_resume()
        before = self.db.read_bytes()
        with patch("socket.create_connection",
                   side_effect=AssertionError("network not allowed")):
            second = self.run_resume(
                getter=lambda url, limit: self.fail("no GET when complete"))
        self.assertEqual(second["network_gets_attempted_this_run"], 0)
        self.assertEqual(second["first_pit_digest_sha256"],
                         completed["first_pit_digest_sha256"])
        self.assertEqual(before, self.db.read_bytes())

    def test_gap_above_safety_limit_fails_without_network_or_writes(self):
        initial = self.initial_capture()
        self.later(initial, hours=145)
        before = self.db.read_bytes()
        with self.assertRaisesRegex(
            J1BybitCaptureError, "resume_catchup_exceeds_144h_safety_limit",
        ):
            self.run_resume(
                getter=lambda url, limit: self.fail("unexpected HTTP"))
        self.assertEqual(before, self.db.read_bytes())

    def test_missing_db_and_wrong_sample_size_fail_before_network(self):
        with self.assertRaises(J1BybitCaptureError):
            self.run_resume(
                getter=lambda url, limit: self.fail("unexpected GET"))
        initial = self.initial_capture()
        with self.assertRaisesRegex(
            J1BybitCaptureError, "sample_size_does_not_match"
        ):
            owner_resume_private_j1(
                database=self.db, max_assets=1,
                allow_public_network=True, allow_private_storage=True,
                confirm_region_and_personal_research=True,
                client=BoundedBybitPublicClient(
                    transport=lambda url,limit: self.fail("unexpected GET")),
                clock_ms=self.clock,
            )
        self.assertEqual(self.audit()["immutable_pit_snapshots"], 1)


if __name__ == "__main__":
    unittest.main()
