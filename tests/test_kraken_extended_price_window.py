"""J1/WU41: longer Kraken historical price-only windows, offline and fail closed."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys

from crypto_intelligence_agent.kraken_candle_validation import stage_kraken_trade_candles
from crypto_intelligence_agent.kraken_price_archive import SQLiteKrakenPriceOnlyArchive
from crypto_intelligence_agent.kraken_public_readonly import KrakenCapturedCandleResearchPage
from crypto_intelligence_agent.market_data import DataGapError, DuplicateCandleError
from crypto_intelligence_agent.private_kraken_research import (
    LocalResearchError, capture_private_research,
)
from test_private_kraken_research import (
    NOW, HOUR, TOP, Reader, market, collect,
)


class WindowReader(Reader):
    def __init__(self, hours: int, *, corrupt_index=None, price_shift=0):
        super().__init__(market_value=market())
        self.hours = hours
        self.corrupt_index = corrupt_index
        self.price_shift = price_shift

    def staged_closed_candles(self, *, symbol, interval, start_open_ms, end_open_ms):
        self.calls.append("chart")
        assert symbol == "PF_XBTUSD" and interval == "1h"
        assert end_open_ms == TOP - HOUR
        assert (end_open_ms - start_open_ms) // HOUR == self.hours
        rows = [
            {
                "time": start_open_ms + i * HOUR,
                "open": str(Decimal("101.123456789123456789") + self.price_shift),
                "high": "150", "low": "90",
                "close": "105.987654321987654321",
                "volume": "77.123456789987654321",
            }
            for i in range(self.hours)
        ]
        if self.corrupt_index is not None:
            rows[self.corrupt_index]["time"] += HOUR
        result = stage_kraken_trade_candles(
            {"candles": rows, "more_candles": False},
            symbol=symbol, interval="1h", start_open_ms=start_open_ms,
            end_open_ms=end_open_ms, observed_at_ms=NOW + 400,
        )
        return KrakenCapturedCandleResearchPage(
            observed_at_ms=NOW + 400, staged=result)


class KrakenExtendedWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "private_hourly.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def _collect(self, reader, *, hours: int):
        return collect(self.db, reader, price_hours=hours)

    def test_extended_day_24_hourly_realistic_exact_decimal_and_quality(self):
        reader = WindowReader(24)
        summary = self._collect(reader, hours=24)
        self.assertEqual(summary.price_hours_requested, 24)
        self.assertEqual(summary.price_symbols_validated, 1)
        self.assertEqual(summary.private_price_candles_added, 24)
        self.assertEqual(summary.price_candles_in_window, 24)
        self.assertEqual(summary.public_gets_on_success, 3)
        self.assertTrue(summary.price_window_complete)
        self.assertEqual(reader.calls, ["instruments_and_tickers", "chart"])
        self.assertFalse(summary.canonical_ohlcv_approved)
        self.assertFalse(summary.historical_top50_approved)
        self.assertFalse(summary.public_or_commercial_rights_approved)
        self.assertFalse(summary.orders_sent)
        start = TOP - 25 * HOUR
        end = TOP - HOUR
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        rows = archive.prices_as_of(
            symbol="PF_XBTUSD", interval="1h", start_open_ms=start,
            end_open_ms=end, as_of_ms=NOW + 400,
        )
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0].open, Decimal("101.123456789123456789"))
        self.assertEqual(rows[-1].open_time_ms, TOP - 2 * HOUR)
        self.assertFalse(hasattr(rows[0], "base_volume"))
        self.assertFalse(hasattr(rows[0], "quote_volume"))
        self.assertTrue(archive.price_quality(
            symbol="PF_XBTUSD", interval="1h", start_open_ms=start,
            end_open_ms=end, as_of_ms=NOW + 400).complete)
        self.assertEqual(archive.prices_as_of(
            symbol="PF_XBTUSD", interval="1h", start_open_ms=start,
            end_open_ms=end, as_of_ms=NOW + 399), ())
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0], 0)
            columns = [x[1] for x in conn.execute(
                "PRAGMA table_info(kraken_research_prices)")]
            self.assertFalse(any("volume" in x for x in columns))

    def test_max_bounded_72_hour_window_and_cross_session_replay(self):
        first = self._collect(WindowReader(72), hours=72)
        self.assertEqual(first.private_price_candles_added, 72)
        second = self._collect(WindowReader(72), hours=72)
        self.assertEqual(second.private_price_candles_added, 0)
        self.assertEqual(second.price_candles_in_window, 72)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_prices").fetchone()[0], 72)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_price_pages").fetchone()[0], 1)

    def test_invalid_hours_do_not_open_database_or_call_any_network(self):
        for bad in (0, -1, 1, 2, 73, 500, True, False, 2.5, "24", None):
            reader = Reader()
            with self.subTest(hours=bad), self.assertRaisesRegex(
                LocalResearchError, "price_hours_must_be_between_3_and_72"
            ):
                self._collect(reader, hours=bad)
            self.assertEqual(reader.calls, [])
            self.assertFalse(self.db.exists())

    def test_missing_hour_in_24_is_hard_gap_before_any_database_write(self):
        reader = WindowReader(24, corrupt_index=3)
        with self.assertRaises(DataGapError):
            self._collect(reader, hours=24)
        self.assertEqual(reader.calls, ["instruments_and_tickers", "chart"])
        self.assertFalse(self.db.exists())

    def test_conflicting_historical_replay_rolls_back_prices(self):
        self._collect(WindowReader(24), hours=24)
        with self.assertRaises(DuplicateCandleError):
            self._collect(WindowReader(24, price_shift=1), hours=24)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_prices").fetchone()[0], 24)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_price_pages").fetchone()[0], 1)

    def test_default_stays_three_hours_with_existing_cli(self):
        reader = WindowReader(3)
        result = collect(self.db, reader)
        self.assertEqual(result.price_hours_requested, 3)
        self.assertEqual(result.private_price_candles_added, 3)

    def test_help_and_denied_cli_do_not_emit_sensitive_db_path(self):
        root = Path(__file__).resolve().parent.parent
        output = subprocess.run(
            [sys.executable, "-m", "scripts.collect_private_kraken_research",
             "--help"], cwd=root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn("--price-hours", output.stdout)
        output = subprocess.run(
            [sys.executable, "-m", "scripts.collect_private_kraken_research",
             "--database", str(self.db), "--price-hours", "24"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(output.returncode, 1)
        self.assertEqual(json.loads(output.stdout)["status"], "double_opt_in_required")
        self.assertNotIn(str(self.db), output.stdout)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
