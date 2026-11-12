"""J1/D297: SQLite online backup of ONLY the pinned N2 research journal.

Does not alter the source, read credentials, issue network calls or trade.
Creates a new private, owner-only rollback copy through SQLite backup API.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:  # Windows CI imports the module but cannot deploy it.
    pwd = None
import sqlite3
import stat

SRC = Path("/home/cia-probe/agent/j1-rest-m3-20261109/canary/j1-rest-hourly-research.sqlite")
DEST = Path("/home/cia-probe/agent/j1-n50-managed-d296-private/n2-before-cutover.sqlite")


def _private(path: Path, *, directory: bool) -> None:
    if path.is_symlink() or not path.is_absolute():
        raise ValueError("private_path_invalid")
    st = path.lstat()
    if (st.st_uid != os.geteuid()
            or (directory and not stat.S_ISDIR(st.st_mode))
            or (not directory and not stat.S_ISREG(st.st_mode))
            or stat.S_IMODE(st.st_mode) != (0o700 if directory else 0o600)
            or (not directory and st.st_nlink != 1)):
        raise ValueError("owner_or_mode_invalid")


def backup_j1_n2_once(*, allow_owner_readonly_backup: bool = False,
                      owner_ok: bool | None = None,
                      source: Path = SRC, destination: Path = DEST) -> dict:
    result = {
        "schema_version": "j1-n2-owner-backup-before-n50-v1",
        "status": "blocked", "stored_candles": 0,
        "published_checkpoints": 0, "digest_sha256": None,
        "source_modified": False, "trading_enabled": False,
        "orders_sent": False, "network_requests": 0,
    }
    if allow_owner_readonly_backup is not True:
        result["status"] = "optin_required"
        return result
    permitted = ((os.name == "posix" and pwd is not None
                  and os.getuid() == os.geteuid()
                  and os.geteuid() == pwd.getpwnam("cia-probe").pw_uid)
                 if owner_ok is None else owner_ok)
    if permitted is not True or not isinstance(source, Path) or not isinstance(
            destination, Path) or destination == source:
        return result
    pending = destination.with_name("." + destination.name + ".pending")
    try:
        _private(source.parent, directory=True)
        _private(source, directory=False)
        _private(destination.parent, directory=True)
        if destination.exists() or destination.is_symlink() or (
                pending.exists() or pending.is_symlink()):
            return result
        fd = os.open(pending, os.O_RDWR | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True,
                                             timeout=2)) as reader:
                reader.execute("PRAGMA query_only=ON")
                if reader.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("source_integrity_invalid")
                before = (
                    reader.execute("SELECT COUNT(*) FROM candles").fetchone()[0],
                    reader.execute("SELECT COUNT(*) FROM published_hour").fetchone()[0],
                )
                with closing(sqlite3.connect(pending, timeout=2)) as copy:
                    reader.backup(copy, pages=16, sleep=0.05)
            _private(pending, directory=False)
            with closing(sqlite3.connect(pending.as_uri() + "?mode=ro", uri=True)) as verify:
                verify.execute("PRAGMA query_only=ON")
                after = (
                    verify.execute("SELECT COUNT(*) FROM candles").fetchone()[0],
                    verify.execute("SELECT COUNT(*) FROM published_hour").fetchone()[0],
                )
                if (verify.execute("PRAGMA integrity_check").fetchone() != ("ok",)
                        or before != after
                        or before[0] < 100 or before[1] < 26):
                    raise ValueError("backup_integrity_invalid")
            fd = os.open(pending, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            # Backup is independent: source never opened with write permissions.
            digest = sha256(pending.read_bytes()).hexdigest()
            # Atomic create-if-absent: never overwrite another rollback copy.
            os.link(pending, destination, follow_symlinks=False)
            dfd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
            result.update(status="backup_verified", stored_candles=after[0],
                          published_checkpoints=after[1], digest_sha256=digest)
            return result
        finally:
            if pending.exists() and not pending.is_symlink():
                pending.unlink()
    except (OSError, PermissionError, sqlite3.Error, ValueError, TypeError):
        return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-owner-readonly-backup", action="store_true")
    opts = vars(p.parse_args(argv))
    report = backup_j1_n2_once(**opts)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "backup_verified" else 65


if __name__ == "__main__":
    raise SystemExit(main())
