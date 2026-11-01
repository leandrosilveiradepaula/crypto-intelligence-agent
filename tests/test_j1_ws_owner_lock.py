"""J1/OPS3 owner-only POSIX lock: never open network or touch REST SQLite."""
from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import SQLiteOfflineClosedStreamJournal
from crypto_intelligence_agent.bybit_ws_owner_lock import exclusive_owner_ws_writer
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError


@unittest.skipUnless(os.name == "posix", "flock owner-only POSIX research")
class LockTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.root.chmod(0o700)
        self.file = self.root / "ws-fixture.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.file)
        self.file.chmod(0o600)

    def lease(self):
        return exclusive_owner_ws_writer(journal=self.journal,
                                         allow_private_ws_writer=True)

    def test_second_writer_rejected_until_first_releases(self):
        with self.lease():
            with self.assertRaises(DataGapError):
                with self.lease():
                    self.fail("second writer was admitted")
        with self.lease():
            pass
        self.assertTrue(self.file.with_name(self.file.name + ".ws-writer.lock").is_file())

    def test_not_opted_in_never_creates_lock_file(self):
        with self.assertRaises(DataValidationError):
            with exclusive_owner_ws_writer(journal=self.journal):
                pass
        self.assertFalse(self.file.with_name(self.file.name + ".ws-writer.lock").exists())

    def test_unsafe_parent_or_file_mode_rejected(self):
        self.root.chmod(0o755)
        with self.assertRaises(DataValidationError):
            with self.lease(): pass
        self.root.chmod(0o700)
        self.file.chmod(0o644)
        with self.assertRaises(DataValidationError):
            with self.lease(): pass

    def test_symlink_journal_rejected(self):
        link = self.root / "alias.sqlite"
        link.symlink_to(self.file)
        other = SQLiteOfflineClosedStreamJournal(link)
        with self.assertRaises(DataValidationError):
            with exclusive_owner_ws_writer(journal=other,
                    allow_private_ws_writer=True): pass

    def test_hardlink_journal_rejected(self):
        link = self.root / "journal.hardlink.sqlite"
        os.link(self.file, link)
        with self.assertRaises(DataValidationError):
            with self.lease(): pass

    def test_unsafe_lock_mode_and_symlink_rejected(self):
        lock = self.file.with_name(self.file.name + ".ws-writer.lock")
        lock.write_text("", encoding="utf-8")
        lock.chmod(0o644)
        with self.assertRaises(DataGapError):
            with self.lease(): pass
        lock.unlink()
        lock.symlink_to(self.file)
        with self.assertRaises(DataGapError):
            with self.lease(): pass


if __name__ == "__main__":
    unittest.main()