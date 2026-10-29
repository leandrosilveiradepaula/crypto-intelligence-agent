"""J1 regression: genuine paginated GETs carry independent server/receive clocks.

All inputs are synthetic; no network, real market data or credentials.
"""
from copy import deepcopy
import unittest

from crypto_intelligence_agent.bybit_paginated_universe_research import (
    classify_bybit_instrument_scan_failure,
    scan_bybit_linear_instruments_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_bybit_paginated_universe_research import (
    T, instrument_page, instrument_row,
)


def responses(first_ms, second_ms):
    return (
        instrument_page([instrument_row("BTCUSDT")],
                        ms=first_ms, cursor="page2"),
        instrument_page([instrument_row("ETHUSDT")],
                        ms=second_ms, cursor=""),
    )


def scan(pages, received=None):
    return scan_bybit_linear_instruments_offline(
        instrument_pages=pages,
        requested_cursors=(None, "page2"),
        observed_at_ms=T,
        registry_variant="expanded-13",
        page_received_at_ms=received,
    )


class BybitPerPageCaptureClockTests(unittest.TestCase):
    def test_long_pagination_does_not_measure_first_page_at_last_page_clock(self):
        pages = responses(T - 40_000, T - 100)
        with self.assertRaisesRegex(DataValidationError, "clock"):
            scan(pages)  # legacy strict mode (no recorded receipts)
        accepted = scan(pages, (T - 39_950, T - 50))
        self.assertEqual(accepted.page_count, 2)
        self.assertEqual(accepted.instrument_row_count, 2)
        self.assertEqual([m.symbol for m in accepted.instruments],
                         ["BTCUSDT", "ETHUSDT"])
        self.assertFalse(accepted.provider_authenticated)

    def test_small_server_time_jitter_only_with_trusted_page_receipt_sequence(self):
        pages = responses(T - 300, T - 1_100)
        with self.assertRaisesRegex(DataValidationError, "noncausal"):
            scan(pages)
        accepted = scan(pages, (T - 100, T))
        self.assertEqual(accepted.page_count, 2)
        farther = responses(T - 300, T - 3_001)
        with self.assertRaisesRegex(DataValidationError, "noncausal"):
            scan(farther, (T - 100, T))

    def test_receipts_cannot_be_future_reordered_duplicated_or_misaligned(self):
        pages = responses(T - 400, T - 200)
        for received in (
            (T - 20,), (T, T + 1), (T, T - 1),
            [T - 20, T], (True, T),
        ):
            with self.subTest(received=received):
                with self.assertRaises(DataValidationError):
                    scan(pages, received)

    def test_cursor_chain_still_fail_closed_with_page_receipt_clocks(self):
        pages = list(responses(T - 400, T - 200))
        pages[0]["result"]["nextPageCursor"] = "wrong"
        with self.assertRaisesRegex(DataValidationError, "cursor"):
            scan(tuple(pages), (T - 100, T))
        pages = list(responses(T - 400, T - 200))
        pages[1]["result"]["list"].append(deepcopy(
            pages[0]["result"]["list"][0]))
        with self.assertRaisesRegex(DataValidationError, "duplicated"):
            scan(tuple(pages), (T - 100, T))

    def test_rejection_classes_are_raw_data_free_and_stable(self):
        cases = {
            "Bybit pagination server timestamps are noncausal": "cross_page_server_clock",
            "Bybit instrument page cursor chain is incomplete": "cursor_chain",
            "Bybit repeated pagination request cursor": "cursor_chain",
            "Bybit instrument symbol malformed or duplicated": "duplicate_instrument",
            "Bybit instruments category or capture clock is invalid": "page_capture_clock",
            "requested crypto registry revision was not yet known": "crypto_registry_or_asof",
        }
        for description, code in cases.items():
            self.assertEqual(
                classify_bybit_instrument_scan_failure(DataValidationError(description)),
                code,
            )
        self.assertEqual(
            classify_bybit_instrument_scan_failure(
                DataValidationError("invalid data: secret-token-from-payload")
            ), "other_schema_rejection")


if __name__ == "__main__":
    unittest.main()
