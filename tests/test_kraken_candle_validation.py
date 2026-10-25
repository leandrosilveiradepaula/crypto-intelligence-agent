"""Kraken trade candle conformance: offline synthetic fixtures only."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from crypto_intelligence_agent.kraken_candle_validation import (
    KRAKEN_RESOLUTIONS, MAX_CANDLES, KrakenTradeCandleStaging,
    epoch_ms_window_to_kraken_seconds, stage_kraken_trade_candles,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataGapError, DataValidationError


HOUR = 3_600_000
DAY = 86_400_000
WEEK = 7 * DAY
START = 10 * HOUR
END = START + 3 * HOUR
NOW = END + 1_000


def fixture_rows(*, start=START, duration=HOUR, count=3):
    return [
        {"time": start + index * duration,
         "open": str(65000 + index), "high": str(65020 + index),
         "low": str(64980 + index), "close": str(65001 + index),
         "volume": 20 + index}
        for index in range(count)
    ]


def fixture_payload(*, start=START, duration=HOUR, count=3, more=False):
    return {"candles": fixture_rows(start=start, duration=duration, count=count),
            "more_candles": more}


def parse(payload=None, **kwargs):
    return stage_kraken_trade_candles(
        fixture_payload() if payload is None else payload,
        symbol=kwargs.get("symbol", "PF_XBTUSD"),
        interval=kwargs.get("interval", "1h"),
        start_open_ms=kwargs.get("start", START),
        end_open_ms=kwargs.get("end", END),
        observed_at_ms=kwargs.get("observed", NOW),
        close_safety_ms=kwargs.get("safety", 1_000),
        max_candles=kwargs.get("max_candles", MAX_CANDLES),
    )


class KrakenCandleStagingTests(unittest.TestCase):
    def test_closed_ohlc_decimal_exact_window_and_more_flag(self):
        page = parse(fixture_payload(more=True))
        self.assertEqual((page.start_open_ms, page.end_open_ms), (START, END))
        self.assertTrue(page.provider_reports_more_candles)
        self.assertEqual(len(page.candles), 3)
        self.assertEqual([c.open_time_ms for c in page.candles],
                         [START, START + HOUR, START + 2 * HOUR])
        self.assertEqual(page.candles[-1].close_time_ms, END - 1)
        self.assertEqual(page.candles[0].open, Decimal("65000"))
        self.assertEqual(page.candles[0].high, Decimal("65020"))
        self.assertTrue(all(isinstance(c, KrakenTradeCandleStaging)
                            and not isinstance(c, ClosedCandle) for c in page.candles))

    def test_raw_volume_is_unverified_not_base_or_quote_volume(self):
        page = parse()
        candle = page.candles[0]
        self.assertEqual(candle.raw_trade_volume_unverified, 20)
        self.assertEqual(candle.raw_volume_unit, "unverified")
        self.assertFalse(hasattr(candle, "base_volume"))
        self.assertFalse(hasattr(candle, "quote_volume"))
        self.assertFalse(hasattr(candle, "market"))
        self.assertFalse(hasattr(page, "persisted"))

    def test_decimal_string_prices_keep_provider_precision(self):
        body = fixture_payload()
        body["candles"][0]["open"] = "65000.123456789123456789"
        body["candles"][0]["high"] = "65050.123456789123456789"
        stage = parse(body)
        self.assertEqual(stage.candles[0].open, Decimal("65000.123456789123456789"))
        self.assertIs(type(stage.candles[0].open), Decimal)

    def test_float_or_bool_or_invalid_string_prices_rejected(self):
        for val in (65000.1, True, None, "NaN", "Infinity", "0", "-1", "garbage", ""):
            with self.subTest(price=val):
                body = fixture_payload()
                body["candles"][0]["open"] = val
                with self.assertRaises(DataValidationError):
                    parse(body)

    def test_extrema_inconsistencies_rejected(self):
        for name, val in (("high", "64000"), ("low", "66000"),
                          ("close", "99999")):
            with self.subTest(name=name):
                body = fixture_payload()
                body["candles"][0][name] = val
                with self.assertRaises(DataValidationError):
                    parse(body)

    def test_page_rejects_gaps_duplicates_out_of_order_and_excess_rows(self):
        for permutation in (
            [START, START + 2 * HOUR, START + 3 * HOUR],
            [START, START, START + 2 * HOUR],
            [START + HOUR, START, START + 2 * HOUR],
        ):
            with self.subTest(permutation=permutation):
                body = fixture_payload()
                for row, timestamp in zip(body["candles"], permutation):
                    row["time"] = timestamp
                with self.assertRaises(DataGapError):
                    parse(body)
        for count in (0, 2, 4):
            with self.subTest(count=count):
                with self.assertRaises(DataGapError):
                    parse(fixture_payload(count=count))

    def test_closure_requires_safety_margin_and_correct_observed_timestamp(self):
        with self.assertRaisesRegex(DataValidationError, "not confirmed closed"):
            parse(observed=END + 998)
        self.assertEqual(len(parse(observed=END + 999).candles), 3)
        for wrong in (True, 0, "123", 3.4):
            with self.subTest(observed=wrong):
                with self.assertRaises(DataValidationError):
                    parse(observed=wrong)
        with self.assertRaises(ValueError):
            parse(safety=-1)

    def test_schema_incomplete_or_wrong_types_rejected(self):
        cases = (
            {},
            {"candles": []},
            {"candles": [], "more_candles": "false"},
            {"candles": "wrong", "more_candles": False},
            {"candles": [None] * 3, "more_candles": False},
        )
        for body in cases:
            with self.subTest(body=repr(body)[:80]):
                with self.assertRaises((DataValidationError, DataGapError)):
                    parse(body)
        with self.assertRaises(DataValidationError):
            stage_kraken_trade_candles(
                None, symbol="PF_XBTUSD", interval="1h",
                start_open_ms=START, end_open_ms=END,
                observed_at_ms=NOW,
            )
        for field in ("open", "high", "low", "close", "volume", "time"):
            with self.subTest(field=field):
                body = fixture_payload()
                del body["candles"][0][field]
                with self.assertRaises(DataValidationError):
                    parse(body)

    def test_trade_volume_only_accepts_64bit_nonnegative_integers(self):
        for val in (-1, True, 1.25, "25", 2 ** 63):
            with self.subTest(value=val):
                body = fixture_payload()
                body["candles"][0]["volume"] = val
                with self.assertRaises(DataValidationError):
                    parse(body)
        body = fixture_payload()
        body["candles"][0]["volume"] = 0
        self.assertEqual(parse(body).candles[0].raw_trade_volume_unverified, 0)

    def test_request_limits_interval_symbol_and_alignment(self):
        for interval in ("3m", "8h", "2h", "1M", "abc"):
            with self.subTest(interval=interval):
                with self.assertRaises(DataValidationError):
                    parse(interval=interval)
        for symbol in ("PF_AAPLXUSD/../../orders", "PI_XBTUSD", "PF_xbtusd", "", "PF_XBT-USD"):
            with self.subTest(symbol=symbol):
                with self.assertRaises(DataValidationError):
                    parse(symbol=symbol)
        for start, end in ((START + 1, END), (START, END + 1), (END, START)):
            with self.subTest(start=start,end=end):
                with self.assertRaises(DataValidationError):
                    parse(start=start,end=end)
        for cap in (0, -1, 501, True):
            with self.subTest(cap=cap):
                with self.assertRaises(ValueError):
                    parse(max_candles=cap)
        with self.assertRaises(DataValidationError):
            parse(max_candles=2)

    def test_weekly_candles_start_monday_utc(self):
        monday_open = 4 * DAY
        body = fixture_payload(start=monday_open, duration=WEEK, count=1)
        result = parse(body, interval="1w", start=monday_open,
                       end=monday_open + WEEK, observed=monday_open + WEEK + 1000)
        self.assertEqual(len(result.candles), 1)
        self.assertEqual(result.candles[0].open_time_ms, monday_open)
        with self.assertRaises(DataValidationError):
            parse(body, interval="1w", start=0, end=WEEK,
                  observed=WEEK + 1000)

    def test_epoch_seconds_range_conversion_never_confuses_ms_with_seconds(self):
        first, last = epoch_ms_window_to_kraken_seconds(
            interval="1h", start_open_ms=START, end_open_ms=END,
        )
        self.assertEqual((first, last), (START // 1000, END // 1000))
        self.assertEqual((last - first), 3 * 3600)
        with self.assertRaises(DataValidationError):
            epoch_ms_window_to_kraken_seconds(
                interval="1h", start_open_ms=START // 1000,
                end_open_ms=END // 1000,
            )

    def test_more_candles_true_does_not_fabricate_gap_in_exact_window(self):
        stage = parse(fixture_payload(more=True))
        self.assertTrue(stage.provider_reports_more_candles)
        self.assertEqual(len(stage.candles), 3)
        self.assertEqual(stage.candles[1].open_time_ms, START + HOUR)

    def test_ohlc_staging_is_deterministic_for_identical_offline_payload(self):
        a = fixture_payload()
        first = parse(a)
        second = parse(deepcopy(a))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
