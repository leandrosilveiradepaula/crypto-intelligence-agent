"""J1 #351: offline ticker priority is never a 24h closed market rank."""
from __future__ import annotations
from copy import deepcopy
import json
import unittest
from crypto_intelligence_agent.bybit_top50_identity_priority import (
    prioritize_unreviewed_bybit_identities_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_bybit_paginated_universe_research import (
    T, instrument_row, instrument_page, tickers,
)


def fixture():
    pages = (
        instrument_page(
            [instrument_row("BTCUSDT"),
             instrument_row("AAPLXUSDT"),
             instrument_row("FAKECOINUSDT")],
            ms=T-400, cursor="next"),
        instrument_page([instrument_row("ETHUSDT"),
                         instrument_row("RANDOMUSDT")], ms=T-200),
    )
    tick = tickers([
        {"symbol":"BTCUSDT","turnover24h":"200","volume24h":"2"},
        {"symbol":"ETHUSDT","turnover24h":"300","volume24h":"3"},
        {"symbol":"FAKECOINUSDT","turnover24h":"100","volume24h":"1"},
        {"symbol":"RANDOMUSDT","turnover24h":"400","volume24h":"4"},
        {"symbol":"AAPLXUSDT","turnover24h":"100000","volume24h":"10"},
    ], ms=T-100)
    return pages, tick


def review(pages=None, tick=None, **kw):
    p,t=fixture()
    return prioritize_unreviewed_bybit_identities_offline(
        instrument_pages=p if pages is None else pages,
        requested_cursors=(None,"next"),
        page_received_at_ms=(T-380,T-180),
        tickers_payload=t if tick is None else tick,
        observed_at_ms=T,
        registry_variant="expanded-13",
        **kw
    )


class IdentityReviewPriorityTests(unittest.TestCase):
    def test_review_queue_only_not_top50_or_crypto_verification(self):
        a=review()
        self.assertEqual(a.reviewed_count, 2)
        self.assertEqual(a.unreviewed_count, 3)
        self.assertEqual(a.review_symbols, ("AAPLXUSDT","RANDOMUSDT","FAKECOINUSDT"))
        report=a.sanitized_report()
        self.assertNotIn("review_symbols_public_only",report)
        self.assertEqual(a.sanitized_report(include_public_symbols=True)
                         ["review_symbols_public_only"], list(a.review_symbols))
        for key in ("marketwide_top50_verified","closed_24h_rank_verified",
                    "ticker_unit_verified","crypto_identity_verified_for_queue",
                    "rights_for_live_authorized","orders_sent"):
            self.assertFalse(report[key])
        self.assertEqual(report["network_requests"],0)

    def test_malformed_missing_duplicate_tickers_fail_closed(self):
        p,t=fixture()
        for bad in ([],[t["result"]["list"][0]],
                    t["result"]["list"]+[t["result"]["list"][0]]):
            changed=deepcopy(t); changed["result"]["list"]=bad
            with self.assertRaises(DataValidationError):review(tick=changed)
        for val in (True,"NaN","-1",2.5):
            changed=deepcopy(t)
            changed["result"]["list"][2]["turnover24h"]=val
            with self.assertRaises(DataValidationError):review(tick=changed)
        changed=deepcopy(t);changed["time"]=T-1000
        with self.assertRaises(DataValidationError):review(tick=changed)
        with self.assertRaises(DataValidationError):review(max_review=51)
        with self.assertRaises(DataValidationError):review(max_review=True)
        with self.assertRaises(DataValidationError):
            review(pages=(p[0],p[0]))

    def test_zero_turnover_never_ranks_and_ties_lexical(self):
        p,t=fixture()
        changed=deepcopy(t)
        for item in changed["result"]["list"]:
            if item["symbol"]=="RANDOMUSDT":
                item["turnover24h"]="0";item["volume24h"]="0"
            if item["symbol"]=="FAKECOINUSDT":
                item["turnover24h"]="100000"
        result=review(tick=changed,max_review=1)
        self.assertEqual(result.review_symbols,("AAPLXUSDT",))
        self.assertEqual(result.omitted_zero_turnover_count,1)
        self.assertEqual(result.ranked_unreviewed_count,2)
        self.assertFalse(result.sanitized_report()["marketwide_top50_verified"])


if __name__=="__main__":
    unittest.main()
