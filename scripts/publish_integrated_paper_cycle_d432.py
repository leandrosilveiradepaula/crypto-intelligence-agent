"""D432: produce an owner-only Console projection from the offline vertical proof.

Never opens a socket or writes a market/AUTO journal. The report itself is
created by the existing J2-to-AUTO2-to-AUTO4-to-runner demo; D392 is run alongside it
to prove the Bybit-shaped intrahour stop-first fixture before publication.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.j2_public_n50_health_cycles_d421 import _owned_directory
from crypto_intelligence_agent.paper_intrahour_proof_d392 import demonstrate_paper_intrahour_cycle
from scripts.demo_full_offline_paper_lifecycle import run_full_offline_paper_lifecycle

_NAME = "latest-integrated-paper-cycle.json"


def publish(directory: Path) -> dict:
    if (os.name != "posix" or os.geteuid() == 0 or not directory.is_absolute()
            or directory.is_symlink()):
        raise DataValidationError("D432 requires a nonroot absolute owner directory")
    _owned_directory(directory)
    report = run_full_offline_paper_lifecycle()
    intrahour = [
        demonstrate_paper_intrahour_cycle(side="LONG"),
        demonstrate_paper_intrahour_cycle(side="SHORT"),
        demonstrate_paper_intrahour_cycle(side="LONG", scenario="unknown_blocks_stop"),
    ]
    if (type(report) is not dict
            or report.get("schema_version") != "j6_full_offline_paper_lifecycle_v1"
            or report.get("mode") != "offline_paper"
            or report.get("stages") != [
                "j2_risk_open_intent_reserved_without_fill",
                "explicit_fixture_open_fill_crosschecked_on_restart",
                "three_explicit_fixture_partial_fills",
                "runner2_hypothetical_trigger",
                "runner_reduce_only_pending_recovered_without_fill",
                "explicit_fixture_runner_fill_and_pre8_audit",
            ]
            or report.get("orders_sent") is not False
            or report.get("live_trading_authorized") is not False
            or report.get("approved_for_live_use") is not False
            or report.get("market_data_real") is not False
            or report.get("financial_pnl_available") is not False
            or report.get("native_stop_verified") is not False
            or report.get("network_requests") != 0
            or report.get("restart_duplicate_orders") != 0
            or report.get("confirmed_remaining_units") != "0"
            or report.get("synthetic_partial_fills_injected_explicitly") != 3
            or [(x.get("status"), x.get("position_side")) for x in intrahour] != [
                ("fixture_cycle_closed", "LONG"),
                ("fixture_cycle_closed", "SHORT"),
                ("fixture_unknown_requires_reconciliation", "LONG"),
            ]
            or any(x.get("orders_sent") is not False
                   or x.get("venue_account_connected") is not False
                   or x.get("real_fills_verified") is not False
                   or x.get("market_source") != "SYNTHETIC_BYBIT_TICKER_FIXTURES"
                   for x in intrahour)):
        raise DataValidationError("D432 only publishes verified offline PAPER fixtures")
    raw = json.dumps(report, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    if not 2 <= len(raw) <= 32_768:
        raise DataValidationError("D432 report size exceeds owner reader limit")
    fd, temporary = tempfile.mkstemp(prefix=".cycle-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        target = directory / _NAME
        if target.is_symlink():
            raise DataValidationError("D432 refuses an existing symlink")
        os.replace(temporary, target)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return {"status": "offline_integrated_cycle_published", "orders_sent": False,
            "network_requests": 0, "bybit_intrahour_fixture_verified": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(publish(args.directory), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
