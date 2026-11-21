"""D443: existing persisted BTC PAPER position, finite public ticker research.

No actual trading, account API, new positions, fills inferred or J1 access.
Requires explicit public data and existing private AUTO4 journal opt-ins.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.j4_held_btc_public_d443 import (
    observe_existing_btc_paper_once,
)
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-paper-directory", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--max-frames", type=int, default=20000)
    for option in (
        "allow-public-network", "allow-public-websocket",
        "confirm-personal-readonly-research", "confirm-region-eligible",
        "allow-private-paper-reservations",
    ):
        parser.add_argument("--" + option, action="store_true")
    args = parser.parse_args(argv)
    gates = (
        args.allow_public_network, args.allow_public_websocket,
        args.confirm_personal_readonly_research, args.confirm_region_eligible,
        args.allow_private_paper_reservations,
    )
    if not all(gates):
        print(json.dumps({
            "status": "explicit_held_paper_and_public_market_optins_required",
            "network_attempted": False, "private_paper_journal_accessed": False,
            "orders_sent": False,
        }, sort_keys=True))
        return 77
    try:
        budget = TickerLeaseBudget(1, args.max_frames, args.seconds)
        if budget.max_seconds > 60 or budget.max_frames > 100_000:
            raise DataValidationError("D443 finite budget exceeded")
    except (DataValidationError, ValueError, TypeError, ArithmeticError):
        print(json.dumps({
            "status": "held_btc_paper_budget_invalid_before_io",
            "network_attempted": False,
            "private_paper_journal_accessed": False,
            "orders_sent": False,
        }, sort_keys=True))
        return 2
    try:
        result = observe_existing_btc_paper_once(
            private_paper_directory=args.private_paper_directory,
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True, confirm_region_eligible=True,
            allow_private_paper_reservations=True, budget=budget,
        )
    except (DataValidationError, DataGapError, ValueError, TypeError,
            ArithmeticError, OSError, ImportError, RuntimeError):
        # Once a gated operator begins, don't falsely claim no journal/network
        # activity after an exception; the AUTO4 journal may have a reservation.
        result = {
            "status": "held_btc_paper_operator_failed_closed",
            "network_attempted": True,
            "private_paper_journal_may_have_been_accessed": True,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result.get("status") == "finite_held_paper_quote_observed_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
