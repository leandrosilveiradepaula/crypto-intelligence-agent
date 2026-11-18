"""D418: bounded 60-900s READ-ONLY Bybit public ticker research operator.

No service, account, order, private J1 write or PAPER journal mutation.
Require explicit owner, public network, personal research and region gates.
The result is count-only; exit 0 proves at most a finite complete
observation-once of the current provisional J1 N50, NOT 24x7 or signal health.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j2_n50_sustained_public_operator_d418 import (
    observe_current_n50_sustained_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

_SCHEMA = "j2-current-n50-sustained-market-observation-d418-v1"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-directory", type=Path, required=True)
    p.add_argument("--positions", default="",
                   help="Owner-reviewed existing PAPER symbols outside the N50")
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument("--max-frames", type=int, default=200_000)
    p.add_argument("--max-sessions", type=int, default=2)
    p.add_argument("--allow-private-pointer-read", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-personal-readonly-research", action="store_true")
    p.add_argument("--confirm-region-eligible", action="store_true")
    args = p.parse_args(argv)
    if not all((
        args.allow_private_pointer_read,
        args.allow_public_websocket,
        args.confirm_personal_readonly_research,
        args.confirm_region_eligible,
    )):
        print(json.dumps({
            "schema_version": _SCHEMA,
            "status": "owner_and_public_network_optin_required",
            "private_state_read": False,
            "network_attempted": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }, sort_keys=True))
        return 77
    try:
        report = observe_current_n50_sustained_once(
            state_directory=args.state_directory,
            position_symbols=(
                tuple(args.positions.split(",")) if args.positions else ()
            ),
            allow_private_pointer_read=True,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            seconds=args.seconds,
            max_frames=args.max_frames,
            max_sessions=args.max_sessions,
        )
    except (DataGapError, DataValidationError, OSError, RuntimeError,
            ValueError, TypeError, ImportError):
        print(json.dumps({
            "schema_version": _SCHEMA,
            "status": "owner_scope_or_public_market_unavailable",
            "private_state_modified": False,
            "orders_sent": False,
            "approved_for_signals": False,
            "approved_for_live_use": False,
        }, sort_keys=True))
        return 65
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return (
        0 if report.get("finite_current_owner_scope_observed_once") is True
        and report.get("real_market_frames_verified") is True
        and report.get("owner_scope_unchanged_after_lease") is True
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
