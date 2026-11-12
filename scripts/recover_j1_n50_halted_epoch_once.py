"""D306: one expressly gated, owner-only N50 HALT recovery into a NEW epoch.

Never reopens or clears the halted journal. Requires N2 OFF (including reboot
state); a separate reversible root release owns N2/N50 systemd transitions.
Not used by the installed recurring N50 unit or any unopted caller.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from crypto_intelligence_agent.j1_n50_managed_cycle import (
    managed_n50_tick_once, _pointer_read,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import _DB_NAME
from crypto_intelligence_agent.j1_rest_resume_readiness import MAX_DB_BYTES
from scripts.audit_bybit_marketwide_closed24h import _strict_owner
from scripts.preflight_j1_n50_systemd_isolation import n50_systemd_n2_quiescence

ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")


def _result(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-halt-recovery-once-v1",
        "status": status, "reason": None,
        "old_epoch_preserved": False, "new_epoch_id": None,
        "old_journal_sha256_unchanged": False,
        "old_scope_sha256_unchanged": False,
        "new_scope_created": False,
        "new_candles_stored": 0,
        "requests_attempted": 0, "failure_category": None,
        "systemd_modified": False, "orders_sent": False,
        "marketwide_top50_verified": False,
        "continuous_collector_verified": False,
        "live_trading_authorized": False,
    }


def _owner_sha(path: Path) -> str:
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_DB_BYTES):
        raise ValueError("private_file_untrusted")
    _strict_owner(path, directory=False)
    digest = sha256()
    with path.open("rb") as handle:
        while data := handle.read(1024*1024):
            digest.update(data)
    return digest.hexdigest()


def recover_halted_epoch_once(
    *, root_directory: Path = ROOT,
    confirm_halt_reviewed: bool = False,
    allow_fresh_public_census: bool = False,
    owner_ok: bool | None = None,
    clock_ms=None,
    client=None,
    isolation_reader=n50_systemd_n2_quiescence,
) -> dict[str, Any]:
    """One bounded fresh capture, not a daemon or attempt to resume old epoch."""
    if confirm_halt_reviewed is not True or allow_fresh_public_census is not True:
        return _result("optin_required")
    if (not isinstance(root_directory, Path)
            or not root_directory.is_absolute()
            or root_directory.is_symlink()):
        return _result("blocked")
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if owner is not True:
        return _result("blocked")
    out = _result("blocked")
    try:
        # Root must disable N2 timer *first* under the separate rollback gate.
        gate = isolation_reader(require_n2_quiesced=True)
        if (gate.get("status") != "n2_quiesced_preflight_only"
                or gate.get("n2_timer_disabled") is not True
                or gate.get("n2_service_inactive") is not True
                or gate.get("orders_sent") is not False):
            out["reason"] = "n2_not_quiesced"
            return out
        _strict_owner(root_directory, directory=True)
        pointer = _pointer_read(root_directory)
        if pointer is None:
            out["reason"] = "active_halted_epoch_missing"
            return out
        old = root_directory/"epochs"/pointer["epoch_id"]
        for path in (old,old/"scope",old/"journal"):
            if path.is_symlink():
                return out
            _strict_owner(path, directory=True)
        from crypto_intelligence_agent.j1_auto_research_epoch import FILE_NAME
        old_db = old/"journal"/_DB_NAME
        old_scope = old/"scope"/FILE_NAME
        journal_before = _owner_sha(old_db)
        scope_before = _owner_sha(old_scope)
        result = managed_n50_tick_once(
            root_directory=root_directory,
            allow_public_network=True,
            allow_private_storage=True,
            allow_private_manifest_read=True,
            allow_private_readonly_audit=True,
            allow_private_manifest_write=True,
            confirm_region_and_personal_research=True,
            enable_managed_n50_tick=True,
            recover_halted_epoch_once=True,
            owner_ok=owner, clock_ms=clock_ms, client=client,
        )
        out["requests_attempted"] = result.get("requests_attempted",0)
        failure = result.get("failure_category")
        if failure is not None and type(failure) is str:
            from crypto_intelligence_agent.j1_rest_incremental_owner import _ALLOWED_FAILURES
            if failure in _ALLOWED_FAILURES:
                out["failure_category"] = failure
        if (result.get("status") != "epoch_recovered_from_halt"
                or result.get("halted_epoch_recovery_verified") is not True
                or result.get("previous_epoch_preserved") is not True
                or result.get("orders_sent") is not False):
            out["reason"] = "fresh_capture_failed_or_forensic_gate_denied"
            return out
        current = _pointer_read(root_directory)
        if (current is None or current["epoch_id"] == pointer["epoch_id"]
                or current["epoch_id"] != result.get("epoch_id")):
            out["reason"] = "new_pointer_not_verified"
            return out
        out["old_journal_sha256_unchanged"] = _owner_sha(old_db) == journal_before
        out["old_scope_sha256_unchanged"] = _owner_sha(old_scope) == scope_before
        out["old_epoch_preserved"] = (
            out["old_journal_sha256_unchanged"] and
            out["old_scope_sha256_unchanged"]
        )
        if not out["old_epoch_preserved"]:
            out["reason"] = "old_epoch_modified"
            return out
        out["new_scope_created"] = True
        out["new_epoch_id"] = current["epoch_id"]
        out["status"] = "new_epoch_sealed_old_halt_preserved"
        return out
    except (OSError,ValueError,TypeError,OverflowError):
        out["reason"] = "private_integrity_or_environment_rejected"
        return out


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm-halt-reviewed",action="store_true")
    p.add_argument("--allow-fresh-public-census",action="store_true")
    opts=p.parse_args(argv)
    report=recover_halted_epoch_once(**vars(opts))
    print(json.dumps(report,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if report["status"]=="new_epoch_sealed_old_halt_preserved" else 65


if __name__=="__main__":
    raise SystemExit(main())
