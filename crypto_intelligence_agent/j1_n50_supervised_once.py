"""D291: one supervised N50 REST research hour via the EXISTING D287/M1 writer.

No scheduler or daemon. All execution is OFF until explicit owner opt-ins.
No implicit bootstrap from a missing/corrupted DB, no changing existing scope,
no auth/private endpoints or trading. D290 plan is evaluated before GET.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from crypto_intelligence_agent.j1_n50_supervision import plan_n50_supervision
from crypto_intelligence_agent.j1_rest_incremental_owner import _DB_NAME
from crypto_intelligence_agent.j1_rest_resume_readiness import audit_existing_rest_resume
from scripts.audit_bybit_marketwide_closed24h import _strict_owner
from scripts.run_j1_current_ranked_epoch_once import (
    load_private_ranked_scope, run_current_ranked_epoch_once,
)


def _report(status: str, reason: str = "") -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-supervised-hourly-once-v1",
        "status": status,
        "reason": reason,
        "decision_action": "none",
        "selected_research_contracts": 0,
        "new_closed_candles": 0,
        "requests_attempted": 0,
        "manifest_modified": False,
        "other_journals_modified": False,
        "systemd_modified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def run_supervised_n50_once(
    *, manifest_directory: Path, output_directory: Path,
    allow_private_manifest_read: bool = False,
    allow_private_readonly_audit: bool = False,
    allow_public_network: bool = False,
    allow_private_storage: bool = False,
    confirm_region_and_personal_research: bool = False,
    enable_n50_research_once: bool = False,
    owner_ok: bool | None = None,
    clock_ms=None,
    client=None,
) -> dict[str, Any]:
    """Execute one *permitted* current UTC hour, never a future/background job.

    A new epoch is bootstrapped ONLY if its output dir is owner-only EMPTY.
    An existing journal must pass full private read-only audit and bind to
    the sealed scope digest. All calls to the actual REST writer go through
    D287, which owns the flock, cursor, digest and fail-stop provider rules.
    """
    out = _report("optin_required")
    if (allow_private_manifest_read is not True
            or allow_private_readonly_audit is not True
            or allow_public_network is not True
            or allow_private_storage is not True
            or confirm_region_and_personal_research is not True
            or enable_n50_research_once is not True):
        return out
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if owner is not True:
        return _report("blocked", "nonroot_owner_required")
    if (not isinstance(manifest_directory, Path)
            or not isinstance(output_directory, Path)
            or not manifest_directory.is_absolute()
            or not output_directory.is_absolute()
            or manifest_directory == output_directory
            or manifest_directory in output_directory.parents
            or output_directory in manifest_directory.parents):
        return _report("blocked", "private_path_invalid")
    clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
    try:
        now = clock()
        if type(now) is not int:
            return _report("blocked", "invalid_clock")
        _strict_owner(output_directory, directory=True)
        scope = load_private_ranked_scope(manifest_directory, now_ms=now)
        db_path = output_directory / _DB_NAME
        if db_path.is_symlink():
            return _report("blocked", "journal_symlink_rejected")
        if db_path.is_file():
            audit = audit_existing_rest_resume(
                output_directory=output_directory, now_ms=now,
                allow_private_readonly_audit=True, expected_members=50,
                owner_ok=owner,
            )
        else:
            # Never assume that a missing DB means a fresh start: all files,
            # including abandoned locks, must be absent to permit bootstrap.
            if list(output_directory.iterdir()):
                return _report("blocked", "existing_epoch_without_journal")
            audit = None
        decision = plan_n50_supervision(
            now_ms=now, sealed_scope=scope, audit=audit,
        )
        if decision.action not in (
            "bootstrap_new_empty_epoch", "run_existing_epoch_once"
        ):
            out = _report(
                "deferred" if decision.status in ("deferred", "no_op")
                else "blocked", decision.reason,
            )
            out["decision_action"] = decision.action
            return out
        # Still needs all six explicit opt-ins above. Revalidation inside
        # the D287 runner and M1 writer catches scope/time changes and races.
        result = run_current_ranked_epoch_once(
            manifest_directory=manifest_directory,
            output_directory=output_directory,
            allow_private_manifest_read=True,
            allow_public_network=True,
            allow_private_storage=True,
            confirm_region_and_personal_research=True,
            owner_ok=owner, clock_ms=clock, client=client,
        )
        out = _report(
            "research_hour_persisted"
            if result.get("status") == "research_sample_closed_hour_persisted"
            else "blocked",
            "delegated_to_existing_m1_writer",
        )
        out["decision_action"] = decision.action
        out["selected_research_contracts"] = result.get(
            "selected_research_contracts", 0)
        out["new_closed_candles"] = result.get("new_closed_candles", 0)
        out["requests_attempted"] = result.get("requests_attempted", 0)
        if (result.get("orders_sent") is not False
                or result.get("marketwide_top50_verified") is not False
                or result.get("live_trading_authorized") is not False
                or result.get("frozen_history_modified") is not False):
            return _report("blocked", "unexpected_writer_safety_flags")
        return out
    except (OSError, ValueError, TypeError, UnicodeError,
            OverflowError):
        return _report("blocked", "private_integrity_or_environment_rejected")
