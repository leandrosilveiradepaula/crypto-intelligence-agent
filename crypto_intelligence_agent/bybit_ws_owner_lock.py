"""J1/OPS3: POSIX owner-only single writer lease for an isolated WS journal.

The lock is advisory and does NOT replace SQLite transactions. This module
opens no network connection and never accesses the private REST raw-pair DB.
A future owner-gated service must hold the lease for its whole collector run.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
from typing import Iterator

from .bybit_closed_stream_cache import SQLiteOfflineClosedStreamJournal
from .market_data import DataGapError, DataValidationError


def _safe_stat(path: Path, *, directory: bool) -> os.stat_result:
    if path.is_symlink():
        raise DataValidationError("WS private journal path is symlink")
    try:
        s = path.lstat()
    except OSError:
        raise DataValidationError("WS private journal not present") from None
    expected_mode = 0o700 if directory else 0o600
    if (s.st_uid != os.getuid()
            or stat.S_IMODE(s.st_mode) != expected_mode
            or (not stat.S_ISDIR(s.st_mode) if directory
                else (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1))):
        raise DataValidationError("WS private journal owner or mode invalid")
    return s


@contextmanager
def exclusive_owner_ws_writer(
    *, journal: SQLiteOfflineClosedStreamJournal,
    allow_private_ws_writer: bool = False,
) -> Iterator[None]:
    """Guard one owner-only WebSocket writer with nonblocking POSIX flock.

    No unlink on release: removing a lockfile opens races between processes.
    Follows no symlink and refuses non-private parent/file/inode replacement.
    On Windows or without explicit opt-in, fails before opening any file.
    """
    if (os.name != "posix" or allow_private_ws_writer is not True
            or type(journal) is not SQLiteOfflineClosedStreamJournal):
        raise DataValidationError("private WS POSIX writer opt-in required")
    path = journal.path
    if not isinstance(path, Path):
        raise DataValidationError("WS journal file path invalid")
    _safe_stat(path.parent, directory=True)
    original = _safe_stat(path, directory=False)
    lock_path = path.with_name(path.name + ".ws-writer.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError:
        raise DataGapError("WS private writer lock open rejected") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise DataGapError("WS private writer lock unsafe")
        from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
        try:
            flock(fd, LOCK_EX | LOCK_NB)
        except OSError:
            raise DataGapError("WS private writer lease already held") from None
        # Verify no file was replaced while obtaining the lock. A symlink,
        # hardlink or changed SQLite inode is never a successful lease.
        again = _safe_stat(path, directory=False)
        lock_now = _safe_stat(lock_path, directory=False)
        if ((original.st_dev, original.st_ino) != (again.st_dev, again.st_ino)
                or (info.st_dev, info.st_ino) != (lock_now.st_dev, lock_now.st_ino)):
            raise DataGapError("WS private writer path changed")
        try:
            yield
        finally:
            flock(fd, LOCK_UN)
    finally:
        os.close(fd)