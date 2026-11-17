"""Run one limited public Bybit V5 ticker WS probe, without trading.

This command does NOT source a marketwide Top50 ranking, install a service,
modify J1, connect private channels, send orders or activate PAPER execution.
The operator supplies a separately reviewed comma-delimited symbol list.
Example (only after region/rights verification and approved network gate):
 python -m scripts.probe_bybit_public_ws_once_d405 \
   --symbols BTCUSDT --seconds 20 \
   --allow-public-websocket --confirm-personal-readonly-research \
   --confirm-region-eligible
"""
from __future__ import annotations

import argparse
import json
import sys

from crypto_intelligence_agent.bybit_public_ws_operational_probe_d405 import (
    observe_finite_public_ws_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--positions", default="")
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--max-frames", type=int, default=12_000)
    parser.add_argument("--sessions", type=int, default=1)
    parser.add_argument("--allow-public-websocket", action="store_true")
    parser.add_argument("--confirm-personal-readonly-research", action="store_true")
    parser.add_argument("--confirm-region-eligible", action="store_true")
    options = parser.parse_args(argv)
    if not all((
        options.allow_public_websocket,
        options.confirm_personal_readonly_research,
        options.confirm_region_eligible,
    )):
        print(json.dumps({
            "schema_version": "bybit-public-ws-network-probe-d405-v1",
            "status": "explicit_network_and_region_optin_required",
            "network_attempted": False,
            "orders_sent": False, "approved_for_live_use": False,
        }, sort_keys=True))
        return 65
    try:
        report = observe_finite_public_ws_once(
            symbols=tuple(options.symbols.split(",")),
            position_symbols=(tuple(options.positions.split(","))
                              if options.positions else ()),
            seconds=options.seconds,
            max_frames=options.max_frames,
            max_sessions=options.sessions,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
        )
    except (DataValidationError, DataGapError, OSError, RuntimeError,
            ImportError, ValueError, TypeError):
        print(json.dumps({
            "schema_version": "bybit-public-ws-network-probe-d405-v1",
            "status": "public_ws_probe_abstained",
            "network_result_verified": False,
            "orders_sent": False, "approved_for_live_use": False,
        }, sort_keys=True))
        return 65
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return (0 if report["finite_coverage_observed_once"]
            and report["finite_coverage_fresh_at_end"] else 2)


if __name__ == "__main__":
    raise SystemExit(main())
