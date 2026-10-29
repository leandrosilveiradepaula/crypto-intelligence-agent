"""J1 #319: full catalog + 24 closed UTC bars over independently reviewed 52.

Pure offline tests use fake Bybit payloads. No real market calls, trading,
files, credentials or access to the owner's private SQLite database.
"""
from copy import deepcopy
import json
import os
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
)
from crypto_intelligence_agent.bybit_top50_closed_hour_rank import (
    HOUR_MS as H, TOP_N, MAX_BATCH_DURATION_MS,
    rank_bybit_reviewed_closed_24h_pit,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from scripts.probe_bybit_top50_closed_pit import (
    owner_rank_bybit_reviewed_closed_24h,
)
from test_bybit_paginated_universe_research import (
    instrument_row, instrument_page,
)
from test_j1_bybit_exit_vertical import kline

REGISTRY_AT = 1793287659000
DECISION = ((REGISTRY_AT // H) + 1) * H
NOW = DECISION + 12_000


def pages_for(symbols, *, ms):
    return (instrument_page(
        [instrument_row(sym) for sym in symbols], ms=ms, cursor="",
    ),)


def kline_for(symbol, turnover, *, at):
    page = kline(symbol, DECISION - 24 * H, 24, turnover)
    page["time"] = at
    return page


def review_params(symbols=("HYPEUSDT", "NEARUSDT"), *,
                  amount=None):
    before = pages_for(symbols, ms=NOW-500)
    after = pages_for(symbols, ms=NOW+180)
    vols = amount or {"HYPEUSDT": "10", "NEARUSDT": "20"}
    return dict(
        before_instrument_pages=before,
        before_requested_cursors=(None,),
        before_page_received_at_ms=(NOW-300,),
        after_instrument_pages=after,
        after_requested_cursors=(None,),
        after_page_received_at_ms=(NOW+250,),
        kline_pages={
            sym: kline_for(sym, vols.get(sym,"1"), at=NOW+50)
            for sym in symbols
        },
        kline_page_received_at_ms={sym: NOW+100 for sym in symbols},
        decision_at_ms=DECISION,
        observed_at_ms=NOW+400,
        registry_variant="expanded-52",
    )


class ReviewedClosedBybitRankingOfflineTests(unittest.TestCase):
    def test_full_two_asset_closed_hour_quote_usdt_rank(self):
        ranked = rank_bybit_reviewed_closed_24h_pit(**review_params())
        self.assertEqual([m.symbol for m in ranked.ranked],
                         ["NEARUSDT", "HYPEUSDT"])
        self.assertEqual(
            [str(m.turnover_24_closed_hours_usdt) for m in ranked.ranked],
            ["480", "240"],
        )
        self.assertEqual(ranked.verified_24h_window_count, 2)
        self.assertEqual(ranked.reviewed_eligible_contracts, 2)
        self.assertEqual(ranked.unreviewed_plausible_contracts, 0)
        report = ranked.sanitized_report()
        self.assertFalse(report["rolling_ticker_used_for_rank"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["historical_pit_marketwide_top50_verified"])
        self.assertFalse(report["orders_sent"])
        self.assertNotIn("public_reviewed_ranked_contract_identifiers_only", report)
        self.assertNotIn("480", json.dumps(report))
        self.assertNotIn("NEARUSDT", json.dumps(report))
        self.assertEqual(
            ranked.sanitized_report(include_public_symbols=True)
            ["public_reviewed_ranked_contract_identifiers_only"],
            ["NEARUSDT", "HYPEUSDT"],
        )
        self.assertEqual(
            rank_bybit_reviewed_closed_24h_pit(**review_params())
            .sanitized_report()["reviewed_rank_digest_sha256"],
            report["reviewed_rank_digest_sha256"],
        )

    def test_52_reviewed_crypto_bases_yield_exactly_50_ranked_but_not_marketwide(self):
        reg = load_reviewed_registry("expanded-52", as_of_ms=NOW)
        symbols = tuple(asset.base+"USDT" for asset in reg.assets)
        self.assertEqual(len(symbols), 52)
        params = review_params(symbols, amount={
            symbol: str(idx+1) for idx, symbol in enumerate(symbols)
        })
        ranked = rank_bybit_reviewed_closed_24h_pit(**params)
        self.assertEqual(ranked.reviewed_eligible_contracts, 52)
        self.assertEqual(ranked.verified_24h_window_count, 52)
        self.assertEqual(len(ranked.ranked), TOP_N)
        self.assertEqual(ranked.ranked[0].symbol, symbols[-1])
        self.assertEqual(ranked.ranked[0].rank, 1)
        self.assertEqual(ranked.ranked[-1].rank, TOP_N)
        report = ranked.sanitized_report()
        self.assertEqual(
            report["status"],
            "j1_reviewed_50_closed_24h_rank_verified_not_marketwide",
        )
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["canonical_ohlcv_approved"])
        self.assertEqual(report["reviewed_complete_closed_24h_windows"], 52)

    def test_missing_or_duplicate_or_future_closed_bars_fail_closed(self):
        params = review_params()
        params["kline_pages"].pop("NEARUSDT")
        with self.assertRaises(DataGapError):
            rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["kline_pages"]["NEARUSDT"]["result"]["list"].pop()
        with self.assertRaises(DataGapError):
            rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["kline_pages"]["NEARUSDT"]["result"]["list"][1][0] = (
            params["kline_pages"]["NEARUSDT"]["result"]["list"][0][0])
        with self.assertRaises(DataGapError):
            rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["kline_pages"]["NEARUSDT"]["result"]["list"][0][0] = str(DECISION)
        with self.assertRaises(DataGapError):
            rank_bybit_reviewed_closed_24h_pit(**params)

    def test_bad_per_page_server_clock_or_metadata_drift_rejected(self):
        params = review_params()
        params["kline_pages"]["HYPEUSDT"]["time"] = NOW-40_000
        with self.assertRaises(DataValidationError):
            rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["after_instrument_pages"][0]["result"]["list"][0]["lotSizeFilter"] = {
            "qtyStep": "0.000000002"
        }
        with self.assertRaisesRegex(DataValidationError, "membership drift"):
            rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["after_instrument_pages"][0]["result"]["list"].append(
            instrument_row("UNIUSDT")
        )
        with self.assertRaisesRegex(DataValidationError, "membership drift"):
            rank_bybit_reviewed_closed_24h_pit(**params)

    def test_pit_cannot_backdate_registry_or_cross_hour_or_use_ticker_rows(self):
        for invalid in (False, DECISION-H):
            with self.subTest(invalid=invalid):
                params = review_params()
                params["decision_at_ms"] = invalid
                with self.assertRaises(DataValidationError):
                    rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["observed_at_ms"] = DECISION + H
        with self.assertRaises(DataValidationError):
            rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["observed_at_ms"] += MAX_BATCH_DURATION_MS
        with self.assertRaises(DataValidationError):
            rank_bybit_reviewed_closed_24h_pit(**params)
        params = review_params()
        params["registry_variant"] = "expanded-13"
        with self.assertRaises(DataValidationError):
            rank_bybit_reviewed_closed_24h_pit(**params)

    def test_new_listing_without_full_24h_is_not_silently_zero_padded(self):
        params = review_params()
        for page in (params["before_instrument_pages"],
                     params["after_instrument_pages"]):
            for member in page[0]["result"]["list"]:
                if member["symbol"] == "NEARUSDT":
                    member["launchTime"] = str(DECISION - 5*H)
        params["kline_pages"].pop("NEARUSDT")
        params["kline_page_received_at_ms"].pop("NEARUSDT")
        ranked = rank_bybit_reviewed_closed_24h_pit(**params)
        self.assertEqual([m.symbol for m in ranked.ranked], ["HYPEUSDT"])
        self.assertEqual(ranked.reviewed_insufficient_listing_history, 1)
        self.assertEqual(ranked.reviewed_eligible_contracts, 2)
        self.assertFalse(ranked.sanitized_report()["marketwide_top50_verified"])


@unittest.skipUnless(os.name == "posix", "owner-only GET probe is POSIX-gated")
class OwnerReviewedClosedBybitTests(unittest.TestCase):
    def test_real_network_disabled_full_flow_catalog_before_and_after_24h(self):
        symbols = ("HYPEUSDT", "NEARUSDT")
        fake_clock = [NOW]
        calls = []
        def clock():
            fake_clock[0] += 85
            return fake_clock[0]
        def fetch(url, limit):
            calls.append(url)
            query = parse_qs(urlsplit(url).query)
            stamp = fake_clock[0] - 50
            if "/instruments-info?" in url:
                return json.dumps(instrument_page(
                    [instrument_row(s) for s in symbols],
                    ms=stamp, cursor="",
                )).encode("ascii")
            sym = query["symbol"][0]
            payload = kline_for(
                sym, "10" if sym == "HYPEUSDT" else "20", at=stamp,
            )
            return json.dumps(payload).encode("ascii")
        client = BoundedBybitPublicClient(transport=fetch)
        events = []
        with patch("socket.create_connection",
                   side_effect=AssertionError("no real network")):
            result = owner_rank_bybit_reviewed_closed_24h(
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                emit_public_ranked_symbols=True,
                client=client, clock_ms=clock,
                progress=events.append,
            )
        self.assertEqual(result["status"],
                         "private_j1_reviewed_closed_24h_rank_verified_not_marketwide")
        self.assertEqual(result["reviewed_eligible_contracts"], 2)
        self.assertEqual(result["network_gets_attempted"], 4)
        self.assertEqual(len(calls), 4)
        self.assertIn("/instruments-info?", calls[0])
        self.assertIn("/instruments-info?", calls[-1])
        self.assertEqual(
            result["public_reviewed_ranked_contract_identifiers_only"],
            ["NEARUSDT", "HYPEUSDT"],
        )
        self.assertTrue(events)
        self.assertFalse(result["data_stored"])
        self.assertFalse(result["marketwide_top50_verified"])

    def test_no_owner_opt_in_before_any_get(self):
        client = BoundedBybitPublicClient(
            transport=lambda url, limit: self.fail("unexpected GET"))
        with self.assertRaisesRegex(J1BybitCaptureError, "opt_in"):
            owner_rank_bybit_reviewed_closed_24h(client=client)
        self.assertEqual(client.requests_attempted, 0)

    def test_unavailable_10006_is_fail_stop_after_first_get(self):
        client = BoundedBybitPublicClient(
            transport=lambda url, limit: b'{"retCode":10006,"retMsg":"NO_LOG"}')
        with self.assertRaisesRegex(J1BybitCaptureError, "rate_limit_no_retry"):
            owner_rank_bybit_reviewed_closed_24h(
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                client=client, clock_ms=lambda: NOW,
            )
        self.assertEqual(client.requests_attempted, 1)

    def test_too_late_hour_fails_before_any_api_call(self):
        client = BoundedBybitPublicClient(
            transport=lambda url, limit: self.fail("unexpected GET"))
        with self.assertRaisesRegex(
            J1BybitCaptureError, "start_too_late_in_utc_hour",
        ):
            owner_rank_bybit_reviewed_closed_24h(
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                client=client,
                clock_ms=lambda: DECISION + H - 60_000,
            )
        self.assertEqual(client.requests_attempted, 0)


if __name__ == "__main__":
    unittest.main()
