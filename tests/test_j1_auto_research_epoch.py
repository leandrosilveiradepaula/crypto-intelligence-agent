"""D287 sealed current research Top50 reuses M1 writer; no production changes."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient
from crypto_intelligence_agent.j1_auto_research_epoch import (
    FILE_NAME, HOUR_MS, build_ranked_research_scope, validate_ranked_research_scope,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import (
    _DB_NAME, _frontier,
)
from scripts.run_j1_current_ranked_epoch_once import (
    seal_current_ranked_scope_once, load_private_ranked_scope,
    run_current_ranked_epoch_once,
)

# Use a closed hour before each decision; no fictitious future PIT.
NOW = 1_794_218_520_000
BASE = NOW // HOUR_MS * HOUR_MS
SELECTED = BASE - HOUR_MS
SYMS = ["BTCUSDT", "ETHUSDT"] + [
    "TST" + str(n) + "USDT" for n in range(48)
]


def report(*, members=None):
    names = list(SYMS if members is None else members)
    return {
        "schema_version": "j1-auto-current-closed24h-research-only-v1",
        "status": "current_closed24h_provisional_perpetual_rank_research_only",
        "catalog_census_matches_before_after": True,
        "source_research_only": True,
        "rolling_ticker_volume_used": False,
        "database_modified": False, "network_accessed": True,
        "marketwide_top50_verified": False,
        "current_crypto_identity_independently_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "ranked_research_candidates": 50,
        "complete_closed24h_candidates": 370,
        "decision_closed_hour_end_ms": SELECTED,
        "catalog_pre_observed_at_ms": SELECTED + 70_000,
        "catalog_post_observed_at_ms": SELECTED + 120_000,
        "current_catalog_provisional_candidates": 370,
        "catalog_provisional_pool_digest_sha256": "a" * 64,
        "rank_digest_sha256": "b" * 64,
        "ranked_public_research_symbols_only": names,
    }


def fake_bybit(url, _limit):
    from urllib.parse import parse_qs, urlsplit
    q = parse_qs(urlsplit(url).query)
    symbol, start, hours = q["symbol"][0], int(q["start"][0]), int(q["limit"][0])
    rows = [
        [str(start + i*HOUR_MS), "1", "2", "1", "2", "20", "40"]
        for i in reversed(range(hours))
    ]
    return json.dumps({"retCode": 0, "result": {
        "category": "linear", "symbol": symbol, "list": rows,
    }}).encode("ascii")


class RankedScopeContractTests(unittest.TestCase):
    def test_scope_pinned_and_no_auto_trading(self):
        valid = build_ranked_research_scope(report(), now_ms=BASE+120_000)
        selected, digest = validate_ranked_research_scope(
            valid, now_ms=BASE+120_000, max_assets=50)
        self.assertEqual(selected, tuple(SYMS))
        self.assertEqual(len(digest), 64)
        self.assertEqual(_frontier(valid, now=BASE+120_000, max_assets=50),
                         (tuple(SYMS), digest))
        self.assertFalse(valid["marketwide_top50_verified"])
        self.assertFalse(valid["live_trading_authorized"])
        self.assertFalse(valid["orders_sent"])
        self.assertEqual(valid["closed_hour_end_ms"], SELECTED)

    def test_scope_fails_on_member_tamper_duplicate_staleness_and_bad_provenance(self):
        raw = report()
        for key, value in [
            ("marketwide_top50_verified", True),
            ("catalog_census_matches_before_after", False),
            ("network_accessed", False),
            ("ranked_public_research_symbols_only", SYMS[:49]),
            ("ranked_public_research_symbols_only", SYMS[:49]+["DUOLUSDT"]),
            ("current_catalog_provisional_candidates", 30),
            ("decision_closed_hour_end_ms", SELECTED + 123),
        ]:
            with self.subTest(key=key):
                bad = deepcopy(raw)
                bad[key] = value
                with self.assertRaises(ValueError):
                    build_ranked_research_scope(bad, now_ms=BASE+120_000)
        valid = build_ranked_research_scope(raw, now_ms=BASE+120_000)
        bad = deepcopy(valid)
        bad["ranked_research_symbols_only"][0] = "FAKEUSDT"
        with self.assertRaises(ValueError):
            validate_ranked_research_scope(
                bad, now_ms=BASE+120_000, max_assets=50)
        for period in (49, 50):
            with self.assertRaises(ValueError):
                validate_ranked_research_scope(
                    valid, now_ms=SELECTED + 120_000 + period*HOUR_MS,
                    max_assets=50)
        with self.assertRaises(ValueError):
            validate_ranked_research_scope(valid, now_ms=BASE+120_000, max_assets=2)
        with self.assertRaises(ValueError):
            validate_ranked_research_scope(
                valid, now_ms=SELECTED+110_000, max_assets=50)


@unittest.skipUnless(os.name == "posix", "owner-only private manifest test POSIX")
class RankedScopePrivateOwnerTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.source = root / "capture"
        self.manifest = root / "scope"
        self.output = root / "epoch-journal"
        for p in (self.source, self.manifest, self.output):
            p.mkdir(mode=0o700)
            p.chmod(0o700)
        self.report_path = self.source / "d286-current.json"
        self.save(report())

    def save(self, data):
        self.report_path.write_text(json.dumps(data), encoding="ascii")
        self.report_path.chmod(0o600)

    def seal(self):
        return seal_current_ranked_scope_once(
            report_path=self.report_path,
            scope_directory=self.manifest, now_ms=BASE + 120_000,
            owner_ok=True, allow_private_manifest_write=True,
        )

    def run_epoch(self, delta=0, source=None, *, optin=True, clock=None):
        return run_current_ranked_epoch_once(
            manifest_directory=self.manifest if source is None else source,
            output_directory=self.output, allow_private_manifest_read=optin,
            allow_public_network=optin, allow_private_storage=optin,
            confirm_region_and_personal_research=optin, owner_ok=True,
            clock_ms=(lambda: BASE+120_000+delta) if clock is None else clock,
            client=BoundedBybitPublicClient(transport=fake_bybit),
        )

    def test_once_sealed_is_immutable_owner_private_and_zero_sql_write(self):
        before = self.report_path.read_bytes()
        out = self.seal()
        self.assertEqual(out["status"],
                         "sealed_current_auto_rank_research_scope_only", out)
        self.assertTrue(out["manifest_written"])
        path = self.manifest / FILE_NAME
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.report_path.read_bytes(), before)
        self.assertEqual(load_private_ranked_scope(
            self.manifest, now_ms=BASE+120_000)["scope_digest_sha256"],
            out["scope_digest_sha256"])
        refused = self.seal()
        self.assertEqual(refused["status"], "abstain")
        self.assertFalse(refused["manifest_written"])
        self.assertFalse(refused["database_modified"])
        self.assertFalse(refused["orders_sent"])

    def test_first_50x24_then_next_hour_incremental_and_idempotent(self):
        self.assertEqual(self.seal()["manifest_written"], True)
        first = self.run_epoch()
        self.assertEqual(first["status"], "research_sample_closed_hour_persisted", first)
        self.assertEqual(first["selected_research_contracts"], 50)
        self.assertEqual((first["new_closed_candles"], first["requests_attempted"]),
                         (1200, 50))
        next_hour = self.run_epoch(HOUR_MS)
        self.assertEqual(next_hour["status"], "research_sample_closed_hour_persisted",
                         next_hour)
        self.assertEqual((next_hour["new_closed_candles"],
                          next_hour["requests_attempted"]), (50,50))
        repeated = self.run_epoch(HOUR_MS)
        self.assertEqual(repeated["requests_attempted"], 0)
        self.assertEqual(repeated["new_closed_candles"], 0)
        with closing(sqlite3.connect(self.output / _DB_NAME)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0],
                             1250)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM published_hour").fetchone()[0], 2)
        for x in (first, next_hour, repeated):
            self.assertFalse(x["marketwide_top50_verified"])
            self.assertFalse(x["orders_sent"])
            self.assertFalse(x["live_trading_authorized"])
            self.assertFalse(x["frozen_history_modified"])

    def test_manifest_rotation_requires_new_epoch_not_overwrite(self):
        self.assertTrue(self.seal()["manifest_written"])
        self.assertEqual(self.run_epoch()["status"], "research_sample_closed_hour_persisted")
        scope = load_private_ranked_scope(self.manifest, now_ms=BASE+120_000)
        scope["closed24h_rank_digest_sha256"] = "c" * 64
        from crypto_intelligence_agent.j1_auto_research_epoch import _binding
        scope["scope_digest_sha256"] = _binding(scope)
        (self.manifest / FILE_NAME).write_text(json.dumps(scope), encoding="ascii")
        (self.manifest / FILE_NAME).chmod(0o600)
        failed = self.run_epoch(HOUR_MS)
        self.assertEqual(failed["status"],
                         "research_integrity_or_environment_abstain", failed)
        self.assertEqual(failed["failure_category"],
                         "frozen_scope_changed_requires_new_journal")
        self.assertEqual(failed["requests_attempted"], 0)

    def test_private_report_rejects_bad_mode_duplicate_json_and_path_types(self):
        self.report_path.chmod(0o644)
        self.assertEqual(self.seal()["status"], "abstain")
        self.report_path.chmod(0o600)
        self.report_path.write_text(
            '{"status":"ok","status":"forged"}', encoding="ascii")
        self.assertEqual(self.seal()["status"], "abstain")
        self.assertFalse((self.manifest / FILE_NAME).exists())
        self.save(report())
        missing_type = seal_current_ranked_scope_once(
            report_path=None, scope_directory=self.manifest,
            now_ms=BASE+120_000, allow_private_manifest_write=True,
            owner_ok=True,
        )
        self.assertEqual(missing_type["status"], "abstain")
        self.assertFalse(missing_type["manifest_written"])

    def test_expired_manifest_blocks_new_epoch_run_before_any_get(self):
        self.assertTrue(self.seal()["manifest_written"])
        out = self.run(50*HOUR_MS)
        self.assertEqual(out["status"], "research_integrity_or_environment_abstain")
        self.assertEqual(out["failure_category"],
                         "current_research_scope_provenance_invalid")
        self.assertEqual(out["requests_attempted"], 0)
        self.assertFalse(out["orders_sent"])

    def test_disabled_and_tampered_and_symlink_block_before_any_get(self):
        with patch("sqlite3.connect", side_effect=AssertionError("DB")):
            off = self.run_epoch(optin=False)
        self.assertEqual(off["status"], "owner_optin_required")
        self.assertFalse(off["orders_sent"])
        self.assertEqual(off["network_requests"], 0)
        self.assertTrue(self.seal()["manifest_written"])
        path = self.manifest / FILE_NAME
        data = json.loads(path.read_text())
        data["ranked_research_symbols_only"][0] = "ZZZUSDT"
        path.write_text(json.dumps(data), encoding="ascii")
        path.chmod(0o600)
        wrong = self.run_epoch()
        self.assertEqual(wrong["status"], "research_integrity_or_environment_abstain")
        self.assertEqual(wrong["requests_attempted"], 0)
        path.unlink()
        redirected = self.manifest / "shared.json"
        redirected.write_text("{}", encoding="ascii")
        redirected.chmod(0o600)
        path.symlink_to(redirected)
        denied = self.run_epoch()
        self.assertEqual(denied["status"], "research_integrity_or_environment_abstain")
        self.assertEqual(denied["requests_attempted"], 0)


if __name__ == "__main__":
    unittest.main()
