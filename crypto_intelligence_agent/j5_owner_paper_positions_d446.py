"""D446: owner-only readback of actual persistent AUTO4 PAPER positions.

The manifest explicitly selects the positions; the existing J5 inspector
reads them together in one SQLite mode=ro transaction. No network, trading,
new fills, secondary ledger or J1 access. Localhost delivery requires a
separate server opt-in and the same non-root POSIX owner as the journal.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .j4_private_paper_ws_operator_d425 import (
    _private_directory, _owner_file, load_private_paper_routes,
)
from .market_data import DataValidationError
from .paper_position_inspection import inspect_paper_positions
from scripts.inspect_paper_positions import multi_paper_snapshot

_JOURNAL = "paper-positions.sqlite"


class OwnerPaperPositionsUnavailable(Exception):
    """Private source rejected; never expose owner paths or position IDs."""


def read_owner_paper_positions(*, directory: Path) -> dict:
    """Map the existing D425 route manifest to D407's original UI contract."""
    try:
        home = _private_directory(directory)
        router = load_private_paper_routes(home)
        position_ids = router.monitored_position_ids
        if not 1 <= len(position_ids) <= 50:
            raise DataValidationError("D446 explicit PAPER position routes required")
        fd = _owner_file(home, _JOURNAL)
        try:
            opened = os.fstat(fd)
            path = home / _JOURNAL
            if (path.is_symlink()
                    or not stat.S_ISREG(opened.st_mode)
                    or opened.st_uid != os.geteuid()
                    or stat.S_IMODE(opened.st_mode) != 0o600
                    or opened.st_nlink != 1):
                raise DataValidationError("D446 owner journal unsafe")
            selected = inspect_paper_positions(path, position_ids)
            after = os.fstat(fd)
            current = path.lstat()
            # Fail closed when the journal changes during this UI snapshot,
            # including a same-owner replace or symlink swap.
            if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                    or (opened.st_dev, opened.st_ino)
                       != (current.st_dev, current.st_ino)
                    or not stat.S_ISREG(current.st_mode)
                    or path.is_symlink()):
                raise DataValidationError("D446 journal changed during read")
        finally:
            os.close(fd)
        report = multi_paper_snapshot(selected)
        if (report.get("schema_version") != "paper_positions_snapshot_v1"
                or report.get("mode") != "offline_paper"
                or report.get("orders_sent") is not False
                or report.get("live_trading_authorized") is not False
                or report.get("approved_for_live_use") is not False
                or report.get("financial_pnl_available") is not False
                or type(report.get("positions")) is not list
                or len(report["positions"]) != len(position_ids)):
            raise DataValidationError("D446 viewer contract invalid")
        return report
    except (DataValidationError, OSError, UnicodeError, ValueError, TypeError,
            OverflowError):
        raise OwnerPaperPositionsUnavailable("owner_paper_positions_unavailable") from None
