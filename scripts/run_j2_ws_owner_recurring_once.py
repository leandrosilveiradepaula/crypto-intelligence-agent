"""J2 #663: exactly one prospective capture tick for an optional owner timer.

Never a daemon or production deployment. One atomic owner-ledger write is
possible only under explicit flags, in a narrow current UTC window, with the
existing J2 private 50x24 audit and ledger. No source paths or times accepted.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.j2_ws_owner_preflight import preflight_owner_ws_decision_once
from crypto_intelligence_agent.j2_ws_prospective_ledger import capture_owner_ws_decision_once


_MINUTE_MS = 60_000
_CAPTURE_FIELDS = frozenset((
    "schema_version", "status", "capture_records_created", "candidates_captured",
    "decision_closed_end_ms", "owner_ws_sqlite_readonly_replayed",
    "local_decision_record_consistency_verified",
    "prospective_registration_independently_verified", "marketwide_top50_verified",
    "financial_backtest_approved", "approved_for_signals", "live_trading_authorized",
    "orders_sent", "network_requests", "database_mutation_statements",
    "systemd_modified",
))


def _empty(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j2-owner-recurring-tick-v1",
        "status": status,
        "decision_created_this_tick": False,
        "decision_closed_end_ms": None,
        "candidates_captured": 0,
        "prospective_registration_independently_verified": False,
        "financial_backtest_approved": False,
        "marketwide_top50_verified": False,
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


def _minute_window(now_ms: int) -> bool:
    """No catch-up or timestamps supplied by caller; schedule at HH:07 UTC."""
    return 7 * _MINUTE_MS <= now_ms % HOUR_MS < 13 * _MINUTE_MS


def _safe_capture_report(capture: object, expected_closed_end_ms: int) -> bool:
    if type(capture) is not dict or set(capture) != _CAPTURE_FIELDS:
        return False
    if (capture["schema_version"] != "j2-ws-owner-ledger-status-v1"
            or any(capture[key] is not False for key in (
                "prospective_registration_independently_verified",
                "marketwide_top50_verified", "financial_backtest_approved",
                "approved_for_signals", "live_trading_authorized",
                "orders_sent", "systemd_modified"))
            or capture["network_requests"] != 0
            or type(capture["network_requests"]) is not int
            or capture["database_mutation_statements"] != 0
            or type(capture["database_mutation_statements"]) is not int):
        return False
    if capture["status"] == "owner_decision_hour_already_recorded":
        return (capture["capture_records_created"] == 0
                and type(capture["capture_records_created"]) is int
                and capture["candidates_captured"] == 0
                and type(capture["candidates_captured"]) is int
                and capture["decision_closed_end_ms"] is None
                and capture["owner_ws_sqlite_readonly_replayed"] is False
                and capture["local_decision_record_consistency_verified"] is False)
    return (
        capture["status"] == "owner_local_decision_captured_not_independent_attestation"
        and capture["capture_records_created"] == 1
        and type(capture["capture_records_created"]) is int
        and type(capture["candidates_captured"]) is int
        and 0 <= capture["candidates_captured"] <= 10
        and type(capture["decision_closed_end_ms"]) is int
        and capture["decision_closed_end_ms"] == expected_closed_end_ms
        and capture["owner_ws_sqlite_readonly_replayed"] is True
        and capture["local_decision_record_consistency_verified"] is True
    )


def run_once(*, allow_private_readonly_research: bool = False,
             allow_private_ledger_write: bool = False,
             confirm_dedicated_owner_tick: bool = False) -> dict[str, Any]:
    """One bounded attempt: never loop, retry, create a timer or log private data."""
    if not all((allow_private_readonly_research is True,
                allow_private_ledger_write is True,
                confirm_dedicated_owner_tick is True)):
        return _empty("owner_scheduler_optins_required")
    if not _owner_runtime():
        return _empty("owner_nonroot_posix_required")
    now = time.time_ns() // 1_000_000
    if not _minute_window(now):
        return _empty("outside_safe_utc_tick_window")
    try:
        preflight = preflight_owner_ws_decision_once(
            allow_private_readonly_research=True
        )
        if (type(preflight) is not dict
                or preflight.get("schema_version") != "j2-ws-owner-preflight-v1"
                or preflight.get("status") != "owner_preflight_ready_no_capture"
                or any(preflight.get(key) is not True for key in (
                    "owner_nonroot_posix_verified", "owner_ledger_parent_dac_verified",
                    "os_ntp_sync_reported", "capture_window_open",
                    "capture_eligible_now", "owner_ws_50x24_readonly_replayed"))
                or any(preflight.get(key) is not False for key in (
                    "prospective_registration_independently_verified",
                    "marketwide_top50_verified", "financial_backtest_approved",
                    "approved_for_signals", "live_trading_authorized",
                    "orders_sent", "systemd_modified"))
                or type(preflight.get("network_requests")) is not int
                or preflight.get("network_requests") != 0
                or type(preflight.get("database_mutation_statements")) is not int
                or preflight.get("database_mutation_statements") != 0):
            return _empty("owner_preflight_abstain")
        next_now = time.time_ns() // 1_000_000
        if (next_now < now or next_now // HOUR_MS != now // HOUR_MS
                or not _minute_window(next_now)):
            return _empty("owner_tick_clock_or_epoch_shift_abstain")
        capture = capture_owner_ws_decision_once(
            allow_private_readonly_research=True, allow_private_ledger_write=True,
        )
        if not _safe_capture_report(capture, now - now % HOUR_MS):
            return _empty("owner_capture_abstain")
        if capture["status"] == "owner_decision_hour_already_recorded":
            return _empty("owner_hour_idempotent_no_new_record")
        report = _empty("owner_new_decision_recorded_research_only")
        report.update(
            decision_created_this_tick=True,
            decision_closed_end_ms=capture["decision_closed_end_ms"],
            candidates_captured=capture["candidates_captured"],
        )
        return report
    except (OSError, ValueError, KeyError, TypeError, OverflowError,
            UnicodeError):
        return _empty("owner_tick_unavailable_abstain")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-research", action="store_true")
    parser.add_argument("--allow-private-ledger-write", action="store_true")
    parser.add_argument("--confirm-dedicated-owner-tick", action="store_true")
    args = parser.parse_args(argv)
    outcome = run_once(
        allow_private_readonly_research=args.allow_private_readonly_research,
        allow_private_ledger_write=args.allow_private_ledger_write,
        confirm_dedicated_owner_tick=args.confirm_dedicated_owner_tick,
    )
    print(json.dumps(outcome, sort_keys=True, separators=(",", ":")))
    return 0 if outcome["status"] in (
        "owner_new_decision_recorded_research_only",
        "owner_hour_idempotent_no_new_record",
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
