"""J3 #667: one owner-only post-decision reference scoring tick, never trading.

When independently authorized for deployment, a fixed hourly timer may call
this script once with fully declared research-only cost assumptions. All
source records/marks remain within the private owner environment.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
import re
import time
from typing import Any

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.j3_ws_watchlist_forward_marks import ForwardCostAssumptions
from crypto_intelligence_agent.j2_ws_prospective_ledger import score_owner_ws_decision_once
from crypto_intelligence_agent.j2_ws_owner_preflight import preflight_owner_ws_decision_once
from crypto_intelligence_agent.market_data import DataValidationError


_WINDOWS_MS = (17 * 60_000, 24 * 60_000)
_HORIZONS = (1, 4, 8)
_FINITE = re.compile(r"-?(?:0|[1-9][0-9]{0,299})(?:[.][0-9]{1,300})?\\Z")
_FALSE = (
    "prospective_registration_verified", "intrabar_path_verified",
    "venue_fees_verified", "funding_schedule_verified",
    "out_of_sample_results_validated", "financial_backtest_approved",
    "marketwide_top50_verified", "approved_for_signals",
    "live_trading_authorized", "orders_sent", "systemd_modified",
    "prospective_registration_independently_verified",
)


def _empty(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j3-owner-forward-score-tick-v1",
        "status": status,
        "horizons": [],
        "evaluations_scored": 0,
        "empty_decisions_verified": 0,
        "horizons_abstained": 0,
        "out_of_sample_results_validated": False,
        "financial_backtest_approved": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _owner_runtime() -> bool:
    return (os.name == "posix" and hasattr(os, "geteuid")
            and os.geteuid() != 0 and os.getuid() == os.geteuid()
            and os.getgid() == os.getegid())


def _window(now_ms: int) -> bool:
    return _WINDOWS_MS[0] <= now_ms % HOUR_MS < _WINDOWS_MS[1]


def _projection(raw: object, *, horizon: int, future_end: int) -> dict[str, Any]:
    """Validate every scored-result safety/chronology field, never raw marks."""
    generic = {"horizon_hours": horizon, "status": "abstained",
               "selected_observations": 0, "matured_observations": 0,
               "net_reference_after_assumed_costs_bps_sum": None}
    if type(raw) is not dict:
        return generic
    status = raw.get("status")
    if (raw.get("schema_version") == "j2-ws-owner-ledger-status-v1"
            and status in (
                "owner_score_abstain", "owner_ws_metadata_changed_forward_abstain",
                "owner_score_horizon_not_supported_for_rotating_epoch",
            )
            and raw.get("orders_sent") is False
            and raw.get("live_trading_authorized") is False
            and raw.get("database_mutation_statements") == 0):
        generic["status"] = "owner_source_abstained"
        return generic
    if (raw.get("schema_version") != "j3-ws-watchlist-forward-reference-v1"
            or status not in (
                "no_observations_selected",
                "ex_post_reference_marks_scored_not_a_backtest",
            )
            or raw.get("quality") != "ex_post_closed_mark_cost_assumptions_not_fills"
            or raw.get("horizon_bars") != horizon
            or raw.get("future_closed_end_ms") != future_end
            or raw.get("decision_closed_end_ms") != future_end-horizon*HOUR_MS
            or raw.get("owner_local_decision_file_verified") is not True
            or raw.get("owner_ws_sqlite_readonly_replayed") is not True
            or raw.get("database_accessed") is not True
            or any(raw.get(k) is not False for k in _FALSE)
            or type(raw.get("network_requests")) is not int
            or raw.get("network_requests") != 0
            or type(raw.get("database_mutation_statements")) is not int
            or raw.get("database_mutation_statements") != 0):
        return generic
    count = raw.get("selected_observations")
    matured = raw.get("matured_observations")
    if (type(count) is not int or not 0 <= count <= 10
            or type(matured) is not int or not 0 <= matured <= count):
        return generic
    if status == "no_observations_selected":
        if (count != 0 or matured != 0
                or any(raw.get(k) != 0 for k in (
                    "aligned_observations", "contrary_observations",
                    "unchanged_observations", "funding_events_hypothetical"))
                or any(raw.get(k) is not None for k in (
                    "gross_reference_bps_sum",
                    "net_reference_after_assumed_costs_bps_sum",
                    "same_side_btc_excess_reference_bps_sum",
                    "assumed_total_cost_quote_units"))):
            return generic
        return {**generic, "status": "no_observations_selected"}
    if (count == 0 or matured != count
            or any(type(raw.get(k)) is not int or not 0 <= raw[k] <= 10
                   for k in ("aligned_observations", "contrary_observations",
                             "unchanged_observations"))
            or sum(raw[k] for k in ("aligned_observations", "contrary_observations",
                                   "unchanged_observations")) != matured
            or type(raw.get("funding_events_hypothetical")) is not int
            or not 0 <= raw["funding_events_hypothetical"] <= 100):
        return generic
    for k in (
        "gross_reference_bps_sum",
        "net_reference_after_assumed_costs_bps_sum",
        "same_side_btc_excess_reference_bps_sum",
        "assumed_total_cost_quote_units",
    ):
        value = raw.get(k)
        if type(value) is not str or len(value) > 600 or _FINITE.fullmatch(value) is None:
            return generic
    return {
        **generic, "status": "reference_marks_scored_hypothetical_only",
        "selected_observations": count,
        "matured_observations": matured,
        "net_reference_after_assumed_costs_bps_sum":
            raw["net_reference_after_assumed_costs_bps_sum"],
    }


def run_once(*, costs: ForwardCostAssumptions,
             allow_private_readonly_research: bool = False,
             allow_private_ledger_read: bool = False,
             confirm_dedicated_owner_score_tick: bool = False) -> dict[str, Any]:
    if not all((
        allow_private_readonly_research is True,
        allow_private_ledger_read is True,
        confirm_dedicated_owner_score_tick is True,
    )):
        return _empty("owner_score_tick_optins_required")
    if not _owner_runtime():
        return _empty("owner_score_tick_nonroot_required")
    if type(costs) is not ForwardCostAssumptions:
        return _empty("owner_score_tick_costs_required")
    now = time.time_ns() // 1_000_000
    if not _window(now):
        return _empty("owner_score_tick_window_closed")
    try:
        pre = preflight_owner_ws_decision_once(
            allow_private_readonly_research=True
        )
        if (type(pre) is not dict
                or pre.get("schema_version") != "j2-ws-owner-preflight-v1"
                or pre.get("status") != "owner_preflight_ready_no_capture"
                or any(pre.get(k) is not True for k in (
                    "owner_nonroot_posix_verified", "owner_ledger_parent_dac_verified",
                    "os_ntp_sync_reported", "capture_window_open",
                    "owner_ws_50x24_readonly_replayed"))
                or any(pre.get(k) is not False for k in (
                    "prospective_registration_independently_verified",
                    "financial_backtest_approved", "marketwide_top50_verified",
                    "approved_for_signals", "live_trading_authorized",
                    "orders_sent", "systemd_modified"))
                or pre.get("network_requests") != 0
                or pre.get("database_mutation_statements") != 0):
            return _empty("owner_score_tick_preflight_abstain")
        checked = time.time_ns() // 1_000_000
        if checked < now or checked//HOUR_MS != now//HOUR_MS or not _window(checked):
            return _empty("owner_score_tick_clock_shift_abstain")
        closed_end = now - now % HOUR_MS
        horizon_rows = []
        for horizon in _HORIZONS:
            value = score_owner_ws_decision_once(
                horizon_bars=horizon, costs=costs,
                allow_private_readonly_research=True,
                allow_private_ledger_read=True,
            )
            after = time.time_ns() // 1_000_000
            if after < now or after//HOUR_MS != now//HOUR_MS or not _window(after):
                return _empty("owner_score_tick_clock_shift_abstain")
            horizon_rows.append(_projection(value, horizon=horizon,
                                            future_end=closed_end))
        report = _empty("owner_score_tick_readonly_finished")
        report["horizons"] = horizon_rows
        report["evaluations_scored"] = sum(
            row["status"] == "reference_marks_scored_hypothetical_only"
            for row in horizon_rows)
        report["empty_decisions_verified"] = sum(
            row["status"] == "no_observations_selected"
            for row in horizon_rows)
        report["horizons_abstained"] = len(_HORIZONS) - (
            report["evaluations_scored"] + report["empty_decisions_verified"])
        return report
    except (OSError, ValueError, KeyError, TypeError, OverflowError,
            UnicodeError, DataValidationError, InvalidOperation):
        return _empty("owner_score_tick_unavailable_abstain")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-research", action="store_true")
    parser.add_argument("--allow-private-ledger-read", action="store_true")
    parser.add_argument("--confirm-dedicated-owner-score-tick", action="store_true")
    for flag in (
        "notional", "entry-fee-bps", "exit-fee-bps",
        "entry-slippage-bps", "exit-slippage-bps",
    ):
        parser.add_argument("--"+flag, required=True)
    args = parser.parse_args(argv)
    try:
        cost_plan = ForwardCostAssumptions(
            hypothetical_notional_quote_units=Decimal(args.notional),
            entry_fee_bps=Decimal(args.entry_fee_bps),
            exit_fee_bps=Decimal(args.exit_fee_bps),
            entry_adverse_slippage_bps=Decimal(args.entry_slippage_bps),
            exit_adverse_slippage_bps=Decimal(args.exit_slippage_bps),
        )
    except (InvalidOperation, ValueError, TypeError, DataValidationError):
        print(json.dumps(_empty("owner_score_tick_costs_invalid"), sort_keys=True))
        return 65
    report = run_once(
        costs=cost_plan,
        allow_private_readonly_research=args.allow_private_readonly_research,
        allow_private_ledger_read=args.allow_private_ledger_read,
        confirm_dedicated_owner_score_tick=args.confirm_dedicated_owner_score_tick,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "owner_score_tick_readonly_finished" else 65


if __name__ == "__main__":
    raise SystemExit(main())
