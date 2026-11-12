"""J1/D297 private owner SQLite rollback backup: offline isolated tests."""
from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.backup_j1_n2_before_cutover import backup_j1_n2_once


@unittest.skipUnless(os.name == "posix", "POSIX 0700/0600 owner-only backup")
class N2RollbackSnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.owner_dir = base / "owner-n2"
        self.root = base / "n50-private"
        for d in (self.owner_dir, self.root):
            d.mkdir(mode=0o700)
            d.chmod(0o700)
        self.src = self.owner_dir / "journal.sqlite"
        self.dest = self.root / "n2-before-cutover.sqlite"
        with sqlite3.connect(self.src) as db:
            db.executescript("""
              CREATE TABLE candles (id INTEGER PRIMARY KEY, quote TEXT);
              CREATE TABLE published_hour (end_ms INTEGER PRIMARY KEY);
            """)
            db.executemany("INSERT INTO candles (id, quote) VALUES (?,?)",
                           [(i, "42.00") for i in range(1, 167)])
            db.executemany("INSERT INTO published_hour (end_ms) VALUES (?)",
                           [(i,) for i in range(1, 40)])
        self.src.chmod(0o600)

    def run_backup(self, **kw):
        opts = dict(
            allow_owner_readonly_backup=True, owner_ok=True,
            source=self.src, destination=self.dest,
        )
        opts.update(kw)
        return backup_j1_n2_once(**opts)

    def test_one_owner_backup_is_integral_and_source_unchanged(self):
        source_digest = sha256(self.src.read_bytes()).hexdigest()
        result = self.run_backup()
        self.assertEqual(result["status"], "backup_verified", result)
        self.assertEqual(result["stored_candles"], 166)
        self.assertEqual(result["published_checkpoints"], 39)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(sha256(self.dest.read_bytes()).hexdigest(),
                         result["digest_sha256"])
        self.assertEqual(sha256(self.src.read_bytes()).hexdigest(),
                         source_digest)
        self.assertFalse(result["source_modified"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(result["network_requests"], 0)
        self.assertNotIn("42.00", str(result))

    def test_duplicate_does_not_overwrite_original_copy(self):
        self.assertEqual(self.run_backup()["status"], "backup_verified")
        data = self.dest.read_bytes()
        self.assertEqual(self.run_backup()["status"], "blocked")
        self.assertEqual(self.dest.read_bytes(), data)

    def test_no_optin_and_untrusted_source_fail_closed(self):
        self.assertEqual(self.run_backup(allow_owner_readonly_backup=False)
                         ["status"], "optin_required")
        self.assertFalse(self.dest.exists())
        bad = self.root / "link.sqlite"
        bad.symlink_to(self.src)
        self.assertEqual(self.run_backup(source=bad)["status"], "blocked")
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.run_backup(owner_ok=False)["status"], "blocked")
        self.assertFalse(self.dest.exists())

    def test_link_collision_fails_without_deleting_source_or_destination(self):
        original = sha256(self.src.read_bytes()).hexdigest()
        with patch("scripts.backup_j1_n2_before_cutover.os.link",
                   side_effect=FileExistsError("collision")):
            result = self.run_backup()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(self.root.glob("*.pending")))
        self.assertEqual(sha256(self.src.read_bytes()).hexdigest(), original)

    def test_corrupt_source_rejected(self):
        self.src.write_bytes(b"not a sqlite database")
        self.src.chmod(0o600)
        self.assertEqual(self.run_backup()["status"], "blocked")
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
