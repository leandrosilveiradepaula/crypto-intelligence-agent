"""D442: explicit owner-only finite BTC ticker -> J3 -> J4 PAPER research."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.j2_j3_j4_btc_paper_shadow_d442 import (
    CostedShadowPolicy, observe_costed_btc_paper_shadow_once,
)
from crypto_intelligence_agent.j4_shadow_public_paper_pilot_d426 import ShadowPaperPolicy
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--side", choices=("LONG", "SHORT"), default="LONG")
    p.add_argument("--margin-quote", default="3")
    p.add_argument("--leverage", type=int, default=50)
    p.add_argument("--stop-bps", default="100")
    p.add_argument("--first-target-bps", default="10")
    p.add_argument("--second-target-bps", default="20")
    for name in ("entry-fee-bps", "exit-fee-bps",
                 "entry-adverse-slippage-bps", "exit-adverse-slippage-bps"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--seconds", type=int, default=30)
    p.add_argument("--max-frames", type=int, default=20000)
    for key in (
        "allow-public-network", "allow-public-websocket",
        "confirm-personal-readonly-research", "confirm-region-eligible",
        "allow-hypothetical-paper-open",
    ):
        p.add_argument("--" + key, action="store_true")
    args = p.parse_args(argv)
    flags = (
        args.allow_public_network, args.allow_public_websocket,
        args.confirm_personal_readonly_research, args.confirm_region_eligible,
        args.allow_hypothetical_paper_open,
    )
    if not all(flags):
        print(json.dumps({"status": "explicit_btc_paper_research_optins_required",
                          "network_attempted": False, "orders_sent": False}))
        return 77
    try:
        policy = CostedShadowPolicy(
            ShadowPaperPolicy(
                "BTCUSDT", SyntheticSide(args.side),
                margin_quote=Decimal(args.margin_quote), leverage=args.leverage,
                stop_distance_bps=Decimal(args.stop_bps),
                target1_distance_bps=Decimal(args.first_target_bps),
                target2_distance_bps=Decimal(args.second_target_bps),
            ),
            Decimal(args.entry_fee_bps), Decimal(args.exit_fee_bps),
            Decimal(args.entry_adverse_slippage_bps),
            Decimal(args.exit_adverse_slippage_bps),
        )
        budget = TickerLeaseBudget(1, args.max_frames, args.seconds)
    except (DataValidationError, ValueError, ArithmeticError):
        print(json.dumps({"status": "invalid_research_policy",
                          "network_attempted": False, "orders_sent": False}))
        return 2
    try:
        report = observe_costed_btc_paper_shadow_once(
            policy=policy,
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True, confirm_region_eligible=True,
            allow_hypothetical_paper_open=True, budget=budget,
        )
    except (DataValidationError, OSError, ValueError, ArithmeticError,
            TypeError, RuntimeError, ImportError):
        # Once the network-capable function has been entered, the caller can
        # no longer assert NO network access on an unexpected failure.
        report = {"status": "btc_public_research_abstained",
                  "network_attempted": True, "orders_sent": False,
                  "approved_for_live_use": False}
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if report.get("status") == "public_quote_routed_to_costed_paper_reservations" else 2


if __name__ == "__main__":
    raise SystemExit(main())
