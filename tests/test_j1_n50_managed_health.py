"""D299 owner N50 health: counts only, no fake PIT, offline real file modes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import (
    SCHEMA, STATUS, FILE_NAME, HOUR_MS, _binding,
)
from crypto_intelligence_agent.j1_n50_managed_cycle import (
    ACTIVE_FILE, ACTIVE_SCHEMA, _pointer_write,
)
from scripts.audit_j1_n50_managed_epochs import audit_managed_n50_epochs

T = 1_800_000_000_000 // HOUR_MS * HOUR_MS


def synthetic_scope(end: int) -> dict:
    obj = {
        "schema_version":SCHEMA, "status":STATUS,
        "closed_hour_end_ms":end,
        "catalog_pre_observed_at_ms":end+65_000,
        "catalog_post_observed_at_ms":end+120_000,
        "pool_candidate_count":370,
        "candidate_pool_digest_sha256":"b"*64,
        "closed24h_rank_digest_sha256":"c"*64,
        "ranked_research_symbols_only":[f"TST{i:02d}USDT" for i in range(50)],
        "scope_digest_sha256":"",
        "provisional_research_only":True,
        "marketwide_top50_verified":False,
        "independent_crypto_identity_verified":False,
        "live_trading_authorized":False, "orders_sent":False,
    }
    obj["scope_digest_sha256"] = _binding(obj)
    return obj


def valid_audit(end: int, digest: str, candles: int = 1200) -> dict:
    return {
        "journal_integrity_verified":True,
        "journal_scope_digest_sha256":digest,
        "reviewed_research_contracts":50,
        "orders_sent":False,"live_trading_authorized":False,
        "marketwide_top50_verified":False,
        "stored_candles":candles, "published_hours":1,
        "last_published_end_ms":end,
    }


@unittest.skipUnless(os.name=="posix", "0700/0600 owner-only POSIX tests")
class N50ManagedHealthTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "root"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        for part in ("lease", "epochs"):
            d = self.root / part
            d.mkdir(mode=0o700)
            d.chmod(0o700)

    def make_epoch(self, decision=T, pubs=(T + HOUR_MS,), active=True):
        name=f"epoch-{decision:013d}"
        epoch=self.root / "epochs" / name
        epoch.mkdir(mode=0o700)
        epoch.chmod(0o700)
        scope_dir=epoch/"scope"
        journal=epoch/"journal"
        for d in (scope_dir, journal):
            d.mkdir(mode=0o700)
            d.chmod(0o700)
        manifest=synthetic_scope(decision)
        p=scope_dir/FILE_NAME
        p.write_text(json.dumps(manifest),encoding="ascii")
        p.chmod(0o600)
        if pubs is not None:
            db=journal/"j1-rest-hourly-research.sqlite"
            with sqlite3.connect(db) as handle:
                handle.execute("CREATE TABLE published_hour(end_ms INTEGER)")
                handle.executemany("INSERT INTO published_hour VALUES (?)",
                                   [(x,) for x in pubs])
            db.chmod(0o600)
        if active:
            ptr={
                "schema_version":ACTIVE_SCHEMA,
                "epoch_id":name,
                "scope_digest_sha256":manifest["scope_digest_sha256"],
                "catalog_post_observed_at_ms":decision+120_000,
            }
            _pointer_write(self.root,ptr,decision=decision)
        return manifest,journal

    def inspect(self, now=T+HOUR_MS+180_000, **over):
        opts = {
            "root_directory":self.root,
            "owner_ok":True,
            "allow_private_readonly_audit":True,
            "now_ms":now,
        }
        opts.update(over)
        return audit_managed_n50_epochs(**opts)

    def test_optin_required_before_any_private_read(self):
        with patch("scripts.audit_j1_n50_managed_epochs._pointer_read",
                   side_effect=AssertionError("private pointer read")):
            out = self.inspect(allow_private_readonly_audit=False)
        self.assertEqual(out["status"],"optin_required")
        self.assertFalse(out["owner_integrity_verified"])
        self.assertFalse(out["continuous_collector_verified"])
        self.assertEqual(out["network_requests"],0)

    def test_before_capture_and_after_capture_without_journal(self):
        out=self.inspect()
        self.assertEqual(out["status"],"awaiting_first_epoch")
        self.assertEqual(out["epoch_count"],0)
        m,j=self.make_epoch(pubs=None)
        out=self.inspect()
        self.assertEqual(out["status"],"awaiting_first_writer",out)
        self.assertEqual(out["epoch_count"],1)
        self.assertFalse(out["owner_integrity_verified"])
        self.assertEqual(out["published_checkpoints"],0)

    def test_one_valid_real_pit_does_not_claim_24h(self):
        m,j=self.make_epoch()
        with patch("scripts.audit_j1_n50_managed_epochs.audit_existing_rest_resume",
                   return_value=valid_audit(T+HOUR_MS,m["scope_digest_sha256"])) as audit:
            out=self.inspect()
        self.assertEqual(out["status"],"verified_epoch_history",out)
        self.assertEqual((out["audited_journals"],out["stored_candles"],
                          out["unique_published_utc_hours"]),(1,1200,1))
        self.assertEqual(out["published_last_24_closed_hours"],1)
        self.assertEqual(out["missing_hours_between_publications"],0)
        self.assertTrue(out["owner_integrity_verified"])
        self.assertFalse(out["continuous_collector_verified"])
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertFalse(out["orders_sent"])
        self.assertNotIn("USDT",json.dumps(out))
        self.assertEqual(audit.call_args.kwargs["expected_members"],50)

    def test_stale_active_publication_is_not_healthy(self):
        m,j=self.make_epoch()
        with patch("scripts.audit_j1_n50_managed_epochs.audit_existing_rest_resume",
                   return_value=valid_audit(T+HOUR_MS,m["scope_digest_sha256"])):
            out=self.inspect(now=T+5*HOUR_MS+180_000)
        self.assertEqual(out["status"],"stale_active_publication",out)
        self.assertTrue(out["owner_integrity_verified"])
        self.assertGreaterEqual(out["latest_published_age_hours"],4)

    def test_gap_not_forged_and_scope_drift_denied(self):
        m,j=self.make_epoch(pubs=[T+HOUR_MS,T+3*HOUR_MS])
        fake=valid_audit(T+3*HOUR_MS,m["scope_digest_sha256"],1300)
        fake["published_hours"]=2
        with patch("scripts.audit_j1_n50_managed_epochs.audit_existing_rest_resume",
                   return_value=fake):
            out=self.inspect(now=T+3*HOUR_MS+180_000)
        self.assertEqual(out["status"],"verified_with_missing_pit",out)
        self.assertEqual(out["missing_hours_between_publications"],1)
        self.assertEqual(out["published_checkpoints"],2)
        bad=dict(fake,journal_scope_digest_sha256="f"*64)
        with patch("scripts.audit_j1_n50_managed_epochs.audit_existing_rest_resume",
                   return_value=bad):
            self.assertEqual(self.inspect(now=T+3*HOUR_MS+180_000)["status"],
                             "blocked")

    def test_owner_failure_symlink_and_tamper_fail_closed(self):
        m,j=self.make_epoch()
        db=j/"j1-rest-hourly-research.sqlite"
        db.unlink()
        db.symlink_to(self.root/ACTIVE_FILE)
        self.assertEqual(self.inspect()["status"],"blocked")
        db.unlink()
        with sqlite3.connect(db) as handle:
            handle.execute("CREATE TABLE published_hour(end_ms INTEGER)")
            handle.execute("INSERT INTO published_hour VALUES (?)",(T+HOUR_MS,))
        db.chmod(0o600)
        with patch("scripts.audit_j1_n50_managed_epochs.audit_existing_rest_resume",
                   return_value={"journal_integrity_verified":False}):
            self.assertEqual(self.inspect()["status"],"blocked")

    def test_wrong_epoch_and_bogus_pointer_block_without_network(self):
        m,j=self.make_epoch()
        pointer=self.root/ACTIVE_FILE
        p=json.loads(pointer.read_text())
        p["scope_digest_sha256"]="0"*64
        pointer.write_text(json.dumps(p),encoding="ascii")
        pointer.chmod(0o600)
        with patch("scripts.audit_j1_n50_managed_epochs.audit_existing_rest_resume",
                   side_effect=AssertionError("must not read db")):
            self.assertEqual(self.inspect()["status"],"blocked")


if __name__ == "__main__":
    unittest.main()
