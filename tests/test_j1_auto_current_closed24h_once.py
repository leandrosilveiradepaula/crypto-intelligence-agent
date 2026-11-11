"""D286: fake Bybit-only full-current closed24h research rank, zero network/IO."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    J1BybitCaptureError,
)
from scripts.run_j1_auto_closed24h_rank_once import (
    HOUR_MS, research_current_closed24h_once,
)

BASE = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
NOW = BASE + 70_000
SYMS = tuple("TOK" + str(n) + "USDT" for n in range(50))


def instrument(sym):
    return dict(
        symbol=sym, baseCoin=sym[:-4], quoteCoin="USDT",
        settleCoin="USDT", contractType="LinearPerpetual",
        status="Trading", deliveryTime="0", isPreListing=False,
        preListingInfo=None, marketRegion="", underlyingTicker="",
        symbolType="", tags=[], fullName="",
    )


class FakeClient:
    def __init__(self, *, symbols=SYMS, changed=False, short=False,
                 fail_symbol=None, clock=lambda: NOW):
        self.symbols = tuple(symbols)
        self.changed = changed
        self.short = short
        self.fail_symbol = fail_symbol
        self.clock = clock
        self.requests_attempted = 0
        self.catalog_calls = 0
        self.klines = 0

    def get(self, url):
        self.requests_attempted += 1
        parts = urlsplit(url)
        q = parse_qs(parts.query)
        if parts.path == "/v5/market/instruments-info":
            self.catalog_calls += 1
            symbols = list(self.symbols)
            if self.changed and self.catalog_calls > 1:
                symbols[-1] = "NEWSYMBOLUSDT"
            obj = {
                "retCode": 0, "time": self.clock() - 1000,
                "result": {
                    "category": "linear", "nextPageCursor": "",
                    "list": [instrument(s) for s in symbols],
                }
            }
        elif parts.path == "/v5/market/kline":
            self.klines += 1
            sym = q["symbol"][0]
            if sym == self.fail_symbol:
                raise J1BybitCaptureError("provider_rate_limit_no_retry")
            opened = int(q["start"][0])
            qty = 23 if self.short and sym == self.symbols[-1] else 24
            # A young listing lacks the EARLIEST hour, never the newest.
            start_index = 24 - qty
            rows = [
                [str(opened+i*HOUR_MS), "1", "2", "1", "2", "20",
                 str(self.symbols.index(sym) + 1)]
                for i in reversed(range(start_index, 24))
            ]
            obj = {"retCode": 0, "result": {
                "category": "linear", "symbol": sym, "list": rows}}
        else:
            raise AssertionError("non-allowlisted GET")
        return json.dumps(obj).encode("ascii"), obj


def call(*, client=None, clock=lambda: NOW, **kw):
    c = client if client is not None else FakeClient()
    return research_current_closed24h_once(
        client=c, clock_ms=clock, owner_ok=True,
        allow_public_network=True,
        confirm_region_and_personal_research=True, **kw,
    ), c


class Closed24hCurrentAutoTests(unittest.TestCase):
    def test_fifty_perps_two_catalogs_and_real_closed_hour_turnover(self):
        out, client = call()
        self.assertEqual(
            out["status"], "current_closed24h_provisional_perpetual_rank_research_only",
            out)
        self.assertEqual(client.requests_attempted, 52)
        self.assertEqual((client.catalog_calls, client.klines), (2, 50))
        self.assertTrue(out["catalog_census_matches_before_after"])
        self.assertEqual(out["current_catalog_provisional_candidates"], 50)
        self.assertEqual(out["complete_closed24h_candidates"], 50)
        self.assertEqual(out["ranked_research_candidates"], 50)
        self.assertEqual(out["insufficient_closed24h_candidates"], 0)
        self.assertEqual(len(out["rank_digest_sha256"]), 64)
        self.assertEqual(out["decision_closed_hour_end_ms"], BASE)
        self.assertFalse(out["rolling_ticker_volume_used"])
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertFalse(out["current_crypto_identity_independently_verified"])
        self.assertFalse(out["database_modified"])
        self.assertFalse(out["orders_sent"])
        self.assertNotIn("TOK", json.dumps(out))
        again, _ = call()
        self.assertEqual(out["rank_digest_sha256"], again["rank_digest_sha256"])

    def test_tradfi_name_and_known_negative_are_excluded_before_klines(self):
        class WithTradFi(FakeClient):
            def get(self, url):
                raw, data = super().get(url)
                if urlsplit(url).path == "/v5/market/instruments-info":
                    data["result"]["list"].extend([
                        {**instrument("DUOLUSDT"), "marketRegion": "US"},
                        {**instrument("BZUSDT"), "fullName": "Brent Oil"},
                    ])
                    return json.dumps(data).encode("ascii"), data
                return raw, data

        out, c = call(client=WithTradFi())
        self.assertEqual(out["status"],
                         "current_closed24h_provisional_perpetual_rank_research_only",
                         out)
        self.assertEqual(out["catalog_scanned_contracts"], 52)
        self.assertEqual(out["current_catalog_provisional_candidates"], 50)
        self.assertEqual(c.klines, 50)
        self.assertEqual(c.requests_attempted, 52)
        self.assertFalse(out["marketwide_top50_verified"])

    def test_optin_only_public_ranked_identifiers_and_volume_sort(self):
        out, _ = call(include_public_symbols=True)
        self.assertEqual(len(out["ranked_public_research_symbols_only"]), 50)
        self.assertEqual(out["ranked_public_research_symbols_only"][0],
                         SYMS[-1])
        self.assertEqual(out["ranked_public_research_symbols_only"][-1],
                         SYMS[0])
        self.assertNotIn("wallet", json.dumps(out))

    def test_missing_closed_hours_are_not_imputed(self):
        out, c = call(client=FakeClient(short=True))
        self.assertEqual(out["status"], "abstain")
        self.assertEqual(out["failure_category"], "current_rank_rejected")
        self.assertEqual(c.klines, 50)

    def test_catalog_churn_blocks_result_after_50_gets(self):
        out, c = call(client=FakeClient(changed=True))
        self.assertEqual(out["status"], "abstain")
        self.assertEqual(out["failure_category"], "current_catalog_after_rejected")
        self.assertEqual(c.requests_attempted, 52)
        self.assertFalse(out["catalog_census_matches_before_after"])

    def test_provider_rate_limit_abstains_without_retry(self):
        # Enumeration is lexicographic, not index order: TOK1 follows TOK0.
        out, c = call(client=FakeClient(fail_symbol="TOK1USDT"))
        self.assertEqual(out["status"], "abstain")
        self.assertEqual(out["failure_category"], "current_closed_kline_rejected")
        self.assertEqual(c.requests_attempted, 3)
        self.assertFalse(out["database_modified"])

    def test_utc_deadline_and_bad_clock_abstain(self):
        bad, c = call(clock=lambda: BASE + 500_000)
        self.assertEqual(bad["status"], "abstain")
        self.assertEqual(bad["failure_category"], "current_clock_rejected")
        self.assertEqual(c.requests_attempted, 0)
        now = {"t": NOW}
        class Clocked(FakeClient):
            def get(self, url):
                answer = super().get(url)
                if self.klines == 1:
                    now["t"] = BASE + 900_001
                return answer
        out, c = call(client=Clocked(clock=lambda: now["t"]),
                      clock=lambda: now["t"])
        self.assertEqual(out["status"], "abstain")
        self.assertEqual(out["failure_category"], "current_closed_kline_rejected")
        self.assertEqual(c.requests_attempted, 2)

    def test_under_over_budget_and_default_deny_are_inert(self):
        c = FakeClient()
        with patch("socket.create_connection", side_effect=AssertionError("GET")):
            out = research_current_closed24h_once(
                client=c, clock_ms=lambda: self.fail("clock must not run"),
                owner_ok=True)
        self.assertEqual(out["status"], "optin_required")
        self.assertEqual(c.requests_attempted, 0)
        out, c = call(max_candidates=49)
        self.assertEqual(out["failure_category"], "invalid_configuration")
        self.assertEqual(c.requests_attempted, 0)
        out, c = call(client=FakeClient(symbols=tuple(
            "T" + str(i) + "USDT" for i in range(401))))
        self.assertEqual(out["status"], "abstain")
        self.assertEqual(out["failure_category"], "current_catalog_before_rejected")
        self.assertEqual(c.klines, 0)


if __name__ == "__main__":
    unittest.main()
