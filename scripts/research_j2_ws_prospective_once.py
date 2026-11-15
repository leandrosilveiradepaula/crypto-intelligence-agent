"""J2/J3 #644: opt-in POSIX owner capture/score using current WS N50 epoch.

A *capture* writes only one private 0600 decision file under an existing
owner home. *score* is read-only and only prints aggregates. No systemd,
network, REST, credential, trading or new SQL access. Not installed by merge.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json

from crypto_intelligence_agent.j2_ws_prospective_ledger import (
    capture_owner_ws_decision_once, score_owner_ws_decision_once,
)
from crypto_intelligence_agent.j3_ws_watchlist_forward_marks import (
    ForwardCostAssumptions,
)
from crypto_intelligence_agent.market_data import DataValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--allow-private-readonly-research", action="store_true")
    capture.add_argument("--allow-private-ledger-write", action="store_true")
    score = commands.add_parser("score")
    score.add_argument("--allow-private-readonly-research", action="store_true")
    score.add_argument("--allow-private-ledger-read", action="store_true")
    score.add_argument("--horizon-bars", type=int, required=True, choices=(1, 4, 8))
    for flag in (
        "notional", "entry-fee-bps", "exit-fee-bps",
        "entry-slippage-bps", "exit-slippage-bps",
    ):
        score.add_argument("--"+flag, required=True)
    args = parser.parse_args(argv)
    if args.command == "capture":
        report = capture_owner_ws_decision_once(
            allow_private_readonly_research=args.allow_private_readonly_research,
            allow_private_ledger_write=args.allow_private_ledger_write,
        )
        ok = report["status"] == "owner_local_decision_captured_not_independent_attestation"
    else:
        try:
            costs = ForwardCostAssumptions(
                hypothetical_notional_quote_units=Decimal(args.notional),
                entry_fee_bps=Decimal(args.entry_fee_bps),
                exit_fee_bps=Decimal(args.exit_fee_bps),
                entry_adverse_slippage_bps=Decimal(args.entry_slippage_bps),
                exit_adverse_slippage_bps=Decimal(args.exit_slippage_bps),
            )
            report = score_owner_ws_decision_once(
                horizon_bars=args.horizon_bars, costs=costs,
                allow_private_readonly_research=args.allow_private_readonly_research,
                allow_private_ledger_read=args.allow_private_ledger_read,
            )
            ok = report["status"] in (
                "ex_post_reference_marks_scored_not_a_backtest",
                "no_observations_selected",
            )
        except (DataValidationError, InvalidOperation, ValueError, TypeError):
            report = {
                "schema_version": "j2-ws-owner-ledger-status-v1",
                "status": "invalid_hypothetical_cost_assumptions",
                "approved_for_signals": False,
                "financial_backtest_approved": False,
                "orders_sent": False,
                "network_requests": 0,
                "systemd_modified": False,
            }
            ok = False
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if ok else 65


if __name__ == "__main__":
    raise SystemExit(main())
