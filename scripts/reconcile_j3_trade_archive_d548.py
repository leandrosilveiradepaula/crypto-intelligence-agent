"""Owner-only comparison of an existing local Bybit daily .csv.gz archive.

No network access, download, extraction to disk, import, or replay.
"""
from __future__ import annotations

import argparse
from datetime import date
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import zlib

from crypto_intelligence_agent.j3_long_history_d528 import DAY, load_plan, read_window
from crypto_intelligence_agent.j3_trade_archive_reconciliation_d548 import (
    MAX_LINE, MAX_ROWS, reconcile_daily_trades,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    _owner_file, _private_directory,
)
from crypto_intelligence_agent.market_data import DataValidationError, MarketDataError
from scripts.run_j3_long_history_d528 import owner_lock

MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
_NAME = re.compile(r"([A-Z0-9]{1,28}USDT)([0-9]{4}-[0-9]{2}-[0-9]{2})\.csv\.gz\Z")


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _bounded_lines(stream):
    total = 0
    while True:
        raw = stream.readline(MAX_LINE + 1)
        if not raw:
            return
        total += len(raw)
        if len(raw) > MAX_LINE or total > MAX_UNCOMPRESSED_BYTES:
            raise DataValidationError("D548 decompressed byte limit")
        yield raw.decode("utf-8", errors="strict")


def _compare(path, reference, symbol, day_start, max_rows):
    parent = _private_directory(path.parent)
    fd = _owner_file(parent, path.name)
    with os.fdopen(fd, "rb") as raw:
        before = os.fstat(raw.fileno())
        if not 1 <= before.st_size <= MAX_COMPRESSED_BYTES:
            raise DataValidationError("D548 compressed byte limit")
        digest = sha256()
        n = 0
        while True:
            chunk = raw.read(1024 * 1024)
            if not chunk:
                break
            n += len(chunk)
            if n > MAX_COMPRESSED_BYTES:
                raise DataValidationError("D548 compressed byte limit")
            digest.update(chunk)
        if n != before.st_size or _identity(os.fstat(raw.fileno())) != _identity(before):
            raise DataValidationError("D548 archive changed")
        raw.seek(0)
        with gzip.GzipFile(fileobj=raw, mode="rb") as gz:
            result = reconcile_daily_trades(
                _bounded_lines(gz), reference, symbol=symbol,
                day_start_ms=day_start, max_rows=max_rows,
            )
        if _identity(os.fstat(raw.fileno())) != _identity(before):
            raise DataValidationError("D548 archive changed")
        result["archive_sha256"] = digest.hexdigest()
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--confirm-personal-readonly-research", action="store_true")
    p.add_argument("--confirm-public-data-rights", action="store_true")
    p.add_argument("--max-rows", type=int, default=MAX_ROWS)
    a = p.parse_args(argv)
    try:
        if not a.confirm_personal_readonly_research or not a.confirm_public_data_rights:
            raise DataValidationError("D548 explicit research authorization required")
        home = _private_directory(a.directory)
        if not home.name.startswith("d528-history") or any(x.startswith("j1-") for x in home.parts):
            raise DataValidationError("D548 research directory required")
        match = _NAME.fullmatch(a.archive.name)
        if match is None or not a.archive.is_absolute():
            raise DataValidationError("D548 archive filename")
        symbol, day_text = match.groups()
        day = date.fromisoformat(day_text)
        start = (day - date(1970, 1, 1)).days * DAY
        if not 1 <= a.max_rows <= MAX_ROWS:
            raise DataValidationError("D548 row limit")
        with owner_lock(home):
            plan = load_plan(home)
            if plan.source_mode != "public_rest_observed_unverified":
                raise DataValidationError("D548 real REST reference required")
            if symbol not in dict(plan.members) or start < dict(plan.members)[symbol] or start + DAY > plan.cutoff_ms:
                raise DataValidationError("D548 day outside eligible reference history")
            reference = read_window(home, plan, symbol, "5m", start, start + DAY, allow_gaps=True)
            result = _compare(a.archive, reference, symbol, start, a.max_rows)
            if load_plan(home).digest != plan.digest:
                raise DataValidationError("D548 plan changed")
            result["plan_sha256"] = plan.digest
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["status"] == "exact_day_match" else 2
    except (MarketDataError, OSError, EOFError, UnicodeError, ValueError,
            ArithmeticError, sqlite3.Error, zlib.error) as exc:
        print(json.dumps({
            "status": "d548_archive_unavailable", "error_type": type(exc).__name__,
            "public_gets": 0, "data_stored": False, "orders_sent": False,
            "profile_modified": False, "source_equivalence_approved": False,
        }, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
