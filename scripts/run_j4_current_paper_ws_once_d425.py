"""D425: finite public Bybit WS -> EXISTING local AUTO4 PAPER positions.

Never a daemon, live account, exchange order, FILL, native stop, systemd
unit, J1 writer or production release. Explicit opt-in required for private
owner scope read, public market network and synthetic PAPER reservations.
The PAPER directory must be pre-created 0700 and contain pre-existing
paper-positions.sqlite and paper-routes.json, both owner 0600.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    observe_existing_paper_positions_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

_SCHEMA = "j4-current-paper-ws-observation-d425-v1"


def _report(status: str) -> None:
    print(json.dumps({
        "schema_version": _SCHEMA, "status": status,
        "orders_sent": False, "approved_for_live_use": False,
        "signals_authorized": False, "native_stop_verified": False,
    }, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-directory", required=True, type=Path)
    p.add_argument("--private-paper-directory", required=True, type=Path)
    p.add_argument("--seconds", type=int, default=30)
    p.add_argument("--max-frames", type=int, default=100_000)
    p.add_argument("--max-sessions", type=int, default=1)
    p.add_argument("--allow-private-pointer-read", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-personal-readonly-research", action="store_true")
    p.add_argument("--confirm-region-eligible", action="store_true")
    p.add_argument("--allow-synthetic-paper-reservations", action="store_true")
    a = p.parse_args(argv)
    if not all((
        a.allow_private_pointer_read, a.allow_public_websocket,
        a.confirm_personal_readonly_research, a.confirm_region_eligible,
        a.allow_synthetic_paper_reservations,
    )):
        _report("owner_market_and_paper_optin_required")
        return 77
    if (os.name != "posix" or os.geteuid() == 0
            or not a.state_directory.is_absolute()
            or not a.private_paper_directory.is_absolute()
            or type(a.seconds) is not int or not 1 <= a.seconds <= 60
            or type(a.max_frames) is not int
            or not 1 <= a.max_frames <= 100_000
            or type(a.max_sessions) is not int
            or not 1 <= a.max_sessions <= 2):
        _report("private_paper_operator_environment_invalid")
        return 65
    os.umask(0o077)
    try:
        result = observe_existing_paper_positions_once(
            state_directory=a.state_directory,
            private_paper_directory=a.private_paper_directory,
            allow_private_pointer_read=True,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            allow_synthetic_paper_reservations=True,
            budget=TickerLeaseBudget(
                max_sessions=a.max_sessions,
                max_frames=a.max_frames,
                max_seconds=a.seconds,
            ),
        )
    except (DataGapError, DataValidationError, OSError, RuntimeError,
            TypeError, ValueError, OverflowError, sqlite3.Error):
        # An exception might follow an already-persisted PAPER intent.
        # Never claim journal rollback or a non-existent FILL.
        _report("private_paper_or_public_market_unavailable_review_journal")
        return 65
    print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                     allow_nan=False))
    # A finite lease never proves protection for every position. Exit 2
    # denotes incomplete observed market health, not a trading failure.
    return (0 if result.get("status") ==
            "finite_paper_lease_completed_with_fresh_scope" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
