"""D257 offline triage tests; no market requests or account connections."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.crypto_asset_registry import registry_sha256
from scripts.audit_bybit_marketwide_closed24h import HOUR_MS, run_census
from scripts.triage_j1_marketwide_identity import (
    REGISTRY_FILE, _rank_with_registry, triage_checkpoint,
)

NOW = 1793971800000
END = NOW // HOUR_MS * HOUR_MS
SYMS = ("BTCUSDT", "ETHUSDT") + tuple(
    f"COIN{i:03d}USDT" for i in range(58)
)


class FakeClient:
    def __init__(self, *, short_count=0):
        self.requests_attempted = 0
        self.short_count = short_count

    def get(self, url):
        self.requests_attempted += 1
        parsed = urlsplit(url)
        if parsed.path.endswith("instruments-info"):
            payload = {
                "retCode": 0, "time": NOW-1000,
                "result": {
                    "category": "linear", "nextPageCursor": "",
                    "list": [
                        {"symbol": s, "baseCoin": s[:-4],
                         "contractType": "LinearPerpetual",
                         "status": "Trading", "quoteCoin": "USDT",
                         "settleCoin": "USDT"} for s in SYMS
                    ],
                },
            }
        else:
            symbol = parse_qs(parsed.query)["symbol"][0]
            index = SYMS.index(symbol)
            rows = [
                [str(END-(i+1)*HOUR_MS), "100", "102", "99",
                 "100", "2", str(3000-index)] for i in range(24)
            ]
            if index >= len(SYMS) - self.short_count:
                rows = rows[:2]
            payload = {"retCode": 0, "result": {
                "category": "linear", "symbol": symbol, "list": rows,
            }}
        return json.dumps(payload).encode("ascii"), payload


class J1D257IdentityTriageTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix":
            self.skipTest("private POSIX owner lock only")
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "owner-research"
        self.dbpath = self.path / "j1-marketwide-closed24h.sqlite"

    def collect(self, *, short=0, size=60):
        return run_census(
            directory=self.path, client=FakeClient(short_count=short),
            now_ms=lambda: NOW, max_contracts=size, owner_ok=True,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
        )

    def triage(self, **kw):
        return triage_checkpoint(
            self.path, **dict({"owner_ok": True}, **kw)
        )

    def fixture_registry(self, *, observed):
        original = json.loads(REGISTRY_FILE.read_text())
        original["observed_at_ms"] = observed
        original["sha256"] = registry_sha256({
            k: v for k, v in original.items() if k != "sha256"
        })
        output = Path(self.tmp.name) / "registry-fixture.json"
        output.write_text(json.dumps(original), encoding="utf-8")
        return output

    def test_stale_registry_is_not_current_identity_and_no_writes(self):
        original = self.collect()
        before = self.dbpath.read_bytes()
        result = self.triage()
        self.assertEqual(result["status"], "identity_review_queue_stale_registry_no_go")
        self.assertEqual(result["historical_registry_assets"], 52)
        self.assertEqual(result["historical_registry_overlap_complete_count"], 2)
        self.assertEqual(result["historical_registry_overlap_top50_subset_count"], 2)
        self.assertEqual(result["identity_review_priority_count"], 58)
        self.assertEqual(result["closed_top50_subset_unmatched_registry_count"], 48)
        self.assertEqual(
            result["closed_top50_subset_digest_sha256"],
            original["top50_complete_subset_digest_sha256"],
        )
        self.assertFalse(result["historical_registry_temporally_usable"])
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["live_identity_approved"])
        self.assertEqual(result["current_eligible_contracts_verified"], 0)
        self.assertEqual(result["requests_attempted"], 0)
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["database_modified"])
        self.assertEqual(self.dbpath.read_bytes(), before)
        self.assertNotIn("BTCUSDT", json.dumps(result))

    def test_negative_tradfi_partition_is_retrospective_only(self):
        from crypto_intelligence_agent.bybit_tradfi_negative_evidence import (
            NEGATIVE_EVIDENCE, classify_retrospective, catalog_digest,
        )
        self.assertEqual(len(NEGATIVE_EVIDENCE), 24)
        self.assertEqual(len(catalog_digest()), 64)
        self.assertEqual(
            classify_retrospective("SOXLUSDT", False),
            "bybit_tradfi_documented_retrospective",
        )
        self.assertEqual(
            classify_retrospective("XAUUSDT", False),
            "bybit_tradfi_documented_retrospective",
        )
        self.assertEqual(
            classify_retrospective("DUOLUSDT", False),
            "bybit_tradfi_documented_retrospective",
        )
        self.assertEqual(
            classify_retrospective("BTCUSDT", True),
            "archived_crypto_reference_only",
        )
        self.assertEqual(
            classify_retrospective("1000PEPEUSDT", False),
            "identity_unresolved",
        )

    def test_negative_evidence_does_not_approve_fixture_marketwide(self):
        self.collect()
        hidden = self.triage()
        visible = self.triage(include_public_symbols=True)
        for result in (hidden, visible):
            self.assertEqual(result["raw_top50_bybit_tradfi_documented_count"], 0)
            self.assertEqual(result["raw_top50_archived_crypto_reference_only_count"], 2)
            self.assertEqual(result["raw_top50_identity_unresolved_count"], 48)
            self.assertFalse(result["negative_evidence_pit_authenticated"])
            self.assertFalse(result["negative_catalog_complete_for_market"])
            self.assertFalse(result["marketwide_top50_verified"])
            self.assertEqual(result["current_eligible_contracts_verified"], 0)
        self.assertNotIn("public_top50_complete_subset_review_only", hidden)
        self.assertEqual(
            visible["public_top50_complete_subset_review_only"][0][
                "retrospective_identity_category"
            ], "archived_crypto_reference_only"
        )
        self.assertEqual(
            visible["public_top50_complete_subset_review_only"][2][
                "retrospective_identity_category"
            ], "identity_unresolved"
        )

    def test_provider_negative_proof_does_not_become_crypto_whitelist(self):
        self.collect()
        with closing(sqlite3.connect(self.dbpath)) as db:
            from scripts.triage_j1_marketwide_identity import _rank_with_registry
            original = json.loads(REGISTRY_FILE.read_text())
            before = _rank_with_registry(
                db, json.dumps(original).encode(), include_public_symbols=True
            )
        self.assertFalse(before["marketwide_top50_verified"])
        self.assertFalse(before["negative_evidence_pit_authenticated"])
        self.assertEqual(
            before["raw_top50_bybit_tradfi_documented_count"] +
            before["raw_top50_archived_crypto_reference_only_count"] +
            before["raw_top50_identity_unresolved_count"],
            50,
        )

    def test_opt_in_public_contract_identifiers_without_financial_values(self):
        self.collect()
        default = self.triage()
        self.assertNotIn("public_top50_complete_subset_review_only", default)
        self.assertNotIn("public_short_history_contracts_review_only", default)

        before = self.dbpath.read_bytes()
        visible = self.triage(include_public_symbols=True)
        ranked = visible["public_top50_complete_subset_review_only"]
        self.assertEqual(len(ranked), 50)
        self.assertEqual([row["rank"] for row in ranked], list(range(1, 51)))
        self.assertEqual(
            sum(row["archived_base_reference_present"] for row in ranked), 2
        )
        self.assertEqual(
            sum(not row["archived_base_reference_present"] for row in ranked), 48
        )
        self.assertEqual(visible["public_short_history_contracts_review_only"], [])
        self.assertEqual(visible["requests_attempted"], 0)
        self.assertFalse(visible["network_accessed"])
        self.assertFalse(visible["database_modified"])
        self.assertFalse(visible["marketwide_top50_verified"])
        self.assertNotIn("quote_turnover", json.dumps(visible))
        self.assertEqual(self.dbpath.read_bytes(), before)

    def test_public_contract_ids_require_explicit_boolean(self):
        self.collect(size=1)
        denied = self.triage(include_public_symbols="yes")
        self.assertEqual(denied["status"], "abstain")
        self.assertEqual(denied["failure_code"], "audit_configuration_invalid")
        self.assertNotIn("public_top50_complete_subset_review_only", denied)

    def test_opt_in_short_history_ids_not_treated_as_ranked(self):
        self.collect(short=3)
        visible = self.triage(include_public_symbols=True)
        ranked = visible["public_top50_complete_subset_review_only"]
        short = visible["public_short_history_contracts_review_only"]
        self.assertEqual(len(ranked), 50)
        self.assertEqual(len(short), 3)
        self.assertFalse(set(short) & {r["symbol"] for r in ranked})
        self.assertEqual(visible["incomplete_24h_contracts"], 3)
        self.assertFalse(visible["full_basic_contract_24h_ranking_complete"])

    def test_short_three_are_preserved_and_not_ranked(self):
        collected = self.collect(short=3)
        report = self.triage()
        self.assertEqual(report["status"], "identity_review_queue_stale_registry_no_go")
        self.assertEqual(report["complete_24h_contracts"], 57)
        self.assertEqual(report["incomplete_24h_contracts"], 3)
        self.assertEqual(report["incomplete_24h_rows"], 6)
        self.assertEqual(report["historical_registry_overlap_incomplete_count"], 0)
        self.assertEqual(report["identity_review_priority_count"], 55)
        self.assertFalse(report["full_basic_contract_24h_ranking_complete"])
        self.assertEqual(
            report["closed_top50_subset_digest_sha256"],
            collected["top50_complete_subset_digest_sha256"],
        )

    def test_future_registry_does_not_backdate_into_census(self):
        self.collect()
        future = self.fixture_registry(observed=END + 60_000)
        output = self.triage(registry_path=future)
        self.assertFalse(output["historical_registry_known_at_window"])
        self.assertFalse(output["historical_registry_temporally_usable"])
        self.assertEqual(output["current_eligible_contracts_verified"], 0)
        self.assertFalse(output["marketwide_top50_verified"])

    def test_fresh_registry_fixture_still_not_a_marketwide_approval(self):
        self.collect()
        fresh = self.fixture_registry(observed=END - HOUR_MS)
        result = self.triage(registry_path=fresh)
        self.assertTrue(result["historical_registry_known_at_window"])
        self.assertTrue(result["historical_registry_temporally_usable"])
        self.assertEqual(result["historical_registry_overlap_complete_count"], 2)
        self.assertEqual(result["current_eligible_contracts_verified"], 0)
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["closed_24h_rank_promoted"])

    def test_missing_or_tampered_registry_is_fail_closed(self):
        self.collect()
        unknown = Path(self.tmp.name) / "missing.json"
        self.assertEqual(self.triage(registry_path=unknown)["status"], "abstain")
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text('{"assets":[],"sha256":"invalid"}', encoding="utf-8")
        output = self.triage(registry_path=bad)
        self.assertEqual(output["status"], "abstain")
        self.assertEqual(output["requests_attempted"], 0)

    def test_storage_integrity_failure_blocks_priority_queue(self):
        self.collect()
        with closing(sqlite3.connect(self.dbpath)) as db, db:
            db.execute("UPDATE candles SET quote_turnover='NaN' WHERE symbol=?", (SYMS[0],))
        output = self.triage()
        self.assertEqual(output["status"], "abstain")
        self.assertEqual(output["failure_stage"], "sqlite_replay")
        self.assertFalse(output["marketwide_top50_verified"])

    def test_partial_census_abstains_without_ranking(self):
        self.collect(size=4)
        output = self.triage()
        self.assertEqual(output["status"], "abstain")
        self.assertEqual(output["failure_code"], "survey_not_fully_inspected")

    def test_owner_denial_or_symlink_fails_closed(self):
        self.assertEqual(self.triage(owner_ok=False)["failure_code"], "owner_gate_required")
        outside = Path(self.tmp.name) / "other"
        outside.mkdir(mode=0o700)
        self.path.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.triage()["status"], "abstain")


if __name__ == "__main__":
    unittest.main()
