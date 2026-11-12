"""D293: serialize N50 catalog refresh and hourly writer on ONE owner lock.

No timer, production deployment, private API or order capability.
The same UTC close may execute only ONE action+target contract; retrying an
identical action preserves existing per-epoch idempotency and D292 recovery.
The durable claim is NOT a market PIT or a trading authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
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

from scripts.audit_bybit_marketwide_closed24h import _strict_owner, _new_private_file
from scripts.run_j1_current_ranked_epoch_once import capture_and_seal_current_rank_once
from crypto_intelligence_agent.j1_n50_supervised_once import run_supervised_n50_once

HOUR_MS = 3_600_000
MIN_PHASE_MS = 60_000
MAX_PHASE_MS = 15 * 60_000
LOCK_FILE = ".n50-census-writer.lock"
CLAIM_PATTERN = re.compile(r"claim-[0-9]{13}\\.json\\Z")
MAX_CLAIM_BYTES = 700
_ACTIONS = frozenset(("capture_seal", "hourly_writer"))


def _report(status: str, reason: str = "") -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-global-lease-v1",
        "status": status, "reason": reason,
        "action": "none", "decision_end_ms": None,
        "requests_attempted": 0,
        "new_closed_candles": 0,
        "claims_created": 0,
        "other_journals_modified": False,
        "systemd_modified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def _read_claim(path: Path) -> dict:
    _strict_owner(path, directory=False)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1
                or not 0 < st.st_size <= MAX_CLAIM_BYTES):
            raise ValueError("claim_invalid")
        with os.fdopen(fd, "rb", closefd=False) as fp:
            raw = fp.read(MAX_CLAIM_BYTES + 1)
    finally:
        os.close(fd)
    def pairs(p):
        result = {}
        for key,value in p:
            if key in result:
                raise ValueError("duplicate_claim_key")
            result[key] = value
        return result
    return json.loads(raw.decode("ascii"), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("nonfinite_claim")))


def _record_claim(directory: Path, *, decision: int, action: str,
                  target_digest: str) -> bool:
    """Create or replay a fixed durable action claim under an exclusive flock.

    Do NOT overwrite an earlier action or its target. A failed process can
    retry only the exact same action and target in the same UTC close.
    """
    path = directory / f"claim-{decision:013d}.json"
    if not CLAIM_PATTERN.fullmatch(path.name):
        raise ValueError("invalid_claim_name")
    claim = {"schema_version": "j1-n50-one-action-hour-v1",
             "action": action, "decision_end_ms": decision,
             "target_sha256": target_digest}
    raw = json.dumps(claim, sort_keys=True, separators=(",", ":")).encode("ascii")+b"\n"
    if len(raw) > MAX_CLAIM_BYTES:
        raise ValueError("claim_too_large")
    if path.exists() or path.is_symlink():
        if _read_claim(path) != claim:
            raise ValueError("conflicting_hourly_action_or_target")
        return False
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as fp:
            fp.write(raw)
            fp.flush()
            os.fsync(fp.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(fd)
    return True


def coordinated_n50_once(
    *, lock_directory: Path, action: str,
    manifest_directory: Path, output_directory: Path | None = None,
    allow_public_network: bool = False,
    allow_private_storage: bool = False,
    allow_private_manifest_read: bool = False,
    allow_private_readonly_audit: bool = False,
    allow_private_manifest_write: bool = False,
    confirm_region_and_personal_research: bool = False,
    enable_coordinated_n50_once: bool = False,
    owner_ok: bool | None = None, clock_ms: Callable[[], int] | None = None,
    client=None,
) -> dict[str, Any]:
    """Exactly one bounded, user-authorized action; never starts a service."""
    if (enable_coordinated_n50_once is not True
            or allow_public_network is not True
            or confirm_region_and_personal_research is not True):
        return _report("optin_required")
    if action == "capture_seal":
        if allow_private_manifest_write is not True:
            return _report("optin_required")
    elif action == "hourly_writer":
        if (allow_private_storage is not True
                or allow_private_manifest_read is not True
                or allow_private_readonly_audit is not True):
            return _report("optin_required")
    else:
        return _report("blocked", "unsupported_action")
    permitted = ((os.name == "posix" and fcntl is not None
                  and os.getuid() == os.geteuid() and os.geteuid() != 0)
                 if owner_ok is None else owner_ok)
    if permitted is not True or fcntl is None:
        return _report("blocked", "posix_nonroot_owner_required")
    if (not isinstance(lock_directory, Path)
            or not isinstance(manifest_directory, Path)
            or not lock_directory.is_absolute()
            or not manifest_directory.is_absolute()
            or lock_directory == manifest_directory
            or lock_directory in manifest_directory.parents
            or manifest_directory in lock_directory.parents
            or (action == "hourly_writer"
                and (not isinstance(output_directory, Path)
                     or not output_directory.is_absolute()
                     or output_directory in lock_directory.parents
                     or lock_directory in output_directory.parents
                     or output_directory == manifest_directory
                     or output_directory in manifest_directory.parents
                     or manifest_directory in output_directory.parents))):
        return _report("blocked", "unsafe_owner_paths")
    clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
    try:
        now = clock()
        if type(now) is not int or not 1_600_000_000_000 <= now < 4_102_444_800_000:
            return _report("blocked", "invalid_clock")
        decision = now // HOUR_MS * HOUR_MS
        if not MIN_PHASE_MS <= now-decision <= MAX_PHASE_MS:
            return _report("deferred", "outside_utc_close_window")
        _strict_owner(lock_directory, directory=True)
        _strict_owner(manifest_directory, directory=True)
        if action == "hourly_writer":
            _strict_owner(output_directory, directory=True)
        for directory in ((lock_directory, manifest_directory)
                          if action == "capture_seal" else
                          (lock_directory, manifest_directory, output_directory)):
            if directory.is_symlink() or directory.resolve(strict=True) != directory:
                raise ValueError("symlink_or_path_alias")
        target = json.dumps(
            [action, str(manifest_directory),
             str(output_directory) if action == "hourly_writer" else ""],
            ensure_ascii=True, separators=(",", ":"),
        ).encode("ascii")
        target_digest = sha256(target).hexdigest()
        lock = lock_directory / LOCK_FILE
        if not lock.exists() and not lock.is_symlink():
            _new_private_file(lock)
        _strict_owner(lock, directory=False)
        fd = os.open(lock, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError):
                return _report("blocked", "global_n50_lease_busy")
            created = _record_claim(
                lock_directory, decision=decision, action=action,
                target_digest=target_digest,
            )
            if action == "capture_seal":
                result = capture_and_seal_current_rank_once(
                    scope_directory=manifest_directory,
                    allow_public_network=True,
                    confirm_region_and_personal_research=True,
                    allow_private_manifest_write=True,
                    owner_ok=permitted, clock_ms=clock, client=client,
                )
                success = result.get("status") == (
                    "sealed_current_auto_rank_research_scope_only")
                status = "capture_sealed" if success else "blocked"
            else:
                result = run_supervised_n50_once(
                    manifest_directory=manifest_directory,
                    output_directory=output_directory,
                    allow_private_manifest_read=True,
                    allow_private_readonly_audit=True,
                    allow_public_network=True,
                    allow_private_storage=True,
                    confirm_region_and_personal_research=True,
                    enable_n50_research_once=True,
                    owner_ok=permitted, clock_ms=clock, client=client,
                )
                success = result.get("status") == "research_hour_persisted"
                status = "research_hour_persisted" if success else (
                    "deferred" if result.get("status") == "deferred" else "blocked")
            out = _report(status, "delegated_to_existing_owner_path")
            out["action"] = action
            out["decision_end_ms"] = decision
            out["claims_created"] = 1 if created else 0
            out["requests_attempted"] = result.get("requests_attempted", 0)
            out["new_closed_candles"] = result.get("new_closed_candles", 0)
            return out
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
    except (OSError, ValueError, TypeError, UnicodeError,
            OverflowError, json.JSONDecodeError):
        return _report("blocked", "lease_integrity_or_environment_rejected")
