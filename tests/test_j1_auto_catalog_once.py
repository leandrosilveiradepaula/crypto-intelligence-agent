"""No live Bybit GET: owner-only automated research catalog offline fixtures."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from scripts.scan_j1_auto_usdt_perps_once import (
    observe_current_usdt_perpetuals,
)

NOW = 1_800_000_120_000


def row(symbol, **kwargs):
    r = dict(
        symbol=symbol, baseCoin=symbol[:-4], quoteCoin="USDT",
        settleCoin="USDT", contractType="LinearPerpetual", status="Trading",
        deliveryTime="0", isPreListing=False, preListingInfo=None,
        marketRegion="", underlyingTicker="", symbolType="",
        tags=[], fullName="",
    )
    r.update(kwargs)
    return r


def page(rows, cursor="", at=NOW-1000):
    return dict(retCode=0, time=at, result={
        "category": "linear", "nextPageCursor": cursor,
        "list": rows,
    })


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.requests_attempted = 0
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        i = self.requests_attempted
        self.requests_attempted += 1
        obj = self.pages[i]
        return json.dumps(obj).encode("utf-8"), obj


class AutoCatalogOnceTests(unittest.TestCase):
    def call(self, pages, *, clock=None, client=None, **kwargs):
        c = client or FakeClient(pages)
        stamps = iter(clock or [NOW, *([NOW + 1000] * len(pages))])
        result = observe_current_usdt_perpetuals(
            client=c, now_ms=lambda: next(stamps),
            owner_ok=True, allow_public_network=True,
            confirm_region_and_personal_research=True, **kwargs)
        return result, c

    def test_default_off_no_network(self):
        c = FakeClient([page([row("BTCUSDT")])])
        result = observe_current_usdt_perpetuals(
            client=c, now_ms=lambda: NOW, owner_ok=True)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["requests_attempted"], 0)
        self.assertEqual(c.requests_attempted, 0)

    def test_causal_multi_page_filter_without_manual_registry(self):
        pages = [
            page([row("BTCUSDT"), row("DUOLUSDT", marketRegion="US")],
                 cursor="next"),
            page([row("NEWTOKENUSDT"), row("BZUSDT", fullName="Brent Oil")],
                 at=NOW),
        ]
        result, c = self.call(pages, clock=[NOW, NOW, NOW + 500])
        self.assertEqual(result["status"],
                         "automatic_usdt_perpetual_research_candidates_only")
        self.assertEqual(result["possible_crypto_perp_research_candidates"], 2)
        self.assertEqual(result["catalog_pages"], 2)
        self.assertEqual(result["requests_attempted"], 2)
        self.assertNotIn("NEWTOKENUSDT", json.dumps(result))
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["database_modified"])
        self.assertIn("cursor=next", c.urls[1])

    def test_opt_in_symbol_output_public_identifiers_only(self):
        result, _ = self.call([page([row("BTCUSDT")])],
                              include_public_symbols=True)
        self.assertEqual(result["research_candidate_symbols_only"],
                         ["BTCUSDT"])
        self.assertNotIn("turnover", json.dumps(result))

    def test_truncated_cursor_denied_without_retry(self):
        result, c = self.call([page([row("BTCUSDT")], cursor="more")])
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(c.requests_attempted, 1)
        self.assertEqual(result["failure_code"], "auto_catalog_network_rejected")

    def test_cross_page_symbol_collision_rejected(self):
        r = row("BTCUSDT")
        result, c = self.call([
            page([r], cursor="next"),
            page([deepcopy(r)], at=NOW),
        ], clock=[NOW, NOW, NOW + 1])
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "auto_catalog_screen_rejected")
        self.assertEqual(c.requests_attempted, 2)

    def test_future_provider_timestamp_is_never_accepted(self):
        result, c = self.call([page([row("BTCUSDT")], at=NOW + 5000)])
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "auto_catalog_screen_rejected")
        self.assertEqual(c.requests_attempted, 1)

    def test_denied_permission_does_no_request(self):
        c = FakeClient([page([row("BTCUSDT")])])
        out = observe_current_usdt_perpetuals(
            client=c, now_ms=lambda: NOW, owner_ok=False,
            allow_public_network=True,
            confirm_region_and_personal_research=True)
        self.assertEqual(out["status"], "abstain")
        self.assertEqual(c.requests_attempted, 0)

    def test_invalid_optin_type_rejected_before_network(self):
        c = FakeClient([page([row("BTCUSDT")])])
        out = observe_current_usdt_perpetuals(
            client=c, now_ms=lambda: NOW, owner_ok=True,
            allow_public_network=True,
            confirm_region_and_personal_research=True,
            include_public_symbols="yes")
        self.assertEqual(out["failure_code"], "configuration_invalid")
        self.assertEqual(c.requests_attempted, 0)


if __name__ == "__main__":
    unittest.main()
