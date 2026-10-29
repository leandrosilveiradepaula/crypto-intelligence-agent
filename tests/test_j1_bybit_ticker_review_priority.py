"""J1 #319: ticker-based identity REVIEW priorities, not trading/Top50.

No network in CI; all market-like values and identities are synthetic.
"""
from copy import deepcopy
from decimal import Decimal
import json
import os
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, tickers_url,
)
from crypto_intelligence_agent.bybit_top50_ticker_priority import (
    rank_bybit_ticker_identity_review_priority,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.prioritize_bybit_top50_identity_review import (
    owner_prioritize_bybit_top50_review,
)
from test_bybit_paginated_universe_research import T, tickers
from test_j1_bybit_top50_coverage_census import fixture, census
from test_j1_private_bybit_capture import FakeFeed


def priority(rows=None, *, pages=None, received=T):
    return rank_bybit_ticker_identity_review_priority(
        instrument_pages=fixture() if pages is None else pages,
        requested_cursors=(None, "more"),
        page_received_at_ms=(T-400, T-120),
        ticker_payload=tickers(
            rows if rows is not None else (
                {"symbol": "BTCUSDT", "turnover24h": "200", "volume24h": "5"},
                {"symbol": "ETHUSDT", "turnover24h": "600", "volume24h": "10"},
                {"symbol": "NEARUSDT", "turnover24h": "500", "volume24h": "15"},
                {"symbol": "UNIUSDT", "turnover24h": "300", "volume24h": "20"},
                {"symbol": "AAPLUSDT", "turnover24h": "999999"},
            ), ms=received-15),
        observed_at_ms=received,
    )


class TickerPriorityOfflineTests(unittest.TestCase):
    def test_exact_decimal_ticker_rank_only_prioritizes_identities(self):
        result = priority()
        self.assertEqual(result.census.reviewed_eligible_usdt_perpetuals, 2)
        self.assertEqual(result.census.plausible_unreviewed_usdt_perpetuals, 2)
        self.assertEqual(result.candidates_with_ticker, 4)
        self.assertEqual(result.candidates_with_positive_proxy, 4)
        self.assertEqual(result.reviewed_in_rolling_proxy_top50, 2)
        self.assertEqual(result.unreviewed_in_rolling_proxy_top50, 2)
        self.assertEqual(result.priority_review_symbols, ("NEARUSDT", "UNIUSDT"))
        self.assertEqual(len(result.rolling_proxy_top50_digest_sha256), 64)
        report = result.sanitized_report()
        self.assertEqual(
            report["status"],
            "j1_top50_rolling_ticker_identity_review_priority_only",
        )
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["full_closed_24h_turnover_rank_verified"])
        self.assertFalse(report["rolling_24h_ticker_proxy_unit_verified"])
        self.assertFalse(report["historical_pit_marketwide_top50_verified"])
        self.assertEqual(report["review_priority_rank_limit"], 75)
        self.assertEqual(report["unreviewed_in_priority_queue"], 2)
        self.assertEqual(
            report["priority_queue_digest_sha256"],
            result.priority_review_symbols_digest_sha256,
        )
        text = json.dumps(report, sort_keys=True)
        for fragment in ("NEARUSDT", "AAPLUSDT", "UNIUSDT", "999999", "200"):
            self.assertNotIn('"public_review_contract_identifiers_only"', text)
        self.assertNotIn("NEARUSDT", text)

    def test_ties_and_zero_are_deterministic_not_fake_top50(self):
        equal = priority(rows=(
            {"symbol": "BTCUSDT", "turnover24h": "2"},
            {"symbol": "ETHUSDT", "turnover24h": "2"},
            {"symbol": "NEARUSDT", "turnover24h": "2"},
            {"symbol": "UNIUSDT", "turnover24h": "0"},
        ))
        self.assertEqual(equal.candidates_with_positive_proxy, 3)
        self.assertEqual(equal.priority_review_symbols, ("NEARUSDT",))
        self.assertEqual(equal.unreviewed_in_rolling_proxy_top50, 1)
        repeated = priority(rows=(
            {"symbol": "NEARUSDT", "turnover24h": "2"},
            {"symbol": "BTCUSDT", "turnover24h": "2"},
            {"symbol": "UNIUSDT", "turnover24h": "0"},
            {"symbol": "ETHUSDT", "turnover24h": "2"},
        ))
        self.assertEqual(equal.rolling_proxy_top50_digest_sha256,
                         repeated.rolling_proxy_top50_digest_sha256)

    def test_missing_or_duplicate_any_relevant_candidate_fails_closed(self):
        base = [
            {"symbol": "BTCUSDT", "turnover24h": "1"},
            {"symbol": "ETHUSDT", "turnover24h": "2"},
            {"symbol": "NEARUSDT", "turnover24h": "3"},
            {"symbol": "UNIUSDT", "turnover24h": "4"},
        ]
        with self.assertRaisesRegex(DataValidationError, "incomplete"):
            priority(rows=base[:3])
        with self.assertRaisesRegex(DataValidationError, "duplicate"):
            priority(rows=base + [deepcopy(base[-1])])
        for bad in ("NaN", "-5", "Infinity", "", True, 3.2, "1e999999"):
            with self.subTest(turnover=bad):
                corrupted = deepcopy(base)
                corrupted[2]["turnover24h"] = bad
                with self.assertRaises(DataValidationError):
                    priority(rows=corrupted)

    def test_unrelated_ticker_cannot_affect_priority(self):
        expected = priority()
        rows = [
            {"symbol": "NEARUSDT", "turnover24h": "500"},
            {"symbol": "UNIUSDT", "turnover24h": "300"},
            {"symbol": "ETHUSDT", "turnover24h": "600"},
            {"symbol": "BTCUSDT", "turnover24h": "200"},
            {"symbol": "USDCUSDT", "turnover24h": "123456789"},
            {"symbol": "AAPLUSDT", "turnover24h": "999999999999"},
        ]
        later = priority(rows=rows)
        self.assertEqual(expected.priority_review_symbols,
                         later.priority_review_symbols)
        self.assertFalse(later.sanitized_report()["marketwide_top50_verified"])

    def test_future_stale_ticker_or_rank_budget_is_rejected(self):
        with self.assertRaises(DataValidationError):
            priority(received=T+60_000)
        for invalid in (49, 101, True, False, "75", 75.0, None):
            with self.subTest(value=invalid), self.assertRaises(DataValidationError):
                rank_bybit_ticker_identity_review_priority(
                    instrument_pages=fixture(),
                    requested_cursors=(None,"more"),
                    page_received_at_ms=(T-400,T-120),
                    ticker_payload=tickers(ms=T-15),
                    observed_at_ms=T,
                    priority_rank_limit=invalid,
                )

    def test_ticker_url_allowlist_exact_public_only(self):
        self.assertEqual(
            tickers_url(), "https://api.bybit.com/v5/market/tickers?category=linear",
        )
        seen = []
        client = BoundedBybitPublicClient(
            transport=lambda url,limit: (
                seen.append((url,limit)) or
                json.dumps(tickers(ms=T-15)).encode("ascii")
            )
        )
        self.assertEqual(client.get(tickers_url())[1]["retCode"], 0)
        self.assertEqual(client.last_request_stage, "ticker_review_proxy")
        self.assertEqual(seen[0][1], 1_500_000)
        for url in (
            tickers_url()+"&symbol=BTCUSDT",
            tickers_url().replace("api.bybit.com", "evil.example.org"),
            tickers_url().replace("category=linear", "category=inverse"),
            tickers_url()+"&limit=1000",
        ):
            with self.subTest(url=url), self.assertRaises(J1BybitCaptureError):
                client.get(url)
        self.assertEqual(client.requests_attempted, 1)

    def test_owner_requires_opt_in_and_no_network(self):
        client = BoundedBybitPublicClient(
            transport=lambda url,limit: self.fail("no owner opt-in"))
        with self.assertRaisesRegex(J1BybitCaptureError, "opt_in"):
            owner_prioritize_bybit_top50_review(client=client)
        self.assertEqual(client.requests_attempted, 0)

    @unittest.skipUnless(os.name == "posix", "owner-only public probe POSIX")
    def test_owner_single_ticker_get_and_optional_public_symbol_list(self):
        feed = FakeFeed()
        hits = []
        def transport(url,limit):
            hits.append(url)
            if "/tickers?" in url:
                from test_bybit_paginated_universe_research import instrument_page
                return json.dumps(tickers(rows=(
                    {"symbol": "BTCUSDT", "turnover24h": "200"},
                    {"symbol": "ETHUSDT", "turnover24h": "300"},
                ),ms=feed.observed-15)).encode("ascii")
            return feed.get(url,limit)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            out = owner_prioritize_bybit_top50_review(
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                emit_public_review_symbols=True,
                client=BoundedBybitPublicClient(transport=transport),
                clock_ms=feed.now,
            )
        self.assertEqual(out["status"],
                         "j1_top50_rolling_ticker_identity_review_priority_only")
        self.assertEqual(len(hits), 2)
        self.assertEqual(out["network_gets_attempted"], 2)
        self.assertEqual(out["public_review_contract_identifiers_only"], [])
        self.assertFalse(out["data_stored"])
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["marketwide_top50_verified"])

    @unittest.skipUnless(os.name == "posix", "owner-only public probe POSIX")
    def test_rate_limit_10006_at_ticker_stops_with_no_retry(self):
        feed = FakeFeed()
        hits=[]
        def transport(url,limit):
            hits.append(url)
            if "/tickers?" in url:
                return b'{"retCode":10006,"retMsg":"PRIVATE_NEVER_PRINT"}'
            return feed.get(url,limit)
        client=BoundedBybitPublicClient(transport=transport)
        with self.assertRaisesRegex(J1BybitCaptureError,"rate_limit_no_retry"):
            owner_prioritize_bybit_top50_review(
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                client=client,clock_ms=feed.now,
            )
        self.assertEqual(client.requests_attempted,2)
        self.assertEqual(client.last_provider_retcode,10006)
        self.assertEqual(client.last_request_stage,"ticker_review_proxy")


if __name__ == "__main__":
    unittest.main()
