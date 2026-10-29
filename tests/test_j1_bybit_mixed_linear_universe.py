"""J1 #310: a paginated linear list is not an all-crypto-perpetual list.

All provider-shaped inputs are synthetic and offline. The scanner must ignore
unrelated products without accepting corrupt or duplicate reviewed crypto
USDT perpetuals, and without asserting historical marketwide Top50.
"""
from copy import deepcopy
import unittest

from crypto_intelligence_agent.bybit_paginated_universe_research import (
    scan_bybit_linear_instruments_offline,
    classify_bybit_instrument_scan_failure,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_bybit_paginated_universe_research import (
    T, instrument_page, instrument_row,
)


def unrelated_futures_row():
    row = instrument_row("BTCUSDT")
    row.update({
        "symbol": "BTC-30OCT26USDC",
        "contractType": "LinearFutures",
        "quoteCoin": "USDC",
        "settleCoin": "USDC",
    })
    return row


def nonstandard_unreviewed_perp():
    row = instrument_row("BTCUSDT")
    row.update({
        "symbol": "AAPL.USDT",
        "baseCoin": "AAPL.",
        "symbolType": "TradFi",
        "marketRegion": "US",
    })
    return row


def mixed_pages():
    unrelated = unrelated_futures_row()
    unknown = nonstandard_unreviewed_perp()
    first = instrument_page(
        [instrument_row("BTCUSDT"), unrelated, unknown],
        ms=T - 450, cursor="continuation",
    )
    second = instrument_page(
        [instrument_row("ETHUSDT"), deepcopy(unrelated), deepcopy(unknown),
         instrument_row("BTCUSDC")],
        ms=T - 200, cursor="",
    )
    return first, second


def scan(pages):
    return scan_bybit_linear_instruments_offline(
        instrument_pages=pages, requested_cursors=(None, "continuation"),
        observed_at_ms=T, registry_variant="expanded-13",
        page_received_at_ms=(T - 420, T - 100),
    )


class MixedBybitLinearUniverseTests(unittest.TestCase):
    def test_unrelated_symbols_can_be_nonstandard_or_repeated(self):
        result = scan(mixed_pages())
        self.assertEqual(result.page_count, 2)
        self.assertEqual(result.instrument_row_count, 7)
        self.assertEqual(
            [m.symbol for m in result.instruments], ["BTCUSDT", "ETHUSDT"])
        self.assertFalse(result.historical_top50_verified)
        self.assertFalse(result.provider_authenticated)

    def test_duplicate_reviewed_cryptocurrency_perpetual_still_fails(self):
        first, second = mixed_pages()
        second["result"]["list"].append(instrument_row("BTCUSDT"))
        with self.assertRaisesRegex(DataValidationError, "symbol duplicated") as cm:
            scan((first, second))
        self.assertEqual(
            classify_bybit_instrument_scan_failure(cm.exception),
            "duplicate_instrument")

    def test_bad_symbol_on_reviewed_crypto_perp_still_fails(self):
        for changed_symbol in ("BTC-30OCT26USDT", "../", "BTC.USDT", "ETHUSDT"):
            first, second = mixed_pages()
            first["result"]["list"][0]["symbol"] = changed_symbol
            with self.subTest(symbol=changed_symbol):
                with self.assertRaisesRegex(DataValidationError, "symbol malformed") as cm:
                    scan((first, second))
                self.assertEqual(
                    classify_bybit_instrument_scan_failure(cm.exception),
                    "malformed_symbol")

    def test_truly_unsafe_raw_symbol_still_fails_even_if_non_target(self):
        first, second = mixed_pages()
        for bad in ("bad\nname", "élément", "", None, 42, "X" * 81):
            current = deepcopy(first)
            current["result"]["list"][2]["symbol"] = bad
            with self.subTest(value=repr(bad)):
                with self.assertRaisesRegex(DataValidationError, "missing or unsafe") as cm:
                    scan((current, second))
                self.assertEqual(
                    classify_bybit_instrument_scan_failure(cm.exception),
                    "malformed_symbol")

    def test_duplicate_unknown_crypto_style_symbol_never_enters_sample(self):
        first, second = mixed_pages()
        unknown = instrument_row("AAPLXUSDT")
        first["result"]["list"].append(unknown)
        second["result"]["list"].append(deepcopy(unknown))
        result = scan((first, second))
        self.assertEqual(len(result.instruments), 2)
        self.assertEqual(result.instrument_row_count, 9)
        self.assertFalse(result.historical_top50_verified)


if __name__ == "__main__":
    unittest.main()
