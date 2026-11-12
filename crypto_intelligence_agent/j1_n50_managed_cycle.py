"""D294: one owner-only managed N50 research tick with immutable epoch rotation.

No daemon, schedule, deployment, trading or credentials. The D293 shared
lock coordinates the D286/D287 census versus the D291/D292 M1 writer. A
separate manager flock serializes pointer transitions and preserves every
prior epoch and its journal.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Callable

try:
    import fcntl
except ImportError:
    fcntl = None

from .j1_auto_research_epoch import (
    HOUR_MS, MAX_SCOPE_AGE_MS, FILE_NAME,
)
from .j1_n50_supervision import RENEWAL_DUE_MS
from .j1_n50_global_lease import (
    coordinated_n50_once, _read_claim,
)
from scripts.audit_bybit_marketwide_closed24h import (
    _new_private_file, _strict_owner,
)
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

MANAGER_LOCK = ".n50-manager.lock"
ACTIVE_FILE = "n50-active-epoch.json"
EPOCH_RE = re.compile(r"epoch-[0-9]{13}\Z")
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
ACTIVE_SCHEMA = "j1-n50-managed-active-v1"
MAX_POINTER_BYTES = 512


def _out(status: str, reason: str = "") -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-managed-tick-v1",
        "status": status, "reason": reason,
        "operation": "none", "epoch_id": None,
        "claims_created": 0, "pointer_updated": False,
        "new_closed_candles": 0, "requests_attempted": 0,
        "failure_category": None,
        "halted_epoch_recovery_verified": False,
        "previous_epoch_preserved": False,
        "network_accessed": False, "trading_enabled": False,
        "systemd_modified": False, "other_journals_modified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "orders_sent": False,
    }


def _pointer_read(root: Path) -> dict | None:
    path = root / ACTIVE_FILE
    if not path.exists() and not path.is_symlink():
        return None
    _strict_owner(path, directory=False)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o600
                or not 0 < st.st_size <= MAX_POINTER_BYTES):
            raise ValueError("active_pointer_invalid")
        with os.fdopen(fd, "rb", closefd=False) as src:
            raw = src.read(MAX_POINTER_BYTES + 1)
    finally:
        os.close(fd)
    def strict_pairs(pairs):
        result = {}
        for key,value in pairs:
            if key in result:
                raise ValueError("active_pointer_duplicate_key")
            result[key] = value
        return result
    obj = json.loads(raw.decode("ascii"), object_pairs_hook=strict_pairs)
    if (type(obj) is not dict or set(obj) != {
            "schema_version","epoch_id","scope_digest_sha256",
            "catalog_post_observed_at_ms"}
            or obj["schema_version"] != ACTIVE_SCHEMA
            or type(obj["epoch_id"]) is not str
            or EPOCH_RE.fullmatch(obj["epoch_id"]) is None
            or type(obj["scope_digest_sha256"]) is not str
            or SHA_RE.fullmatch(obj["scope_digest_sha256"]) is None
            or type(obj["catalog_post_observed_at_ms"]) is not int):
        raise ValueError("active_pointer_invalid")
    return obj


def _pointer_write(root: Path, pointer: dict, *, decision: int) -> None:
    target = root / ACTIVE_FILE
    if target.exists() or target.is_symlink():
        _strict_owner(target, directory=False)
    tmp = root / f".n50-pointer-{decision:013d}.tmp"
    raw = (json.dumps(pointer, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=True).encode("ascii")
           + b"\n")
    if len(raw) > MAX_POINTER_BYTES:
        raise ValueError("pointer_oversize")
    if tmp.exists() or tmp.is_symlink():
        # A crash may occur AFTER writing/fsync and BEFORE atomic rename.
        # Only the SAME fully valid payload is adoptable, never a partial
        # file, modified target or symlink. Leave mismatches for owner review.
        _strict_owner(tmp, directory=False)
        fd = os.open(tmp, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or st.st_uid != os.geteuid()
                    or stat.S_IMODE(st.st_mode) != 0o600
                    or st.st_size != len(raw)):
                raise ValueError("pointer_staged_invalid")
            with os.fdopen(fd, "rb", closefd=False) as src:
                if src.read(MAX_POINTER_BYTES + 1) != raw:
                    raise ValueError("pointer_staged_drift")
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as dest:
                dest.write(raw)
                dest.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
    os.replace(tmp, target)
    dir_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _epoch_dirs(epochs: Path, *, decision: int) -> tuple[str, Path, Path]:
    name = f"epoch-{decision:013d}"
    if EPOCH_RE.fullmatch(name) is None:
        raise ValueError("invalid_epoch_id")
    root = epochs / name
    if not root.exists() and not root.is_symlink():
        root.mkdir(mode=0o700)
    _strict_owner(root, directory=True)
    if root.is_symlink():
        raise ValueError("epoch_symlink")
    scope = root / "scope"
    journal = root / "journal"
    for p in (scope, journal):
        if not p.exists() and not p.is_symlink():
            p.mkdir(mode=0o700)
        _strict_owner(p, directory=True)
        if p.is_symlink():
            raise ValueError("epoch_path_symlink")
    if set(x.name for x in root.iterdir()) != {"scope", "journal"}:
        raise ValueError("unexpected_epoch_files")
    return name, scope, journal


def _verify_capture_claim(lock_directory: Path, *, decision: int,
                          scope: Path) -> None:
    path = lock_directory / f"claim-{decision:013d}.json"
    claim = _read_claim(path)
    target = sha256(json.dumps(
        ["capture_seal", str(scope), ""], separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")).hexdigest()
    if claim != {
        "schema_version": "j1-n50-one-action-hour-v1",
        "action": "capture_seal",
        "decision_end_ms": decision,
        "target_sha256": target,
    }:
        raise ValueError("capture_claim_missing_or_mismatched")


def managed_n50_tick_once(
    *, root_directory: Path,
    allow_public_network: bool = False,
    allow_private_storage: bool = False,
    allow_private_manifest_read: bool = False,
    allow_private_readonly_audit: bool = False,
    allow_private_manifest_write: bool = False,
    confirm_region_and_personal_research: bool = False,
    enable_managed_n50_tick: bool = False,
    recover_halted_epoch_once: bool = False,
    owner_ok: bool | None = None,
    clock_ms: Callable[[], int] | None = None,
    client=None,
) -> dict[str, Any]:
    """Choose either one capture+rotation OR one writer per current UTC hour."""
    if (enable_managed_n50_tick is not True
            or allow_public_network is not True
            or allow_private_storage is not True
            or allow_private_manifest_read is not True
            or allow_private_readonly_audit is not True
            or allow_private_manifest_write is not True
            or confirm_region_and_personal_research is not True):
        return _out("optin_required")
    permitted = ((os.name == "posix" and fcntl is not None
                  and os.getuid() == os.geteuid() and os.geteuid() != 0)
                 if owner_ok is None else owner_ok)
    if (permitted is not True or fcntl is None
            or type(recover_halted_epoch_once) is not bool):
        return _out("blocked", "posix_owner_required")
    if not isinstance(root_directory, Path) or not root_directory.is_absolute():
        return _out("blocked", "invalid_root")
    clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
    try:
        now = clock()
        if type(now) is not int or not 1_600_000_000_000 <= now < 4_102_444_800_000:
            return _out("blocked", "invalid_clock")
        decision = now // HOUR_MS * HOUR_MS
        if not 60_000 <= now-decision <= 900_000:
            return _out("deferred", "outside_utc_close_window")
        _strict_owner(root_directory, directory=True)
        if (root_directory.is_symlink()
                or root_directory.resolve(strict=True) != root_directory):
            return _out("blocked", "root_alias")
        lock_directory = root_directory / "lease"
        epochs = root_directory / "epochs"
        for path in (lock_directory, epochs):
            _strict_owner(path, directory=True)
            if path.is_symlink():
                return _out("blocked", "untrusted_owner_dir")
        guard = root_directory / MANAGER_LOCK
        if not guard.exists() and not guard.is_symlink():
            _new_private_file(guard)
        _strict_owner(guard, directory=False)
        fd = os.open(guard, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return _out("blocked", "manager_lock_busy")
            active = _pointer_read(root_directory)
            if recover_halted_epoch_once and active is None:
                return _out("blocked", "halted_recovery_requires_active_epoch")
            recovery_verified = False
            age = None
            if active is not None:
                active_root = epochs / active["epoch_id"]
                scope = active_root / "scope"
                journal = active_root / "journal"
                _strict_owner(active_root, directory=True)
                _strict_owner(scope, directory=True)
                _strict_owner(journal, directory=True)
                # Recheck old scope at the last valid instant even after
                # expiry, ONLY to choose a new capture, never to trade.
                snapshot = load_private_ranked_scope(
                    scope, now_ms=min(now,active["catalog_post_observed_at_ms"]
                                             + MAX_SCOPE_AGE_MS),
                )
                if (snapshot["scope_digest_sha256"] != active["scope_digest_sha256"]
                        or snapshot["catalog_post_observed_at_ms"]
                           != active["catalog_post_observed_at_ms"]):
                    return _out("blocked", "active_scope_drift")
                age = now - active["catalog_post_observed_at_ms"]
                if age < 0:
                    return _out("blocked", "future_active_scope")
                if recover_halted_epoch_once:
                    # Never clear the HALT or reuse the saved 6 partial candles.
                    # A new frozen epoch is the ONLY recovery action.
                    from .j1_n50_halted_forensic import audit_halted_n50_epoch
                    verified = audit_halted_n50_epoch(
                        scope_directory=scope, journal_directory=journal,
                        allow_private_readonly_audit=True, owner_ok=permitted,
                        now_ms=now,
                    )
                    if (verified.get("status") != "halted_owner_review_verified"
                            or verified.get("saved_rows_integrity_verified") is not True
                            or verified.get("halted_reason") !=
                               "provider_denied_owner_review"
                            or verified.get("scope_digest_sha256") !=
                               active["scope_digest_sha256"]
                            or verified.get("historical_missing_publication_hours") != 0
                            or verified.get("resume_authorized") is not False
                            or verified.get("orders_sent") is not False
                            or verified.get("network_requests") != 0
                            or verified.get("database_mutation_statements") != 0):
                        return _out("blocked", "halted_recovery_forensic_gate_failed")
                    recovery_verified = True
            rotate = (active is None or age >= RENEWAL_DUE_MS
                      or recovery_verified)
            if rotate:
                epoch_id, new_scope, new_journal = _epoch_dirs(
                    epochs,decision=decision)
                new_file = new_scope / FILE_NAME
                if next(new_journal.iterdir(), None) is not None:
                    return _out("blocked", "new_epoch_journal_not_empty")
                if new_file.is_file() and not new_file.is_symlink():
                    # Crash between successful capture and pointer update.
                    # Adopt only a D287 sealed scope with the exact D293
                    # durable capture claim for this SAME UTC close.
                    _verify_capture_claim(
                        lock_directory,decision=decision,scope=new_scope)
                    result = {"status":"sealed_current_auto_rank_research_scope_only",
                              "requests_attempted":0,"claims_created":0}
                else:
                    if new_file.is_symlink() or next(new_scope.iterdir(),None) is not None:
                        return _out("blocked", "incomplete_scope_not_adoptable")
                    result = coordinated_n50_once(
                        lock_directory=lock_directory,action="capture_seal",
                        manifest_directory=new_scope,
                        allow_public_network=True,
                        allow_private_manifest_write=True,
                        confirm_region_and_personal_research=True,
                        enable_coordinated_n50_once=True,
                        owner_ok=permitted,clock_ms=clock,client=client,
                    )
                if result["status"] not in (
                        "capture_sealed","sealed_current_auto_rank_research_scope_only"):
                    denied=_out("blocked", "current_rank_capture_abstained")
                    count=result.get("requests_attempted")
                    if type(count) is int and 0<=count<=500:
                        denied["requests_attempted"]=count
                        denied["network_accessed"]=count>0
                    claims=result.get("claims_created")
                    if type(claims) is int and 0<=claims<=1:
                        denied["claims_created"]=claims
                    # Do not copy arbitrary provider messages into logs.
                    from crypto_intelligence_agent.j1_rest_incremental_owner import (
                        _ALLOWED_FAILURES,
                    )
                    failure=result.get("failure_category")
                    if type(failure) is str and failure in _ALLOWED_FAILURES:
                        denied["failure_category"]=failure
                    return denied
                fresh = load_private_ranked_scope(new_scope, now_ms=clock())
                if fresh["closed_hour_end_ms"] != decision:
                    return _out("blocked","capture_clock_drift")
                new_pointer = {
                    "schema_version": ACTIVE_SCHEMA, "epoch_id": epoch_id,
                    "scope_digest_sha256": fresh["scope_digest_sha256"],
                    "catalog_post_observed_at_ms":
                        fresh["catalog_post_observed_at_ms"],
                }
                _pointer_write(root_directory,new_pointer,decision=decision)
                out=_out(
                    "epoch_recovered_from_halt" if recovery_verified
                    else "epoch_rotated" if active else "epoch_started"
                )
                out["halted_epoch_recovery_verified"] = recovery_verified
                out["previous_epoch_preserved"] = bool(active)
                out["operation"]="capture_seal"
                out["epoch_id"]=epoch_id
                out["pointer_updated"]=True
                out["claims_created"]=result.get("claims_created",0)
                out["requests_attempted"]=result.get("requests_attempted",0)
                out["network_accessed"]=out["requests_attempted"] > 0
                return out
            result=coordinated_n50_once(
                lock_directory=lock_directory,action="hourly_writer",
                manifest_directory=scope,output_directory=journal,
                allow_public_network=True,allow_private_storage=True,
                allow_private_manifest_read=True,
                allow_private_readonly_audit=True,
                confirm_region_and_personal_research=True,
                enable_coordinated_n50_once=True,
                owner_ok=permitted,clock_ms=clock,client=client,
            )
            out=_out(result["status"],result.get("reason",""))
            out["operation"]="hourly_writer"
            out["epoch_id"]=active["epoch_id"]
            out["claims_created"]=result.get("claims_created",0)
            out["new_closed_candles"]=result.get("new_closed_candles",0)
            out["requests_attempted"]=result.get("requests_attempted",0)
            out["network_accessed"]=out["requests_attempted"] > 0
            from crypto_intelligence_agent.j1_rest_incremental_owner import _ALLOWED_FAILURES
            failure = result.get("failure_category")
            if type(failure) is str and failure in _ALLOWED_FAILURES:
                out["failure_category"] = failure
            return out
        finally:
            try:
                fcntl.flock(fd,fcntl.LOCK_UN)
            finally:
                os.close(fd)
    except (ValueError,OSError,TypeError,UnicodeError,OverflowError,
            json.JSONDecodeError):
        return _out("blocked","managed_integrity_or_environment_rejected")
