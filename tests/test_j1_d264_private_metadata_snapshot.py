"""D264: owner-private current negative capture, no-clobber and offline replay."""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlsplit, parse_qs

from scripts.audit_bybit_marketwide_closed24h import HOUR_MS, run_census
from scripts.audit_j1_bybit_current_metadata_negative import audit_current_metadata
from scripts.j1_d264_private_metadata_snapshot import (
    FILE_NAME, _default, build_snapshot, validate_snapshot,
    replay_private_snapshot,
)

NOW = 1793971800000
END = NOW // HOUR_MS * HOUR_MS
SYMS = ("BTCUSDT", "SOXLUSDT", "XAUUSDT") + tuple(
    f"COIN{i:03d}USDT" for i in range(57)
)


def catalog():
    rows = []
    for sym in SYMS:
        row = {
            "symbol": sym, "baseCoin": sym[:-4],
            "contractType": "LinearPerpetual", "status": "Trading",
            "quoteCoin": "USDT", "settleCoin": "USDT",
            "marketRegion": "", "underlyingTicker": "",
        }
        if sym == "SOXLUSDT":
            row["marketRegion"] = "US"
            row["underlyingTicker"] = "SOXL"
        if sym == "XAUUSDT":
            row["underlyingTicker"] = "XAU"
        rows.append(row)
    return {"retCode": 0, "time": NOW-1000,
            "result": {"category": "linear", "nextPageCursor": "",
                       "list": rows}}


class FakeClient:
    def __init__(self, payload=None):
        self.payload = payload if payload is not None else catalog()
        self.requests_attempted = 0

    def get(self, url):
        self.requests_attempted += 1
        if urlsplit(url).path.endswith("instruments-info"):
            return json.dumps(self.payload).encode(), self.payload
        sym = parse_qs(urlsplit(url).query)["symbol"][0]
        bars = [[str(END-(i+1)*HOUR_MS), "100", "101", "99", "100",
                 "5", str(120+i)] for i in range(24)]
        response = {"retCode": 0, "result": {"category": "linear",
                                             "symbol": sym, "list": bars}}
        return json.dumps(response).encode(), response


class D264PortableTests(unittest.TestCase):
    def test_build_and_validate_minimal_negative_only(self):
        manifest = build_snapshot(
            catalog(), frozen_members=frozenset(SYMS),
            frozen_end_ms=END, captured_at_ms=NOW-2000,
            received_at_ms=NOW,
        )
        self.assertEqual(manifest["current_provider_negative_symbols"],
                         ["SOXLUSDT", "XAUUSDT"])
        self.assertEqual(manifest["current_metadata_missing_fields_symbols"], [])
        self.assertFalse(manifest["frozen_pit_authenticated"])
        self.assertFalse(manifest["marketwide_top50_verified"])
        self.assertEqual(len(manifest["sha256"]), 64)
        self.assertEqual(validate_snapshot(
            manifest, frozen_members=frozenset(SYMS),
            frozen_end_ms=END), manifest)

    def test_manipulations_and_missing_scope_veto(self):
        manifest = build_snapshot(
            catalog(), frozen_members=frozenset(SYMS),
            frozen_end_ms=END, captured_at_ms=NOW-2000,
            received_at_ms=NOW,
        )
        for field, value in (
            ("sha256", "0"*64),
            ("frozen_pit_authenticated", True),
            ("marketwide_top50_verified", True),
            ("frozen_window_end_ms", NOW),
            ("current_provider_negative_symbols", ["SOXLUSDT", "SOXLUSDT"]),
            ("current_provider_negative_symbols", ["EVILUSDT"]),
        ):
            altered = deepcopy(manifest)
            altered[field] = value
            with self.subTest(field=field, value=str(value)[:20]):
                with self.assertRaises(ValueError):
                    validate_snapshot(altered, frozen_members=frozenset(SYMS),
                                      frozen_end_ms=END)
        with self.assertRaises(ValueError):
            build_snapshot(catalog(), frozen_members=frozenset(SYMS),
                           frozen_end_ms=NOW, captured_at_ms=NOW-2000,
                           received_at_ms=NOW)

    def test_provider_churn_is_not_retroactively_inserted(self):
        changed = catalog()
        changed["result"]["list"][4].update(
            symbol="NEWUSDT", baseCoin="NEW")
        with self.assertRaisesRegex(ValueError, "d264_scope_drift_no_snapshot"):
            build_snapshot(changed, frozen_members=frozenset(SYMS),
                           frozen_end_ms=END, captured_at_ms=NOW-2000,
                           received_at_ms=NOW)


class D264PrivateOwnerTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix":
            self.skipTest("private snapshot is POSIX owner-only")
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "research"
        self.database = self.directory / "j1-marketwide-closed24h.sqlite"

    def setup_census(self):
        result = run_census(
            directory=self.directory, client=FakeClient(),
            now_ms=lambda: NOW, max_contracts=60,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True, owner_ok=True,
        )
        self.assertEqual(result["completed_contracts"], 60)
        return result

    def capture(self, client=None):
        clock = iter([NOW-2000, NOW])
        return audit_current_metadata(
            directory=self.directory, client=client or FakeClient(),
            now_ms=lambda: next(clock), owner_ok=True,
            allow_public_network=True,
            confirm_region_and_personal_research=True,
            save_private_snapshot=True,
        )

    def test_single_get_immutable_capture_then_zero_get_replay(self):
        self.setup_census()
        before = self.database.read_bytes()
        client = FakeClient()
        cap = self.capture(client)
        self.assertEqual(cap["status"], "current_provider_negative_survey_only")
        self.assertTrue(cap["private_snapshot_created"])
        self.assertEqual(client.requests_attempted, 1)
        self.assertEqual(cap["requests_attempted"], 1)
        target = self.directory / FILE_NAME
        self.assertTrue(target.is_file())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        snap = json.loads(target.read_text())
        self.assertEqual(snap["sha256"], cap["private_snapshot_sha256"])
        self.assertEqual(snap["current_provider_negative_symbols"],
                         ["SOXLUSDT", "XAUUSDT"])
        self.assertEqual(self.database.read_bytes(), before)
        proof = replay_private_snapshot(self.directory, owner_ok=True)
        self.assertEqual(proof["status"],
                         "retrospective_negative_overlay_research_only")
        self.assertEqual(proof["frozen_complete_contracts"], 60)
        self.assertEqual(proof["current_provider_negative_count"], 2)
        self.assertEqual(proof["research_frontier_count"], 50)
        sensitivity = proof["conditional_cutoff_sensitivity"]
        self.assertEqual(sensitivity["complete_candle_contracts"], 60)
        self.assertEqual(sensitivity["retrospectively_excluded_complete_contracts"], 2)
        self.assertEqual(sensitivity["scenarios"][0]["replacements_in_top50_count"], 0)
        self.assertNotIn("replacement_symbols_only", sensitivity["scenarios"][0])
        self.assertFalse(sensitivity["marketwide_top50_verified"])
        self.assertTrue(proof["current_provider_negative_exclusions_not_pit"])
        batch = proof["frontier_identity_review_worklist"]
        self.assertEqual(batch["research_frontier_count"], 50)
        self.assertEqual(batch["identity_review_pending_count"], 50)
        self.assertEqual(batch["identity_approved_count"], 0)
        self.assertNotIn("private_research_worklist_only", batch)
        self.assertFalse(batch["marketwide_top50_verified"])
        self.assertFalse(proof["marketwide_top50_verified"])
        self.assertFalse(proof["metadata_pit_valid_for_frozen_window"])
        self.assertFalse(proof["network_accessed"])
        self.assertEqual(proof["requests_attempted"], 0)
        self.assertNotIn("SOXLUSDT", json.dumps(proof))
        self.assertEqual(self.database.read_bytes(), before)

    def test_no_clobber_fail_before_network(self):
        self.setup_census()
        first = self.capture()
        self.assertTrue(first["private_snapshot_created"])
        original = (self.directory / FILE_NAME).read_bytes()
        client = FakeClient()
        second = self.capture(client)
        self.assertEqual(second["status"], "abstain")
        self.assertEqual(second["failure_code"], "d264_snapshot_already_exists")
        self.assertEqual(second["requests_attempted"], 0)
        self.assertEqual(client.requests_attempted, 0)
        self.assertEqual((self.directory / FILE_NAME).read_bytes(), original)

    def test_tampered_private_snapshot_fails_closed_and_no_network(self):
        self.setup_census()
        self.capture()
        target = self.directory / FILE_NAME
        snap = json.loads(target.read_text())
        snap["current_provider_negative_symbols"] = []
        target.write_text(json.dumps(snap))
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        result = replay_private_snapshot(self.directory, owner_ok=True)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "d264_hash_invalid")
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["database_modified"])
        self.assertFalse(result["marketwide_top50_verified"])

    def test_replay_private_symbols_explicit_optin_only(self):
        self.setup_census()
        self.capture()
        default = replay_private_snapshot(self.directory, owner_ok=True)
        optin = replay_private_snapshot(
            self.directory, owner_ok=True, include_private_symbols=True)
        self.assertNotIn("private_research_symbols_only", default)
        self.assertEqual(len(optin["private_research_symbols_only"]), 50)
        ids = [x["symbol"] for x in optin["private_research_symbols_only"]]
        self.assertNotIn("SOXLUSDT", ids)
        self.assertNotIn("XAUUSDT", ids)
        scenarios = optin["conditional_cutoff_sensitivity"]["scenarios"]
        self.assertEqual(len(scenarios), 3)
        self.assertIn("replacement_symbols_only", scenarios[0])
        self.assertFalse(optin["conditional_cutoff_sensitivity"]["marketwide_top50_verified"])
        worklist = optin["frontier_identity_review_worklist"]
        self.assertEqual(worklist["identity_review_pending_count"], 50)
        self.assertEqual(len(worklist["private_research_worklist_only"]), 50)
        self.assertEqual(
            [row["symbol"] for row in worklist["private_research_worklist_only"]],
            ids,
        )
        self.assertTrue(all(
            row["identity_approved"] is False
            for row in worklist["private_research_worklist_only"]
        ))
        self.assertFalse(optin["marketwide_top50_verified"])


if __name__ == "__main__":
    unittest.main()
