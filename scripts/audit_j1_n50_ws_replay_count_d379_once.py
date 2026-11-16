"""Count-only read-only audit of two recent N50 WS closed hours.

No repair, ingestion, SQL writes, network, public market data, or secrets.
An audit of counts does NOT certify provider values or resolved replay conflicts.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, MAX_JOURNAL_ROWS,
)
from crypto_intelligence_agent.j1_n50_ws_epoch_rotation import load_active_n50_ws_epoch

_SCHEMA = "j1-bybit-ws-closed-fixture-v1"


def count_only_hours(path: Path, *, end_ms: int) -> dict:
    """Read exactly one consistent SQLite snapshot; no symbols or market values."""
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.is_file()
            or type(end_ms) is not int or end_ms <= 2 * HOUR_MS
            or end_ms % HOUR_MS):
        raise ValueError("invalid bounded read-only audit input")
    uri = "file:" + quote(path.as_posix(), safe="/") + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
        db.execute("BEGIN")
        ok = db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        meta = db.execute("SELECT value FROM meta WHERE key='schema'").fetchall()
        objects = set(db.execute(
            "SELECT type,name FROM sqlite_master "
            "WHERE type IN ('table','view','trigger')"
        ))
        if not ok or meta != [(_SCHEMA,)] or objects != {
            ("table", "meta"), ("table", "confirmed")
        }:
            raise ValueError("journal structure or integrity invalid")
        total = db.execute("SELECT COUNT(*) FROM confirmed").fetchone()[0]
        markers = db.execute(
            "SELECT COUNT(*) FROM meta WHERE key LIKE 'gap:%'"
        ).fetchone()[0]
        if not 0 <= total <= MAX_JOURNAL_ROWS or not 0 <= markers <= MAX_JOURNAL_ROWS:
            raise ValueError("journal bounded count invalid")
        hours = []
        for hour_end in (end_ms - HOUR_MS, end_ms):
            rows, distinct = db.execute(
                "SELECT COUNT(*),COUNT(DISTINCT symbol) "
                "FROM confirmed WHERE open_ms=?",
                (hour_end - HOUR_MS,),
            ).fetchone()
            if not 0 <= rows <= 50 or distinct != rows:
                raise ValueError("hour count exceeds sealed N50 budget")
            hours.append({
                "closed_hour_end_ms": hour_end,
                "persisted_rows": rows,
                "distinct_contracts": distinct,
            })
        return {
            "schema_version": "j1-n50-ws-replay-count-audit-v1",
            "status": "count_only_not_content_verified",
            "sqlite_integrity_ok": True,
            "journal_rows": total,
            "declared_gap_markers": markers,
            "hours": hours,
            "orders_sent": False,
            "database_modified": False,
            "marketwide_top50_verified": False,
            "approved_for_signals": False,
            "live_trading_authorized": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-directory", type=Path, default=Path(
        "/home/cia-probe/agent/j1-n50-ws-epochs/active"))
    parser.add_argument("--closed-hour-end-ms", type=int, required=True)
    parser.add_argument("--allow-private-owner-read", action="store_true")
    args = parser.parse_args(argv)
    result: dict = {
        "schema_version": "j1-n50-ws-replay-count-audit-v1",
        "status": "owner_audit_unavailable",
        "orders_sent": False,
        "database_modified": False,
    }
    try:
        if (not args.allow_private_owner_read or os.name != "posix"
                or os.getuid() == 0 or os.getuid() != os.geteuid()
                or os.getgid() != os.getegid()
                or not args.state_directory.is_absolute()
                or ".." in args.state_directory.parts):
            raise ValueError("owner gate")
        now_ms = time.time_ns() // 1_000_000
        if (type(args.closed_hour_end_ms) is not int
                or args.closed_hour_end_ms > (now_ms // HOUR_MS) * HOUR_MS
                or now_ms - args.closed_hour_end_ms > 48 * HOUR_MS):
            raise ValueError("clock gate")
        active = load_active_n50_ws_epoch(
            state_directory=args.state_directory,
            current_at_ms=now_ms,
            allow_private_pointer_read=True,
        )
        if active.status != "active_n50_ws_epoch_revalidated" or active.ws_directory is None:
            raise ValueError("active epoch unavailable")
        journal_path = active.ws_directory / "ws-confirmed.sqlite"
        # The existing owner pointer and its DAC protections are checked by
        # load_active_n50_ws_epoch. No file is opened for writing.
        result = count_only_hours(journal_path, end_ms=args.closed_hour_end_ms)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, TypeError, KeyError):
        pass  # Always suppress private paths and raw database exceptions.
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "count_only_not_content_verified" else 65


if __name__ == "__main__":
    raise SystemExit(main())
