"""Bounded owner-only WS lease for an OFF-BY-DEFAULT service manager.

A successful lease is NOT a live-feed or Top50 certification. All four
permissions are explicit, and failures map to stable service exit statuses.
Never place orders, issue private API requests, run REST kline backfill, or
install/start a systemd unit from this module.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Callable

OK = 0
INVALID_ARGUMENTS = 64
PROVIDER_DENIED = 65
INTEGRITY_FAIL_STOP = 66
OWNER_GATE_REQUIRED = 77
TRANSIENT_TRANSPORT = 75
STOPPED = 130

_SUCCESS = frozenset({
    "ws_pilot_sample_rank_ready_not_marketwide",
    "ws_pilot_warming_up_abstain",
    "ws_pilot_scope_refreshed_waiting_next_closed_hour",
})
_TRANSIENT_FAILURES = frozenset({
    "transport_disconnected", "reconnection_deferred", "receive_budget",
})


def classify_owner_pilot_result(report) -> tuple[int, str, str | None]:
    """Fail closed on unknown statuses, never automatically restart 10006."""
    status = getattr(report, "status", None)
    failure = getattr(report, "failure_category", None)
    if type(status) is not str:
        return INTEGRITY_FAIL_STOP, "ws_service_untrusted_result", None
    if status in _SUCCESS:
        return OK, status, None
    if status == "ws_pilot_catalog_denied_no_retry":
        return PROVIDER_DENIED, status, "provider_or_quota"
    if status == "owner_opt_in_required":
        return OWNER_GATE_REQUIRED, status, None
    if status == "pilot_arguments_invalid":
        return INVALID_ARGUMENTS, status, None
    if status == "ws_pilot_degraded_abstain" and failure in _TRANSIENT_FAILURES:
        return TRANSIENT_TRANSPORT, status, failure
    return INTEGRITY_FAIL_STOP, "ws_service_fail_closed_abstain", None


def execute_owner_service_lease(*, directory: str, seconds: int,
                                allow_public_network: bool = False,
                                allow_public_websocket: bool = False,
                                allow_private_storage: bool = False,
                                confirm_region_and_personal_research: bool = False,
                                runner: Callable | None = None,
                                budget_factory: Callable | None = None,
                                owner_check: Callable[[], bool] | None = None,
                                ) -> tuple[int, str, str | None]:
    """One finite lease. Injected runner/budget allow zero-I/O tests."""
    if not all((allow_public_network is True, allow_public_websocket is True,
                allow_private_storage is True,
                confirm_region_and_personal_research is True)):
        return OWNER_GATE_REQUIRED, "owner_opt_in_required", None
    if (type(directory) is not str or not directory.startswith("/")
            or type(seconds) is not int or not 300 <= seconds <= 3_590):
        return INVALID_ARGUMENTS, "ws_service_invalid_configuration", None
    if owner_check is None:
        owner_check = lambda: os.name == "posix" and os.geteuid() != 0
    if not owner_check():
        return OWNER_GATE_REQUIRED, "owner_posix_unprivileged_required", None
    try:
        if runner is None:
            from crypto_intelligence_agent.bybit_ws_owner_pilot import run_owner_ws_pilot
            runner = run_owner_ws_pilot
        if budget_factory is None:
            from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
            budget_factory = WSRunBudget
        budget = budget_factory(max_seconds=seconds)
        outcome = runner(
            directory=directory,
            budget=budget,
            allow_public_network=True,
            allow_public_websocket=True,
            allow_private_storage=True,
            confirm_region_and_personal_research=True,
        )
        return classify_owner_pilot_result(outcome)
    except KeyboardInterrupt:
        return STOPPED, "ws_service_stopped_by_operator", None
    except Exception:
        # A stable category is sufficient for journald/monitoring; never echo
        # private paths, payloads, environment or interpreter traceback.
        return INTEGRITY_FAIL_STOP, "ws_service_unhandled_failure_abstain", None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--seconds", type=int, default=3300)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-public-websocket", action="store_true")
    parser.add_argument("--allow-private-storage", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = parser.parse_args(argv)
    code, status, failure = execute_owner_service_lease(
        directory=args.directory, seconds=args.seconds,
        allow_public_network=args.allow_public_network,
        allow_public_websocket=args.allow_public_websocket,
        allow_private_storage=args.allow_private_storage,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
    )
    print(json.dumps({
        "status": status, "failure_category": failure, "service_exit_code": code,
        "worker_running_verified": False, "marketwide_top50_verified": False,
        "live_trading_authorized": False, "orders_sent": False,
    }, separators=(",", ":"), sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())