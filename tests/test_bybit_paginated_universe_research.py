"""J1/WU49: untrusted Bybit paginated fixtures never become an approved feed."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.bybit_paginated_universe_research import (
    BybitPaginatedUniverseResearch, MAX_PAGES,
    audit_bybit_linear_universe_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError, ClosedCandle
from test_bybit_instrument_volume_contract import instrument

T = 1_793_000_000_000
D = Decimal


def instrument_row(symbol="BTCUSDT", **changes):
    row = deepcopy(instrument(symbol=symbol)["result"]["list"][0])
    row.update(changes)
    return row


def instrument_page(rows, *, ms=T - 250, cursor=""):
    return {
        "retCode": 0, "retMsg": "OK", "time": ms,
        "result": {
            "category": "linear", "nextPageCursor": cursor,
            "list": list(rows),
        },
    }


def tickers(rows=None, *, ms=T - 100):
    if rows is None:
        rows = (
            {"symbol": "BTCUSDT", "turnover24h": "200.25", "volume24h": "2.00"},
            {"symbol": "ETHUSDT", "turnover24h": "300.50", "volume24h": "3.00"},
        )
    return {
        "retCode": 0, "retMsg": "OK", "time": ms,
        "result": {"category": "linear", "list": list(rows)},
    }


def pages():
    return (
        instrument_page([instrument_row("BTCUSDT")], ms=T - 400, cursor="cursor-B"),
        instrument_page([instrument_row("ETHUSDT")], ms=T - 250, cursor=""),
    )


def check(*, source_pages=None, cursors=(None, "cursor-B"), tick=None,
          at=T, limit=50, registry="expanded-13", age=30_000):
    return audit_bybit_linear_universe_offline(
        instrument_pages=pages() if source_pages is None else source_pages,
        requested_cursors=cursors,
        tickers_payload=tickers() if tick is None else tick,
        observed_at_ms=at, registry_variant=registry,
        max_symbols=limit, max_capture_age_ms=age,
    )


class BybitPaginatedUniverseOfflineTests(unittest.TestCase):
    def test_complete_two_page_chain_ranks_quote_usdt_not_usd(self):
        out = check()
        self.assertIsInstance(out, BybitPaginatedUniverseResearch)
        self.assertEqual([x.symbol for x in out.selected], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual([x.rank for x in out.selected], [1, 2])
        self.assertEqual(out.selected[0].turnover24h_usdt, D("300.50"))
        self.assertEqual(out.selected[0].volume24h_base, D("3.00"))
        self.assertEqual(out.instrument_page_count, 2)
        self.assertEqual(out.instrument_row_count, 2)
        self.assertEqual(out.candidate_contract_count, 2)
        self.assertEqual(out.ticker_row_count, 2)
        self.assertEqual(out.ranking_basis, "documented_quote_turnover_24h_usdt_not_usd")
        self.assertEqual(out.source_quality, "unverified_caller_supplied_offline_payload")
        self.assertTrue(out.cursor_chain_complete_as_asserted)
        for attr in (
            "live_source_verified", "canonical_ohlcv_ready",
            "verified_top50_coverage", "rights_verified",
            "usd_comparable_volume_verified", "point_in_time_history_verified",
            "automatic_trading_authorized", "orders_sent",
        ):
            self.assertFalse(getattr(out, attr), attr)
        self.assertFalse(any(isinstance(x, ClosedCandle) for x in out.selected))
        with self.assertRaises(FrozenInstanceError):
            out.selected = ()

    def test_final_page_not_supplied_never_silently_selects_first_page(self):
        with self.assertRaisesRegex(DataValidationError, "not terminal"):
            check(source_pages=pages()[:1], cursors=(None,))
        with self.assertRaisesRegex(DataValidationError, "cursor chain"):
            check(cursors=(None, None))
        with self.assertRaisesRegex(DataValidationError, "first cursor"):
            check(cursors=("cursor-B", "cursor-B"))

    def test_first_page_terminated_then_extra_page_is_rejected(self):
        one = instrument_page([instrument_row()], ms=T - 300)
        with self.assertRaisesRegex(DataValidationError, "after termination"):
            check(source_pages=(one, pages()[1]), cursors=(None, None))

    def test_cursor_cycle_empty_nonascii_or_missing_value_fail(self):
        one, two = pages()
        with self.assertRaisesRegex(DataValidationError, "cycle"):
            check(source_pages=(one, instrument_page(
                [instrument_row("ETHUSDT")], ms=T - 250, cursor="cursor-B",
            )))
        for cursor in (None, 123, "a b", "a\n", "☃", "x" * 301):
            with self.subTest(cursor=repr(cursor)), self.assertRaises(DataValidationError):
                check(source_pages=(instrument_page(
                    [instrument_row()], cursor=cursor,
                ), pages()[1]))
        three = instrument_page([instrument_row("SOLUSDT")], ms=T - 250)
        with self.assertRaises(DataValidationError):
            check(source_pages=(pages()[0], pages()[0], three),
                  cursors=(None, "cursor-B", "cursor-B"))

    def test_wrong_category_status_and_server_clock_fail(self):
        p = list(pages())
        bad = deepcopy(p[0])
        bad["result"]["category"] = "spot"
        with self.assertRaises(DataValidationError):
            check(source_pages=(bad, p[1]))
        bad = deepcopy(p[0])
        bad["retCode"] = True
        with self.assertRaises(DataValidationError):
            check(source_pages=(bad, p[1]))
        bad = deepcopy(p[0])
        bad["time"] = T + 1
        with self.assertRaises(DataValidationError):
            check(source_pages=(bad, p[1]))
        bad = deepcopy(p[0])
        bad["time"] = T - 30_001
        with self.assertRaises(DataValidationError):
            check(source_pages=(bad, p[1]))
        bad = deepcopy(p[1])
        bad["time"] = T - 999
        with self.assertRaisesRegex(DataValidationError, "noncausal"):
            check(source_pages=(p[0], bad))

    def test_ticker_snapshot_must_follow_all_instrument_pages(self):
        with self.assertRaisesRegex(DataValidationError, "predates"):
            check(tick=tickers(ms=T - 900))
        bad = tickers()
        bad["result"]["category"] = "inverse"
        with self.assertRaises(DataValidationError):
            check(tick=bad)
        bad = tickers()
        bad["time"] = T + 2
        with self.assertRaises(DataValidationError):
            check(tick=bad)

    def test_ticker_missing_duplicate_and_type_error_fail(self):
        with self.assertRaisesRegex(DataValidationError, "missing contemporaneous ticker"):
            check(tick=tickers(rows=[tickers()["result"]["list"][0]]))
        raw = tickers()
        raw["result"]["list"].append(deepcopy(raw["result"]["list"][0]))
        with self.assertRaisesRegex(DataValidationError, "duplicate"):
            check(tick=raw)
        for rows in (None, [], [None], "not_rows"):
            with self.subTest(rows=str(rows)):
                bad = tickers()
                bad["result"]["list"] = rows
                with self.assertRaises(DataValidationError):
                    check(tick=bad)

    def test_decimal_turnover_volume_strict_no_float_or_nan(self):
        for value in (None, D("12.5"), 12.5, True, -1, "NaN",
                      "Infinity", "-1", "1e2", "+1", "01", "1.2e3",
                      "1.123456789012345678901"):
            for field in ("turnover24h", "volume24h"):
                with self.subTest(value=str(value), field=field):
                    raw = tickers()
                    raw["result"]["list"][0][field] = value
                    with self.assertRaises(DataValidationError):
                        check(tick=raw)

    def test_zero_turnover_is_excluded_not_ranked_or_inferred(self):
        raw = tickers()
        raw["result"]["list"][0]["turnover24h"] = "0"
        raw["result"]["list"][0]["volume24h"] = "0"
        out = check(tick=raw)
        self.assertEqual([x.symbol for x in out.selected], ["ETHUSDT"])
        self.assertEqual(out.candidate_contract_count, 2)
        for amount in ("0", "1"):
            bad = tickers()
            bad["result"]["list"][0]["turnover24h"] = amount
            bad["result"]["list"][0]["volume24h"] = "1" if amount == "0" else "0"
            with self.assertRaisesRegex(DataValidationError, "consistency"):
                check(tick=bad)

    def test_usdc_quote_is_not_mixed_into_usdt_ranking(self):
        one, two = pages()
        with_usdc = deepcopy(two)
        with_usdc["result"]["list"].append(instrument_row("BTCUSDC"))
        raw = tickers()
        raw["result"]["list"].append(
            {"symbol": "BTCUSDC", "turnover24h": "99999999999", "volume24h": "999"}
        )
        out = check(source_pages=(one, with_usdc), tick=raw)
        self.assertEqual(len(out.selected), 2)
        self.assertEqual(out.candidate_contract_count, 2)
        self.assertNotIn("BTCUSDC", [x.symbol for x in out.selected])

    def test_tradfi_even_with_btc_ticker_is_excluded(self):
        one, two = pages()
        for change in (
            {"symbolType": "TradFi"},
            {"symbolType": "xStocks"},
            {"marketRegion": "US"},
            {"underlyingTicker": "BTC"},
            {"isPreListing": True},
            {"contractType": "LinearFutures"},
            {"status": "PreLaunch"},
            {"deliveryTime": "12345"},
        ):
            with self.subTest(change=change):
                bad = deepcopy(one)
                bad["result"]["list"][0].update(change)
                result = check(source_pages=(bad, two))
                self.assertEqual([x.symbol for x in result.selected], ["ETHUSDT"])
                self.assertEqual(result.candidate_contract_count, 1)

    def test_only_registry_known_bases_considered_and_version_date_locked(self):
        bad = deepcopy(pages()[0])
        bad["result"]["list"].append(instrument_row("AAPLXUSDT"))
        out = check(source_pages=(bad, pages()[1]))
        self.assertEqual(len(out.selected), 2)
        self.assertEqual(out.instrument_row_count, 3)
        with self.assertRaises(DataValidationError):
            check(registry="unreviewed")
        with self.assertRaises(DataValidationError):
            check(at=1_792_982_300_000, age=30_000)

    def test_stable_tie_breaker_and_limit_independent_of_row_order(self):
        equal = tickers()
        equal["result"]["list"][0]["turnover24h"] = "200"
        equal["result"]["list"][1]["turnover24h"] = "200"
        equal["result"]["list"].reverse()
        result = check(tick=equal, limit=1)
        self.assertEqual([x.symbol for x in result.selected], ["BTCUSDT"])
        self.assertEqual([x.rank for x in result.selected], [1])
        p = instrument_page([instrument_row("ETHUSDT"), instrument_row()], ms=T - 250)
        out = check(source_pages=(p,), cursors=(None,), tick=equal)
        self.assertEqual(out.selected[0].symbol, "BTCUSDT")
        with self.assertRaises(DataValidationError):
            check(limit=51)
        with self.assertRaises(DataValidationError):
            check(limit=True)

    def test_instrument_duplicate_and_bad_symbol_fail(self):
        a, b = pages()
        second = deepcopy(b)
        second["result"]["list"].append(instrument_row())
        with self.assertRaisesRegex(DataValidationError, "duplicated"):
            check(source_pages=(a, second))
        bad = deepcopy(a)
        bad["result"]["list"][0]["symbol"] = "../"
        with self.assertRaises(DataValidationError):
            check(source_pages=(bad, b))

    def test_page_and_ticker_budgets_fail_closed(self):
        long_page = instrument_page(
            [{"symbol": f"X{i:05d}USDT"} for i in range(1001)], cursor="",
        )
        with self.assertRaises(DataValidationError):
            check(source_pages=(long_page,), cursors=(None,))
        with self.assertRaises(DataValidationError):
            check(source_pages=(pages()[0],) * (MAX_PAGES + 1),
                  cursors=(None,) * (MAX_PAGES + 1))
        oversized = tickers(
            rows=[{"symbol": f"X{i:05d}USDT"} for i in range(10_001)]
        )
        with self.assertRaises(DataValidationError):
            check(tick=oversized)

    def test_never_network_or_export_private_market_data(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                out = check()
        self.assertEqual(out.instrument_page_count, 2)
        self.assertFalse(out.orders_sent)
        self.assertFalse(out.automatic_trading_authorized)
        self.assertFalse(hasattr(out, "place_order"))
        self.assertFalse(hasattr(out, "as_closed_candle"))


if __name__ == "__main__":
    unittest.main()
