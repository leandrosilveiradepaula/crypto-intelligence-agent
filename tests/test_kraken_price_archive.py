"""J1/WU34: SQLite price-only research must not become canonical OHLCV."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest

from crypto_intelligence_agent.kraken_candle_validation import stage_kraken_trade_candles
from crypto_intelligence_agent.kraken_public_readonly import (
    KrakenCapturedCandleResearchPage,
)
from crypto_intelligence_agent.kraken_price_archive import SQLiteKrakenPriceOnlyArchive
from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DuplicateCandleError,
)

HOUR = 3_600_000
START = 20 * HOUR
END = START + 3 * HOUR
OBSERVED = END + 2_000


def captured(*, start=START, count=3, observed=None, price_shift=0):
    end = start + count * HOUR
    if observed is None:
        observed = end + 2_000
    payload = {
        "more_candles": False,
        "candles": [
            {
                "time": start + i * HOUR,
                "open": str(Decimal("100.000000000000123456") + price_shift),
                "high": "105", "low": "90",
                "close": "101.000000000000098765",
                "volume": "12.500000000000000001",
            }
            for i in range(count)
        ],
    }
    stage = stage_kraken_trade_candles(
        payload, symbol="PF_XBTUSD", interval="1h",
        start_open_ms=start, end_open_ms=end,
        observed_at_ms=observed, close_safety_ms=1_000,
    )
    return KrakenCapturedCandleResearchPage(observed_at_ms=observed, staged=stage)


class PriceOnlyStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "private_research.sqlite"
        self.store = SQLiteKrakenPriceOnlyArchive(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def prices(self, *, start=START, end=END, when=OBSERVED):
        return self.store.prices_as_of(
            symbol="PF_XBTUSD", interval="1h",
            start_open_ms=start, end_open_ms=end, as_of_ms=when,
        )

    def quality(self, *, start=START, end=END, when=OBSERVED):
        return self.store.price_quality(
            symbol="PF_XBTUSD", interval="1h",
            start_open_ms=start, end_open_ms=end, as_of_ms=when,
        )

    def test_price_only_persisted_not_canonical_and_no_volume_columns(self):
        self.assertEqual(self.store.commit_price_only(captured()), 3)
        rows = self.prices()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].open, Decimal("100.000000000000123456"))
        self.assertEqual(rows[0].close, Decimal("101.000000000000098765"))
        self.assertEqual(rows[0].first_observed_at_ms, OBSERVED)
        self.assertFalse(rows[0].canonical_ohlcv)
        self.assertNotIsInstance(rows[0], ClosedCandle)
        self.assertFalse(hasattr(rows[0], "base_volume"))
        self.assertFalse(hasattr(rows[0], "quote_volume"))
        self.assertFalse(hasattr(rows[0], "raw_trade_volume_unverified"))
        with closing(sqlite3.connect(self.path)) as conn, conn:
            columns = [row[1] for row in conn.execute(
                "PRAGMA table_info(kraken_research_prices)").fetchall()]
        self.assertEqual(columns.count("open"), 1)
        self.assertFalse(any("volume" in name for name in columns))
        self.assertEqual(
            self.store.candles(exchange="kraken_futures", market="linear_perpetual",
                               symbol="PF_XBTUSD", interval="1h",
                               start_open_ms=START, end_open_ms=END),
            (),
        )

    def test_page_coverage_precise_and_receipts_required(self):
        self.assertEqual(self.store.commit_price_only(captured()), 3)
        result = self.quality()
        self.assertTrue(result.complete)
        self.assertFalse(result.canonical_ohlcv)
        self.assertEqual(result.expected, 3)
        self.assertEqual(result.captured, 3)
        self.assertEqual(result.missing_open_times_ms, ())
        self.assertTrue(result.backed_by_page_receipts)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DELETE FROM kraken_research_price_pages")
        without_receipt = self.quality()
        self.assertFalse(without_receipt.complete)
        self.assertFalse(without_receipt.backed_by_page_receipts)

    def test_replay_across_sessions_is_idempotent_and_captures_first_time(self):
        page = captured()
        self.assertEqual(self.store.commit_price_only(page), 3)
        reopened = SQLiteKrakenPriceOnlyArchive(self.path)
        self.assertEqual(reopened.commit_price_only(page), 0)
        self.assertEqual(len(reopened.prices_as_of(
            symbol="PF_XBTUSD", interval="1h", start_open_ms=START,
            end_open_ms=END, as_of_ms=OBSERVED)), 3)
        self.assertEqual(reopened.commit_price_only(captured(observed=OBSERVED + 5_000)), 0)
        self.assertTrue(all(row.first_observed_at_ms == OBSERVED for row in self.prices()))

    def test_known_only_after_real_capture_time_no_historical_backfill(self):
        self.store.commit_price_only(captured())
        self.assertEqual(self.prices(when=OBSERVED - 1), ())
        self.assertEqual(self.quality(when=OBSERVED - 1).captured, 0)
        self.assertFalse(self.quality(when=OBSERVED - 1).complete)
        self.assertEqual(len(self.prices(when=OBSERVED)), 3)

    def test_consecutive_pages_require_real_receipts_and_no_gaps(self):
        self.store.commit_price_only(captured())
        future = captured(start=END, observed=END + 3 * HOUR + 2_000)
        self.store.commit_price_only(future)
        six = self.quality(end=END + 3 * HOUR, when=future.observed_at_ms)
        self.assertEqual(six.expected, 6)
        self.assertEqual(six.captured, 6)
        self.assertTrue(six.complete)
        early = self.quality(end=END + 3 * HOUR, when=OBSERVED)
        self.assertFalse(early.complete)
        self.assertEqual(early.missing_open_times_ms,
                         (END, END + HOUR, END + 2 * HOUR))

    def test_partial_window_without_contiguous_page_not_complete(self):
        self.store.commit_price_only(captured())
        page = captured(start=END + HOUR, observed=END + 4 * HOUR + 2_000)
        self.store.commit_price_only(page)
        result = self.quality(end=END + 4 * HOUR, when=page.observed_at_ms)
        self.assertEqual(result.missing_open_times_ms, (END,))
        self.assertFalse(result.complete)

    def test_conflict_rolls_back_new_candles_and_receipt(self):
        self.store.commit_price_only(captured())
        conflicting = captured(start=START + HOUR, price_shift=1,
                               observed=END + 2 * HOUR + 2_000)
        with self.assertRaises(DuplicateCandleError):
            self.store.commit_price_only(conflicting)
        self.assertEqual(len(self.prices(end=END + HOUR, when=conflicting.observed_at_ms)), 3)
        self.assertFalse(self.quality(
            end=END + HOUR, when=conflicting.observed_at_ms).complete)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            count, = conn.execute("SELECT COUNT(*) FROM kraken_research_price_pages").fetchone()
        self.assertEqual(count, 1)

    def test_rejects_backdated_reobservation_of_existing_page(self):
        self.store.commit_price_only(captured(observed=OBSERVED + 9_000))
        with self.assertRaises(DuplicateCandleError):
            self.store.commit_price_only(captured(observed=OBSERVED))
        self.assertEqual(self.prices(when=OBSERVED), ())

    def test_rejects_forged_volume_unit_source_and_timestamp(self):
        page = captured()
        broken = [
            replace(page, source="untrusted"),
            replace(page, observed_at_ms=END + 10),
            replace(page, staged=replace(page.staged, candles=page.staged.candles[:2])),
            replace(page, staged=replace(
                page.staged, candles=(
                    replace(page.staged.candles[0], raw_volume_unit="base"),
                    *page.staged.candles[1:],
                ))),
            replace(page, staged=replace(
                page.staged, candles=(
                    replace(page.staged.candles[0], source="other"),
                    *page.staged.candles[1:],
                ))),
            replace(page, staged=replace(
                page.staged, candles=(
                    replace(page.staged.candles[0],
                            raw_trade_volume_unverified=Decimal("-1")),
                    *page.staged.candles[1:],
                ))),
        ]
        for item in broken:
            with self.subTest(item=repr(item)[:150]), self.assertRaises(DataGapError):
                self.store.commit_price_only(item)
        self.assertEqual(self.prices(), ())

    def test_rejects_nan_float_and_bad_ohlc_forged_dataclass(self):
        base = captured()
        for change in (
            {"open": Decimal("NaN")}, {"open": float(100)},
            {"high": Decimal("99")}, {"close": Decimal("-1")},
            {"raw_trade_volume_unverified": Decimal("Infinity")},
        ):
            corrupted = replace(base.staged.candles[0], **change)
            page = replace(base, staged=replace(
                base.staged, candles=(corrupted, *base.staged.candles[1:])))
            with self.subTest(change=change), self.assertRaises(DataGapError):
                self.store.commit_price_only(page)
        self.assertEqual(self.prices(), ())

    def test_query_rejects_unknown_and_unaligned_windows(self):
        for start, end, when in (
            (START + 1, END, OBSERVED), (END, START, OBSERVED),
            (START, END, True), (START, END, 0),
        ):
            with self.subTest(start=start, end=end, when=when), self.assertRaises(DataGapError):
                self.store.prices_as_of(
                    symbol="PF_XBTUSD", interval="1h",
                    start_open_ms=start, end_open_ms=end, as_of_ms=when)
        with self.assertRaises(DataGapError):
            self.store.prices_as_of(
                symbol="PF_XBTUSD", interval="1M",
                start_open_ms=START, end_open_ms=END, as_of_ms=OBSERVED)

    def test_rejects_canonical_row_as_research_payload(self):
        with self.assertRaises(DataGapError):
            self.store.commit_price_only(object())
        self.assertEqual(self.prices(), ())


if __name__ == "__main__":
    unittest.main()
