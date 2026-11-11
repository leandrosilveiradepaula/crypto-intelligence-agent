"""Automatic crypto-USDT research screening: no registry and no live authority."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal as D
import unittest

from crypto_intelligence_agent.j1_auto_usdt_perp import (
    screen_bybit_usdt_perps_offline, rank_auto_candidates_closed24h_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError

AT = 1_800_000_120_000
END = 1_800_000_000_000
HOUR = 3_600_000


def item(symbol="BTCUSDT", **fields):
    row = {
        "symbol": symbol, "baseCoin": symbol[:-4],
        "quoteCoin": "USDT", "settleCoin": "USDT",
        "contractType": "LinearPerpetual", "status": "Trading",
        "deliveryTime": "0", "isPreListing": False,
        "preListingInfo": None, "symbolType": "",
        "marketRegion": "", "underlyingTicker": "",
        "tags": [], "fullName": "",
    }
    row.update(fields)
    return row


def page(rows, *, cursor="", time=AT-1000):
    return {
        "retCode": 0, "time": time,
        "result": {"category": "linear", "nextPageCursor": cursor,
                   "list": rows},
    }


def screen(rows):
    return screen_bybit_usdt_perps_offline(
        instrument_pages=(page(rows),), requested_cursors=(None,),
        page_received_at_ms=(AT,), observed_at_ms=AT,
    )


def bars(amount="10", *, hours=24):
    return tuple((END-(hours-i)*HOUR, D(amount)) for i in range(hours))


class AutoUSDTPerpTests(unittest.TestCase):
    def test_btc_eth_new_token_no_manual_positive_registry_required(self):
        r = screen([item("BTCUSDT"), item("ETHUSDT"),
                    item("NEWTOKENUSDT", marketRegion=None,
                         underlyingTicker=None)])
        self.assertEqual(r.candidate_symbols,
                         ("BTCUSDT", "ETHUSDT", "NEWTOKENUSDT"))
        self.assertEqual(r.candidate_missing_optional_markers, 1)
        output = r.sanitized_report()
        self.assertFalse(output["marketwide_top50_verified"])
        self.assertFalse(output["order_execution_enabled"])
        self.assertNotIn("BTCUSDT", str(output))
        self.assertEqual(
            len(r.sanitized_report(include_public_symbols=True)[
                "research_candidate_symbols_only"]), 3)

    def test_usdt_suffix_not_crypto_proof_and_explicit_exclusions(self):
        r = screen([
            item("BTCUSDT"),
            item("DUOLUSDT", marketRegion="US", underlyingTicker="DUOL"),
            item("BZUSDT", fullName="Brent Oil"),
            item("STOCKUSDT", marketRegion="US"),
            item("USDCBTCUSDT", contractType="LinearFutures"),
            item("XUSDT", isPreListing=True),
            item("BADUSDT", tags=["unknown"]),
            item("CRYPTOUSDC", quoteCoin="USDC", settleCoin="USDC"),
        ])
        self.assertEqual(r.candidate_symbols, ("BTCUSDT",))
        self.assertGreaterEqual(
            r.excluded_documented_tradfi + r.excluded_provider_tradfi +
            r.excluded_fullname_tradfi, 2)
        self.assertGreaterEqual(r.excluded_product, 2)

    def test_complete_pagination_and_duplicate_guard(self):
        a = page([item("BTCUSDT")], cursor="PAGE2")
        b = page([item("ETHUSDT")], time=AT-500)
        result = screen_bybit_usdt_perps_offline(
            instrument_pages=(a, b), requested_cursors=(None, "PAGE2"),
            page_received_at_ms=(AT-600, AT), observed_at_ms=AT)
        self.assertEqual(len(result.candidate_symbols), 2)
        for pages, cursors in (
            ((a,), (None,)),
            ((a, b), (None, "WRONG")),
            ((page([item()]), page([item()])), (None, "")),
        ):
            with self.subTest(cursors=cursors), self.assertRaises(DataValidationError):
                screen_bybit_usdt_perps_offline(
                    instrument_pages=pages, requested_cursors=cursors,
                    page_received_at_ms=tuple(AT for _ in pages),
                    observed_at_ms=AT)
        with self.assertRaises(DataValidationError):
            screen([item("BTCUSDT"), item("BTCUSDT")])

    def test_invalid_metadata_fails_closed(self):
        for change in (
            {"symbol": "BTC USDT"}, {"symbolType": 2}, {"tags": [4]},
            {"fullName": 9}, {"marketRegion": ["US"]},
        ):
            with self.subTest(change=change):
                row = item("BTCUSDT")
                row.update(change)
                if "symbol" in change:
                    with self.assertRaises(DataValidationError):
                        screen([row])
                else:
                    r = screen([row])
                    self.assertEqual(r.candidate_symbols, ())

    def test_24_closed_hours_uses_exact_usdt_turnover(self):
        p = screen([item("BTCUSDT"), item("ETHUSDT"),
                    item("NEWTOKENUSDT")])
        result = rank_auto_candidates_closed24h_offline(
            p, closed_hour_end_ms=END,
            closed_candle_turnovers={
                "BTCUSDT": bars("10"),
                "ETHUSDT": bars("20"),
                "NEWTOKENUSDT": bars("100", hours=2),
            })
        self.assertEqual(result.ranked,
                         (("ETHUSDT", D("480")), ("BTCUSDT", D("240"))))
        self.assertEqual(result.insufficient_count, 1)
        self.assertFalse(result.sanitized_report()["marketwide_top50_verified"])
        self.assertFalse(result.sanitized_report()["approved_for_trading"])

    def test_invalid_time_values_and_missing_not_zero(self):
        p = screen([item("BTCUSDT")])
        good = bars()
        cases = (
            good[:-1],
            ((good[0][0]+1, D("10")),) + good[1:],
            ((good[0][0], D("-1")),) + good[1:],
            ((good[0][0], D("NaN")),) + good[1:],
            ((good[0][0], 1.0),) + good[1:],
        )
        for bad in cases[1:]:
            with self.subTest(first=bad[0]), self.assertRaises(DataValidationError):
                rank_auto_candidates_closed24h_offline(
                    p, closed_hour_end_ms=END,
                    closed_candle_turnovers={"BTCUSDT": bad})
        result = rank_auto_candidates_closed24h_offline(
            p, closed_hour_end_ms=END, closed_candle_turnovers={
                "BTCUSDT": cases[0],
            })
        self.assertEqual(result.insufficient_count, 1)
        self.assertEqual(result.ranked, ())

    def test_zero_turnover_not_a_positive_liquidity_candidate(self):
        p = screen([item("BTCUSDT")])
        result = rank_auto_candidates_closed24h_offline(
            p, closed_hour_end_ms=END,
            closed_candle_turnovers={"BTCUSDT": bars("0")})
        self.assertEqual(result.zero_turnover_count, 1)
        self.assertEqual(result.covered_count, 0)
        self.assertEqual(result.ranked, ())


if __name__ == "__main__":
    unittest.main()
