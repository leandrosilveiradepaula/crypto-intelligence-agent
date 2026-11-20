"""D451 offline dynamic public REST capture: 50 by rolling turnover, never J1."""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal
import json
from unittest import TestCase
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, instruments_url, tickers_url,
)
from crypto_intelligence_agent.j2_dynamic_public_n50_d451 import (
    capture_dynamic_public_n50, select_dynamic_public_n50,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_j2_j4_public_paper_cycle_d449 import ticker

NOW = 1_799_500_000_000


def row(i):
    name = "BTC" if i == 0 else "ALT" + str(i)
    return {
        "symbol": name + "USDT", "baseCoin": name,
        "quoteCoin": "USDT", "settleCoin": "USDT",
        "contractType": "LinearPerpetual", "status": "Trading",
        "symbolType": "", "marketRegion": "", "underlyingTicker": "",
        "tags": [], "isPreListing": False, "preListingInfo": None,
        "deliveryTime": "0", "launchTime": str(NOW - 30 * 86_400_000),
        "priceFilter": {"tickSize": "0.01"},
        "lotSizeFilter": {
            "qtyStep": "0.01", "minOrderQty": "0.01",
            "minNotionalValue": "5", "maxOrderQty": "1000",
        },
        "leverageFilter": {"minLeverage": "1", "maxLeverage": "50"},
    }


def response(rows, *, timestamp, cursor=""):
    return {
        "retCode": 0, "retMsg": "OK", "time": timestamp - 100,
        "result": {
            "category": "linear",
            "nextPageCursor": cursor, "list": list(rows),
        },
    }


def scenario():
    rows = [row(i) for i in range(60)]
    tradfi = row(90)
    tradfi["marketRegion"] = "US"
    rows.append(tradfi)
    future = row(91)
    future["contractType"] = "LinearFutures"
    rows.append(future)
    pages = (
        response(rows[:31], timestamp=NOW - 300, cursor="cursor2"),
        response(rows[31:], timestamp=NOW - 200),
    )
    tick = response(
        [{"symbol": r["symbol"],
          "turnover24h": "1" if r["symbol"] == "BTCUSDT"
          else str(10_000 - i),
          "volume24h": "100"}
         for i, r in enumerate(rows)], timestamp=NOW,
    )
    return pages, tick


def selected(pages=None, ticks=None, cursors=(None, "cursor2"),
             received=(NOW - 300, NOW - 200), at=NOW):
    base_pages, base_ticks = scenario()
    return select_dynamic_public_n50(
        instrument_pages=base_pages if pages is None else pages,
        requested_cursors=cursors, page_received_at_ms=received,
        ticker_payload=base_ticks if ticks is None else ticks,
        ticker_received_at_ms=at,
    )


class DynamicN50Tests(TestCase):
    def test_complete_paginated_50_perps_roll24h_preserves_btc_context(self):
        out = selected()
        self.assertEqual(len(out.ranked), 50)
        self.assertEqual(out.eligible_rows, 60)
        self.assertEqual(out.catalog_rows, 62)
        self.assertEqual(out.symbols[0], "ALT1USDT")
        self.assertEqual(out.symbols[-1], "BTCUSDT")
        self.assertTrue(out.btc_added_as_context)
        self.assertNotIn("ALT90USDT", out.symbols)
        self.assertEqual(len(out.scope.contracts), 50)
        self.assertEqual(out.scope.registry_sha256, out.fingerprint_sha256)
        self.assertFalse(out.sanitized_report()["marketwide_crypto_identity_verified"])
        self.assertFalse(out.sanitized_report()["full_24_closed_hour_rank_verified"])
        self.assertFalse(out.sanitized_report()["orders_sent"])
        q = ticker("ALT1USDT", at=NOW + 1500, mark="100")
        contract = out.contract_for_quote(q)
        self.assertEqual(contract.max_notional_quote, Decimal("100000"))
        self.assertEqual(contract.min_notional_quote, Decimal("5"))
        self.assertEqual(contract.max_leverage_assumed, 50)
        self.assertFalse(contract.exchange_lot_rules_verified)
        with self.assertRaises(DataValidationError):
            out.contract_for_quote(ticker("ALT1USDT", at=NOW + 65_000))

    def test_pagination_ticker_gaps_duplicate_and_tradfi_rejected(self):
        pages, tick = scenario()
        for broken in [
            lambda a,b: a[0]["result"].update(nextPageCursor=""),
            lambda a,b: a[1]["result"].update(nextPageCursor="cursor3"),
            lambda a,b: a[1]["result"]["list"].append(deepcopy(a[0]["result"]["list"][0])),
            lambda a,b: b["result"]["list"].pop(0),
            lambda a,b: b["result"]["list"].append(deepcopy(b["result"]["list"][0])),
            lambda a,b: b["result"]["list"][0].update(turnover24h="NaN"),
            lambda a,b: b.update(retCode=10006),
        ]:
            p = deepcopy(pages)
            b = deepcopy(tick)
            broken(p,b)
            with self.subTest(broken=str(broken)), self.assertRaises(DataValidationError):
                selected(pages=p,ticks=b)
        with self.assertRaises(DataValidationError):
            selected(cursors=(None, None))
        with self.assertRaises(DataValidationError):
            selected(received=(NOW-300, NOW + 1))
        with self.assertRaises(DataValidationError):
            selected(at=NOW-400)

    def test_real_origin_uses_existing_bounded_public_get_only_with_flags(self):
        pages, tick = scenario()
        expected_urls = [instruments_url(), instruments_url(cursor="cursor2"), tickers_url()]
        received = []
        reply = {
            expected_urls[0]: pages[0], expected_urls[1]: pages[1],
            expected_urls[2]: tick,
        }
        def transport(url, maxbytes):
            received.append((url, maxbytes))
            return json.dumps(reply[url]).encode("ascii")
        client = BoundedBybitPublicClient(transport=transport)
        opts = dict(
            client=client, wall_ms=lambda: NOW, allow_public_network=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True, confirm_public_data_rights=True,
        )
        with patch("socket.create_connection",
                   side_effect=AssertionError("REST fixture must not touch network")):
            output = capture_dynamic_public_n50(**opts)
        self.assertEqual([x[0] for x in received], expected_urls)
        self.assertEqual(client.requests_attempted, 3)
        self.assertEqual(output.source_mode, "injected_offline_protocol_replay")
        self.assertEqual(len(output.ranked), 50)
        with self.assertRaises(DataValidationError):
            capture_dynamic_public_n50(**{**opts,"confirm_region_eligible":False})
        self.assertEqual(len(received), 3)

    def test_missing_btc_and_too_few_eligible_cannot_bootstrap(self):
        pages, tick = scenario()
        p = deepcopy(pages)
        p[0]["result"]["list"][0]["contractType"] = "LinearFutures"
        with self.assertRaises(DataValidationError):
            selected(pages=p)
        t = deepcopy(tick)
        for item in t["result"]["list"]:
            if item["symbol"].startswith("ALT") and int(item["symbol"][3:-4]) > 45:
                item["turnover24h"] = "0"
        with self.assertRaises(DataValidationError):
            selected(ticks=t)


if __name__ == "__main__":
    import unittest
    unittest.main()
