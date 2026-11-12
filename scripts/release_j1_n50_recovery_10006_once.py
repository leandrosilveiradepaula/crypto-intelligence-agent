"""D312: OFF-by-default cutover after a NEW, independently audited 10006 HALT.

The previous D306 release script was pinned to another epoch (3 PITs, six
partial candles and an older systemd unit) and MUST NOT be reused now.
No production release is implied by a merge; owner/root release gate separate.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:
    pwd = None
import re
import signal
import socket
import subprocess
import time

from scripts.install_j1_n50_cutover_once import (
    _call, _show, N2_SERVICE, N2_TIMER, N50_TIMER, N50_SERVICE,
    FALLBACK_SERVICE, HOSTNAME, EXPECTED_ORIGIN, EXPECTED_N2_UNIT_HASH,
    UNIT_ROOT,
)
from scripts.preflight_j1_n50_systemd_isolation import n50_systemd_n2_quiescence
from scripts.release_j1_n50_halt_recovery_once import (
    _owner_report, _audit_live_n2_recovery, _atomic_service_replace,
    _restore_original_service, _return_to_n2,
)
from scripts.audit_j1_n50_recovery_candidate_once import EXPECTED_HALTED_EPOCH

OWNER = "cia-probe"
ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")
PYTHON = Path("/home/cia-probe/agent/ws-venv/bin/python")
ORIGINAL_SOURCE = "/home/cia-probe/agent/j1-n50-d306-main-code"
UNIT_SHA256 = {
    N50_SERVICE: "41db7486de1f007a78f95cd44fd90091b6bc616376d3f7c15aefdc1de1c82de2",
    N50_TIMER: "477ac621744c9ca180f6be4a94e6f33b5e280f57fc64434a0e5d23590662dc69",
    FALLBACK_SERVICE: "bc6c0c32e13ce2a2442cec7b85c62bb7553d63909919b1a7a2d5cc96492e3ac0",
}
_SAFE_WORKTREE = re.compile(r"/home/cia-probe/agent/[A-Za-z0-9._/-]{1,96}\Z")


def _unit_hashes_match() -> bool:
    for name, expected in UNIT_SHA256.items():
        path = UNIT_ROOT / name
        if (path.is_symlink() or not path.is_file()
                or sha256(path.read_bytes()).hexdigest() != expected):
            return False
    for name, blob in EXPECTED_N2_UNIT_HASH.items():
        path = UNIT_ROOT / name
        if (path.is_symlink() or not path.is_file()
                or _call(["/usr/bin/git", "hash-object", str(path)]) != blob):
            return False
    return True


def _valid_candidate(report: dict) -> bool:
    if type(report) is not dict:
        return False
    return (
        report.get("schema_version") == "j1-n50-recovery-candidate-v1"
        and report.get("status") == "current_halted_epoch_candidate_verified"
        and report.get("active_epoch_id") == EXPECTED_HALTED_EPOCH
        and report.get("halted_reason") == "provider_denied_owner_review"
        and report.get("owner_integrity_verified") is True
        and report.get("resume_authorized") is False
        and report.get("orders_sent") is False
        and report.get("live_trading_authorized") is False
        and report.get("marketwide_top50_verified") is False
        and report.get("network_requests") == 0
        and report.get("database_mutation_statements") == 0
        and report.get("systemd_modified") is False
        and type(report.get("published_hours")) is int
        and 1 <= report["published_hours"] <= 72
        and type(report.get("partial_contracts_at_next_hour")) is int
        and 1 <= report["partial_contracts_at_next_hour"] < 50
        and type(report.get("stored_candles")) is int
        and report["stored_candles"] >= 1200 + report["partial_contracts_at_next_hour"]
        and (report["stored_candles"] - report["partial_contracts_at_next_hour"]) % 50 == 0
        and type(report.get("last_published_end_ms")) is int
        and report["last_published_end_ms"] % 3_600_000 == 0
        and type(report.get("scope_digest_sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", report["scope_digest_sha256"]) is not None
    )


def _state(unit: str) -> dict[str, str]:
    return _show(unit)


def preflight(*, source: Path, expected_sha: str) -> dict:
    """Strict root + owner + revision/instance proof, with NO mutations."""
    if (os.name != "posix" or pwd is None or os.getuid() != 0
            or os.geteuid() != 0 or socket.gethostname() != HOSTNAME):
        raise PermissionError("wrong_root_or_host")
    if (not isinstance(source, Path) or not source.is_absolute()
            or source.is_symlink() or not source.is_dir()
            or source.resolve(strict=True) != source
            or _SAFE_WORKTREE.fullmatch(str(source)) is None
            or any(part in (".", "..") for part in source.parts)
            or str(source) == ORIGINAL_SOURCE
            or type(expected_sha) is not str
            or re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None
            or PYTHON.resolve(strict=True) != Path("/usr/bin/python3.12")):
        raise ValueError("invalid_owner_worktree_or_python")
    if _call(["/usr/bin/timedatectl", "show",
              "--property=NTPSynchronized", "--value"]) != "yes":
        raise ValueError("ntp_not_synchronized")
    owner_uid = pwd.getpwnam(OWNER).pw_uid
    for part in (source, ROOT, ROOT / "lease", ROOT / "epochs"):
        st = part.lstat()
        if (not part.is_dir() or part.is_symlink()
                or st.st_uid != owner_uid
                or st.st_mode & 0o777 != 0o700):
            raise ValueError("owner_worktree_or_root_untrusted")
    git = ["/usr/sbin/runuser", "-u", OWNER, "--",
           "/usr/bin/git", "-C", str(source)]
    if (_call(git + ["rev-parse", "HEAD"]) != expected_sha
            or _call(git + ["status", "--porcelain"])
            or _call(git + ["remote", "get-url", "origin"]) != EXPECTED_ORIGIN):
        raise ValueError("owner_worktree_sha_or_origin_drift")
    if not _unit_hashes_match():
        raise ValueError("installed_systemd_units_drift")
    if (_state(N2_TIMER) != {
            "LoadState":"loaded", "ActiveState":"active", "UnitFileState":"enabled"}
            or _state(N2_SERVICE) != {
                "LoadState":"loaded", "ActiveState":"inactive", "UnitFileState":"static"}
            or _state(N50_TIMER) != {
                "LoadState":"loaded", "ActiveState":"inactive", "UnitFileState":"disabled"}
            or _state(N50_SERVICE)["LoadState"] != "loaded"
            or _state(N50_SERVICE)["ActiveState"] not in ("failed", "inactive")
            or _state(FALLBACK_SERVICE)["LoadState"] != "loaded"):
        raise ValueError("n2_failback_state_drift")
    n2 = _audit_live_n2_recovery(source=source)
    report = _owner_report(
        source=source,
        module="scripts.audit_j1_n50_recovery_candidate_once",
        args=["--expected-epoch-id", EXPECTED_HALTED_EPOCH,
              "--allow-private-readonly-audit"],
    )
    if not _valid_candidate(report):
        raise ValueError("current_epoch_forensic_not_verified")
    original = (UNIT_ROOT / N50_SERVICE).read_text("ascii")
    old = "WorkingDirectory=" + ORIGINAL_SOURCE + "\n"
    new = "WorkingDirectory=" + str(source) + "\n"
    if (original.count(old) != 1 or original.count("OnFailure=" + FALLBACK_SERVICE + "\n") != 1
            or "ExecStartPre=" not in original or "Restart=no\n" not in original):
        raise ValueError("installed_n50_service_template_drift")
    replacement = original.replace(old, new)
    if (replacement == original or replacement.replace(new, old) != original
            or len(replacement.encode("ascii")) > 16_000):
        raise ValueError("n50_service_repoint_drift")
    return {
        "original_service": original,
        "replacement_service": replacement,
        "expected_sha": expected_sha,
        "current_halt_verified": True,
        "current_epoch_id": EXPECTED_HALTED_EPOCH,
        "halted_saved_candles": report["stored_candles"],
        "halted_published_hours": report["published_hours"],
        "halted_partial_candles": report["partial_contracts_at_next_hour"],
        "halted_scope_digest_sha256": report["scope_digest_sha256"],
        "n2_last_published_end_ms": n2["last_published_end_ms"],
        "n2_integrity_verified": True,
    }


def _base() -> dict:
    return {
        "schema_version": "j1-n50-d312-release-v1",
        "status": "blocked", "preflight_verified": False,
        "current_halt_verified": False,
        "new_epoch_started": False, "n50_timer_enabled": False,
        "n50_service_repointed": False,
        "n2_restored_after_failure": None,
        "previous_service_restored": None,
        "systemd_modified": False,
        "network_requests": 0,
        "failure_category": None,
        "database_mutation_statements": 0,
        "orders_sent": False,
        "live_trading_authorized": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
    }


def execute(*, source: Path, expected_sha: str,
            confirm_recovery_cutover: bool = False,
            allow_systemd_modifications: bool = False) -> dict:
    out = _base()
    gate = preflight(source=source, expected_sha=expected_sha)
    out["preflight_verified"] = True
    out["current_halt_verified"] = gate["current_halt_verified"]
    # Without BOTH flags, there is no systemctl write, no HTTP GET and no
    # archive/active SQLite modification. Checking preflight is not a release.
    if confirm_recovery_cutover is not True or allow_systemd_modifications is not True:
        out["status"] = "preflight_pass_no_changes"
        return out
    now = time.time_ns() // 1_000_000
    # Need enough time for bounded 372-GET fresh census, but NEVER retry
    # 10006. No same-hour reuse of an old lease/claim is allowed.
    if not 65_000 <= now % 3_600_000 <= 110_000:
        out["status"] = "early_utc_close_window_required"
        return out
    changed = False
    service_changed = False
    previous_signal = signal.getsignal(signal.SIGTERM)
    def fail_signal(_number, _frame):
        raise InterruptedError("d312_release_interrupted")
    signal.signal(signal.SIGTERM, fail_signal)
    try:
        if (_state(N2_SERVICE)["ActiveState"] != "inactive"
                or _state(N2_TIMER)["ActiveState"] != "active"):
            raise RuntimeError("n2_isolation_not_ready")
        changed = True
        _call(["/usr/bin/systemctl", "disable", "--now", N2_TIMER], timeout=40)
        isolation = n50_systemd_n2_quiescence(require_n2_quiesced=True)
        if isolation.get("status") != "n2_quiesced_preflight_only":
            raise RuntimeError("n2_isolation_failed")
        # This owner script replays the CURRENT HALT and creates a NEW epoch.
        # It never clears, patches, resumes or retcons the halted SQLite.
        result = _owner_report(
            source=source,
            module="scripts.recover_j1_n50_halted_epoch_once",
            args=["--confirm-halt-reviewed", "--allow-fresh-public-census"],
            allow_dataerr=True,
        )
        attempts = result.get("requests_attempted")
        if type(attempts) is int and 0 <= attempts <= 500:
            out["network_requests"] = attempts
        from crypto_intelligence_agent.j1_rest_incremental_owner import _ALLOWED_FAILURES
        fail = result.get("failure_category")
        if type(fail) is str and fail in _ALLOWED_FAILURES:
            out["failure_category"] = fail
        if (result.get("status") != "new_epoch_sealed_old_halt_preserved"
                or result.get("old_epoch_preserved") is not True
                or result.get("old_journal_sha256_unchanged") is not True
                or result.get("old_scope_sha256_unchanged") is not True
                or result.get("new_scope_created") is not True
                or result.get("orders_sent") is not False):
            raise RuntimeError("owner_new_epoch_recovery_not_verified")
        out["new_epoch_started"] = True
        service_changed = True
        _atomic_service_replace(gate["replacement_service"], suffix="d312-install")
        _call(["/usr/bin/systemctl", "daemon-reload"], timeout=30)
        _call(["/usr/bin/systemd-analyze", "verify",
               str(UNIT_ROOT / N50_SERVICE), str(UNIT_ROOT / N50_TIMER),
               str(UNIT_ROOT / FALLBACK_SERVICE)], timeout=30)
        if sha256((UNIT_ROOT / N50_SERVICE).read_bytes()).hexdigest() != sha256(
                gate["replacement_service"].encode("ascii")).hexdigest():
            raise RuntimeError("n50_service_install_hash_drift")
        out["n50_service_repointed"] = True
        _call(["/usr/bin/systemctl", "reset-failed", N50_SERVICE], timeout=20)
        _call(["/usr/bin/systemctl", "enable", "--now", N50_TIMER], timeout=40)
        if (_state(N2_TIMER) != {
                "LoadState":"loaded", "ActiveState":"inactive", "UnitFileState":"disabled"}
                or _state(N50_TIMER) != {
                    "LoadState":"loaded", "ActiveState":"active", "UnitFileState":"enabled"}
                or _state(N2_SERVICE)["ActiveState"] != "inactive"):
            raise RuntimeError("n50_cutover_postflight_failed")
        out["status"] = "new_n50_epoch_timer_enabled"
        out["n50_timer_enabled"] = True
        out["systemd_modified"] = True
        return out
    except (OSError, ValueError, TypeError, RuntimeError, InterruptedError,
            subprocess.TimeoutExpired):
        if changed:
            out["n2_restored_after_failure"] = _return_to_n2()
            if service_changed:
                out["previous_service_restored"] = _restore_original_service(
                    gate["original_service"]
                )
            out["systemd_modified"] = True
            safe = (out["n2_restored_after_failure"] is True
                    and (not service_changed or out["previous_service_restored"] is True))
            out["status"] = "rolled_back_to_n2" if safe else "CRITICAL_rollback_unverified"
        return out
    finally:
        signal.signal(signal.SIGTERM, previous_signal)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--confirm-recovery-cutover", action="store_true")
    p.add_argument("--allow-systemd-modifications", action="store_true")
    try:
        out = execute(**vars(p.parse_args(argv)))
    except (OSError, RuntimeError, ValueError, PermissionError, TypeError,
            subprocess.TimeoutExpired, json.JSONDecodeError):
        out = _base()
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if out["status"] in (
        "preflight_pass_no_changes", "new_n50_epoch_timer_enabled",
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
