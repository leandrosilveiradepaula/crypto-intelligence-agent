"""Finite owner-only Bybit WS sample pilot; explicit network and storage opt-in.

Not a daemon; prints aggregate-only research status. Never sends orders.
"""
from __future__ import annotations

import argparse
import json
from crypto_intelligence_agent.bybit_ws_owner_pilot import run_owner_ws_pilot
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", required=True)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--allow-private-storage", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    p.add_argument("--seconds", type=int, default=180)
    a = p.parse_args(argv)
    # No implicit access without all four flags; the service is not installed.
    try:
        budget = WSRunBudget(max_seconds=a.seconds)
    except ValueError:
        p.error("invalid bounded pilot seconds")
    result = run_owner_ws_pilot(
        directory=a.directory, budget=budget,
        allow_public_network=a.allow_public_network,
        allow_public_websocket=a.allow_public_websocket,
        allow_private_storage=a.allow_private_storage,
        confirm_region_and_personal_research=a.confirm_region_and_personal_research,
    )
    print(json.dumps(result.sanitized_report(), sort_keys=True, separators=(",", ":")))
    return 0 if result.status in (
        "ws_pilot_sample_rank_ready_not_marketwide",
        "ws_pilot_warming_up_abstain",
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())