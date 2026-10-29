"""Offline tests of owner J1 capture without real HTTP or persistent private data."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
)
from scripts.capture_private_bybit_j1 import owner_private_j1_capture
from test_j1_bybit_exit_vertical import H, T, DECISION, rows_for
from test_bybit_paginated_universe_research import instrument_row, instrument_page


class FakeFeed:
    def __init__(self):
        self.observed = T
        self.call_count = 0

    def now(self):
        self.observed += 5
        return self.observed

    def get(self, url, limit):
        self.call_count += 1
        q = parse_qs(urlsplit(url).query)
        if "/instruments-info" in url:
            symbol = q.get("symbol", ["BTCUSDT"])[0]
            if "symbol" not in q:
                data = instrument_page(
                    [instrument_row("BTCUSDT", launchTime=str(T - 1000*H)),
                     instrument_row("ETHUSDT", launchTime=str(T - 1000*H))],
                    ms=self.observed - 40, cursor="")
            else:
                data = instrument_page(
                    [instrument_row(symbol, launchTime=str(T - 1000*H))],
                    ms=self.observed - 40, cursor="")
        else:
            symbol = q["symbol"][0]
            start = int(q["start"][0])
            end = int(q["end"][0]) + 1
            count = (end - start) // H
            data = {"retCode": 0, "result": {
                "category": "linear", "symbol": symbol,
                "list": rows_for(symbol, start, count,
                                 "1000" if symbol == "BTCUSDT" else "100"),
            }}
        return json.dumps(data).encode("ascii")


@unittest.skipUnless(os.name == "posix", "private permission tests require POSIX")
class OwnerJ1CaptureTests(unittest.TestCase):
    def test_complete_two_assets_30d_no_real_network(self):
        fake = FakeFeed()
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "private"
            directory.mkdir(mode=0o700)
            db = directory / "bybit.sqlite"
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                report = owner_private_j1_capture(
                    database=db, max_assets=2,
                    allow_public_network=True, allow_private_storage=True,
                    confirm_region_and_personal_research=True,
                    client=BoundedBybitPublicClient(transport=fake.get),
                    clock_ms=fake.now,
                )
            self.assertEqual(report["selected_assets"], 2)
            self.assertEqual(report["closed_candles"], 1440)
            self.assertEqual(report["consecutive_hourly_updates"], 0)
            self.assertEqual(report["requests_attempted"], 43)
            self.assertFalse(report["marketwide_top50_verified"])
            self.assertFalse(report["orders_sent"])
            self.assertTrue(db.is_file())
            self.assertEqual(db.stat().st_mode & 0o777, 0o600)

    def test_fail_closed_without_opt_in(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "private"
            directory.mkdir(mode=0o700)
            db = directory / "research.sqlite"
            with self.assertRaisesRegex(J1BybitCaptureError, "opt_in"):
                owner_private_j1_capture(database=db)
            self.assertFalse(db.exists())

    def test_network_failure_does_not_create_database(self):
        fake = FakeFeed()
        def failing(url, limit):
            if fake.call_count == 2:
                raise J1BybitCaptureError("synthetic_http_429")
            return fake.get(url, limit)
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "private"
            directory.mkdir(mode=0o700)
            db = directory / "bybit.sqlite"
            with self.assertRaisesRegex(J1BybitCaptureError, "429"):
                owner_private_j1_capture(
                    database=db, max_assets=2,
                    allow_public_network=True, allow_private_storage=True,
                    confirm_region_and_personal_research=True,
                    client=BoundedBybitPublicClient(transport=failing),
                    clock_ms=fake.now,
                )
            self.assertFalse(db.exists())


if __name__ == "__main__":
    unittest.main()
