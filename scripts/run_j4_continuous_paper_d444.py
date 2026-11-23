"""D444/D445: run continuing all-held PAPER owner monitor without J1.

No actual orders, fills, API keys, J1 files, live-trading permissions, timer or
production installation. Long-running mode (--max-cycles 0) is explicit opt-in.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal

from crypto_intelligence_agent.j4_continuous_paper_worker_d444 import (
    PaperWorkerPolicy, run_owner_continuous_paper_worker,
)
from crypto_intelligence_agent.market_data import DataValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-paper-directory", type=Path, required=True)
    parser.add_argument("--status-directory", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=0,
                        help="0 = continuing process; positive = finite trial")
    parser.add_argument("--lease-seconds", type=int, default=45)
    parser.add_argument("--max-frames", type=int, default=80000)
    parser.add_argument("--max-consecutive-failures", type=int, default=8)
    for flag in ("allow-public-network", "allow-public-websocket",
                 "confirm-personal-readonly-research",
                 "confirm-region-eligible", "confirm-public-data-rights",
                 "allow-private-paper-reservations", "enable-continuous-worker"):
        parser.add_argument("--" + flag, action="store_true")
    parser.add_argument("--simulate-explicit-demo-exit-fills",
                        action="store_true",
                        help="D483: simulate delayed BBO fills only for the D482 fixture journal")
    a = parser.parse_args(argv)
    gates = (
        a.allow_public_network, a.allow_public_websocket,
        a.confirm_personal_readonly_research, a.confirm_region_eligible,
        a.confirm_public_data_rights, a.allow_private_paper_reservations,
        a.enable_continuous_worker,
    )
    if not all(gates):
        print(json.dumps({
            "status": "explicit_continuous_paper_research_optins_required",
            "network_attempted": False, "orders_sent": False,
        }, sort_keys=True))
        return 77
    try:
        policy = PaperWorkerPolicy(
            max_cycles=a.max_cycles, lease_seconds=a.lease_seconds,
            max_frames=a.max_frames,
            max_consecutive_failures=a.max_consecutive_failures,
        )
    except (DataValidationError, ValueError, TypeError):
        print(json.dumps({"status": "invalid_continuous_worker_policy",
                          "network_attempted": False, "orders_sent": False}))
        return 2
    stopped = {"requested": False}
    def mark_stop(_signum, _frame):
        stopped["requested"] = True
    signal.signal(signal.SIGINT, mark_stop)
    signal.signal(signal.SIGTERM, mark_stop)
    try:
        result = run_owner_continuous_paper_worker(
            private_paper_directory=a.private_paper_directory,
            status_directory=a.status_directory, policy=policy,
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True, confirm_public_data_rights=True,
            allow_private_paper_reservations=True, enable_continuous_worker=True,
            simulate_explicit_demo_exit_fills=a.simulate_explicit_demo_exit_fills,
            should_stop=lambda: stopped["requested"],
        )
    except (DataValidationError, OSError, ValueError, TypeError, RuntimeError):
        # A committed PAPER reservation may survive a failing lease; never
        # claim no network or private-journal side effect on this path.
        result = {"status": "owner_paper_worker_failed_closed",
                  "network_may_have_been_attempted": True,
                  "paper_reservations_may_have_been_written": True,
                  "orders_sent": False, "approved_for_live_use": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result.get("phase") in (
        "stopped_by_operator", "completed_finite_cycles",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
