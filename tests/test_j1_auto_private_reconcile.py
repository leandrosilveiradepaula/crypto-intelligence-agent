"""D281 integration tests against actual private SQLite, no HTTP/network."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_usdt_perp import (
    screen_bybit_usdt_perps_offline,
)
from crypto_intelligence_agent.j1_auto_private_reconcile import (
    reconcile_auto_pool_with_private_census,
)
from scripts.audit_bybit_marketwide_closed24h import HOUR_MS, run_census
from scripts.j1_d264_private_metadata_snapshot import (
    build_snapshot, save_new_snapshot,
)
from scripts.scan_j1_auto_usdt_perps_once import (
    observe_current_usdt_perpetuals,
)

NOW = 1793971800000
END = (NOW // HOUR_MS) * HOUR_MS
SYMBOLS = tuple(f"COIN{i:03d}USDT" for i in range(60))


def item(symbol, *, tradfi=False):
    return {
        "symbol": symbol, "baseCoin": symbol[:-4],
        "contractType": "LinearPerpetual", "status": "Trading",
        "quoteCoin": "USDT", "settleCoin": "USDT",
        "deliveryTime": "0", "isPreListing": False,
        "preListingInfo": None, "marketRegion": "US" if tradfi else "",
        "underlyingTicker": symbol[:-4] if tradfi else "",
        "tags": [], "symbolType": "", "fullName": "",
    }


def payload(rows, at=NOW+1500):
    return {
        "retCode": 0, "time": at,
        "result": {"category": "linear", "nextPageCursor": "",
                   "list": rows},
    }


class CensusClient:
    def __init__(self, catalog=None):
        self.requests_attempted = 0
        self.catalog = catalog or payload([item(s) for s in SYMBOLS], at=NOW-1000)

    def get(self, url):
        from urllib.parse import parse_qs, urlsplit
        self.requests_attempted += 1
        parts = urlsplit(url)
        if parts.path.endswith("/instruments-info"):
            data = self.catalog
        else:
            symbol = parse_qs(parts.query)["symbol"][0]
            data = {
                "retCode": 0, "result": {"category": "linear", "symbol": symbol,
                "list": [[str(END-(i+1)*HOUR_MS), "100", "102", "99",
                          "101", "2", str(100+i)]
                         for i in range(24)]},
            }
        return json.dumps(data).encode("ascii"), data


@unittest.skipUnless(os.name == "posix", "POSIX owner/lock/SQLite integration")
class AutoPrivateJoinTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name) / "data"
        r = run_census(
            directory=self.directory, now_ms=lambda: NOW,
            client=CensusClient(), max_contracts=60,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            owner_ok=True,
        )
        self.assertEqual(r["inspected_contracts"], 60)
        self.file = self.directory / "j1-marketwide-closed24h.sqlite"
        old = payload([
            item(s, tradfi=(s == "COIN001USDT")) for s in SYMBOLS
        ], at=NOW+1500)
        snapshot = build_snapshot(
            old, frozen_members=frozenset(SYMBOLS),
            frozen_end_ms=END, captured_at_ms=NOW+1000,
            received_at_ms=NOW+2000,
        )
        save_new_snapshot(self.directory, snapshot)
        self.current = payload(
            [item(s) for s in SYMBOLS] + [item("NEWTOKENUSDT")],
            at=NOW+3500,
        )
        self.pool = screen_bybit_usdt_perps_offline(
            instrument_pages=(self.current,), requested_cursors=(None,),
            page_received_at_ms=(NOW+4000,), observed_at_ms=NOW+4000,
        )

    def read(self):
        return reconcile_auto_pool_with_private_census(
            self.pool, self.directory, allow_private_readonly_audit=True,
            owner_ok=True,
        )

    def test_real_sqlite_join_uses_veto_no_recapture_and_never_promotes(self):
        original = self.file.read_bytes()
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP")):
            result = self.read()
        self.assertEqual(result["status"],
                         "retrospective_auto_crypto_usdt_overlap_research_only")
        self.assertEqual(result["d256_sqlite_completed_contracts"], 60)
        self.assertEqual(result["d264_persisted_tradfi_negative_vetoes_applied"], 1)
        self.assertEqual(result["today_provisional_pool_contracts"], 61)
        self.assertEqual(result["today_candidates_not_in_frozen_catalog"], 1)
        self.assertEqual(result["retrospective_candidates_after_veto"], 60)
        self.assertEqual(result["complete_24h_positive_turnover_overlap"], 59)
        self.assertEqual(result["incomplete_or_unavailable_24h_candidates"], 1)
        self.assertEqual(result["retrospective_top50_research_size"], 50)
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["historical_pit_crypto_identity_verified"])
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(self.file.read_bytes(), original)
        self.assertNotIn("NEWTOKENUSDT", json.dumps(result))

    def test_optin_denied_before_sqlite(self):
        with patch("sqlite3.connect", side_effect=AssertionError("DB")):
            result = reconcile_auto_pool_with_private_census(
                self.pool, self.directory, owner_ok=True)
        self.assertEqual(result["status"], "owner_optin_required")

    def test_corrupt_existing_sqlite_abstains(self):
        import sqlite3
        with sqlite3.connect(self.file) as db:
            db.execute("UPDATE candles SET quote_turnover='NaN' "
                       "WHERE symbol='COIN002USDT'")
        self.assertEqual(self.read()["status"], "abstain")

    def test_one_shot_cli_join_is_owner_and_get_only(self):
        old = self.file.read_bytes()
        client = CensusClient(catalog=self.current)
        times = iter((NOW+3000, NOW+4000))
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP")):
            r = observe_current_usdt_perpetuals(
                client=client, now_ms=lambda: next(times),
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                private_directory=self.directory,
                allow_private_readonly_audit=True,
                owner_ok=True,
            )
        self.assertEqual(r["requests_attempted"], 1)
        self.assertEqual(r["network_requests"], 1)
        self.assertEqual(r["retrospective_private_join"]["network_requests"], 0)
        self.assertEqual(r["retrospective_private_join"]["retrospective_top50_research_size"], 50)
        self.assertEqual(r["status"], "automatic_usdt_perpetual_research_candidates_only")
        self.assertFalse(r["marketwide_top50_verified"])
        self.assertEqual(old, self.file.read_bytes())

    def test_missing_private_optin_stops_before_provider_get(self):
        c = CensusClient(catalog=self.current)
        r = observe_current_usdt_perpetuals(
            client=c, now_ms=lambda: NOW+4000,
            allow_public_network=True,
            confirm_region_and_personal_research=True,
            private_directory=self.directory, owner_ok=True)
        self.assertEqual(r["failure_code"], "configuration_invalid")
        self.assertEqual(c.requests_attempted, 0)


if __name__ == "__main__":
    unittest.main()
