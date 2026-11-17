"""Probe public Bybit ticker WS using current J1 owner N50, not hand-typed rank.

No daemon, order, account endpoint, new ranker, J1 writer or JSON of symbols.
J1 protected scope stays read-only and requires its existing owner UID and
all explicit market/research/region opt-ins. A pilot lasts at most 60s.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j2_current_j1_n50_public_scope_d406 import (
    probe_current_j1_n50_ws_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-directory", type=Path, required=True)
    p.add_argument("--positions", default="",
                   help="Optional owner-reviewed symbols of PAPER positions outside N50")
    p.add_argument("--seconds", type=int, default=20)
    p.add_argument("--allow-private-pointer-read", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-personal-readonly-research", action="store_true")
    p.add_argument("--confirm-region-eligible", action="store_true")
    a = p.parse_args(argv)
    if not (a.allow_private_pointer_read and a.allow_public_websocket
            and a.confirm_personal_readonly_research and a.confirm_region_eligible):
        print(json.dumps({
            "schema_version": "j2-current-owner-n50-ws-probe-d406-v1",
            "status": "owner_scope_and_public_ws_optin_required",
            "private_state_read": False,
            "network_attempted": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }, sort_keys=True))
        return 77
    try:
        out = probe_current_j1_n50_ws_once(
            state_directory=a.state_directory,
            allow_private_pointer_read=True,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            position_symbols=(tuple(a.positions.split(",")) if a.positions else ()),
            seconds=a.seconds,
        )
    except (DataValidationError, DataGapError, OSError, RuntimeError, ImportError,
            ValueError, TypeError):
        print(json.dumps({
            "schema_version": "j2-current-owner-n50-ws-probe-d406-v1",
            "status": "owner_n50_or_market_data_unavailable",
            "verified_current_cohort": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }, sort_keys=True))
        return 65
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    return (0 if out.get("real_market_frames_verified") is True
            and out.get("finite_coverage_observed_once") is True
            and out.get("finite_coverage_fresh_at_end") is True else 2)


if __name__ == "__main__":
    raise SystemExit(main())
