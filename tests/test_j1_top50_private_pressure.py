"""J1/#319 read-only bridge integration against the existing private census."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_top50_private_pressure import (
    audit_private_top50_pressure,
)
from scripts.audit_bybit_marketwide_closed24h import HOUR_MS, run_census


NOW = 1793971800000
END = NOW // HOUR_MS * HOUR_MS
SYMS = tuple(f"COIN{i:03d}USDT" for i in range(60))


class FakeClient:
    def __init__(self):
        self.requests_attempted = 0

    def get(self, url):
        from urllib.parse import parse_qs, urlsplit
        self.requests_attempted += 1
        p = urlsplit(url)
        if p.path.endswith("/instruments-info"):
            payload = {"retCode": 0, "time": NOW - 1000, "result": {
                "category": "linear", "nextPageCursor": "",
                "list": [
                    {"symbol": s, "baseCoin": s[:-4],
                     "contractType": "LinearPerpetual", "status": "Trading",
                     "quoteCoin": "USDT", "settleCoin": "USDT"}
                    for s in SYMS],
            }}
        else:
            sym = parse_qs(p.query)["symbol"][0]
            payload = {"retCode": 0, "result": {
                "category": "linear", "symbol": sym,
                "list": [[str(END - (i+1)*HOUR_MS), "100", "102", "99",
                          "101", "2", str(100+i)] for i in range(24)],
            }}
        return json.dumps(payload).encode("ascii"), payload


@unittest.skipUnless(os.name == "posix", "owner-only private SQLite test")
class PrivateTop50PressureTests(unittest.TestCase):
    def setUp(self):
        self.t = TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.folder = Path(self.t.name) / "private"
        self.client = FakeClient()

    def collect(self, n=60):
        return run_census(
            directory=self.folder, now_ms=lambda: NOW,
            client=self.client, max_contracts=n,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True, owner_ok=True,
        )

    def read(self, **kwargs):
        return audit_private_top50_pressure(
            self.folder, owner_ok=True,
            allow_private_readonly_audit=True, **kwargs,
        )

    def test_whole_existing_db_produces_review_queue_without_authentication(self):
        self.collect()
        p = self.folder / "j1-marketwide-closed24h.sqlite"
        before = p.read_bytes()
        with patch("urllib.request.urlopen", side_effect=AssertionError("HTTP")):
            report = self.read(include_public_symbols=True)
        self.assertEqual(report["status"], "existing_census_rank_review_queue_unverified")
        self.assertEqual(report["catalog_members"], 60)
        self.assertEqual(report["completed_contracts"], 60)
        self.assertEqual(report["short_contracts"], 0)
        self.assertEqual(report["additional_crypto_reviews_needed_at_least"], 50)
        self.assertEqual(len(report["review_priority_symbols_only"]), 50)
        self.assertEqual(report["unresolved_unmeasured_contracts"], 0)
        self.assertEqual(report["network_requests"], 0)
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["trading_enabled"])
        self.assertEqual(p.read_bytes(), before)

    def test_default_omits_symbols_and_rejects_premature_promotion(self):
        self.collect()
        report = self.read()
        self.assertEqual(report["status"], "existing_census_rank_review_queue_unverified")
        self.assertNotIn("COIN000", json.dumps(report))
        self.assertEqual(report["identity_reviewed_positive_count"], 0)
        self.assertEqual(report["retrospective_negative_auto_promoted_count"], 0)

    def test_partial_census_fail_closed_without_new_requests(self):
        self.collect(n=3)
        attempted = self.client.requests_attempted
        report = self.read()
        self.assertEqual(report["status"], "abstain")
        self.assertEqual(self.client.requests_attempted, attempted)
        self.assertFalse(report["marketwide_top50_verified"])

    def test_tampered_volume_abstains(self):
        self.collect()
        p = self.folder / "j1-marketwide-closed24h.sqlite"
        with sqlite3.connect(p) as db:
            db.execute("UPDATE candles SET quote_turnover='NaN' WHERE symbol=?",
                       (SYMS[0],))
        self.assertEqual(self.read()["status"], "abstain")

    def test_read_requires_optin(self):
        with patch("sqlite3.connect", side_effect=AssertionError("DB")):
            r = audit_private_top50_pressure(self.folder, owner_ok=True)
        self.assertEqual(r["status"], "owner_optin_required")


if __name__ == "__main__":
    unittest.main()
