"""J1 #319 — complete universe COVERAGE is not turnover Top50 evidence.

All provider responses are synthetic, no real GET, storage, order or secrets.
"""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_top50_coverage_census import (
    census_bybit_top50_identity_coverage,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.probe_bybit_top50_gap import (
    MAX_CENSUS_DURATION_MS, owner_probe_bybit_top50_gap,
)
from test_bybit_paginated_universe_research import (
    T, instrument_page, instrument_row,
)
from test_j1_private_bybit_capture import FakeFeed


def fixture():
    unknown = instrument_row("NEARUSDT")
    not_target_tradfi = instrument_row("AAPLUSDT", symbolType="tradfi",
                                       marketRegion="US",
                                       underlyingTicker="AAPL")
    listing = instrument_row("PENDUSDT", status="PreLaunch",
                             isPreListing=True)
    futures = instrument_row("EXPIRYUSDT", contractType="LinearFutures")
    usdc = instrument_row("BTCUSDC", quoteCoin="USDC", settleCoin="USDC")
    first = instrument_page(
        [instrument_row("BTCUSDT"), unknown, not_target_tradfi],
        ms=T-500, cursor="more",
    )
    second = instrument_page(
        [instrument_row("ETHUSDT"), instrument_row("UNIUSDT"),
         listing, futures, usdc],
        ms=T-180, cursor="",
    )
    return (first, second)


def census(pages=None):
    return census_bybit_top50_identity_coverage(
        instrument_pages=fixture() if pages is None else pages,
        requested_cursors=(None, "more"),
        observed_at_ms=T,
        page_received_at_ms=(T-400, T-120),
    )


class Top50IdentityCoverageTests(unittest.TestCase):
    def test_true_full_page_census_reports_unreviewed_without_promoting(self):
        outcome = census()
        self.assertEqual(outcome.scanned_pages, 2)
        self.assertEqual(outcome.scanned_rows, 8)
        self.assertEqual(outcome.reviewed_crypto_registry_bases, 13)
        self.assertEqual(outcome.reviewed_eligible_usdt_perpetuals, 2)
        self.assertEqual(outcome.plausible_unreviewed_usdt_perpetuals, 2)
        # BTCUSDC has a *reviewed base* BTC, but the contract itself is
        # ineligible because quote/settle are USDC. Keep it separate from
        # unknown-base TradFi/futures/premarket exclusions.
        self.assertEqual(outcome.excluded_other_or_tradfi_rows, 3)
        self.assertEqual(outcome.reviewed_but_noneligible_rows, 1)
        result = outcome.sanitized_report()
        self.assertEqual(result["positive_registry_top50_capacity_gap"], 48)
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["full_closed_24h_turnover_rank_verified"])
        self.assertFalse(result["historical_pit_marketwide_top50_verified"])
        self.assertFalse(result["crypto_identity_for_unreviewed_candidates_verified"])
        self.assertFalse(result["orders_sent"])
        printed = json.dumps(result, sort_keys=True)
        for secret in ("BTCUSDT", "NEARUSDT", "UNIUSDT",
                       "AAPLUSDT", "PENDUSDT", "EXPIRYUSDT"):
            self.assertNotIn(secret, printed)
        self.assertEqual(
            result["plausible_candidate_symbol_digest_sha256"],
            census().plausible_candidate_symbol_digest_sha256,
        )

    def test_unreviewed_duplicate_across_pages_fails_closed(self):
        a,b = deepcopy(fixture())
        b["result"]["list"].append(deepcopy(a["result"]["list"][1]))
        with self.assertRaisesRegex(DataValidationError, "repeated"):
            census((a,b))

    def test_incomplete_cursor_chain_or_bad_crypto_contract_is_not_accepted(self):
        a,b = deepcopy(fixture())
        a["result"]["nextPageCursor"] = "wrong"
        with self.assertRaisesRegex(DataValidationError, "cursor"):
            census((a,b))
        a,b = deepcopy(fixture())
        a["result"]["list"][0]["symbol"] = "BTC.UNSAFEUSDT"
        with self.assertRaisesRegex(DataValidationError, "malformed"):
            census((a,b))

    @unittest.skipUnless(os.name == "posix", "owner-only GET capture is POSIX-gated")
    def test_fake_full_scan_owner_never_persists_or_trades(self):
        feed = FakeFeed()
        client = BoundedBybitPublicClient(transport=feed.get)
        with patch("socket.create_connection",
                   side_effect=AssertionError("no live network")):
            report = owner_probe_bybit_top50_gap(
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                client=client, clock_ms=feed.now,
            )
        self.assertEqual(report["status"],
                         "j1_top50_marketwide_identity_coverage_incomplete")
        self.assertEqual(report["reviewed_eligible_usdt_perpetuals"], 2)
        self.assertEqual(report["network_gets_attempted"], 1)
        self.assertFalse(report["data_stored"])
        self.assertFalse(report["marketwide_top50_verified"])

    def test_without_owner_opt_in_no_http(self):
        client = BoundedBybitPublicClient(
            transport=lambda url,limit: self.fail("no owner opt-in"))
        with self.assertRaisesRegex(
            J1BybitCaptureError, "opt_in",
        ):
            owner_probe_bybit_top50_gap(client=client)
        self.assertEqual(client.requests_attempted, 0)

    @unittest.skipUnless(os.name == "posix", "owner-only GET capture is POSIX-gated")
    def test_10006_rate_limit_stops_without_retry(self):
        client = BoundedBybitPublicClient(
            transport=lambda url,limit: (
                b'{"retCode":10006,"retMsg":"secret_untrusted"}'))
        with self.assertRaisesRegex(J1BybitCaptureError, "rate_limit_no_retry"):
            owner_probe_bybit_top50_gap(
                client=client, clock_ms=lambda: T,
                allow_public_network=True,
                confirm_region_and_personal_research=True,
            )
        self.assertEqual(client.requests_attempted, 1)

    @unittest.skipUnless(os.name == "posix", "owner-only GET capture is POSIX-gated")
    def test_long_census_does_not_fake_freshness(self):
        feed = FakeFeed()
        initial_get = feed.get

        def delayed(url, limit):
            feed.observed += MAX_CENSUS_DURATION_MS + 5
            return initial_get(url, limit)
        client = BoundedBybitPublicClient(transport=delayed)
        with self.assertRaisesRegex(
            J1BybitCaptureError, "exceeds_120s",
        ):
            owner_probe_bybit_top50_gap(
                client=client, clock_ms=feed.now,
                allow_public_network=True,
                confirm_region_and_personal_research=True,
            )
        self.assertEqual(client.requests_attempted, 1)


if __name__ == "__main__":
    unittest.main()
