"""D430 opt-in out-of-process observer for a FINITE D428 PAPER test.

This DOES NOT install or start a permanent service. It runs exactly one
existing D428 owner-only trial, with one extra consent to supervise its
process timeout. It cannot authorize orders, signal, real stops or live.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j4_paper_bounded_trial_d428 import PaperTrialBudget
from crypto_intelligence_agent.j6_paper_child_watchdog_d430 import (
    supervise_finite_paper_child,
)
from crypto_intelligence_agent.market_data import DataValidationError

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-directory", required=True, type=Path)
    parser.add_argument("--private-paper-directory", required=True, type=Path)
    parser.add_argument("--paper-watch-directory", required=True, type=Path)
    parser.add_argument("--max-leases", type=int, default=3)
    parser.add_argument("--lease-seconds", type=int, default=20)
    parser.add_argument("--max-total-seconds", type=int, default=90)
    parser.add_argument("--max-gap-ms", type=int, default=5000)
    parser.add_argument("--max-frames-per-lease", type=int, default=25000)
    for flag in (
        "--allow-private-pointer-read",
        "--allow-public-websocket",
        "--confirm-personal-readonly-research",
        "--confirm-region-eligible",
        "--allow-synthetic-paper-reservations",
        "--allow-multiple-finite-leases",
        "--allow-paper-watch-output",
        "--allow-child-process-watchdog",
    ):
        parser.add_argument(flag, action="store_true")
    args = parser.parse_args(argv)
    try:
        budget = PaperTrialBudget(
            max_leases=args.max_leases,
            lease_seconds=args.lease_seconds,
            max_total_seconds=args.max_total_seconds,
            max_interlease_gap_ms=args.max_gap_ms,
            max_frames_per_lease=args.max_frames_per_lease,
        )
        report = supervise_finite_paper_child(
            state_directory=args.state_directory,
            private_paper_directory=args.private_paper_directory,
            watch_directory=args.paper_watch_directory,
            budget=budget,
            allow_private_pointer_read=args.allow_private_pointer_read,
            allow_public_websocket=args.allow_public_websocket,
            confirm_personal_readonly_research=args.confirm_personal_readonly_research,
            confirm_region_eligible=args.confirm_region_eligible,
            allow_synthetic_paper_reservations=args.allow_synthetic_paper_reservations,
            allow_multiple_finite_leases=args.allow_multiple_finite_leases,
            allow_paper_watch_output=args.allow_paper_watch_output,
            allow_child_process_watchdog=args.allow_child_process_watchdog,
        )
    except (DataValidationError, OSError, ValueError, TypeError):
        report = {
            "schema_version": "j6-finite-paper-child-watchdog-d430-v1",
            "status": "finite_child_preflight_failed_closed",
            "continuous_24x7_verified": False, "orders_sent": False,
            "approved_for_live_use": False, "approved_for_signals": False,
        }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "finite_child_ended_without_live_protection" else 2

if __name__ == "__main__":
    raise SystemExit(main())
