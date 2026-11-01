"""J1 EXIT5: 50-asset offline resume preserving real-looking 720h SQLite.

Every Bybit response is injected; no live calls, credentials, orders or VPS.
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
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from scripts.audit_private_bybit_j1_progress import audit_private_bybit_j1_progress
from scripts.capture_private_bybit_j1 import owner_private_j1_capture
from scripts.resume_private_bybit_j1 import owner_resume_private_j1
from test_bybit_paginated_universe_research import instrument_row, instrument_page
from test_j1_bybit_top50_closed_hour_rank import NOW
from test_j1_bybit_exit_vertical import H, kline


@unittest.skipUnless(os.name == "posix", "private sqlite 0700/0600 POSIX only")
class Resume50OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.path.chmod(0o700)
        self.db = self.path / "research.sqlite"
        catalog = load_reviewed_registry("expanded-52", as_of_ms=NOW)
        self.symbols = tuple(x.base + "USDT" for x in catalog.assets)
        self.assertEqual(len(self.symbols), 52)
        self.now_ms = NOW
        self.gets = []
        self.churn = False

    def clock(self):
        self.now_ms += 90
        return self.now_ms

    def sleep(self, seconds):
        self.now_ms += int(seconds * 1000) + 90

    def transport(self, url, limit):
        self.gets.append(url)
        q = parse_qs(urlsplit(url).query)
        received = self.now_ms - 45
        if "/instruments-info" in url:
            names = (q["symbol"][0],) if "symbol" in q else self.symbols
            page = instrument_page(
                [instrument_row(sym) for sym in names], ms=received, cursor="")
            for row in page["result"]["list"]:
                row.pop("marketRegion", None)
                row.pop("underlyingTicker", None)
            return json.dumps(page).encode("ascii")
        sym = q["symbol"][0]
        start = int(q["start"][0])
        hours = (int(q["end"][0]) + 1 - start) // H
        self.assertIn(hours, (*range(1, 73), 720))
        idx = self.symbols.index(sym)
        turnover = "1000" if self.churn and idx == 0 else str(idx + 1)
        data = kline(sym, start, hours, turnover)
        data["time"] = received
        return json.dumps(data).encode("ascii")

    def transport_client(self, getter=None):
        return BoundedBybitPublicClient(transport=getter or self.transport)

    def initial(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            result = owner_private_j1_capture(
                database=self.db, max_assets=50, history_page_hours=720,
                registry_variant="expanded-52", two_hourly_updates=False,
                allow_public_network=True, allow_private_storage=True,
                confirm_region_and_personal_research=True,
                client=self.transport_client(), clock_ms=self.clock)
        self.assertEqual(result["closed_candles"], 36000)
        state = self.audit()
        self.assertEqual(state["stored_closed_candle_rows"], 36000)
        self.assertEqual(state["immutable_pit_snapshots"], 1)
        return state

    def audit(self):
        return audit_private_bybit_j1_progress(
            database=self.db, allow_private_readonly_audit=True)

    def resume(self, transport=None):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            return owner_resume_private_j1(
                database=self.db, max_assets=50,
                allow_public_network=True, allow_private_storage=True,
                confirm_region_and_personal_research=True,
                client=self.transport_client(transport),
                clock_ms=self.clock, sleep=self.sleep)

    def test_50_history_preserved_catchup_12h_and_genuine_2_pit_updates(self):
        original = self.initial()
        start = original["last_pit_decision_ms"]
        initial_digest = original["initial_snapshot_digest_sha256"]
        self.now_ms = start + 12*H + 15_000
        self.gets.clear()
        final = self.resume()
        self.assertEqual(final["sample_assets"], 50)
        self.assertEqual(final["stored_closed_candles"], 36000 + 50*13)
        self.assertEqual(final["immutable_pit_snapshots"], 3)
        self.assertEqual(final["distinct_hourly_pit_updates_after_initial"], 2)
        self.assertEqual(final["consecutive_hourly_updates_at_end"], 1)
        self.assertEqual(final["first_pit_digest_sha256"], initial_digest)
        self.assertTrue(final["old_720h_history_preserved"])
        self.assertFalse(final["marketwide_top50_verified"])
        self.assertFalse(final["orders_sent"])
        shorter = [url for url in self.gets if "/kline" in url
                   and parse_qs(urlsplit(url).query)["limit"] in (["12"], ["1"])]
        self.assertEqual(len(shorter), 100)
        self.assertFalse(any(
            "/kline" in url and parse_qs(urlsplit(url).query)["limit"] == ["720"]
            for url in self.gets))
        self.assertTrue(self.audit()["sqlite_integrity_passed"])
        before = self.db.read_bytes()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            repeat = owner_resume_private_j1(
                database=self.db, max_assets=50,
                allow_public_network=True, allow_private_storage=True,
                confirm_region_and_personal_research=True,
                client=self.transport_client(lambda *_: self.fail("new GET")),
                clock_ms=self.clock)
        self.assertEqual(repeat["network_gets_attempted_this_run"], 0)
        self.assertEqual(before, self.db.read_bytes())

    def test_50_dynamic_member_enters_without_repeating_original_720h(self):
        original = self.initial()
        self.now_ms = original["last_pit_decision_ms"] + 12*H + 15_000
        self.churn = True
        self.gets.clear()
        final = self.resume()
        self.assertEqual(final["sample_assets"], 50)
        self.assertEqual(final["stored_closed_candles"], 36000 + 50*13 + 720)
        self.assertEqual(self.audit()["distinct_stored_asset_count"], 51)
        self.assertEqual(self.audit()["latest_selected_asset_count"], 50)
        self.assertEqual(final["immutable_pit_snapshots"], 3)
        # Only the newly selected member needs the 720h prefix.
        self.assertEqual(sum(
            "/kline" in url and parse_qs(urlsplit(url).query)["limit"] == ["720"]
            for url in self.gets), 1)
        self.assertTrue(self.audit()["private_page_replay_passed"])
        # Deselected series legitimately ends before newest PIT. Completed
        # resume must be safely read as idempotent without a new GET.
        frozen = self.db.read_bytes()
        replay = owner_resume_private_j1(
            database=self.db, max_assets=50,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            client=self.transport_client(
                lambda *_: self.fail("no GET after completed churn")),
            clock_ms=self.clock)
        self.assertEqual(replay["network_gets_attempted_this_run"], 0)
        self.assertEqual(self.db.read_bytes(), frozen)

    def test_rate_limit_aborts_before_partial_pit_and_preserves_full_history(self):
        original = self.initial()
        self.now_ms = original["last_pit_decision_ms"] + 12*H + 15_000
        original_sha = original["initial_snapshot_digest_sha256"]

        def limited(url, limit):
            if "/kline" in url and parse_qs(urlsplit(url).query)["limit"] == ["12"]:
                return b'{"retCode":10006,"retMsg":"DO_NOT_DISCLOSE_PRIVATE_TOKEN"}'
            return self.transport(url, limit)

        with self.assertRaisesRegex(J1BybitCaptureError,
                                    "provider_rate_limit_no_retry") as err:
            self.resume(transport=limited)
        self.assertNotIn("DO_NOT_DISCLOSE", str(err.exception))
        after = self.audit()
        self.assertEqual(after["stored_closed_candle_rows"], 36000)
        self.assertEqual(after["immutable_pit_snapshots"], 1)
        self.assertEqual(after["initial_snapshot_digest_sha256"], original_sha)
        self.assertTrue(after["sqlite_integrity_passed"])

    def test_50_budget_and_request_shape_fail_closed(self):
        from crypto_intelligence_agent.bybit_public_j1_transport import kline_url
        t = NOW // H * H
        client = self.transport_client(lambda *_: self.fail("not allowed"))
        for hours in (3, 12, 23, 37, 71):
            uri = kline_url("BTCUSDT", t-hours*H, t)
            self.assertEqual(parse_qs(urlsplit(uri).query)["limit"], [str(hours)])
            self.assertTrue(uri.startswith("https://api.bybit.com/"))
        for hours in (0, 73, 719, 721):
            with self.assertRaises(J1BybitCaptureError):
                kline_url("BTCUSDT", t-hours*H, t)
        self.assertEqual(client.requests_attempted, 0)


if __name__ == "__main__":
    unittest.main()
