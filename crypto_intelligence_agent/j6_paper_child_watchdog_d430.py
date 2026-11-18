"""D430: an OUT-OF-PROCESS timeout/crash observer for finite D428 PAPER runs.

The child is the existing, opt-in D428 owner operator. This parent never
reads financial SQLite, connects to Bybit, sends orders, retries UNKNOWN
intents or starts a daemon. A child timeout/crash must publish D427
fail-closed, not replay a financial action. A successful child has merely
finished a FINITE trial; it is not active position supervision.

This is not an independent OS/service watchdog for parent failure, a venue
stop, a private account connector, or evidence of 24x7 availability.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

from .j4_paper_bounded_trial_d428 import (
    PaperTrialBudget, _result as _child_result,
    _validate_separate_directories,
)
from .j5_paper_watch_d427 import (
    PaperWatchUnavailable, publish_paper_watch,
    read_paper_watch, unavailable_finite_paper_lease,
)
from .market_data import DataValidationError

_SCHEMA = "j6-finite-paper-child-watchdog-d430-v1"
_MAX_STDOUT = 8192
_CHILD_SCHEMA = "j4-bounded-paper-supervision-trial-d428-v1"
_MAX_WALL_MS = 4_102_444_800_000


def _report(status: str) -> dict:
    """Public result contains status and safety flags, never owner identifiers."""
    return {
        "schema_version": _SCHEMA,
        "status": status,
        "finite_child_run_only": True,
        "independent_parent_process_observed": status ==
            "finite_child_ended_without_live_protection",
        "continuous_24x7_verified": False,
        "active_position_supervision_verified": False,
        "native_stop_verified": False,
        "real_fills_verified": False,
        "open_new_positions_authorized": False,
        "orders_sent": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "live_trading_authorized": False,
    }


def _now_ms(clock: Callable[[], int]) -> int:
    now = clock()
    if type(now) is not int or not 1_600_000_000_000 <= now <= _MAX_WALL_MS:
        raise DataValidationError("D430 invalid watchdog UTC clock")
    return now


def _fail_closed(directory: Path, category: str,
                 clock: Callable[[], int]) -> dict:
    """Do not mask failure with a previous success-looking finite sample."""
    try:
        publish_paper_watch(
            directory,
            unavailable_finite_paper_lease(sampled_at_ms=_now_ms(clock)),
        )
    except (DataValidationError, PaperWatchUnavailable, OSError,
            TypeError, ValueError):
        return _report("failclosed_publication_unavailable")
    return _report(category)


def _valid_child_result(stdout: bytes, budget: PaperTrialBudget) -> dict | None:
    if type(stdout) is not bytes or not 1 <= len(stdout) <= _MAX_STDOUT:
        return None
    try:
        # The only valid output is a single sanitized JSON object; duplicates
        # and non-standard JSON numeric constants fail closed.
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate child field")
                result[key] = value
            return result

        data = json.loads(
            stdout.decode("ascii"), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, TypeError):
        return None
    reference = _child_result("bounded_trial_completed_no_live_protection")
    if (type(data) is not dict or set(data) != set(reference)
            or data.get("schema_version") != _CHILD_SCHEMA
            or data.get("status") != "bounded_trial_completed_no_live_protection"
            or type(data.get("leases_attempted")) is not int
            or data["leases_attempted"] != budget.max_leases
            or type(data.get("leases_with_fresh_position_quotes")) is not int
            or data["leases_with_fresh_position_quotes"] != budget.max_leases
            or type(data.get("last_terminal_watch_at_ms")) is not int
            or not 1_600_000_000_000 <= data["last_terminal_watch_at_ms"] <= _MAX_WALL_MS
            or any(data.get(k) is not False for k in (
                "active_position_supervision_verified",
                "continuous_24x7_verified", "full_position_coverage_verified",
                "native_stop_verified", "real_fills_verified",
                "open_new_positions_authorized", "orders_sent",
                "live_trading_authorized", "approved_for_live_use",
                "approved_for_signals", "finite_trial_ended",
            ) if k != "finite_trial_ended")
            or data.get("finite_trial_ended") is not True
            or any(type(data.get(k)) is not int or data[k] < 0
                   for k in (
                       "quotes_forwarded_to_paper",
                       "synthetic_exit_reservation_events",
                       "reconciliation_required_events",
                       "largest_interlease_gap_ms",
                       "public_ws_reconnect_events",
                   ))):
        return None
    return data


def supervise_finite_paper_child(
    *, state_directory: Path, private_paper_directory: Path,
    watch_directory: Path, budget: PaperTrialBudget = PaperTrialBudget(),
    allow_private_pointer_read: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_synthetic_paper_reservations: bool = False,
    allow_multiple_finite_leases: bool = False,
    allow_paper_watch_output: bool = False,
    allow_child_process_watchdog: bool = False,
    clock: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> dict:
    """Watch a finite, already gated D428 child in a separate OS process.

    Success means only that the bounded subprocess terminated successfully
    and the SAME D427 owner-only terminal sample was observed. The parent
    does not trust stdout without checking that protected file.
    """
    gates = (
        allow_private_pointer_read, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        allow_synthetic_paper_reservations, allow_multiple_finite_leases,
        allow_paper_watch_output, allow_child_process_watchdog,
    )
    if any(type(flag) is not bool for flag in gates):
        raise DataValidationError("D430 opt-ins must be boolean")
    if not all(gates):
        return _report("eight_explicit_owner_optins_required")
    if (os.name != "posix" or not hasattr(os, "geteuid")
            or os.geteuid() == 0 or type(budget) is not PaperTrialBudget
            or not callable(clock)):
        raise DataValidationError("D430 nonroot POSIX bounded watchdog required")
    _validate_separate_directories(
        state_directory=state_directory,
        private_paper_directory=private_paper_directory,
        watch_directory=watch_directory,
    )
    # Never allow the previous finite watch to look current while child runs.
    _now_ms(clock)
    if _fail_closed(
        watch_directory, "child_not_started_failclosed", clock,
    )["status"] == "failclosed_publication_unavailable":
        return _report("failclosed_publication_unavailable")

    argv = [
        sys.executable, "-m", "scripts.run_j4_paper_bounded_trial_d428",
        "--state-directory", str(state_directory),
        "--private-paper-directory", str(private_paper_directory),
        "--paper-watch-directory", str(watch_directory),
        "--max-leases", str(budget.max_leases),
        "--lease-seconds", str(budget.lease_seconds),
        "--max-total-seconds", str(budget.max_total_seconds),
        "--max-gap-ms", str(budget.max_interlease_gap_ms),
        "--max-frames-per-lease", str(budget.max_frames_per_lease),
        "--allow-private-pointer-read", "--allow-public-websocket",
        "--confirm-personal-readonly-research", "--confirm-region-eligible",
        "--allow-synthetic-paper-reservations",
        "--allow-multiple-finite-leases", "--allow-paper-watch-output",
    ]
    # Fixed executable/module/flags: no caller-supplied command or shell.
    # subprocess.run terminates AND waits for its direct child on timeout.
    try:
        child = subprocess.run(
            argv, shell=False, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True, timeout=budget.max_total_seconds + 10,
        )
    except subprocess.TimeoutExpired:
        return _fail_closed(watch_directory, "child_timeout_failclosed", clock)
    except (OSError, ValueError, subprocess.SubprocessError):
        return _fail_closed(watch_directory, "child_start_failed_closed", clock)

    if type(child.returncode) is not int or child.returncode != 0:
        return _fail_closed(watch_directory, "child_exited_abnormally", clock)
    result = _valid_child_result(child.stdout, budget)
    if result is None:
        return _fail_closed(watch_directory, "child_output_unverified", clock)
    try:
        owner_sample = read_paper_watch(
            directory=watch_directory, now_ms=_now_ms(clock),
        )
    except (PaperWatchUnavailable, DataValidationError, OSError, ValueError):
        return _fail_closed(watch_directory, "child_terminal_watch_unavailable", clock)
    if (owner_sample["status"] != "finite_paper_lease_ended"
            or owner_sample["sampled_at_ms"] != result["last_terminal_watch_at_ms"]
            or owner_sample["configured_position_routes"] < 1
            or owner_sample["quote_events_forwarded"] < 1
            or owner_sample["market_lease_completed"] is not True
            or owner_sample["owner_cohort_unchanged"] is not True):
        return _fail_closed(watch_directory, "child_terminal_watch_unverified", clock)
    return _report("finite_child_ended_without_live_protection")
