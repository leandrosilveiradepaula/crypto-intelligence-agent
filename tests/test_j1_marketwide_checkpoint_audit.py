"""D256: offline private checkpoint audit; no public network or orders."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from scripts.audit_j1_marketwide_checkpoint import audit_private_checkpoint
from scripts.audit_bybit_marketwide_closed24h import HOUR_MS, run_census
from urllib.parse import parse_qs, urlsplit

NOW = 1793971800000
END = NOW // HOUR_MS * HOUR_MS
SYMS = tuple(f"COIN{x:03d}USDT" for x in range(60))


class FakeClient:
    def __init__(self):
        self.requests_attempted = 0

    def get(self, url):
        self.requests_attempted += 1
        parsed = urlsplit(url)
        if parsed.path.endswith("/instruments-info"):
            payload = {"retCode": 0, "time": NOW-1000, "result": {
                "category": "linear", "nextPageCursor": "",
                "list": [
                    {"symbol": s, "baseCoin": s[:-4],
                     "contractType": "LinearPerpetual", "status": "Trading",
                     "quoteCoin": "USDT", "settleCoin": "USDT"}
                    for s in SYMS
                ],
            }}
        else:
            symbol = parse_qs(parsed.query)["symbol"][0]
            payload = {"retCode": 0, "result": {
                "category": "linear", "symbol": symbol,
                "list": [[str(END-(i+1)*HOUR_MS), "100.1", "102", "99",
                          "100.2", "2.0", str(100+i)] for i in range(24)],
            }}
        return json.dumps(payload).encode("ascii"), payload


class ReadonlyCensusProofTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix":
            self.skipTest("owner-only POSIX data store")
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "owner-research"
        self.db_path = self.directory / "j1-marketwide-closed24h.sqlite"

    def collect(self, *, size=5, client=None):
        return run_census(
            directory=self.directory, now_ms=lambda: NOW,
            client=client or FakeClient(), max_contracts=size,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True, owner_ok=True,
        )

    def audit(self, **kw):
        return audit_private_checkpoint(self.directory, **dict({"owner_ok": True}, **kw))

    def test_replay_read_only_no_network_matches_partial_state(self):
        collected = self.collect(size=5)
        before = self.db_path.read_bytes()
        report = self.audit()
        self.assertEqual(report["status"], "basic_survey_partial_integrity_pass_unverified")
        self.assertEqual(report["completed_contracts"], 5)
        self.assertEqual(report["remaining_contracts"], 55)
        self.assertEqual(report["validated_closed_1h_rows"], 120)
        self.assertEqual(report["requests_attempted"], 0)
        self.assertFalse(report["network_accessed"])
        self.assertFalse(report["database_modified"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["request_trace_complete_verified"])
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(report["capture_window_end_ms"], collected["capture_window_end_ms"])

    def test_incomplete_survey_matches_digest_without_promoting_top50(self):
        class ThreeShort(FakeClient):
            def get(self, url):
                from urllib.parse import urlsplit, parse_qs
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    symbol = parse_qs(urlsplit(url).query)["symbol"][0]
                    if symbol in SYMS[:3]:
                        payload["result"]["list"] = payload["result"]["list"][:2]
                return raw, payload

        collected = self.collect(size=60, client=ThreeShort())
        before = self.db_path.read_bytes()
        report = self.audit()
        self.assertEqual(report["status"], "basic_survey_integrity_pass_incomplete_unverified")
        self.assertEqual(report["basic_eligible_contracts"], 60)
        self.assertEqual(report["completed_contracts"], 57)
        self.assertEqual(report["incomplete_24h_contracts"], 3)
        self.assertEqual(report["incomplete_24h_rows"], 6)
        self.assertEqual(report["inspected_contracts"], 60)
        self.assertEqual(report["remaining_contracts"], 0)
        self.assertEqual(report["top50_complete_subset_count"], 50)
        self.assertEqual(
            report["top50_complete_subset_digest_sha256"],
            collected["top50_complete_subset_digest_sha256"],
        )
        self.assertFalse(report["full_basic_contract_24h_ranking_complete"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertNotIn("COIN000", json.dumps(report))

    def test_fully_complete_basic_rank_remains_unverified_crypto(self):
        self.collect(size=60)
        report = self.audit()
        self.assertEqual(report["status"], "basic_rank_integrity_pass_crypto_unverified")
        self.assertTrue(report["full_basic_contract_24h_ranking_complete"])
        self.assertFalse(report["crypto_identity_independently_verified"])
        self.assertFalse(report["marketwide_top50_verified"])

    def test_report_gap_minimum_unattributed_is_60(self):
        self.collect(size=60)
        report = self.audit(previous_inspected=0, last_run_requests=1)
        self.assertEqual(report["minimum_unattributed_inspections"], 60)
        self.assertFalse(report["adjacent_run_counts_consistent"])
        self.assertFalse(report["request_trace_complete_verified"])

    def test_consistent_counts_are_not_proof_of_complete_trace(self):
        self.collect(size=60)
        report = self.audit(previous_inspected=40, last_run_requests=21)
        self.assertEqual(report["minimum_unattributed_inspections"], 0)
        self.assertTrue(report["adjacent_run_counts_consistent"])
        self.assertFalse(report["request_trace_complete_verified"])

    def test_invalid_operator_counts_fail_closed(self):
        self.collect(size=1)
        result = self.audit(previous_inspected=10, last_run_requests=3)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "request_trace_inputs_invalid")
        for kwargs in (
            {"previous_inspected": 0},
            {"previous_inspected": True, "last_run_requests": 10},
            {"previous_inspected": 0, "last_run_requests": 0},
        ):
            self.assertEqual(self.audit(**kwargs)["status"], "abstain")

    def test_malformed_candle_fails_before_rank(self):
        self.collect(size=60)
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("UPDATE candles SET quote_turnover='NaN' WHERE symbol=?", (SYMS[0],))
        result = self.audit()
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_stage"], "sqlite_replay")
        self.assertEqual(result["failure_code"], "stored_candles_invalid")
        self.assertFalse(result["marketwide_top50_verified"])

    def test_invalid_short_digest_fails(self):
        class ShortOne(FakeClient):
            def get(self, url):
                from urllib.parse import urlsplit
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    payload["result"]["list"] = payload["result"]["list"][:2]
                return raw, payload

        self.collect(size=1, client=ShortOne())
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("UPDATE incomplete SET digest_sha256='bad'")
        result = self.audit()
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "stored_shorts_invalid")

    def test_modified_scope_hash_fails(self):
        self.collect(size=1)
        with closing(sqlite3.connect(self.db_path)) as db, db:
            db.execute("UPDATE scope SET scope_sha256='bad'")
        result = self.audit()
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "scope_fingerprint_invalid")

    def test_no_owner_and_symlink_denied(self):
        self.assertEqual(self.audit(owner_ok=False)["failure_code"], "owner_gate_required")
        outside = Path(self.temp.name) / "outside"
        outside.mkdir(mode=0o700)
        self.directory.symlink_to(outside, target_is_directory=True)
        denied = self.audit()
        self.assertEqual(denied["status"], "abstain")
        self.assertEqual(denied["failure_stage"], "private_files")
        self.assertFalse(denied["network_accessed"])


if __name__ == "__main__":
    unittest.main()
