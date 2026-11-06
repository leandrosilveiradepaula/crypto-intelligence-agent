"""J1 transport/catalog shape regression: no live Bybit requests or orders."""
from __future__ import annotations

import json
import re
import unittest

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, HOUR_MS, J1BybitCaptureError,
    instruments_url, kline_url,
)
from scripts.audit_bybit_marketwide_closed24h import (
    _catalog, CensusAbstain,
)

WINDOW_END = 1793970000000


def catalog_payload(*symbols: str) -> dict:
    return {
        "retCode": 0, "time": WINDOW_END + 70000,
        "result": {
            "category": "linear", "nextPageCursor": "",
            "list": [
                {"symbol": s, "baseCoin": s[:-4],
                 "status": "Trading", "contractType": "LinearPerpetual",
                 "quoteCoin": "USDT", "settleCoin": "USDT"}
                for s in symbols
            ],
        },
    }


class J1SymbolShapeContractTests(unittest.TestCase):
    def test_catalog_accepted_symbols_are_transportable_at_boundaries(self):
        members = tuple(f"COIN{i:02d}USDT" for i in range(48)) + (
            "AUSDT", "A" * 28 + "USDT",
        )
        scope, _, count = _catalog(catalog_payload(*members), WINDOW_END + 80000)
        self.assertEqual(count, 50)
        self.assertEqual(len(scope), 50)
        for symbol in scope:
            with self.subTest(symbol_len=len(symbol)):
                kline = kline_url(symbol, WINDOW_END-24*HOUR_MS, WINDOW_END)
                metadata = instruments_url(symbol=symbol)
                self.assertIn("/v5/market/kline", kline)
                self.assertIn("/v5/market/instruments-info", metadata)

    def test_client_accepts_valid_one_character_and_28_character_bases(self):
        requests = []
        def offline_transport(url: str, limit: int) -> bytes:
            requests.append(url)
            return json.dumps({"retCode": 0, "result": {
                "category": "linear", "symbol": "AUSDT", "list": []
            }}).encode("ascii")
        client = BoundedBybitPublicClient(transport=offline_transport)
        for symbol in ("AUSDT", "A"*28+"USDT"):
            with self.subTest(symbol_len=len(symbol)):
                url = kline_url(symbol, WINDOW_END-24*HOUR_MS, WINDOW_END)
                _, response = client.get(url)
                self.assertEqual(response["retCode"], 0)
        self.assertEqual(client.requests_attempted, 2)
        self.assertEqual(len(requests), 2)

    def test_oversized_or_malformed_symbols_do_not_issue_any_get(self):
        invalid = ("USDT", "A"*29+"USDT", "aUSDT", "ABC-USDT",
                   "BTCUSDC", "X/USDT", "ABC USDT", "BTCUSDT\\n")
        calls = []
        def forbidden_network(url, limit):
            calls.append(url)
            raise AssertionError("network must never be called")
        client = BoundedBybitPublicClient(transport=forbidden_network)
        for symbol in invalid:
            with self.subTest(shape=len(symbol)):
                with self.assertRaises(J1BybitCaptureError):
                    kline_url(symbol, WINDOW_END-24*HOUR_MS, WINDOW_END)
                with self.assertRaises(J1BybitCaptureError):
                    instruments_url(symbol=symbol)
        self.assertEqual(client.requests_attempted, 0)
        self.assertFalse(calls)

    def test_census_rejects_shape_not_supported_by_transport(self):
        members = tuple(f"COIN{i:02d}USDT" for i in range(49))
        with self.assertRaises(CensusAbstain):
            _catalog(catalog_payload(*members, "A"*29+"USDT"), WINDOW_END+80000)

    def test_time_window_invalid_is_distinct_from_symbol_length(self):
        symbol = "A"*28 + "USDT"
        self.assertIn("/v5/market/kline",
                      kline_url(symbol, WINDOW_END-24*HOUR_MS, WINDOW_END))
        for end in (WINDOW_END+1, WINDOW_END-25*HOUR_MS+1):
            with self.assertRaisesRegex(J1BybitCaptureError, "invalid_kline_window"):
                kline_url(symbol, WINDOW_END-24*HOUR_MS, end)


if __name__ == "__main__":
    unittest.main()
