"""D463 PAPER contract freshness: no stale metadata or synchronous ticker GETs."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import Event, Thread
import json
import os
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, instruments_url,
)
from crypto_intelligence_agent.j4_public_paper_contract_refresh_d463 import (
    AsyncPublicPaperContractTerms,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_j2_dynamic_public_n50_d451 import NOW, row, selected, response
from test_j2_j4_public_paper_cycle_d449 import ticker


class PublicContractFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = selected()
        self.stamp = [NOW + 2000]
        self.row = row(1)
        self.calls = []
        def transport(url, maxbytes):
            self.calls.append(url)
            if url != instruments_url(symbol="ALT1USDT"):
                raise AssertionError("D463 may GET one selected contract only")
            return json.dumps(response(
                [deepcopy(self.row)], timestamp=self.stamp[0],
            ), separators=(",", ":")).encode("ascii")
        self.client = BoundedBybitPublicClient(transport=transport)
        self.source = AsyncPublicPaperContractTerms(
            snapshot=self.snapshot, max_age_ms=30_000,
            enable_public_contract_refresh=True, client=self.client,
            wall_ms=lambda: self.stamp[0],
        )

    def test_no_http_on_first_quote_and_proven_new_quote_after_refresh(self):
        first = ticker("ALT1USDT", at=NOW+1500, mark="100")
        with patch("socket.create_connection",
                   side_effect=AssertionError("ticker callback must not GET")):
            with self.assertRaises(DataGapError):
                self.source(first)
        self.assertEqual(self.calls, [])
        self.assertTrue(self.source.refresh_one())
        self.assertEqual(self.calls, [instruments_url(symbol="ALT1USDT")])
        # A quote recorded before that GET cannot retroactively use its terms.
        with self.assertRaises(DataGapError):
            self.source(first)
        newer = ticker("ALT1USDT", at=NOW+2200, mark="100")
        found = self.source(newer)
        self.assertEqual(found.observed_at_ms,NOW+2000)
        self.assertEqual(found.symbol,"ALT1USDT")
        self.assertTrue(found.fixture_version.startswith("fixture_d463"))
        self.assertFalse(found.exchange_lot_rules_verified)
        self.assertEqual(self.source.sanitized_report()["unchanged_rules_refreshed"],1)
        self.assertFalse(self.source.sanitized_report()["orders_sent"])
        self.assertFalse(self.source.refresh_one())

    def test_changed_contract_stops_new_paper_open(self):
        self.row["status"]="Settled"
        with self.assertRaises(DataGapError):
            self.source(ticker("ALT1USDT",at=NOW+1000))
        self.assertTrue(self.source.refresh_one())
        self.assertEqual(self.source.sanitized_report()["unchanged_rules_refreshed"],0)
        self.assertEqual(self.source.sanitized_report()["stale_or_changed_contracts_rejected"],1)
        with self.assertRaises(DataGapError):
            self.source(ticker("ALT1USDT",at=NOW+3500))

    def test_stale_30s_terms_requeue_only_after_bounded_cooldown(self):
        with self.assertRaises(DataGapError):
            self.source(ticker("ALT1USDT",at=NOW+1500))
        self.assertTrue(self.source.refresh_one())
        self.assertIsNotNone(self.source(ticker("ALT1USDT",at=NOW+2200)))
        self.stamp[0]=NOW+40_000
        with self.assertRaises(DataGapError):
            self.source(ticker("ALT1USDT",at=NOW+41_000))
        self.assertTrue(self.source.refresh_one())
        refreshed = self.source(ticker("ALT1USDT",at=NOW+41_100))
        self.assertEqual(refreshed.observed_at_ms,NOW+40_000)
        self.assertEqual(len(self.calls),2)

    def test_injected_async_worker_stops_without_network_when_idle(self):
        stop = Event()
        t = Thread(target=self.source.run,args=(stop,),daemon=True)
        t.start()
        stop.set()
        t.join(timeout=3)
        self.assertFalse(t.is_alive())
        self.assertEqual(self.calls,[])

    def test_explicit_source_mode_optin_and_bounds(self):
        with self.assertRaises(DataValidationError):
            AsyncPublicPaperContractTerms(
                snapshot=self.snapshot,max_age_ms=30_000,
                client=self.client,wall_ms=lambda:NOW+1000,
            )
        with self.assertRaises(DataValidationError):
            AsyncPublicPaperContractTerms(
                snapshot=self.snapshot,max_age_ms=61_000,
                enable_public_contract_refresh=True,
                client=self.client,wall_ms=lambda:NOW+1000,
            )
        self.assertEqual(self.calls,[])


if __name__=="__main__":
    unittest.main()
