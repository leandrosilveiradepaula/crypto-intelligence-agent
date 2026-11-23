"""D461: one owner-only 50 x 24 closed-hour Bybit REST J2 research session.

A bounded, permission-gated public-read workflow; does NOT write the
WebSocket-only J2 journal, touch J1, open PAPER orders or install a service.
The same owner policy's strategy is used to calculate research hypotheses.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from crypto_intelligence_agent.j2_dynamic_public_n50_d451 import (
    capture_dynamic_public_n50,
)
from crypto_intelligence_agent.j2_rest_n50_history_d461 import (
    capture_rest_n50_24h, research_rest_n50_24h,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read 24h x N50 Bybit public closed REST candles for J2 research only",
    )
    parser.add_argument("--j2-directory", type=Path, required=True)
    parser.add_argument("--policy-file", type=Path, required=True)
    for flag in (
        "allow-public-network", "confirm-personal-readonly-research",
        "confirm-region-eligible", "confirm-public-data-rights",
    ):
        parser.add_argument("--"+flag, action="store_true")
    options = parser.parse_args(argv)
    if not all((
        options.allow_public_network,
        options.confirm_personal_readonly_research,
        options.confirm_region_eligible,
        options.confirm_public_data_rights,
    )):
        print(json.dumps({
            "status": "four_public_rest_optins_required",
            "network_attempted": False, "orders_sent": False,
        }, sort_keys=True))
        return 2
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() == 0:
        print(json.dumps({
            "status": "nonroot_owner_required",
            "network_attempted": False, "orders_sent": False,
        }, sort_keys=True))
        return 2
    policy = read_owner_paper_policy(options.policy_file)
    snapshot = capture_dynamic_public_n50(
        allow_public_network=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True, confirm_public_data_rights=True,
    )
    history = capture_rest_n50_24h(
        snapshot=snapshot, private_j2_directory=options.j2_directory,
        allow_public_network=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True, confirm_public_data_rights=True,
    )
    observations = research_rest_n50_24h(
        history=history, config=policy.research,
    )
    # Sanitized readout includes every symbol and indicator result, not
    # raw price bars. No account, secret, production order or fake WS ACK.
    report = {
        "schema_version": "d461-j2-n50-historical-operator-v1",
        "status": "historical_n50_research_completed",
        "cohort": snapshot.sanitized_report(),
        "history": history.sanitized_report(),
        "research": observations,
        "real_orders_sent": False,
        "live_signals_generated": False,
        "ws_journal_written": False,
        "j1_touched": False,
    }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
