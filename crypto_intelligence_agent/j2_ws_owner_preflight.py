"""J2/J3 #656: no-write operational preflight for the existing WS owner ledger.

Only a read-only replay of the *current* J1 WS cohort is permitted, after
the owner, DAC, clock and opt-in gates. This never captures, scores or trades.
"""
from __future__ import annotations

import os
import stat
import subprocess
import time
from typing import Any

from .bybit_closed_stream_cache import HOUR_MS
from . import j2_ws_prospective_ledger as ledger
from .market_data import DataValidationError


def _report(status: str) -> dict[str, Any]:
    # Explicit allowlist: no symbols, prices, directory names or raw snapshots.
    return {
        "schema_version": "j2-ws-owner-preflight-v1",
        "status": status,
        "owner_nonroot_posix_verified": False,
        "owner_ledger_parent_dac_verified": False,
        "ledger_directory_exists": False,
        "os_ntp_sync_reported": False,
        "capture_window_open": False,
        "owner_ws_50x24_readonly_replayed": False,
        "capture_eligible_now": False,
        "reference_utc_closed_end_ms": None,
        "score_horizons_hours": [1, 4, 8],
        "score_requires_existing_prior_decision": True,
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


def _os_ntp_synchronized() -> bool:
    """Use a bounded OS-only check; never assume NTP from a plausible date."""
    try:
        completed = subprocess.run(
            ["/usr/bin/timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, check=False, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return False
    return completed.returncode == 0 and completed.stdout.strip() == "yes"


def _read_only_ledger_dac() -> bool:
    """Return whether the dedicated ledger already exists; NEVER mkdir/chmod.

    The owner parent must be trusted even for a future atomic create. Existing
    ledgers reuse the original ledger's validation instead of a second policy.
    """
    root = ledger.LEDGER_ROOT
    parent = root.parent
    if parent.is_symlink():
        raise DataValidationError("owner parent link")
    info = parent.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o022):
        raise DataValidationError("owner parent DAC invalid")
    try:
        root.lstat()
    except FileNotFoundError:
        return False
    ledger._owner_directory(create=False)
    return True


def preflight_owner_ws_decision_once(
    *, allow_private_readonly_research: bool = False,
) -> dict[str, Any]:
    """Read-only readiness check; no caller-supplied clock or arbitrary paths.

    The private J1 owner reader is used unchanged. A ready result only means
    an owner *may* separately request one capture; it creates no evidence.
    """
    if allow_private_readonly_research is not True:
        return _report("owner_read_optin_required")
    result = _report("owner_preflight_abstain")
    try:
        ledger._owner_guard()
        result["owner_nonroot_posix_verified"] = True
        result["ledger_directory_exists"] = _read_only_ledger_dac()
        result["owner_ledger_parent_dac_verified"] = True
    except (OSError, ValueError, TypeError, DataValidationError):
        result["status"] = "owner_preflight_dac_abstain"
        return result

    if not _os_ntp_synchronized():
        result["status"] = "owner_os_clock_sync_unverified"
        return result
    result["os_ntp_sync_reported"] = True

    now = time.time_ns() // 1_000_000
    end = now - now % HOUR_MS
    result["reference_utc_closed_end_ms"] = end
    if not 180_000 <= now-end < HOUR_MS-60_000:
        result["status"] = "owner_capture_window_closed"
        return result
    result["capture_window_open"] = True

    try:
        # Reuses D624/D348 and their existing dual audit, epoch and 50x24
        # guards. Private rows remain in memory; they are never serialized.
        snapshot, _private_closes = ledger._private_source(now)
        after = time.time_ns() // 1_000_000
        if (snapshot["latest_closed_end_ms"] != end
                or after < now
                or after >= end + HOUR_MS-60_000
                or after // HOUR_MS != now // HOUR_MS):
            result["status"] = "owner_clock_or_epoch_shift_abstain"
            return result
    except (OSError, ValueError, KeyError, TypeError, OverflowError,
            UnicodeError, DataValidationError):
        result["status"] = "owner_ws_50x24_unavailable"
        return result

    result["owner_ws_50x24_readonly_replayed"] = True
    result["capture_eligible_now"] = True
    result["status"] = "owner_preflight_ready_no_capture"
    return result
