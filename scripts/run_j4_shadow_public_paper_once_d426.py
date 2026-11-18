"""D426 — FINITE public-Bybit shadow PAPER observation, no real trades.

The first fresh, post-ACK public quote opens a *fabricated* PAPER scenario
at its mark price; subsequent quotes can reserve hypothetical AUTO4 exits.
No true fill, executable entry, account, native protection, or signal.
The generated PAPER journal is destroyed after the one finite observation.
No service/timer/cron/deploy or real order transport is provided.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sys

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget,
)
from crypto_intelligence_agent.j4_shadow_public_paper_pilot_d426 import (
    ShadowPaperPolicy, observe_shadow_paper_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

_SCHEMA = "j4-ephemeral-public-paper-shadow-d426-v1"


def _blocked(reason: str) -> int:
    print(json.dumps({
        "schema_version": _SCHEMA, "status": reason,
        "orders_sent": False, "approved_for_live_use": False,
        "synthetic_open_created": False,
    }, sort_keys=True, separators=(",", ":")))
    return 65


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-directory", type=Path, required=True)
    p.add_argument("--symbol", type=str, required=True)
    p.add_argument("--side", choices=("LONG", "SHORT"), required=True)
    p.add_argument("--margin-usdt", default="3")
    p.add_argument("--leverage", type=int, default=50)
    p.add_argument("--stop-bps", default="100")
    p.add_argument("--target1-bps", default="10")
    p.add_argument("--target2-bps", default="20")
    p.add_argument("--seconds", type=int, default=30)
    p.add_argument("--max-frames", type=int, default=100000)
    p.add_argument("--allow-private-pointer-read", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-personal-readonly-research", action="store_true")
    p.add_argument("--confirm-region-eligible", action="store_true")
    p.add_argument("--allow-hypothetical-paper-open", action="store_true")
    a = p.parse_args(argv)

    if not all((
        a.allow_private_pointer_read, a.allow_public_websocket,
        a.confirm_personal_readonly_research, a.confirm_region_eligible,
        a.allow_hypothetical_paper_open,
    )):
        print(json.dumps({
            "schema_version": _SCHEMA,
            "status": "explicit_owner_market_shadow_optins_required",
            "network_attempted": False, "owner_scope_read": False,
            "synthetic_open_created": False, "orders_sent": False,
            "approved_for_live_use": False,
        }, sort_keys=True, separators=(",", ":")))
        return 77
    if (os.name != "posix" or os.geteuid() == 0
            or not a.state_directory.is_absolute()
            or not 1 <= a.seconds <= 60
            or not 1 <= a.max_frames <= 100000):
        return _blocked("shadow_operator_environment_or_budget_invalid")
    try:
        policy = ShadowPaperPolicy(
            symbol=a.symbol, side=SyntheticSide(a.side),
            margin_quote=Decimal(a.margin_usdt), leverage=a.leverage,
            stop_distance_bps=Decimal(a.stop_bps),
            target1_distance_bps=Decimal(a.target1_bps),
            target2_distance_bps=Decimal(a.target2_bps),
        )
        result = observe_shadow_paper_once(
            state_directory=a.state_directory, policy=policy,
            allow_private_pointer_read=True,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            allow_hypothetical_paper_open=True,
            budget=TickerLeaseBudget(
                max_sessions=1, max_frames=a.max_frames, max_seconds=a.seconds,
            ),
        )
    except (DataGapError, DataValidationError, OSError,
            TypeError, ValueError, InvalidOperation,
            ArithmeticError, OverflowError, RuntimeError):
        return _blocked("shadow_market_or_owner_unavailable_no_real_trade")
    print(json.dumps(result, sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return (0 if result["status"] == "shadow_public_quote_routed_paper_only"
            else 2)


if __name__ == "__main__":
    sys.exit(main())
