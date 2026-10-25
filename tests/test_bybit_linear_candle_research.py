"""Bybit V5 linear OHLCV research: synthetic offline fixtures, no API access."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from crypto_intelligence_agent.bybit_linear_candle_research import (
    SOURCE, UNIT_BASIS, BybitLinearCandleResearch,
    stage_bybit_linear_kline,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataGapError, DataValidationError


HOUR = 3_600_000
START = 10 * HOUR
END = START + 3 * HOUR
OBSERVED = END + 1000


def fixture(*, quote="USDT"):
    return {
        "retCode": 0, "retMsg": "OK",
        "result": {
            "category": "linear", "symbol": "BTC" + quote,
            "list": [
                [str(START + i * HOUR), str(60000 + i), str(60100 + i),
                 str(59900 + i), str(60001 + i),
                 f"1.{i}23456789123456789",
                 f"60001.{i}23456789123456789"]
                for i in (2, 1, 0)
            ],
        },
    }


def parse(payload=None, **kwargs):
    return stage_bybit_linear_kline(
        fixture() if payload is None else payload,
        symbol=kwargs.get("symbol", "BTCUSDT"),
        quote_currency=kwargs.get("quote", "USDT"),
        contract_type=kwargs.get("type", "LinearPerpetual"),
        contract_status=kwargs.get("status", "Trading"),
        contract_observed_at_ms=kwargs.get("contract_observed", START),
        observed_at_ms=kwargs.get("observed", OBSERVED),
        max_contract_age_ms=kwargs.get("max_contract_age", 4 * HOUR),
        interval=kwargs.get("interval", "1h"),
        start_open_ms=kwargs.get("start", START),
        end_open_ms=kwargs.get("end", END),
        close_safety_ms=kwargs.get("safety", 1_000),
        max_candles=kwargs.get("max_candles", 1000),
    )


class BybitLinearCandleOfflineTests(unittest.TestCase):
    def test_documented_base_volume_and_quote_turnover_are_exact(self):
        page = parse()
        self.assertEqual(page.source, SOURCE)
        self.assertEqual(page.quote_currency, "USDT")
        self.assertEqual([x.open_time_ms for x in page.candles],
                         [START, START + HOUR, START + 2 * HOUR])
        self.assertEqual(page.candles[0].close_time_ms, START + HOUR - 1)
        self.assertIsInstance(page.candles[0], BybitLinearCandleResearch)
        self.assertNotIsInstance(page.candles[0], ClosedCandle)
        self.assertEqual(page.candles[0].documented_base_volume,
                         Decimal("1.023456789123456789"))
        self.assertEqual(page.candles[0].documented_quote_turnover,
                         Decimal("60001.023456789123456789"))
        self.assertEqual(page.candles[-1].unit_basis, UNIT_BASIS)
        self.assertFalse(hasattr(page.candles[0], "base_volume"))
        self.assertFalse(hasattr(page.candles[0], "quote_volume"))

    def test_usdc_volume_remains_explicitly_usdc_not_usd(self):
        page = parse(fixture(quote="USDC"), symbol="BTCUSDC", quote="USDC")
        self.assertEqual(page.quote_currency, "USDC")
        self.assertTrue(all(x.quote_currency == "USDC" for x in page.candles))
        self.assertNotEqual(page.quote_currency, "USD")

    def test_no_inference_that_turnover_equals_close_times_volume(self):
        row = parse().candles[0]
        self.assertNotEqual(row.documented_quote_turnover,
                            row.close * row.documented_base_volume)

    def test_zero_volume_and_zero_turnover_are_valid_prices_positive(self):
        payload = fixture()
        payload["result"]["list"][0][-2:] = ["0.000000000000", "0"]
        result = parse(payload)
        self.assertEqual(result.candles[-1].documented_base_volume, Decimal(0))
        self.assertEqual(result.candles[-1].documented_quote_turnover, Decimal(0))

    def test_reverse_order_is_required_not_silently_sorted(self):
        payload = fixture()
        payload["result"]["list"].reverse()
        with self.assertRaises(DataGapError):
            parse(payload)

    def test_missing_gap_duplicate_or_extra_row_rejected(self):
        for mutation in ("missing", "duplicate", "extra", "time_shift"):
            with self.subTest(mutation=mutation):
                payload = fixture()
                rows = payload["result"]["list"]
                if mutation == "missing":
                    rows.pop(1)
                elif mutation == "duplicate":
                    rows[1][0] = rows[0][0]
                elif mutation == "extra":
                    rows.append(deepcopy(rows[-1]))
                else:
                    rows[1][0] = str(int(rows[1][0]) + 1)
                with self.assertRaises(DataGapError):
                    parse(payload)

    def test_unclosed_latest_kline_is_rejected_not_used_as_closed(self):
        with self.assertRaisesRegex(DataValidationError, "not confirmed closed"):
            parse(observed=END + 998)
        self.assertEqual(len(parse(observed=END + 999).candles), 3)

    def test_price_invalid_extrema_and_nonfinite_values_fail(self):
        for val in ("0", "-1", "NaN", "Infinity", "1e2", "+100",
                    100.5, True, None, "100.1234567891234567891234567"):
            with self.subTest(val=val):
                payload = fixture()
                payload["result"]["list"][0][1] = val
                with self.assertRaises(DataValidationError):
                    parse(payload)
        for i, wrong in ((2, "0.01"), (3, "99999"), (4, "90000")):
            payload = fixture()
            payload["result"]["list"][0][i] = wrong
            with self.assertRaises(DataValidationError):
                parse(payload)

    def test_volume_turnover_invalid_values_fail(self):
        for val in (float("nan"), 1.0, True, None, [], {},
                    "NaN", "Infinity", "-1", "1e3", "01.0", "+10",
                    "1.0000000000000000000000001"):
            for field in (5, 6):
                with self.subTest(value=str(val), field=field):
                    payload = fixture()
                    payload["result"]["list"][0][field] = val
                    with self.assertRaises(DataValidationError):
                        parse(payload)

    def test_wrong_category_or_spot_inverse_rejected(self):
        for category in ("inverse", "spot", None):
            payload = fixture()
            payload["result"]["category"] = category
            with self.assertRaises(DataValidationError):
                parse(payload)

    def test_only_linear_perpetual_trading_contract_can_be_staged(self):
        for ctype, status in (("LinearFutures", "Trading"),
                              ("InversePerpetual", "Trading"),
                              ("LinearPerpetual", "PreLaunch"),
                              ("LinearPerpetual", "Settling")):
            with self.subTest(ctype=ctype, status=status):
                with self.assertRaises(DataValidationError):
                    parse(type=ctype, status=status)

    def test_timestamp_anti_lookahead_and_contract_freshness(self):
        with self.assertRaisesRegex(DataValidationError, "future"):
            parse(contract_observed=OBSERVED + 1)
        with self.assertRaisesRegex(DataValidationError, "stale"):
            parse(max_contract_age=OBSERVED - START - 1)
        self.assertEqual(len(parse(max_contract_age=OBSERVED - START).candles), 3)
        for bad in (True, -1, 1.5, "1000"):
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError, DataValidationError)):
                    parse(max_contract_age=bad)
                with self.assertRaises(DataValidationError):
                    parse(observed=bad)

    def test_symbol_and_quote_consistency_require_usdt_or_usdc(self):
        for symbol, quote in (
            ("BTCUSD", "USD"), ("BTCUSDT", "USDC"), ("BTCUSDT/../", "USDT"),
            ("btcUSDT", "USDT"), ("BTCUSD", "USDT"), ("", "USDT"),
        ):
            with self.subTest(symbol=symbol,quote=quote):
                with self.assertRaises(DataValidationError):
                    parse(symbol=symbol, quote=quote)

    def test_status_payload_shape_and_string_row_requirements(self):
        payload = fixture()
        payload["retCode"] = True
        with self.assertRaises(DataValidationError):
            parse(payload)
        payload = fixture()
        payload["result"]["symbol"] = "ETHUSDT"
        with self.assertRaises(DataValidationError):
            parse(payload)
        for rows in (None, "invalid", [None, None, None],
                     [[1,2,3,4,5,6,7]] * 3,
                     [["0"] * 8] * 3):
            payload = fixture()
            payload["result"]["list"] = rows
            with self.subTest(rows=repr(rows)[:40]):
                with self.assertRaises((DataValidationError, DataGapError)):
                    parse(payload)

    def test_utc_grid_page_limit_and_week_monday(self):
        for start, end in ((START + 1, END), (START, END + 1), (END, START)):
            with self.subTest(start=start,end=end):
                with self.assertRaises(DataValidationError):
                    parse(start=start,end=end)
        for max_candles in (True, 0, -1, 1001, 2):
            with self.subTest(max_candles=max_candles):
                with self.assertRaises(DataValidationError):
                    parse(max_candles=max_candles)
        monday = 4 * 86_400_000
        # Make one weekly candle with its opening on Monday at 00:00 UTC.
        weekly = {"retCode":0,"result":{"category":"linear","symbol":"BTCUSDT",
                   "list":[[str(monday),"60000","60100","59900","60001","1","60001"]]}}
        page = parse(weekly, interval="1w", start=monday,
                     end=monday+7*86_400_000,
                     contract_observed=monday,
                     observed=monday+7*86_400_000+1000,
                     max_contract_age=7*86_400_000+1000)
        self.assertEqual(page.candles[0].open_time_ms, monday)
        with self.assertRaises(DataValidationError):
            parse(weekly, interval="1w", start=0,
                  end=7*86_400_000, contract_observed=monday,
                  observed=monday+7*86_400_000+1000)

    def test_deterministic_offline_replay(self):
        self.assertEqual(parse(fixture()), parse(deepcopy(fixture())))


if __name__ == "__main__":
    unittest.main()
