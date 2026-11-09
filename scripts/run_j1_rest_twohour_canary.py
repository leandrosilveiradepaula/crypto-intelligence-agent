"""J1/M3 finite two-closed-hour REST canary; NO timers, trading or default IO."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable

from crypto_intelligence_agent.j1_rest_incremental_owner import (
    HOUR_MS, _DB_NAME, _validate_cursor, run_hourly_once,
)
from scripts.audit_bybit_marketwide_closed24h import _strict_owner

HOUR = HOUR_MS // 1000
START_OFFSET = 120
MAX_SECONDS = 2 * HOUR + 900
_SAFE_FAILURES = frozenset({
    "unsafe_owner_or_optin", "unsafe_output", "unsafe_frozen", "existing_journal",
    "outside_canary_window", "one_shot_failed", "second_hour_not_sequential",
    "sqlite_or_replay_invalid", "unexpected_failure",
})


def _report(status="optin_required", failure=None):
    return {
        "schema_version": "j1-m3-twohour-canary-v1",
        "status": status, "failure_category": failure,
        "rounds_completed": 0, "published_hours": 0,
        "closed_candles": 0, "requests_attempted": 0,
        "two_hour_canary_verified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def _audit(db_path: Path, first_end: int, second_end: int) -> tuple[int, int]:
    # This is deliberately independent of network and runs on the original
    # SQLite file in query-only mode. Verify row digests via shared replay.
    _strict_owner(db_path, directory=False)
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("invalid_sqlite")
        scope = db.execute("SELECT members_json,initial_end_ms,halted_reason FROM scope WHERE id=1").fetchone()
        if scope is None or scope[2] is not None or scope[1] != first_end:
            raise ValueError("invalid_scope")
        members = json.loads(scope[0])
        if not isinstance(members, list) or len(members) != 2 or len(set(members)) != 2:
            raise ValueError("invalid_members")
        published = db.execute(
            "SELECT end_ms,observed_contracts FROM published_hour ORDER BY end_ms"
        ).fetchall()
        if published != [(first_end, 2), (second_end, 2)]:
            raise ValueError("invalid_published_hours")
        for member in members:
            if _validate_cursor(db, member, first_end, second_end) != second_end:
                raise ValueError("invalid_cursor")
        rows = db.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        if rows != 50:
            raise ValueError("invalid_closed_candle_count")
        return len(published), rows


def run_canary(*, frozen: Path, output: Path,
               allow_public_network=False, allow_private_storage=False,
               confirm_region_and_personal_research=False,
               clock: Callable[[], float] = time.time,
               sleep: Callable[[float], None] = time.sleep,
               worker: Callable = run_hourly_once,
               audit: Callable = _audit,
               owner_ok: bool | None = None) -> dict:
    result = _report()
    allowed = (os.name == "posix" and os.getuid() == os.geteuid()
               and os.geteuid() != 0) if owner_ok is None else owner_ok
    if not (allowed and allow_public_network is True
            and allow_private_storage is True
            and confirm_region_and_personal_research is True):
        return result
    if (not isinstance(frozen, Path) or not isinstance(output, Path)
            or not frozen.is_absolute() or not output.is_absolute()
            or frozen == output or frozen in output.parents or output in frozen.parents):
        return _report("abstain", "unsafe_output")
    try:
        _strict_owner(frozen, directory=True)
        _strict_owner(output.parent, directory=True)
        if output.exists() or output.is_symlink():
            return _report("abstain", "existing_journal")
        output.mkdir(mode=0o700)
        _strict_owner(output, directory=True)
        now = clock()
        if not isinstance(now, (int, float)) or not 0 < now < 4_102_444_800:
            return _report("abstain", "outside_canary_window")
        next_end = ((int(now) // HOUR) + 1) * HOUR
        decision_ends = (next_end, next_end + HOUR)
        for i, end in enumerate(decision_ends):
            target = end + START_OFFSET
            delay = target - clock()
            if delay > MAX_SECONDS or delay < -720:
                return {**result, "status": "abstain",
                        "failure_category": "outside_canary_window"}
            if delay > 0:
                sleep(delay)
            now_at_call = clock()
            if not 60 <= now_at_call - end <= 900:
                return {**result, "status": "abstain",
                        "failure_category": "outside_canary_window"}
            response = worker(
                frozen_directory=frozen, output_directory=output,
                max_assets=2, allow_public_network=True,
                allow_private_storage=True,
                confirm_region_and_personal_research=True,
            )
            result["requests_attempted"] += response.get("requests_attempted", 0)
            if response.get("status") != "research_sample_closed_hour_persisted":
                result["status"] = "abstain"
                result["failure_category"] = "one_shot_failed"
                return result
            if response.get("decision_end_ms") != end * 1000:
                result["status"] = "abstain"
                result["failure_category"] = "second_hour_not_sequential"
                return result
            if (response.get("selected_research_contracts") != 2
                    or response.get("contracts_at_decision") != 2):
                result["status"] = "abstain"
                result["failure_category"] = "one_shot_failed"
                return result
            result["rounds_completed"] = i + 1
        try:
            hours, candles = audit(output / _DB_NAME, next_end * 1000,
                                   (next_end + HOUR) * 1000)
        except (OSError, sqlite3.Error, ValueError, TypeError):
            result["status"] = "abstain"
            result["failure_category"] = "sqlite_or_replay_invalid"
            return result
        result["published_hours"] = hours
        result["closed_candles"] = candles
        result["status"] = "two_hour_research_canary_verified"
        result["two_hour_canary_verified"] = True
        return result
    except (OSError, ValueError, TypeError, sqlite3.Error):
        result["status"] = "abstain"
        result["failure_category"] = "unexpected_failure"
        return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frozen-directory", type=Path, required=True)
    p.add_argument("--output-directory", type=Path, required=True)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-private-storage", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = p.parse_args(argv)
    report = run_canary(
        frozen=args.frozen_directory, output=args.output_directory,
        allow_public_network=args.allow_public_network,
        allow_private_storage=args.allow_private_storage,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["two_hour_canary_verified"] else 65


if __name__ == "__main__":
    raise SystemExit(main())
