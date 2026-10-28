"""J1 #253: all archive payloads are synthetic; never persist real market rows."""
from __future__ import annotations
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal
import gzip
import unittest

from crypto_intelligence_agent.bybit_public_trade_archive import (
    FIELDS, inspect_trade_archive,
)
from crypto_intelligence_agent.bybit_trade_hourly_research import (
    reconstruct_weekly_trade_hours,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_bybit_archive_week import samples

D = Decimal
FIRST = date(2020, 4, 5)
MIDNIGHT = int(datetime(2020, 4, 5, tzinfo=timezone.utc).timestamp())


def _row(timestamp: str, price: str, size: str = "1") -> str:
    return ",".join((
        timestamp, "BTCUSDT", "Buy", size, price, "PlusTick",
        "synthetic-id", "100000000", size, size,
    ))


def _replace_first_day(rows: list[str]) -> tuple[tuple[str, bytes], ...]:
    records = samples(FIRST)
    csv_data = ",".join(FIELDS) + "\n" + "\n".join(rows) + "\n"
    return ((records[0][0], gzip.compress(csv_data.encode("ascii"), mtime=0)),
            *records[1:])


class HourlyResearchTests(unittest.TestCase):
    def test_hourly_ohlc_decimal_units_and_missing_buckets(self):
        t = str(MIDNIGHT)
        rows = [_row(t, "100", "0.000000000000000001"),
                _row(str(MIDNIGHT + 3), "90", "1.5"),
                _row(str(MIDNIGHT + 3599), "110", "2")]
        series = reconstruct_weekly_trade_hours(_replace_first_day(rows))
        self.assertEqual(len(series.hours), 7)
        self.assertEqual(len(series.missing_hour_open_ms), 161)
        self.assertEqual(series.hours[0].trade_count, 3)
        self.assertEqual(series.hours[0].open_price, D("100"))
        self.assertEqual(series.hours[0].high_price, D("110"))
        self.assertEqual(series.hours[0].low_price, D("90"))
        self.assertEqual(series.hours[0].close_price, D("110"))
        self.assertEqual(series.hours[0].reported_size_total,
                         D("3.500000000000000001"))
        self.assertEqual(series.hours[0].reported_home_notional_total,
                         D("3.500000000000000001"))
        self.assertEqual(series.hours[0].reported_foreign_notional_total,
                         D("3.500000000000000001"))
        self.assertEqual(series.ambiguous_boundary_hours, 0)
        self.assertEqual(series.unambiguous_boundary_hours, 7)
        self.assertFalse(series.canonical_ohlcv_approved)
        self.assertFalse(series.rights_authorized)
        self.assertFalse(series.financial_backtest_approved)
        self.assertFalse(series.orders_sent)
        self.assertEqual(series, reconstruct_weekly_trade_hours(_replace_first_day(rows)))
        with self.assertRaises(FrozenInstanceError):
            series.hours[0].trade_count = 999

    def test_descending_archive_keeps_chronological_open_close(self):
        t = str(MIDNIGHT)
        rows = [_row(t, "100"), _row(str(MIDNIGHT + 1), "70"),
                _row(str(MIDNIGHT + 2), "110")]
        forward = reconstruct_weekly_trade_hours(_replace_first_day(rows))
        reverse = reconstruct_weekly_trade_hours(_replace_first_day(list(reversed(rows))))
        for r in (forward.hours[0], reverse.hours[0]):
            self.assertEqual((r.open_price, r.high_price, r.low_price, r.close_price),
                             (D("100"), D("110"), D("70"), D("110")))
        self.assertEqual(forward.hours[0], reverse.hours[0])

    def test_timestamp_ties_with_different_prices_omit_boundary_values(self):
        t = str(MIDNIGHT)
        rows = [_row(t, "100"), _row(t, "101"),
                _row(str(MIDNIGHT + 1), "110"),
                _row(str(MIDNIGHT + 2), "120"),
                _row(str(MIDNIGHT + 2), "119")]
        one = reconstruct_weekly_trade_hours(_replace_first_day(rows))
        hour = one.hours[0]
        self.assertIsNone(hour.open_price)
        self.assertIsNone(hour.close_price)
        self.assertTrue(hour.open_boundary_ambiguous)
        self.assertTrue(hour.close_boundary_ambiguous)
        self.assertEqual(hour.low_price, D("100"))
        self.assertEqual(hour.high_price, D("120"))
        self.assertEqual(one.ambiguous_boundary_hours, 1)
        self.assertEqual(one.unambiguous_boundary_hours, 6)

    def test_microseconds_do_not_collapse_into_fake_monotonicity(self):
        t = str(MIDNIGHT)
        records = _replace_first_day([
            _row(t + ".000001", "100"),
            _row(t + ".000003", "101"),
            _row(t + ".000002", "102"),
        ])
        with self.assertRaises(DataGapError):
            inspect_trade_archive(records[0][1], archive_name=records[0][0])
        with self.assertRaises(DataGapError):
            reconstruct_weekly_trade_hours(records)

    def test_invalid_calendar_and_tampered_gzip_are_not_reconstructed(self):
        data = samples(FIRST)
        for candidate in (data[:-1], data[::-1],
                          data[:2]+((data[2][0], b"corrupt"),)+data[3:]):
            with self.subTest(count=len(candidate)), self.assertRaises(DataValidationError):
                reconstruct_weekly_trade_hours(candidate)


if __name__ == "__main__":
    unittest.main()
