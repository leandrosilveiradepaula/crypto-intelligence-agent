"""OKX SWAP candle schema research: entirely synthetic and offline."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
import unittest

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError,
)
from crypto_intelligence_agent.okx_swap_candle_research import (
    MAX_HISTORY_PAGE, SOURCE, UNIT_BASIS,
    OkxSwapHistoryCandleResearch, stage_okx_linear_swap_history,
)


HOUR = 3_600_000
DAY = 86_400_000
START = 10 * HOUR
END = START + 3 * HOUR
OBSERVED = END + 1_000


def fixture(*, records=3):
    return {
        "code": "0", "msg": "", "data": [
            [str(START + i * HOUR), str(60000 + i),
             str(60100 + i), str(59900 + i), str(60001 + i),
             f"1.{i}123456789123456789", f"0.{i}987654321987654321",
             f"12345.{i}123456789123456789", "1"]
            for i in range(records - 1, -1, -1)
        ],
    }


def stage(response=None, **opts):
    return stage_okx_linear_swap_history(
        fixture() if response is None else response,
        instrument_id=opts.get("instrument_id", "BTC-USDT-SWAP"),
        quote_currency=opts.get("quote", "USDT"),
        instrument_type=opts.get("instrument_type", "SWAP"),
        contract_type=opts.get("contract_type", "linear"),
        instrument_status=opts.get("status", "live"),
        settlement_currency=opts.get("settlement", "USDT"),
        instrument_observed_at_ms=opts.get("instrument_observed", START),
        observed_at_ms=opts.get("observed", OBSERVED),
        max_instrument_age_ms=opts.get("max_instrument_age", 4 * HOUR),
        bar=opts.get("bar", "1H"),
        start_open_ms=opts.get("start", START),
        end_open_ms=opts.get("end", END),
        close_safety_ms=opts.get("safety", 1_000),
        max_candles=opts.get("max_candles", MAX_HISTORY_PAGE),
        price_adjustment=opts.get("price_adjustment", "unadjusted"),
    )


class OkxOfflineSchemaTests(unittest.TestCase):
    def test_contract_base_and_quote_volumes_are_distinct_decimals(self):
        page = stage()
        self.assertEqual(page.source, SOURCE)
        self.assertEqual(page.interval, "1h")
        self.assertEqual([c.open_time_ms for c in page.candles],
                         [START, START + HOUR, START + 2 * HOUR])
        self.assertEqual(page.candles[-1].close_time_ms, END - 1)
        candle = page.candles[0]
        self.assertIsInstance(candle, OkxSwapHistoryCandleResearch)
        self.assertNotIsInstance(candle, ClosedCandle)
        self.assertEqual(candle.documented_contract_volume,
                         Decimal("1.0123456789123456789"))
        self.assertEqual(candle.documented_base_volume,
                         Decimal("0.0987654321987654321"))
        self.assertEqual(candle.documented_quote_volume,
                         Decimal("12345.0123456789123456789"))
        self.assertEqual(candle.unit_basis, UNIT_BASIS)
        self.assertFalse(candle.crypto_identity_verified)
        self.assertFalse(candle.exchange_schema_verified_live)
        self.assertFalse(page.rights_for_distribution)
        self.assertFalse(hasattr(candle, "base_volume"))
        self.assertFalse(hasattr(candle, "quote_volume"))

    def test_usdc_is_not_usd_or_usdt(self):
        result = stage(instrument_id="ETH-USDC-SWAP", quote="USDC", settlement="USDC")
        self.assertEqual(result.quote_currency, "USDC")
        self.assertEqual(result.candles[0].quote_currency, "USDC")
        self.assertNotEqual(result.quote_currency, "USD")

    def test_quote_is_not_closed_price_times_base(self):
        candle = stage().candles[0]
        self.assertNotEqual(candle.documented_quote_volume,
                            candle.close * candle.documented_base_volume)

    def test_zero_trading_volume_is_valid(self):
        payload = fixture()
        payload["data"][0][5:8] = ["0", "0.00000", "0"]
        page = stage(payload)
        self.assertEqual(page.candles[-1].documented_contract_volume, Decimal(0))
        self.assertEqual(page.candles[-1].documented_base_volume, Decimal(0))
        self.assertEqual(page.candles[-1].documented_quote_volume, Decimal(0))

    def test_incomplete_candles_cannot_be_promoted(self):
        for flag in ("0", "yes", "", "2"):
            payload = fixture()
            payload["data"][0][8] = flag
            with self.subTest(flag=flag), self.assertRaises(DataValidationError):
                stage(payload)

    def test_response_status_and_msg_types(self):
        for code in (0, True, "1", "51000", None):
            payload = fixture()
            payload["code"] = code
            with self.subTest(code=code), self.assertRaises(DataValidationError):
                stage(payload)
        for value in (None, [], {}, 0, True):
            payload = fixture()
            payload["msg"] = value
            with self.subTest(msg=value), self.assertRaises(DataValidationError):
                stage(payload)

    def test_malformed_rows_exact_nine_strings_required(self):
        variants = [
            None, [], 1, ["0"] * 8, ["0"] * 10,
            [0] + ["1"] * 8, ["0"] * 8 + [False],
        ]
        for variant in variants:
            payload = fixture()
            payload["data"][0] = variant
            with self.subTest(value=repr(variant)), self.assertRaises(DataValidationError):
                stage(payload)
        for wrong in (None, {}, "missing", ()):
            payload = fixture()
            payload["data"] = wrong
            with self.subTest(value=wrong), self.assertRaises(DataValidationError):
                stage(payload)

    def test_reverse_order_duplicate_extra_missing_and_shifted_timestamp(self):
        for change in ("reverse", "duplicate", "missing", "extra", "shift"):
            payload = fixture()
            rows = payload["data"]
            if change == "reverse":
                rows.reverse()
            elif change == "duplicate":
                rows[1][0] = rows[0][0]
            elif change == "missing":
                rows.pop()
            elif change == "extra":
                rows.append(deepcopy(rows[-1]))
            elif change == "shift":
                rows[1][0] = str(START + HOUR + 1)
            with self.subTest(change=change), self.assertRaises(DataGapError):
                stage(payload)

    def test_timestamp_must_be_bounded_decimal_string(self):
        for t in (0, True, None, "NaN", "-1", "01", "1e4", "99999999999999999"):
            payload = fixture()
            payload["data"][0][0] = t
            with self.subTest(timestamp=t), self.assertRaises(DataValidationError):
                stage(payload)

    def test_invalid_prices_rejected_exactly(self):
        invalid = ("0", "-1", "NaN", "Inf", "Infinity", "1e3", "+1", "01.0",
                   "1.0000000000000000000000001", 1.0, True, None, {}, [])
        for value in invalid:
            payload = fixture()
            payload["data"][0][1] = value
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                stage(payload)

    def test_inconsistent_ohlc_rejected(self):
        for field, value in ((2, "1"), (3, "90000"), (4, "90000")):
            payload = fixture()
            payload["data"][0][field] = value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                stage(payload)

    def test_invalid_contract_base_and_quote_quantities_rejected(self):
        for field in (5, 6, 7):
            for value in (-1, 1.5, True, None, "NaN", "-1", "+2", "1e3",
                          "001.2", "0.0000000000000000000000001"):
                payload = fixture()
                payload["data"][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(DataValidationError):
                    stage(payload)

    def test_rejects_non_swap_inverse_or_inactive_contract(self):
        changes = [
            {"instrument_type": "FUTURES"},
            {"instrument_type": "SPOT"},
            {"contract_type": "inverse"},
            {"status": "suspend"},
            {"status": "post_only"},
            {"settlement": "USD"},
            {"settlement": "USDC"},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                stage(**change)

    def test_rejects_wrong_symbol_or_non_stablecoin_quote(self):
        samples = [
            ("BTC-USD-SWAP", "USD"),
            ("BTC-USDT", "USDT"),
            ("BTC-USDC-SWAP", "USDT"),
            ("btc-USDT-SWAP", "USDT"),
            ("BTC-USDT-SWAP/../", "USDT"),
            ("BTC-USDT-SWAP", "USDC"),
            ("", "USDT"),
        ]
        for instrument_id, quote in samples:
            with self.subTest(symbol=instrument_id, quote=quote), self.assertRaises(DataValidationError):
                stage(instrument_id=instrument_id, quote=quote)

    def test_future_instrument_metadata_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "future"):
            stage(instrument_observed=OBSERVED + 1)

    def test_stale_instrument_metadata_and_exact_boundary(self):
        age = OBSERVED - START
        with self.assertRaisesRegex(DataValidationError, "stale"):
            stage(max_instrument_age=age - 1)
        self.assertEqual(len(stage(max_instrument_age=age).candles), 3)

    def test_timestamp_and_age_wrong_types_rejected(self):
        for x in (True, -1, 1.5, "1000", None):
            with self.subTest(value=x):
                with self.assertRaises(DataValidationError):
                    stage(max_instrument_age=x)
                with self.assertRaises(DataValidationError):
                    stage(observed=x)
                with self.assertRaises(DataValidationError):
                    stage(instrument_observed=x)

    def test_unclosed_time_and_safety_threshold(self):
        with self.assertRaisesRegex(DataValidationError, "open or too recent"):
            stage(observed=END + 998)
        self.assertEqual(len(stage(observed=END + 999).candles), 3)
        with self.assertRaises(DataValidationError):
            stage(safety=-1)

    def test_utc_grid_is_strict_and_non_default(self):
        for start, end in ((START + 1, END), (START, END + 1), (END, START)):
            with self.subTest(start=start, end=end), self.assertRaises(DataValidationError):
                stage(start=start, end=end)

    def test_reject_utc8_1d_and_accept_explicit_utc_1d(self):
        for bad in ("1D", "1W", "1Hutc", "6H", "1M", "1D-utc"):
            with self.subTest(bar=bad), self.assertRaises(DataValidationError):
                stage(bar=bad)
        opening = 10 * DAY
        row = [[str(opening), "60000", "60100", "59900", "60001", "2", "0.01", "600", "1"]]
        page = stage({"code": "0", "msg": "", "data": row},
                     bar="1Dutc", start=opening, end=opening + DAY,
                     instrument_observed=opening, observed=opening + DAY + 1_000,
                     max_instrument_age=2 * DAY)
        self.assertEqual(page.interval, "1d")
        self.assertEqual(page.candles[0].open_time_ms, opening)

    def test_max_page_limit_and_negative_settings_rejected(self):
        for count in (True, 0, -1, 301, 2, "300", 1.5):
            with self.subTest(count=count), self.assertRaises(DataValidationError):
                stage(max_candles=count)
        with self.assertRaises(DataValidationError):
            stage(start=START, end=START + 301 * HOUR, max_candles=300)
        with self.assertRaises(DataValidationError):
            stage(price_adjustment="forward")

    def test_replay_is_deterministic_and_result_is_immutable(self):
        self.assertEqual(stage(fixture()), stage(deepcopy(fixture())))
        with self.assertRaises(FrozenInstanceError):
            stage().candles[0].quote_currency = "USD"


if __name__ == "__main__":
    unittest.main()
