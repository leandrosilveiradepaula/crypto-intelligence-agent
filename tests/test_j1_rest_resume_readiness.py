"""J1/OPS2 REST owner-only resume: real SQLite, adversaries and fake UTC clock."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_rest_incremental_owner import HOUR_MS, _DB_NAME
from crypto_intelligence_agent.j1_rest_resume_readiness import (
    _next_safe_target, audit_existing_rest_resume,
)
from scripts.audit_bybit_marketwide_closed24h import _digest

D = "a" * 64
INITIAL = (1_794_200_400_000 // HOUR_MS) * HOUR_MS
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SYMBOLS_50 = SYMBOLS + tuple(f"TST{i}USDT" for i in range(48))
DATA = ("1", "2", "1", "2", "20", "40")


def make_journal(path: Path, *, publications: int = 26,
                 initial_publication_offset: int = 0,
                 skip_hour: int | None = 2, halted=None,
                 symbols: tuple[str, ...] = SYMBOLS) -> int:
    """Represent the actual trial: a missing 18:00 publication, not candles.

    Scope at 16:00 and one catch-up across 18:00 gives 100 candles for two
    symbols but only 26 actual publications, with an explicit PIT gap.
    """
    offsets = [initial_publication_offset + i
               for i in range(publications + (1 if skip_hour is not None else 0))
               if initial_publication_offset + i != skip_hour]
    assert len(offsets) == publications
    last = INITIAL + offsets[-1] * HOUR_MS
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE scope (id INTEGER PRIMARY KEY,
               scope_digest TEXT NOT NULL, members_json TEXT NOT NULL,
               initial_end_ms INTEGER NOT NULL, halted_reason TEXT);
            CREATE TABLE cursor (
               symbol TEXT PRIMARY KEY, next_open_ms INTEGER NOT NULL);
            CREATE TABLE candles (
               symbol TEXT NOT NULL, open_ms INTEGER NOT NULL,
               open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL,
               close TEXT NOT NULL, base_volume TEXT NOT NULL,
               quote_turnover TEXT NOT NULL, received_at_ms INTEGER NOT NULL,
               digest_sha256 TEXT NOT NULL,
               PRIMARY KEY(symbol,open_ms));
            CREATE TABLE published_hour (
               end_ms INTEGER PRIMARY KEY, observed_at_ms INTEGER NOT NULL,
               scope_digest TEXT NOT NULL, observed_contracts INTEGER NOT NULL);
        """)
        db.execute("INSERT INTO scope VALUES(1,?,?,?,?)",
                   (D, json.dumps(symbols), INITIAL, halted))
        for symbol in symbols:
            db.execute("INSERT INTO cursor VALUES(?,?)", (symbol,last))
            for opened in range(INITIAL - 24 * HOUR_MS, last, HOUR_MS):
                row = (str(opened), *DATA)
                db.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (symbol, opened, *DATA, last + 60_000,
                            _digest([symbol, row])))
        for offset in offsets:
            end = INITIAL + offset * HOUR_MS
            db.execute("INSERT INTO published_hour VALUES (?,?,?,?)",
                       (end, end+120_000, D, len(symbols)))
    path.chmod(0o600)
    return last


@unittest.skipUnless(os.name == "posix", "private SQLite owner checks require POSIX")
class RestResumeReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name) / "journal"
        self.dir.mkdir(mode=0o700)
        self.dir.chmod(0o700)
        self.path = self.dir / _DB_NAME
        self.last = make_journal(self.path)

    def check(self, delta: int, **kw):
        return audit_existing_rest_resume(
            output_directory=self.dir, now_ms=self.last + delta,
            allow_private_readonly_audit=True, owner_ok=True, **kw,
        )

    def test_actual_trial_shape_100_candles_26_publications_without_forgery(self):
        r=self.check(HOUR_MS+120_000)
        self.assertEqual(r["status"],"historical_checkpoint_gaps_require_review")
        self.assertEqual(r["historical_unpublished_hours"], 1)
        self.assertTrue(r["historical_checkpoint_gaps_present"])
        self.assertTrue(r["journal_integrity_verified"])
        self.assertEqual(r["last_published_end_ms"],self.last)
        self.assertEqual(r["published_hours"],26)
        self.assertEqual(r["stored_candles"],100)
        self.assertEqual(r["reviewed_research_contracts"],2)
        self.assertEqual(r["catchup_hours"],1)
        self.assertEqual(r["unobserved_closed_hours"],0)
        self.assertTrue(r["catchup_within_worker_limit"])
        self.assertFalse(r["activation_authorized"])
        self.assertFalse(r["marketwide_top50_verified"])
        self.assertFalse(r["continuous_collector_verified"])
        self.assertEqual(r["network_requests"],0)
        self.assertEqual(r["database_mutation_statements"],0)
        self.assertFalse(r["orders_sent"])
        self.assertNotIn("BTCUSDT",json.dumps(r))

    def test_50_member_owner_cohort_closed24h_ranking_and_no_top50_claim(self):
        self.path.unlink()
        self.last = make_journal(self.path, symbols=SYMBOLS_50)
        r = self.check(HOUR_MS + 120_000, expected_members=50)
        self.assertEqual(r["status"], "historical_checkpoint_gaps_require_review", r)
        self.assertTrue(r["journal_integrity_verified"])
        self.assertEqual(r["reviewed_research_contracts"], 50)
        self.assertEqual(r["stored_candles"], 2500)
        self.assertEqual(r["published_hours"], 26)
        self.assertEqual(r["research_closed_24h_ranked_contracts"], 50)
        self.assertEqual(len(r["research_closed_24h_rank_digest_sha256"]), 64)
        self.assertEqual(r["research_closed_24h_window_end_ms"], self.last)
        self.assertTrue(r["rank_is_sample_only_not_marketwide"])
        self.assertFalse(r["marketwide_top50_verified"])
        self.assertFalse(r["activation_authorized"])
        self.assertEqual(r["network_requests"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(r))
        self.assertEqual(
            self.check(HOUR_MS+120_000)["status"],
            "journal_unavailable_or_integrity_blocked")
        self.assertEqual(
            self.check(HOUR_MS+120_000, expected_members=50)["research_closed_24h_rank_digest_sha256"],
            r["research_closed_24h_rank_digest_sha256"])
        # The immutable 50-member scope cannot silently masquerade as another cohort.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE scope SET members_json=? WHERE id=1",
                       (json.dumps(SYMBOLS_50[:-1]+("BTCUSDT",)),))
        self.assertFalse(self.check(HOUR_MS+120_000, expected_members=50)
                         ["journal_integrity_verified"])

    def test_invalid_expected_member_count_fails_before_read(self):
        for count in (True, 0, -1, 51, 100, "50"):
            with self.subTest(count=count), patch(
                "sqlite3.connect", side_effect=AssertionError("must not open")
            ):
                r = self.check(HOUR_MS+120_000, expected_members=count)
                self.assertEqual(r["status"], "invalid_configuration")

    def test_initial_publication_at_scope_initial_is_also_supported(self):
        self.path.unlink()
        self.last=make_journal(self.path,initial_publication_offset=0,
                               skip_hour=None)
        r=self.check(HOUR_MS+120_000)
        self.assertEqual(r["status"],"no_gap")
        self.assertEqual(r["stored_candles"],98)
        self.assertEqual(r["published_hours"],26)

    def test_catchup_same_hour_6_hours_exact_48_and_49(self):
        self.assertEqual(self.check(120_000)["catchup_hours"],0)
        self.assertEqual(self.check(HOUR_MS+120_000)["status"],
                         "historical_checkpoint_gaps_require_review")
        r=self.check(6*HOUR_MS+120_000)
        self.assertEqual(r["status"],"catchup_with_unobserved_hours_requires_review")
        self.assertEqual(r["catchup_hours"],6)
        self.assertEqual(r["unobserved_closed_hours"],5)
        self.assertTrue(r["catchup_within_worker_limit"])
        self.assertFalse(r["activation_authorized"])
        r=self.check(48*HOUR_MS+120_000)
        self.assertTrue(r["catchup_within_worker_limit"])
        self.assertEqual(r["catchup_hours"],48)
        r=self.check(49*HOUR_MS+120_000)
        self.assertEqual(r["status"],"catchup_exceeds_48h_blocked")
        self.assertFalse(r["catchup_within_worker_limit"])
        self.assertFalse(r["activation_authorized"])

    def test_safe_utc_target_before_one_minute_and_after_fifteen(self):
        self.assertEqual(_next_safe_target(self.last+20_000),self.last)
        self.assertEqual(_next_safe_target(self.last+60_000),self.last)
        self.assertEqual(_next_safe_target(self.last+900_000),self.last)
        self.assertEqual(_next_safe_target(self.last+900_001),self.last+HOUR_MS)

    def test_latched_immutable_but_never_grants_restart(self):
        self.path.unlink()
        self.last=make_journal(self.path,halted="provider_denied_owner_review")
        r=self.check(HOUR_MS+120_000)
        self.assertEqual(r["status"],"halted_owner_review")
        self.assertTrue(r["journal_integrity_verified"])
        self.assertFalse(r["activation_authorized"])
        self.assertIsNone(r["catchup_hours"])

    def test_proof_never_mutates_bytes_or_accesses_network(self):
        before=self.path.read_bytes()
        with patch("urllib.request.urlopen",side_effect=AssertionError("network")):
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                r=self.check(HOUR_MS+120_000)
        self.assertEqual(r["status"],"historical_checkpoint_gaps_require_review")
        self.assertEqual(self.path.read_bytes(),before)

    def test_reject_missing_ambiguous_and_noncontiguous_publications(self):
        for sql in (
            "DELETE FROM published_hour WHERE end_ms=(SELECT MAX(end_ms) FROM published_hour)",
            "UPDATE published_hour SET observed_contracts=1 WHERE end_ms=(SELECT MAX(end_ms) FROM published_hour)",
            "UPDATE published_hour SET scope_digest='wrong' WHERE end_ms=(SELECT MAX(end_ms) FROM published_hour)",
            "UPDATE published_hour SET observed_at_ms=end_ms WHERE end_ms=(SELECT MAX(end_ms) FROM published_hour)",
            "UPDATE published_hour SET observed_at_ms=end_ms+901000 WHERE end_ms=(SELECT MAX(end_ms) FROM published_hour)",
            "UPDATE candles SET digest_sha256='bad' WHERE rowid=(SELECT MIN(rowid) FROM candles)",
            "DELETE FROM candles WHERE rowid=(SELECT MIN(rowid) FROM candles)",
            "UPDATE cursor SET next_open_ms=next_open_ms-3600000",
            "UPDATE scope SET members_json='[\"BTCUSDT\",\"BTCUSDT\"]'",
            "UPDATE scope SET scope_digest='not-a-sha'",
            "UPDATE scope SET id=2",
        ):
            with self.subTest(sql=sql):
                self.path.unlink()
                self.last=make_journal(self.path)
                with closing(sqlite3.connect(self.path)) as db,db:
                    db.execute(sql)
                self.path.chmod(0o600)
                r=self.check(HOUR_MS+120_000)
                self.assertEqual(r["status"],"journal_unavailable_or_integrity_blocked",r)
                self.assertFalse(r["journal_integrity_verified"])

    def test_denies_symlinks_bad_mode_and_no_optin_without_read(self):
        r=audit_existing_rest_resume(
            output_directory=self.dir,now_ms=self.last+120_000,
            allow_private_readonly_audit=False,
            owner_ok=True)
        self.assertEqual(r["status"],"optin_required")
        with patch("sqlite3.connect",side_effect=AssertionError("DB should not open")):
            r=audit_existing_rest_resume(
                output_directory=self.dir,now_ms=True,
                allow_private_readonly_audit=True,owner_ok=True)
            self.assertEqual(r["status"],"invalid_configuration")
            r=audit_existing_rest_resume(
                output_directory=self.dir,now_ms=self.last+120_000,
                allow_private_readonly_audit=True,owner_ok=False)
            self.assertEqual(r["status"],"owner_required")
        self.path.chmod(0o644)
        self.assertEqual(self.check(HOUR_MS+120_000)["status"],
                         "journal_unavailable_or_integrity_blocked")
        self.path.chmod(0o600)
        fake=self.dir/"symlink.sqlite"
        self.path.rename(fake)
        self.path.symlink_to(fake)
        self.assertEqual(self.check(HOUR_MS+120_000)["status"],
                         "journal_unavailable_or_integrity_blocked")

    def test_historical_result_is_not_continuous_execution(self):
        r=self.check(25*HOUR_MS+120_000)
        self.assertEqual(r["status"],"catchup_with_unobserved_hours_requires_review")
        self.assertFalse(r["continuous_collector_verified"])
        self.assertFalse(r["source_authenticated"])


class PortableReadinessTests(unittest.TestCase):
    def test_no_optin_is_inert_cross_platform(self):
        with patch("sqlite3.connect",side_effect=AssertionError("DB")):
            r=audit_existing_rest_resume(
                output_directory=Path("/nonexistent"),now_ms=0,
                allow_private_readonly_audit=False)
        self.assertEqual(r["status"],"optin_required")


if __name__=="__main__":
    unittest.main()
