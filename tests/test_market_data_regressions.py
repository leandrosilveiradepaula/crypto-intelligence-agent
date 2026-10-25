"""Regression cases for financial-market-data integrity; all tests are offline."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import (
    BinanceFuturesPublicAdapter, DataValidationError, HttpResponse,
)

FIXTURES = Path(__file__).parent / "fixtures"


class ConstantTransport:
    def __init__(self, payload):
        self.payload = payload
        self.request_count = 0

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        self.request_count += 1
        return HttpResponse(200, json.dumps(self.payload))


class RoutedTransport:
    def __init__(self, contracts, tickers):
        self.contracts = contracts
        self.tickers = tickers
        self.request_count = 0

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        self.request_count += 1
        return HttpResponse(200, json.dumps(self.contracts if "exchangeInfo" in url else self.tickers))


def example_klines():
    return json.loads((FIXTURES / "klines.json").read_text(encoding="utf-8"))


def example_contracts():
    return json.loads((FIXTURES / "exchange_info.json").read_text(encoding="utf-8"))


def example_tickers():
    return json.loads((FIXTURES / "ticker_24h.json").read_text(encoding="utf-8"))


class MarketIntegrityRegressionTests(unittest.TestCase):
    def test_malformed_ohlc_and_negative_quantities_fail_closed(self):
        for index, bad_value in ((1, "-1"), (3, "-99"), (5, "-0.5"), (7, "-5")):
            with self.subTest(index=index):
                rows = [example_klines()[1]]
                rows[0][index] = bad_value
                adapter = BinanceFuturesPublicAdapter(ConstantTransport(rows))
                with self.assertRaises(DataValidationError):
                    adapter.closed_candles("BTCUSDT", "1h", observed_at_ms=10_000_000)

    def test_future_observation_cannot_mark_incomplete_candles_closed(self):
        transport = ConstantTransport(example_klines())
        adapter = BinanceFuturesPublicAdapter(transport, clock_ms=lambda: 10_000)
        with self.assertRaises(DataValidationError):
            adapter.closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)
        self.assertEqual(transport.request_count, 0)

    def test_wrong_candle_close_time_is_rejected_even_for_single_row(self):
        rows = [example_klines()[1]]
        rows[0][6] += 50
        adapter = BinanceFuturesPublicAdapter(ConstantTransport(rows))
        with self.assertRaises(DataValidationError):
            adapter.closed_candles("BTCUSDT", "1h", observed_at_ms=10_000_000)

    def test_fractional_timestamps_are_not_silently_truncated(self):
        rows = [example_klines()[1]]
        rows[0][0] = 0.75
        adapter = BinanceFuturesPublicAdapter(ConstantTransport(rows))
        with self.assertRaises(DataValidationError):
            adapter.closed_candles("BTCUSDT", "1h", observed_at_ms=10_000_000)

    def test_fictional_historical_universe_from_live_24h_ticker_is_rejected(self):
        transport = RoutedTransport(example_contracts(), example_tickers())
        adapter = BinanceFuturesPublicAdapter(transport)
        with self.assertRaises(DataValidationError):
            adapter.universe(observed_at_ms=10_000)
        self.assertEqual(transport.request_count, 0)  # reject before reaching live endpoints

    def test_live_contract_metadata_cannot_be_backdated(self):
        transport = ConstantTransport(example_contracts())
        adapter = BinanceFuturesPublicAdapter(transport)
        with self.assertRaises(DataValidationError):
            adapter.contracts(observed_at_ms=10_000)
        self.assertEqual(transport.request_count, 0)

    def test_duplicate_conflicting_ticker_rows_are_not_last_wins(self):
        tickers = example_tickers()
        tickers.append({"symbol": "BTCUSDT", "quoteVolume": "99999"})
        adapter = BinanceFuturesPublicAdapter(
            RoutedTransport(example_contracts(), tickers),
            clock_ms=lambda: 10_000,
        )
        with self.assertRaises(DataValidationError):
            adapter.universe(observed_at_ms=10_000)

    def test_query_ranges_must_be_valid_before_request(self):
        transport = ConstantTransport(example_klines())
        adapter = BinanceFuturesPublicAdapter(transport)
        with self.assertRaises(ValueError):
            adapter.closed_candles(
                "BTCUSDT", "1h", observed_at_ms=10_000_000,
                start_time_ms=6_000, end_time_ms=1_000,
            )
        self.assertEqual(transport.request_count, 0)

    def test_negative_contract_filters_cannot_enter_domain(self):
        payload = example_contracts()
        payload["symbols"][0]["filters"][0]["tickSize"] = "-0.10"
        adapter = BinanceFuturesPublicAdapter(ConstantTransport(payload), clock_ms=lambda: 10_000)
        with self.assertRaises(DataValidationError):
            adapter.contracts(observed_at_ms=10_000)

    def test_unsupported_intervals_are_rejected_before_http(self):
        transport = ConstantTransport(example_klines())
        adapter = BinanceFuturesPublicAdapter(transport)
        with self.assertRaises(DataValidationError):
            adapter.closed_candles("BTCUSDT", "17h", observed_at_ms=10_000_000)
        self.assertEqual(transport.request_count, 0)


if __name__ == "__main__":
    unittest.main()
