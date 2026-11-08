"""D263 offline tests: owner-only negative metadata must never promote crypto."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from scripts.audit_bybit_marketwide_closed24h import HOUR_MS, run_census
from scripts.audit_j1_bybit_current_metadata_negative import (
    _classify, audit_current_metadata,
)

NOW = 1793971800000
END = (NOW // HOUR_MS) * HOUR_MS
MEMBERS = ("BTCUSDT", "SOXLUSDT", "XAUUSDT") + tuple(
    f"COIN{i:03d}USDT" for i in range(57)
)


def provider_catalog():
    records = []
    for symbol in MEMBERS:
        row = {
            "symbol": symbol, "baseCoin": symbol[:-4],
            "contractType": "LinearPerpetual", "status": "Trading",
            "quoteCoin": "USDT", "settleCoin": "USDT",
            "marketRegion": "", "underlyingTicker": "",
        }
        if symbol == "SOXLUSDT":
            row["marketRegion"] = "US"
            row["underlyingTicker"] = "SOXL"
        if symbol == "XAUUSDT":
            row["underlyingTicker"] = "XAU"
        records.append(row)
    return {
        "retCode": 0, "time": NOW - 1000,
        "result": {"category": "linear", "nextPageCursor": "",
                   "list": records},
    }


class FakeClient:
    def __init__(self, payload=None):
        self.payload = payload if payload is not None else provider_catalog()
        self.requests_attempted = 0

    def get(self, url):
        self.requests_attempted += 1
        path = urlsplit(url).path
        if path.endswith("/instruments-info"):
            return json.dumps(self.payload).encode("ascii"), self.payload
        symbol = parse_qs(urlsplit(url).query)["symbol"][0]
        data = {"retCode": 0, "result": {
            "category": "linear", "symbol": symbol,
            "list": [
                [str(END-(i+1)*HOUR_MS), "100", "101", "99",
                 "100", "5", str(120+i)] for i in range(24)
            ],
        }}
        return json.dumps(data).encode("ascii"), data


class D263MetadataNegativeTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix":
            self.skipTest("private SQLite and flock require POSIX owner")
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "research"
        self.db = self.directory / "j1-marketwide-closed24h.sqlite"

    def collect(self):
        return run_census(
            directory=self.directory, now_ms=lambda: NOW,
            client=FakeClient(), max_contracts=60,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True, owner_ok=True,
        )

    def audit(self, client=None, **kwargs):
        clock = iter([NOW - 2000, NOW])
        return audit_current_metadata(
            directory=self.directory,
            client=client if client is not None else FakeClient(),
            now_ms=lambda: next(clock),
            owner_ok=True, allow_public_network=True,
            confirm_region_and_personal_research=True, **kwargs,
        )

    def test_provider_only_retro_negative_no_trading_and_db_unchanged(self):
        self.collect()
        old = self.db.read_bytes()
        report = self.audit()
        self.assertEqual(report["status"], "current_provider_negative_survey_only")
        self.assertEqual(report["current_basic_contract_count"], 60)
        self.assertEqual(report["current_frozen_contract_overlap_count"], 60)
        self.assertEqual(report["current_provider_tradfi_indicator_count"], 2)
        self.assertEqual(report["frozen_overlap_provider_tradfi_indicator_count"], 2)
        self.assertEqual(report["frozen_overlap_documented_tradfi_negative_count"], 2)
        self.assertEqual(report["frozen_overlap_documented_negative_without_provider_indicator_count"], 0)
        self.assertEqual(report["current_possible_crypto_unverified_count"], 58)
        self.assertEqual(report["requests_attempted"], 1)
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["metadata_pit_valid_for_frozen_window"])
        self.assertFalse(report["provider_negative_is_crypto_allowlist"])
        self.assertFalse(report["provider_negative_catalog_complete_for_market"])
        self.assertFalse(report["database_modified"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(self.db.read_bytes(), old)
        self.assertNotIn("SOXLUSDT", json.dumps(report))

    def test_default_off_prevents_any_get(self):
        self.collect()
        client = FakeClient()
        result = audit_current_metadata(
            directory=self.directory, client=client, now_ms=lambda: NOW,
            owner_ok=True,
        )
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "owner_opt_in_required")
        self.assertEqual(result["requests_attempted"], 0)
        self.assertEqual(client.requests_attempted, 0)

    def test_missing_metadata_is_unknown_not_crypto(self):
        payload = provider_catalog()
        payload["result"]["list"][0].pop("marketRegion")
        payload["result"]["list"][0].pop("underlyingTicker")
        result = _classify(payload, frozen_members=frozenset(MEMBERS),
                           captured_at_ms=NOW-2000, received_at_ms=NOW)
        self.assertEqual(result["frozen_overlap_missing_metadata_indicator_count"], 1)
        self.assertFalse(result["provider_negative_is_crypto_allowlist"])

    def test_reject_page_incomplete_duplicate_and_bad_region(self):
        base = provider_catalog()
        for mutation in (
            lambda p: p["result"].update(nextPageCursor="nonempty"),
            lambda p: p["result"]["list"].append(p["result"]["list"][0]),
            lambda p: p["result"]["list"][0].update(marketRegion="UNKNOWN_REGION"),
            lambda p: p["result"]["list"][0].update(underlyingTicker=1),
            lambda p: p.update(time=NOW+1),
            lambda p: p["result"]["list"].pop(),
        ):
            payload = deepcopy(base)
            mutation(payload)
            with self.subTest(payload=payload["result"].get("nextPageCursor")):
                if len(payload["result"]["list"]) == 59 and (
                    payload["result"]["nextPageCursor"] == ""
                ):
                    # A smaller valid full catalog is structurally allowed.
                    continue
                with self.assertRaises(ValueError):
                    _classify(payload, frozen_members=frozenset(MEMBERS),
                              captured_at_ms=NOW-2000, received_at_ms=NOW)

    def test_drift_never_rewrites_frozen_scope(self):
        self.collect()
        old = self.db.read_bytes()
        payload = provider_catalog()
        payload["result"]["list"][3]["symbol"] = "NEWCOINUSDT"
        payload["result"]["list"][3]["baseCoin"] = "NEWCOIN"
        result = self.audit(FakeClient(payload))
        self.assertEqual(result["status"], "current_provider_negative_survey_only")
        self.assertEqual(result["frozen_missing_from_current_count"], 1)
        self.assertEqual(result["current_not_in_frozen_count"], 1)
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertEqual(self.db.read_bytes(), old)

    def test_provider_failure_stops_once_without_retry(self):
        self.collect()
        class Deny(FakeClient):
            def get(self, url):
                self.requests_attempted += 1
                raise ValueError("PRIVATE_SYMBOL_NEVER_LOG")
        c = Deny()
        report = self.audit(c)
        self.assertEqual(report["status"], "abstain")
        self.assertEqual(report["requests_attempted"], 1)
        self.assertEqual(report["failure_stage"], "network")
        self.assertNotIn("PRIVATE_SYMBOL", json.dumps(report))
        self.assertFalse(report["marketwide_top50_verified"])


class D263MetadataParsePortableTests(unittest.TestCase):
    """No owner paths, SQLite, fcntl or HTTP: portable negative classifier."""

    def test_negative_only_and_no_crypto_approval_cross_platform(self):
        payload = provider_catalog()
        report = _classify(
            payload, frozen_members=frozenset(MEMBERS),
            captured_at_ms=NOW - 2000, received_at_ms=NOW,
        )
        self.assertEqual(report["current_provider_tradfi_indicator_count"], 2)
        self.assertEqual(report["frozen_overlap_documented_tradfi_negative_count"], 2)
        self.assertFalse(report["provider_negative_is_crypto_allowlist"])
        self.assertFalse(report["metadata_pit_valid_for_frozen_window"])
        self.assertFalse(report["marketwide_top50_verified"])

    def test_duplicate_cursor_and_invalid_provider_metadata_cross_platform(self):
        for mutation in (
            lambda p: p["result"].update(nextPageCursor="next"),
            lambda p: p["result"]["list"].append(p["result"]["list"][0]),
            lambda p: p["result"]["list"][0].update(marketRegion="BAD"),
            lambda p: p["result"]["list"][0].update(underlyingTicker=123),
            lambda p: p.update(retCode=False),
        ):
            payload = deepcopy(provider_catalog())
            mutation(payload)
            with self.assertRaises(ValueError):
                _classify(
                    payload, frozen_members=frozenset(MEMBERS),
                    captured_at_ms=NOW - 2000, received_at_ms=NOW,
                )


if __name__ == "__main__":
    unittest.main()
