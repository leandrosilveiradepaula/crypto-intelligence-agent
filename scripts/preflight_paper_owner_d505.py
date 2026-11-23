"""D505: read-only owner rehearsal of a PAPER code cutover.

Read exactly the existing owner policy and financial journals using the
D453/D487/D502 readers. No service restart, network, file creation, order
submission, policy write, login or new research session. Exit nonzero on any
inconsistency so a deployment gate never mistakes an offline unit test for
a verified readback of the operator's actual private journal.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import OwnerPaperPositionsUnavailable
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _private_directory
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy
from scripts.serve_paper_profile_lab_d487 import (
    _paper_session_read, _paper_history_page,
)

_SCHEMA = "d505-paper-owner-readonly-preflight-v1"


def preflight_paper_owner(*, paper_directory: Path, policy_file: Path) -> dict:
    """Return only aggregate facts; never expose IDs, symbols, paths or prices."""
    if os.name != "posix" or os.geteuid() == 0:
        raise DataValidationError("D505 requires unprivileged POSIX owner")
    _private_directory(paper_directory)
    policy = read_owner_paper_policy(policy_file)
    session = _paper_session_read(directory=paper_directory)
    if (session.get("status") != "paper_journal_readback"
            or session.get("orders_sent") is not False
            or type(session.get("position_count")) is not int
            or type(session.get("open_position_count")) is not int
            or type(session.get("closed_position_count")) is not int
            or not 0 <= session["open_position_count"] <= 50
            or session["position_count"] < 1
            or session["position_count"] != (
                session["open_position_count"] +
                session["closed_position_count"]
            )):
        raise DataValidationError("D505 owner PAPER journal count invalid")
    page = _paper_history_page(
        directory=paper_directory, offset=0, limit=25,
    )
    if (page.get("schema_version") != "d502-owner-paper-history-page-v1"
            or page.get("orders_sent") is not False
            or page.get("position_count") != session["position_count"]
            or not 1 <= len(page.get("positions", [])) <= 25
            or any(x.get("real_orders_sent") is not False
                   for x in page["positions"])):
        raise DataValidationError("D505 PAPER history page does not match ledger")
    mode = policy.research.entry_mode
    periods = policy.research.ema_cross_periods
    if (mode not in ("breakout", "ema_cross")
            or (mode == "ema_cross" and periods is None)):
        raise DataValidationError("D505 invalid future PAPER profile")
    return {
        "schema_version": _SCHEMA,
        "status": "private_owner_paper_readback_consistent",
        "current_session_open_positions": session["open_position_count"],
        "current_session_closed_positions": session["closed_position_count"],
        "historical_position_count": session["position_count"],
        "owner_history_page_checked": len(page["positions"]),
        "next_session_entry_mode": mode,
        "next_session_ema_cross_periods": list(periods) if periods else None,
        "broker_execution_verified": False,
        "native_stop_verified": False,
        "orders_sent": False,
        "read_only": True,
        "vps_release_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="D505 verified owner PAPER read-only cutover preflight"
    )
    parser.add_argument("--paper-directory", type=Path, required=True)
    parser.add_argument("--policy-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = preflight_paper_owner(
            paper_directory=args.paper_directory,
            policy_file=args.policy_file,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (DataValidationError, OwnerPaperPositionsUnavailable, OSError,
            ValueError, TypeError, OverflowError):
        print(json.dumps({
            "schema_version": _SCHEMA, "status": "owner_paper_preflight_denied",
            "orders_sent": False, "read_only": True,
            "vps_release_executed": False,
        }, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
