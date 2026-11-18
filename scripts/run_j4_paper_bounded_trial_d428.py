"""D428: bounded, opt-in NONROOT PAPER market observation, not a daemon.

Two to four finite real-public Bybit leases, one existing PAPER journal/router
and lock, no account, private Bybit channel, native stop, FILL or trading.
No installer, timer, infinite loop, production permission or J1 mutation.
Only valid terminal count-only D427 watches are published in owner 0700.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3

from crypto_intelligence_agent.j4_paper_bounded_trial_d428 import (
    PaperTrialBudget, run_bounded_paper_trial,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

_SCHEMA = "j4-bounded-paper-supervision-trial-d428-v1"


def _reject(status: str) -> int:
    print(json.dumps({
        "schema_version": _SCHEMA, "status": status,
        "orders_sent": False, "live_trading_authorized": False,
        "active_position_supervision_verified": False,
        "continuous_24x7_verified": False,
        "approved_for_live_use": False,
    }, sort_keys=True, separators=(",", ":")))
    return 65


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-directory", type=Path, required=True)
    p.add_argument("--private-paper-directory", type=Path, required=True)
    p.add_argument("--paper-watch-directory", type=Path, required=True)
    p.add_argument("--max-leases", type=int, default=3)
    p.add_argument("--lease-seconds", type=int, default=20)
    p.add_argument("--max-total-seconds", type=int, default=90)
    p.add_argument("--max-gap-ms", type=int, default=5_000)
    p.add_argument("--max-frames-per-lease", type=int, default=25_000)
    p.add_argument("--allow-private-pointer-read", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-personal-readonly-research", action="store_true")
    p.add_argument("--confirm-region-eligible", action="store_true")
    p.add_argument("--allow-synthetic-paper-reservations", action="store_true")
    p.add_argument("--allow-multiple-finite-leases", action="store_true")
    p.add_argument("--allow-paper-watch-output", action="store_true")
    a = p.parse_args(argv)
    required = (
        a.allow_private_pointer_read, a.allow_public_websocket,
        a.confirm_personal_readonly_research, a.confirm_region_eligible,
        a.allow_synthetic_paper_reservations,
        a.allow_multiple_finite_leases, a.allow_paper_watch_output,
    )
    if not all(required):
        return _reject("seven_explicit_owner_optins_required")
    if (os.name != "posix" or os.geteuid() == 0
            or not all(v.is_absolute() for v in (
                a.state_directory, a.private_paper_directory,
                a.paper_watch_directory))):
        return _reject("unprivileged_posix_owner_directories_required")
    os.umask(0o077)
    try:
        budget = PaperTrialBudget(
            max_leases=a.max_leases, lease_seconds=a.lease_seconds,
            max_total_seconds=a.max_total_seconds,
            max_interlease_gap_ms=a.max_gap_ms,
            max_frames_per_lease=a.max_frames_per_lease,
        )
        result = run_bounded_paper_trial(
            state_directory=a.state_directory,
            private_paper_directory=a.private_paper_directory,
            watch_directory=a.paper_watch_directory,
            allow_private_pointer_read=True,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            allow_synthetic_paper_reservations=True,
            allow_multiple_finite_leases=True,
            allow_paper_watch_output=True,
            budget=budget,
        )
    except (DataGapError, DataValidationError, OSError,
            TypeError, ValueError, OverflowError, RuntimeError,
            ArithmeticError, sqlite3.Error):
        # After a failure, never assume an AUTO4 reservation was rolled back.
        return _reject("paper_trial_failed_closed_review_existing_journal")
    print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    return 0 if result["status"] == "bounded_trial_completed_no_live_protection" else 2


if __name__ == "__main__":
    raise SystemExit(main())
