"""J1/WU39: Bybit instrument + kline unit contract; all tests offline."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import unittest

from crypto_intelligence_agent.bybit_instrument_volume_contract import (
    BybitLinearDocumentedPageResearch,
    BybitLinearInstrumentResearch,
    stage_bybit_documented_linear_pair,
    validate_bybit_linear_instrument,
)
from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError,
)
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry

HOUR = 3_600_000
NOW = 1792968148000 + HOUR
START = (NOW // HOUR - 4) * HOUR
END = START + 3 * HOUR
KLINE_NOW = NOW + 500


def instrument(*, symbol="BTCUSDT", quote=None, leverage="20.00"):
    if quote is None:
        quote = "USDT" if symbol.endswith("USDT") else "USDC"
    base = symbol[:-len(quote)]
    return {
        "retCode": 0, "retMsg": "OK", "time": NOW - 50,
        "result": {
            "category": "linear", "nextPageCursor": "",
            "list": [{
                "symbol": symbol, "baseCoin": base,
                "quoteCoin": quote, "settleCoin": quote,
                "contractType": "LinearPerpetual", "status": "Trading",
                "symbolType": "", "marketRegion": "", "underlyingTicker": "",
                "tags": [], "isPreListing": False, "preListingInfo": None,
                "deliveryTime": "0", "launchTime": str(NOW - 100_000),
                "priceFilter": {"tickSize": "0.01000000000001"},
                "lotSizeFilter": {"qtyStep": "0.00001000"},
                "leverageFilter": {
                    "minLeverage": "1.0", "maxLeverage": leverage,
                },
            }],
        },
    }


def kline(*, symbol="BTCUSDT"):
    # Kline is newest-first; quote turnover is deliberately NOT close * base.
    return {
        "retCode": 0, "retMsg": "OK",
        "result": {
            "category": "linear", "symbol": symbol,
            "list": [
                [str(START + i * HOUR), "100.0000000000001",
                 "105", "95", "101.0000000000001",
                 "1.123456789123456789", "99.987654321987654321"]
                for i in (2, 1, 0)
            ],
        },
    }


def validate(payload=None, *, symbol="BTCUSDT", at=NOW, revision="expanded-10"):
    return validate_bybit_linear_instrument(
        instrument(symbol=symbol) if payload is None else payload,
        symbol=symbol, observed_at_ms=at, registry_variant=revision,
    )


def pair(metadata=None, prices=None, *, symbol="BTCUSDT", revision="expanded-10",
         contract_at=NOW, chart_at=KLINE_NOW):
    return stage_bybit_documented_linear_pair(
        instrument_payload=instrument(symbol=symbol) if metadata is None else metadata,
        kline_payload=kline(symbol=symbol) if prices is None else prices,
        symbol=symbol, instrument_observed_at_ms=contract_at,
        kline_observed_at_ms=chart_at,
        registry_variant=revision, interval="1h",
        start_open_ms=START, end_open_ms=END,
    )


class BybitOfficialSchemaConformanceTests(unittest.TestCase):
    def test_linear_btc_base_usdt_quote_exact_without_fake_closedcandle(self):
        result = pair()
        self.assertIsInstance(result, BybitLinearDocumentedPageResearch)
        self.assertIsInstance(result.instrument, BybitLinearInstrumentResearch)
        self.assertEqual(result.instrument.symbol, "BTCUSDT")
        self.assertEqual(result.instrument.base_coin, "BTC")
        self.assertEqual(result.instrument.quote_coin, "USDT")
        self.assertEqual(result.instrument.settle_coin, "USDT")
        self.assertEqual(result.instrument.registry_sha256,
                         load_reviewed_registry("expanded-10", as_of_ms=NOW).sha256_digest)
        self.assertEqual(result.instrument.max_leverage, Decimal("20.00"))
        self.assertEqual(result.instrument.tick_size, Decimal("0.01000000000001"))
        self.assertEqual(result.instrument.quantity_step, Decimal("0.00001000"))
        self.assertEqual(result.base_volume_unit, "BTC")
        self.assertEqual(result.quote_turnover_unit, "USDT")
        self.assertFalse(result.canonical_ohlcv)
        self.assertFalse(result.live_provider_verified)
        self.assertFalse(result.public_or_commercial_use_authorized)
        self.assertFalse(result.instrument.live_metadata_authenticated)
        self.assertFalse(result.instrument.public_or_commercial_use_authorized)
        self.assertEqual([x.open_time_ms for x in result.page.candles],
                         [START, START + HOUR, START + 2 * HOUR])
        self.assertEqual(len(result.page.candles), 3)
        self.assertTrue(all(not isinstance(x, ClosedCandle) for x in result.page.candles))
        self.assertTrue(all(x.documented_base_volume == Decimal("1.123456789123456789")
                            for x in result.page.candles))
        self.assertTrue(all(x.documented_quote_turnover == Decimal("99.987654321987654321")
                            for x in result.page.candles))
        self.assertNotEqual(result.page.candles[0].documented_quote_turnover,
                            result.page.candles[0].close *
                            result.page.candles[0].documented_base_volume)

    def test_usdc_is_explicit_quote_stablecoin_not_usd(self):
        result = pair(symbol="BTCUSDC")
        self.assertEqual(result.quote_turnover_unit, "USDC")
        self.assertEqual(result.instrument.settle_coin, "USDC")
        self.assertNotEqual(result.quote_turnover_unit, "USD")
        self.assertTrue(all(row.quote_currency == "USDC" for row in result.page.candles))

    def test_solana_requires_expanded_registry_not_old_two_base(self):
        sol = instrument(symbol="SOLUSDT")
        self.assertEqual(validate(sol, symbol="SOLUSDT").base_coin, "SOL")
        with self.assertRaises(DataValidationError):
            validate(sol, symbol="SOLUSDT", revision="btc-eth")

    def test_registry_revision_not_available_before_real_review(self):
        with self.assertRaises(DataValidationError):
            validate(at=1792968148000 - 1)
        with self.assertRaises(DataValidationError):
            validate(revision="unreviewed")
        self.assertEqual(validate(revision="btc-eth").base_coin, "BTC")

    def test_reject_spot_inverse_future_not_trading_and_prelist(self):
        alterations = [
            {"contractType": "InversePerpetual"},
            {"contractType": "LinearFutures"},
            {"contractType": "Spot"},
            {"status": "PreLaunch"},
            {"status": "Settling"},
            {"isPreListing": True},
            {"deliveryTime": str(NOW + HOUR)},
            {"preListingInfo": {"auction": "start"}},
        ]
        for change in alterations:
            with self.subTest(change=change):
                raw = instrument()
                raw["result"]["list"][0].update(change)
                with self.assertRaises(DataValidationError):
                    validate(raw)

    def test_block_tradfi_even_if_asset_symbol_spoofs_crypto(self):
        alterations = [
            {"symbolType": "xStocks"},
            {"symbolType": "TradFi"},
            {"marketRegion": "US"},
            {"marketRegion": "HK"},
            {"underlyingTicker": "BTC"},
            {"tags": ["ST"]},
            {"tags": ["equity"]},
            {"symbolType": None},
            {"marketRegion": None},
            {"underlyingTicker": None},
        ]
        for change in alterations:
            with self.subTest(change=change):
                raw = instrument()
                raw["result"]["list"][0].update(change)
                with self.assertRaises(DataValidationError):
                    validate(raw)

    def test_base_symbol_quote_and_settlement_must_be_identical(self):
        alterations = [
            {"symbol": "ETHUSDT"},
            {"baseCoin": "ETH"},
            {"quoteCoin": "USDC"},
            {"settleCoin": "USDC"},
            {"baseCoin": "AAPLX"},
            {"symbol": "BTCUSD"},
        ]
        for change in alterations:
            with self.subTest(change=change):
                raw = instrument()
                raw["result"]["list"][0].update(change)
                with self.assertRaises(DataValidationError):
                    validate(raw)
        for wrong in ("BTCUSD", "BTCUSDT/../", "BTCUSDTUSDT", "btcUSDT", "", "AAPLXUSDT"):
            with self.subTest(symbol=wrong), self.assertRaises(DataValidationError):
                validate(instrument(symbol=wrong), symbol=wrong)

    def test_bad_api_error_pagination_ambiguity_and_structures(self):
        raw = instrument()
        for change in (
            {"retCode": 10001},
            {"retCode": True},
            {"time": str(NOW)},
        ):
            bad = deepcopy(raw)
            bad.update(change)
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                validate(bad)
        for change in (
            {"category": "inverse"},
            {"nextPageCursor": "more"},
            {"nextPageCursor": None},
            {"list": []},
            {"list": [instrument()["result"]["list"][0]] * 2},
            {"list": None},
        ):
            bad = deepcopy(raw)
            bad["result"].update(change)
            with self.subTest(change=str(change)[:80]), self.assertRaises(DataValidationError):
                validate(bad)

    def test_clock_launch_and_leverage_rejections(self):
        raw = instrument()
        with self.assertRaises(DataValidationError):
            validate(raw, at=NOW - 101_000)
        for change in (
            {"launchTime": str(NOW + 500)},
            {"launchTime": "not_epoch"},
            {"deliveryTime": 0},
            {"priceFilter": {"tickSize": "0"}},
            {"priceFilter": {"tickSize": "NaN"}},
            {"lotSizeFilter": {"qtyStep": "-1"}},
            {"leverageFilter": {"minLeverage": "30", "maxLeverage": "20"}},
            {"leverageFilter": {"minLeverage": "1", "maxLeverage": "Infinity"}},
            {"leverageFilter": None},
        ):
            bad = deepcopy(raw)
            bad["result"]["list"][0].update(change)
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                validate(bad)
        for bad in (True, None, "now", 0, -1, 1.1):
            with self.subTest(at=bad), self.assertRaises(DataValidationError):
                validate(raw, at=bad)

    def test_metadata_server_time_must_be_close_to_capture(self):
        raw = instrument()
        bad = deepcopy(raw)
        bad["time"] = NOW + 1
        with self.assertRaises(DataValidationError):
            validate(bad)
        bad["time"] = NOW - 30_001
        with self.assertRaises(DataValidationError):
            validate(bad)

    def test_instrument_age_and_chart_causality(self):
        raw = instrument()
        with self.assertRaises(DataValidationError):
            pair(metadata=raw, chart_at=NOW - 1)
        with self.assertRaises(DataValidationError):
            pair(metadata=raw, chart_at=NOW + 30_001)
        with self.assertRaises(DataValidationError):
            pair(metadata=raw, contract_at=NOW + 2)
        with self.assertRaises(DataValidationError):
            pair(metadata=raw, contract_at=NOW - 100_000)

    def test_price_page_must_match_verified_market_exactly(self):
        bad = kline(symbol="ETHUSDT")
        with self.assertRaises(DataValidationError):
            pair(prices=bad)
        for row_idx in (0, 1, 2):
            bad = kline()
            bad["result"]["list"][row_idx][0] = str(END)
            with self.subTest(row=row_idx), self.assertRaises(DataGapError):
                pair(prices=bad)
        bad = kline()
        bad["result"]["category"] = "inverse"
        with self.assertRaises(DataValidationError):
            pair(prices=bad)
        bad = kline()
        bad["result"]["list"][0][5] = "NaN"
        with self.assertRaises(DataValidationError):
            pair(prices=bad)

    def test_documented_leverage_not_guarantee_of_global_50x(self):
        instrument_data = instrument(leverage="5.00")
        contract = validate(instrument_data)
        self.assertEqual(contract.max_leverage, Decimal("5.00"))
        self.assertLess(contract.max_leverage, Decimal(50))
        self.assertFalse(contract.live_metadata_authenticated)

    def test_determinism_and_no_hidden_data_provider_access(self):
        raw_meta, raw_prices = instrument(), kline()
        x = pair(raw_meta, raw_prices)
        y = pair(deepcopy(raw_meta), deepcopy(raw_prices))
        self.assertEqual(x, y)
        self.assertEqual(x.instrument.source, "bybit_v5_linear_instrument_offline_schema")
        self.assertFalse(hasattr(x, "submit_order"))
        self.assertFalse(hasattr(x, "persist"))
        self.assertFalse(hasattr(x, "as_closed_candle"))


if __name__ == "__main__":
    unittest.main()
