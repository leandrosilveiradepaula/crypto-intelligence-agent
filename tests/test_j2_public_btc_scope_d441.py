"""D441 single BTCUSDT public REST scope: offline contracts only."""
from __future__ import annotations

from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.j2_public_btc_scope_d441 import (
    reviewed_single_btc_scope, fetch_single_btc_scope_from_public_rest,
)
from crypto_intelligence_agent.bybit_public_j1_transport import instruments_url

NOW = 1_800_000_000_000


def response():
    return {
        "retCode": 0, "retMsg": "OK", "time": NOW - 250,
        "result": {
            "category": "linear", "nextPageCursor": "",
            "list": [{
                "symbol": "BTCUSDT", "baseCoin": "BTC",
                "quoteCoin": "USDT", "settleCoin": "USDT",
                "contractType": "LinearPerpetual", "status": "Trading",
                "symbolType": "", "marketRegion": "", "underlyingTicker": "",
                "tags": [], "isPreListing": False, "preListingInfo": None,
                "deliveryTime": "0", "launchTime": str(NOW - 200_000),
                "priceFilter": {"tickSize": "0.10"},
                "lotSizeFilter": {"qtyStep": "0.001"},
                "leverageFilter": {"minLeverage": "1", "maxLeverage": "50"},
            }],
        },
    }


class D441PublicSingleInstrumentTests(TestCase):
    def test_offline_rest_payload_constructs_only_btc_scope(self):
        scope = reviewed_single_btc_scope(response(), observed_at_ms=NOW)
        self.assertEqual(tuple(x.symbol for x in scope.contracts), ("BTCUSDT",))
        self.assertEqual(scope.observed_at_ms, NOW)
        self.assertEqual(scope.asserted_full_catalog_rows, 1)
        self.assertFalse(scope.contracts[0].live_metadata_authenticated)
        self.assertFalse(scope.contracts[0].public_or_commercial_use_authorized)

    def test_wrong_or_stale_metadata_fails_closed(self):
        for key, value in (
            ("status", "PreLaunch"), ("quoteCoin", "USDC"),
            ("contractType", "LinearFutures"), ("symbol", "ETHUSDT"),
            ("marketRegion", "US"), ("symbolType", "TradFi"),
        ):
            altered = deepcopy(response())
            altered["result"]["list"][0][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(DataValidationError):
                    reviewed_single_btc_scope(altered, observed_at_ms=NOW)
        for observed in (NOW - 1000, NOW + 31_000):
            with self.subTest(observed=observed):
                with self.assertRaises(DataValidationError):
                    reviewed_single_btc_scope(response(), observed_at_ms=observed)

    def test_exactly_one_public_rest_instrument_query_without_j1(self):
        class FakePublicClient:
            def __init__(self):
                self.get_calls = []
            def get(self, url):
                self.get_calls.append(url)
                return b"{}" , response()
        fake = FakePublicClient()
        with patch("crypto_intelligence_agent.j2_public_btc_scope_d441.BoundedBybitPublicClient",
                   return_value=fake):
            with patch("crypto_intelligence_agent.j2_public_btc_scope_d441.time.time_ns",
                       return_value=NOW * 1_000_000):
                scope = fetch_single_btc_scope_from_public_rest()
        self.assertEqual(fake.get_calls, [instruments_url(symbol="BTCUSDT")])
        self.assertEqual(len(scope.contracts), 1)
