"""Synthetic tests only: public trade archive never proves provider origin."""
from __future__ import annotations
from dataclasses import FrozenInstanceError
import gzip
import unittest

from crypto_intelligence_agent.bybit_public_trade_archive import (
    inspect_trade_archive, FIELDS,
)
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError

NAME = "BTCUSDT2020-04-05.csv.gz"
DAY = 1586044800

def payload(rows=None, header=None):
    header = header or FIELDS
    rows = rows if rows is not None else [
        (str(DAY+i*3600), "BTCUSDT", "Buy", "1.25", "9000.5",
         "PlusTick", f"trade-{i}", "1125062500000", "1.25", "11250.625")
        for i in range(24)
    ]
    data = ",".join(header)+"\n"+"\n".join(",".join(row) for row in rows)+"\n"
    return gzip.compress(data.encode(), mtime=0)


class BybitTradeArchiveTests(unittest.TestCase):
    def test_strict_24_hour_synthetic_day(self):
        blob = payload()
        a = inspect_trade_archive(blob, archive_name=NAME)
        self.assertEqual(a, inspect_trade_archive(blob, archive_name=NAME))
        self.assertEqual(a.trades, 24)
        self.assertEqual(a.observed_hour_count, 24)
        self.assertEqual(a.first_timestamp_ms, DAY*1000)
        self.assertFalse(a.canonical_ohlcv_approved)
        self.assertFalse(a.dataset_rights_authorized_for_production)
        self.assertFalse(a.orders_sent)
        self.assertFalse(a.live_trading_authorized)
        with self.assertRaises(FrozenInstanceError):
            a.trades = 50

    def test_missing_hours_are_not_filled(self):
        rows = [(str(DAY+i*3600), "BTCUSDT", "Buy", "1.25", "9000.5",
                 "PlusTick", f"trade-{i}", "1125062500000", "1.25", "11250.625")
                for i in (0, 4, 12)]
        result = inspect_trade_archive(payload(rows), archive_name=NAME)
        self.assertEqual(result.observed_hour_count, 3)
        self.assertEqual(result.trades, 3)

    def test_name_schema_and_bad_gzip_rejected(self):
        for name in ("ETHUSDT2020-04-05.csv.gz", "../"+NAME, NAME[:-3],
                     "BTCUSDT2020-02-30.csv.gz"):
            with self.subTest(name=name), self.assertRaises(DataValidationError):
                inspect_trade_archive(payload(), archive_name=name)
        for sample in (b"", b"x"*32, gzip.compress(b"a"*30000001,mtime=0)):
            with self.subTest(size=len(sample)), self.assertRaises(DataValidationError):
                inspect_trade_archive(sample, archive_name=NAME)
        with self.assertRaises(DataValidationError):
            inspect_trade_archive(payload(header=FIELDS[:-1]), archive_name=NAME)

    def test_bad_price_symbol_date_and_order_rejected(self):
        good = [(str(DAY+i*3600), "BTCUSDT", "Buy", "1.25", "9000.5",
                 "PlusTick", f"trade-{i}", "1125062500000", "1.25", "11250.625")
                for i in range(2)]
        edits = [
            (0, 1, "ETHUSDT"), (0, 2, "Hold"),
            (0, 3, "NaN"), (0, 4, "-1"), (0, 4, "0"),
            (0, 0, str(DAY-1)), (1, 0, str(DAY-1)),
        ]
        for index, field, value in edits:
            rows = [list(row) for row in good]
            rows[index][field] = value
            with self.subTest(field=field, value=value), self.assertRaises((DataValidationError, DataGapError)):
                inspect_trade_archive(payload(rows), archive_name=NAME)
        with self.assertRaises(DataGapError):
            inspect_trade_archive(payload(list(reversed(good))), archive_name=NAME)

if __name__ == "__main__":
    unittest.main()
