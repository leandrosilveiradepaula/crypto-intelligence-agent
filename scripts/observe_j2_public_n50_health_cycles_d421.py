"""D421: optional owner-only finite WS cycles to private count-only health JSON.

This never creates or deploys a service, daemon, timer, public HTTP endpoint,
credentials, orders, J1 writer or PAPER fills. Explicit owner flags required.
Output directory MUST already exist as an owner 0700 directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from crypto_intelligence_agent.j2_n50_sustained_public_operator_d418 import (
    observe_current_n50_sustained_once,
)
from crypto_intelligence_agent.j2_public_n50_health_cycles_d421 import (
    exclusive_private_health_lock, publish_private_health,
    run_readonly_health_cycles,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--allow-private-pointer-read", action="store_true")
    parser.add_argument("--allow-public-websocket", action="store_true")
    parser.add_argument("--confirm-personal-readonly-research", action="store_true")
    parser.add_argument("--confirm-region-eligible", action="store_true")
    parser.add_argument("--allow-local-health-write", action="store_true")
    args = parser.parse_args(argv)
    if not all((
        args.allow_private_pointer_read,
        args.allow_public_websocket,
        args.confirm_personal_readonly_research,
        args.confirm_region_eligible,
        args.allow_local_health_write,
    )):
        print(json.dumps({
            "schema_version": "j2-n50-private-health-cycles-d421-v1",
            "status": "owner_readonly_and_local_health_optins_required",
            "private_state_read": False, "network_attempted": False,
            "health_file_written": False, "orders_sent": False,
        }, sort_keys=True))
        return 77
    if (os.name != "posix" or os.geteuid() == 0
            or type(args.cycles) is not int or not 1 <= args.cycles <= 24
            or type(args.seconds) is not int or not 60 <= args.seconds <= 900
            or not args.state_directory.is_absolute()
            or not args.output_directory.is_absolute()):
        print(json.dumps({
            "status": "owner_environment_or_cycle_limit_invalid",
            "orders_sent": False, "systemd_modified": False,
        }, sort_keys=True))
        return 65

    try:
        lock = exclusive_private_health_lock(args.output_directory)
    except (OSError, DataValidationError, BlockingIOError):
        print(json.dumps({
            "status": "private_health_lock_or_directory_unavailable",
            "orders_sent": False, "systemd_modified": False,
        }, sort_keys=True))
        return 65
    try:
        def probe() -> dict:
            return observe_current_n50_sustained_once(
                state_directory=args.state_directory,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                seconds=args.seconds,
                max_frames=200_000,
                max_sessions=2,
            )

        result = run_readonly_health_cycles(
            cycles=args.cycles, probe=probe,
            publisher=lambda r: publish_private_health(args.output_directory, r),
        )
    except (OSError, ValueError, TypeError, RuntimeError,
            DataGapError, DataValidationError):
        print(json.dumps({
            "status": "private_market_health_unavailable",
            "orders_sent": False, "systemd_modified": False,
        }, sort_keys=True))
        return 65
    finally:
        os.close(lock)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["degraded_samples"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
