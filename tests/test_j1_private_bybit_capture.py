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
            # Production V5 example omits the two TradFi-only keys.
            for row in data["result"]["list"]:
                row.pop("marketRegion", None)
                row.pop("underlyingTicker", None)
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

    def test_bulk_720h_exact_closed_history_has_seven_gets_and_replay(self):
        fake = FakeFeed()
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "private"
            folder.mkdir(mode=0o700)
            db = folder / "bulk.sqlite"
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                report = owner_private_j1_capture(
                    database=db, max_assets=2, history_page_hours=720,
                    registry_variant="expanded-13",
                    allow_public_network=True, allow_private_storage=True,
                    confirm_region_and_personal_research=True,
                    client=BoundedBybitPublicClient(transport=fake.get),
                    clock_ms=fake.now,
                )
            self.assertEqual(report["requests_attempted"], 7)
            self.assertEqual(report["closed_candles"], 1440)
            self.assertTrue(report["quality_and_readonly_replay"])
            self.assertFalse(report["marketwide_top50_verified"])
            self.assertEqual(db.stat().st_mode & 0o777, 0o600)

    def test_bulk_invalid_modes_fail_before_network(self):
        fake = FakeFeed()
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "private"
            folder.mkdir(mode=0o700)
            for invalid in (
                {"history_page_hours": 719},
                {"history_page_hours": 721},
                {"registry_variant": "invalid"},
                {"max_assets": 51},
                {"max_assets": 14, "registry_variant": "expanded-13"},
            ):
                with self.subTest(invalid=invalid), self.assertRaises(J1BybitCaptureError):
                    owner_private_j1_capture(
                        database=folder / "bulk.sqlite",
                        allow_public_network=True, allow_private_storage=True,
                        confirm_region_and_personal_research=True,
                        client=BoundedBybitPublicClient(transport=fake.get),
                        clock_ms=fake.now, **invalid)
            self.assertEqual(fake.call_count, 0)

    def test_expanded_52_ranks_50_and_stages_full_private_720h(self):
        """Single fake run: 52 eligible, 50 ranked, 36,000 closed bars, no HTTP."""
        from test_j1_bybit_top50_closed_hour_rank import NOW, DECISION
        from test_j1_bybit_exit_vertical import kline
        from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
        from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
        from crypto_intelligence_agent.bybit_pit_research import BybitPITResearchSelection

        reg = load_reviewed_registry("expanded-52", as_of_ms=NOW)
        symbols = tuple(a.base + "USDT" for a in reg.assets)
        self.assertEqual(len(symbols), 52)
        now = [NOW]
        calls = []
        def clock():
            now[0] += 90
            return now[0]
        def transport(url, limit):
            calls.append(url)
            q = parse_qs(urlsplit(url).query)
            stamp = now[0] - 45
            if "/instruments-info" in url:
                syms = (q["symbol"][0],) if "symbol" in q else symbols
                page = instrument_page(
                    [instrument_row(sym) for sym in syms],
                    ms=stamp, cursor="")
                for row in page["result"]["list"]:
                    row.pop("marketRegion", None)
                    row.pop("underlyingTicker", None)
                return json.dumps(page).encode("ascii")
            sym = q["symbol"][0]
            start, end = int(q["start"][0]), int(q["end"][0]) + 1
            hours = (end - start) // H
            self.assertIn(hours, (24, 720))
            page = kline(sym, start, hours, str(symbols.index(sym) + 1))
            page["time"] = stamp
            return json.dumps(page).encode("ascii")

        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "private"
            folder.mkdir(mode=0o700)
            db = folder / "bulk-50.sqlite"
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                result = owner_private_j1_capture(
                    database=db, max_assets=50,
                    history_page_hours=720, registry_variant="expanded-52",
                    allow_public_network=True, allow_private_storage=True,
                    confirm_region_and_personal_research=True,
                    client=BoundedBybitPublicClient(transport=transport),
                    clock_ms=clock,
                )
            self.assertEqual(result["selected_assets"],50)
            self.assertEqual(result["closed_candles"],36000)
            self.assertEqual(result["reviewed_eligible_ranked_count"],52)
            self.assertEqual(result["requests_attempted"],154)
            self.assertEqual(db.stat().st_mode & 0o777,0o600)
            self.assertFalse(result["marketwide_top50_verified"])
            self.assertFalse(result["orders_sent"])
            store=SQLiteBybitResearchStore(db)
            self.assertTrue(store.quality_report(
                symbol=symbols[-1],interval="1h",
                start_open_ms=DECISION-720*H,
                end_open_ms=DECISION).complete_for_offline_staging_only)
            self.assertFalse(store.replay_pit_research_snapshot(
                result["last_pit_sha256"] if False else next(
                    row[0] for row in __import__("sqlite3").connect(db).execute(
                        "SELECT observed_at_ms FROM bybit_research_pit_snapshots LIMIT 1"
                    ))
            ).verified_market_top50)

    def test_expanded_52_below_requested_count_aborts_before_storage(self):
        from test_j1_bybit_top50_closed_hour_rank import NOW
        from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
        reg=load_reviewed_registry("expanded-52",as_of_ms=NOW)
        symbols=tuple(a.base+"USDT" for a in reg.assets[:49])
        now=[NOW]
        def clock():
            now[0]+=100
            return now[0]
        def transport(url,limit):
            q=parse_qs(urlsplit(url).query)
            if "/instruments-info" in url:
                page=instrument_page(
                    [instrument_row(sym) for sym in symbols], ms=now[0]-40)
                for row in page["result"]["list"]:
                    row.pop("marketRegion",None)
                    row.pop("underlyingTicker",None)
                return json.dumps(page).encode("ascii")
            from test_j1_bybit_exit_vertical import kline
            sym=q["symbol"][0]
            start=int(q["start"][0])
            page=kline(sym,start,24,"1")
            page["time"]=now[0]-40
            return json.dumps(page).encode("ascii")
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)/"private"
            folder.mkdir(mode=0o700)
            db=folder/"bulk-50.sqlite"
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                with self.assertRaisesRegex(J1BybitCaptureError,"below_requested_assets"):
                    owner_private_j1_capture(
                        database=db,max_assets=50,history_page_hours=720,
                        registry_variant="expanded-52",
                        allow_public_network=True,allow_private_storage=True,
                        confirm_region_and_personal_research=True,
                        client=BoundedBybitPublicClient(transport=transport),
                        clock_ms=clock)
            self.assertFalse(db.exists())

    def test_one_run_30d_and_two_distinct_hourly_updates(self):
        fake = FakeFeed()
        def advance(seconds):
            fake.observed += int(seconds * 1000) + 100
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "private"
            directory.mkdir(mode=0o700)
            report = owner_private_j1_capture(
                database=directory / "research.sqlite", max_assets=2,
                two_hourly_updates=True,
                allow_public_network=True, allow_private_storage=True,
                confirm_region_and_personal_research=True,
                client=BoundedBybitPublicClient(transport=fake.get),
                clock_ms=fake.now, sleep=advance,
            )
            self.assertEqual(report["consecutive_hourly_updates"], 2)
            self.assertEqual(report["pit_snapshot_count"], 3)
            self.assertEqual(report["closed_candles"], 1444)
            self.assertEqual(report["requests_attempted"], 57)
            self.assertTrue(report["quality_and_readonly_replay"])
            self.assertFalse(report["marketwide_top50_verified"])

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
