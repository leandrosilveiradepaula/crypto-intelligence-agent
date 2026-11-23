"""D444: repeat all held PAPER quote leases without J1 or real orders.

A long-running owner process reuses D443 (which in turn uses D425/D390/
D391/AUTO4), recovers from bounded transport failures, and writes only a
count-only private status for the local UI. Existing PAPER reservations and
explicit fills remain in the same owner SQLite across cycles. This is PAPER
research, NOT exchange stop protection or proof of uninterrupted coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import time
from typing import Callable

try:
    import fcntl
except ImportError:  # imported but never run on non-POSIX CI
    fcntl = None

from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .j4_held_multi_public_d445 import observe_existing_held_paper_once
from .market_data import DataValidationError

_SCHEMA = "j4-btc-continuous-paper-worker-d444-v1"
_STATE_FILE = "paper-monitor-state.json"
_LOCK_FILE = ".paper-monitor-worker.lock"
_MAX_OUTPUT_BYTES = 4096
_MAX_UTC_MS = 4_102_444_800_000
_SUCCESS = "finite_held_paper_quote_observed_unverified"
_EXPECTED_REAL_MODE = "public_ws_observed_unverified"
_EXPECTED_TEST_MODE = "injected_offline_protocol_replay"


@dataclass(frozen=True)
class PaperWorkerPolicy:
    """Zero cycles means explicit continuing operation, not a hidden timer."""

    max_cycles: int = 0
    lease_seconds: int = 45
    max_frames: int = 80_000
    normal_gap_seconds: int = 1
    first_retry_seconds: int = 2
    max_retry_seconds: int = 60
    max_consecutive_failures: int = 8

    def __post_init__(self) -> None:
        v = (
            self.max_cycles, self.lease_seconds, self.max_frames,
            self.normal_gap_seconds, self.first_retry_seconds,
            self.max_retry_seconds, self.max_consecutive_failures,
        )
        if any(type(x) is not int for x in v) or not (
            0 <= self.max_cycles <= 100_000
            and 1 <= self.lease_seconds <= 60
            and 1 <= self.max_frames <= 100_000
            and 1 <= self.normal_gap_seconds <= 30
            and 1 <= self.first_retry_seconds <= 30
            and self.first_retry_seconds <= self.max_retry_seconds <= 300
            and 1 <= self.max_consecutive_failures <= 100
        ):
            raise DataValidationError("D444 invalid finite lease or reconnect policy")


def _safe_lease(report: object, expected_mode: str) -> tuple[bool, bool, int]:
    """Only a *completed, fresh* D443 lease counts as healthy.

    Unexpected or contradictory outcomes are not retried as successful and
    cannot be converted into a positive source-authentication claim.
    """
    if type(report) is not dict:
        return False, False, 0
    unsafe = (report.get("orders_sent") is not False
              or report.get("order_submission_enabled") is not False
              or report.get("approved_for_live_use") is not False
              or report.get("new_paper_position_created") is not False
              or report.get("synthetic_fill_inferred_from_ticker") is not False
              or report.get("j1_state_accessed") is not False)
    n = report.get("held_quote_frames_forwarded")
    count = n if type(n) is int and 0 <= n <= 1_000_000 else 0
    healthy = (not unsafe and report.get("status") == _SUCCESS
               and report.get("data_mode") == expected_mode
               and report.get("held_quote_fresh_at_lease_end") is True
               and type(n) is int and n > 0)
    return healthy, unsafe, count


def drive_paper_cycles(
    *, policy: PaperWorkerPolicy, lease_once: Callable[[], dict],
    now_ms: Callable[[], int], sleeper: Callable[[float], None],
    publish: Callable[[dict], None], should_stop: Callable[[], bool],
    expected_mode: str = _EXPECTED_TEST_MODE,
) -> dict:
    """Pure driver; injectable seams are *offline-only* at the CLI boundary.

    Each iteration starts a NEW D443 session; D443 reloads owner routes and
    maintains exclusive financial-journal locks during each lease. The driver
    never generates positions, fills, symbols, market prices, or financial PnL.
    """
    if (type(policy) is not PaperWorkerPolicy
            or expected_mode not in (_EXPECTED_REAL_MODE, _EXPECTED_TEST_MODE)
            or not all(callable(x) for x in (
                lease_once, now_ms, sleeper, publish, should_stop))):
        raise DataValidationError("D444 invalid worker dependencies")
    attempts = successes = consecutive = total_quotes = 0
    last_good_ms = None
    last_outcome = "not_started"

    def emit(phase: str) -> dict:
        stamp = now_ms()
        if type(stamp) is not int or not 1_600_000_000_000 <= stamp < _MAX_UTC_MS:
            raise DataValidationError("D444 invalid owner wall clock")
        out = {
            "schema_version": _SCHEMA,
            "phase": phase,
            "updated_at_ms": stamp,
            "last_good_lease_at_ms": last_good_ms,
            "lease_attempts": attempts,
            "healthy_lease_count": successes,
            "consecutive_lease_failures": consecutive,
            "accepted_quote_events_total": total_quotes,
            "last_lease_outcome": last_outcome,
            "source_mode": expected_mode,
            "lease_active": phase == "lease_started",
            "native_stop_active": False,
            "exchange_source_authenticated": False,
            "uninterrupted_coverage_verified": False,
            "paper_positions_automatically_filled": False,
            "j1_state_accessed": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
        publish(out)
        return out

    result = emit("starting")
    while policy.max_cycles == 0 or attempts < policy.max_cycles:
        if should_stop():
            return emit("stopped_by_operator")
        attempts += 1
        last_outcome = "lease_started"
        emit("lease_started")
        try:
            raw = lease_once()
        except (Exception,):  # never expose provider payloads, paths or traceback
            raw = None
        healthy, unsafe, frames = _safe_lease(raw, expected_mode)
        if unsafe:
            last_outcome = "unexpected_financial_or_source_claim"
            return emit("failed_closed")
        if healthy:
            successes += 1
            total_quotes += frames
            consecutive = 0
            last_good_ms = now_ms()
            last_outcome = "fresh_finite_paper_lease"
        else:
            consecutive += 1
            last_outcome = "lease_degraded_abstain"
        result = emit("between_leases")
        if consecutive >= policy.max_consecutive_failures:
            return emit("stopped_after_repeated_degradation")
        if policy.max_cycles and attempts >= policy.max_cycles:
            return emit("completed_finite_cycles")
        if should_stop():
            return emit("stopped_by_operator")
        delay = (policy.normal_gap_seconds if healthy else
                 min(policy.max_retry_seconds,
                     policy.first_retry_seconds * (2 ** min(16, consecutive - 1))))
        sleeper(delay)
    return result


def _owner_directory(path: Path) -> Path:
    if (os.name != "posix" or not hasattr(os, "geteuid")
            or os.geteuid() == 0 or not isinstance(path, Path)
            or not path.is_absolute() or path.is_symlink()):
        raise DataValidationError("D444 nonroot private owner directory required")
    try:
        info = path.stat()
    except OSError:
        raise DataValidationError("D444 owner directory unavailable") from None
    if (not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise DataValidationError("D444 private owner directory invalid")
    return path


class PrivateWorkerStatus:
    """Atomic owner-only status JSON, not a license to expose prices or IDs."""

    def __init__(self, directory: Path):
        self.directory = _owner_directory(directory)
        self.dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.lock_fd = None
        try:
            self.lock_fd = os.open(
                _LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600, dir_fd=self.dirfd,
            )
            info = os.fstat(self.lock_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_nlink != 1 or fcntl is None):
                raise DataValidationError("D444 unsafe worker lock")
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def close(self) -> None:
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
        if self.dirfd is not None:
            os.close(self.dirfd)
            self.dirfd = None

    def publish(self, state: dict) -> None:
        if (type(state) is not dict
                or state.get("schema_version") != _SCHEMA
                or state.get("orders_sent") is not False
                or state.get("approved_for_live_use") is not False
                or state.get("j1_state_accessed") is not False):
            raise DataValidationError("D444 unsafe worker status")
        raw = json.dumps(state, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
        if not 2 <= len(raw) <= _MAX_OUTPUT_BYTES:
            raise DataValidationError("D444 status output oversized")
        import secrets
        temp = ".paper-monitor-" + secrets.token_hex(12)
        fd = os.open(
            temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=self.dirfd,
        )
        try:
            os.write(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temp, _STATE_FILE, src_dir_fd=self.dirfd,
                       dst_dir_fd=self.dirfd)
            os.fsync(self.dirfd)
        finally:
            # A failed replace must not leave many owner-private temp files.
            try:
                os.unlink(temp, dir_fd=self.dirfd)
            except FileNotFoundError:
                pass


def run_owner_continuous_paper_worker(
    *, private_paper_directory: Path, status_directory: Path,
    policy: PaperWorkerPolicy,
    allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    confirm_public_data_rights: bool = False,
    allow_private_paper_reservations: bool = False,
    enable_continuous_worker: bool = False,
    simulate_explicit_demo_exit_fills: bool = False,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    """One resident owner process, no daemon installation or account API.

    Public network is entered ONLY after explicit opt-ins and owner/directory
    gates. The status directory is disjoint from the private financial journal.
    """
    flags = (allow_public_network, allow_public_websocket,
             confirm_personal_readonly_research, confirm_region_eligible,
             confirm_public_data_rights, allow_private_paper_reservations,
             enable_continuous_worker)
    denied = {
        "status": "explicit_continuous_paper_research_optins_required",
        "network_attempted": False, "private_paper_journal_accessed": False,
        "orders_sent": False, "approved_for_live_use": False,
    }
    if (any(type(x) is not bool for x in flags)
            or type(simulate_explicit_demo_exit_fills) is not bool):
        raise DataValidationError("D444 explicit owner flags required")
    if not all(flags):
        return denied
    if type(policy) is not PaperWorkerPolicy:
        raise DataValidationError("D444 policy required")
    if (not hasattr(os, "getuid") or os.getuid() != os.geteuid()
            or os.geteuid() == 0):
        return {**denied, "status": "unprivileged_owner_required"}
    paper_dir = _owner_directory(private_paper_directory)
    status_dir = _owner_directory(status_directory)
    financial = paper_dir.resolve(strict=True)
    status = status_dir.resolve(strict=True)
    if (financial == status or financial in status.parents
            or status in financial.parents
            or any(part.startswith("j1-") for part in financial.parts + status.parts)):
        raise DataValidationError("D444 status and PAPER directories must be isolated")
    if should_stop is None:
        should_stop = lambda: False
    with PrivateWorkerStatus(status_dir) as state:
        try:
            output = drive_paper_cycles(
                policy=policy,
                lease_once=lambda: observe_existing_held_paper_once(
                    private_paper_directory=paper_dir,
                    allow_public_network=True, allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    allow_private_paper_reservations=True,
                    simulate_explicit_demo_exit_fills=simulate_explicit_demo_exit_fills,
                    budget=TickerLeaseBudget(1, policy.max_frames,
                                             policy.lease_seconds),
                ),
                now_ms=lambda: time.time_ns() // 1_000_000,
                sleeper=time.sleep,
                publish=state.publish,
                should_stop=should_stop,
                expected_mode=_EXPECTED_REAL_MODE,
            )
        except BaseException:
            # No claim that the process is still watching after interruption.
            raise
    return output


class WorkerStatusUnavailable(Exception):
    """Public-facing local reader must never leak private owner paths."""


_STATUS_KEYS = frozenset((
    "schema_version", "phase", "updated_at_ms", "last_good_lease_at_ms",
    "lease_attempts", "healthy_lease_count", "consecutive_lease_failures",
    "accepted_quote_events_total", "last_lease_outcome", "source_mode",
    "lease_active", "native_stop_active", "exchange_source_authenticated",
    "uninterrupted_coverage_verified", "paper_positions_automatically_filled",
    "j1_state_accessed", "orders_sent", "approved_for_live_use",
))
_PHASES = frozenset((
    "starting", "lease_started", "between_leases", "stopped_by_operator",
    "failed_closed", "stopped_after_repeated_degradation",
    "completed_finite_cycles",
))
_TERMINAL = frozenset((
    "stopped_by_operator", "failed_closed",
    "stopped_after_repeated_degradation", "completed_finite_cycles",
))


def read_private_worker_status(*, directory: Path, now_ms: int) -> dict:
    """Strict count-only local projection for J5; never a protection claim.

    Active/reconnecting records older than 120 seconds are rejected rather
    than displayed as a still-running supervisor. Terminal status is retained
    for 24 hours, clearly labelled as stopped.
    """
    if type(now_ms) is not int or not 1_600_000_000_000 <= now_ms < _MAX_UTC_MS:
        raise WorkerStatusUnavailable("paper_worker_unavailable")
    try:
        home = _owner_directory(directory)
        dirfd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(
                _STATE_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=dirfd,
            )
            try:
                before = os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode)
                        or before.st_uid != os.geteuid()
                        or before.st_nlink != 1
                        or stat.S_IMODE(before.st_mode) != 0o600
                        or not 2 <= before.st_size <= _MAX_OUTPUT_BYTES):
                    raise ValueError("unsafe status")
                raw = os.read(fd, _MAX_OUTPUT_BYTES + 1)
                after = os.fstat(fd)
                if (len(raw) != before.st_size
                        or (before.st_ino, before.st_dev, before.st_mtime_ns,
                            before.st_size) !=
                           (after.st_ino, after.st_dev, after.st_mtime_ns,
                            after.st_size)):
                    raise ValueError("unstable status")
            finally:
                os.close(fd)
        finally:
            os.close(dirfd)

        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate keys")
                result[key] = value
            return result

        obj = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=no_duplicates,
            parse_float=lambda _: (_ for _ in ()).throw(ValueError("float")),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")),
        )
        if (type(obj) is not dict or set(obj) != _STATUS_KEYS
                or obj["schema_version"] != _SCHEMA
                or obj["phase"] not in _PHASES
                or obj["source_mode"] not in (
                    _EXPECTED_REAL_MODE, _EXPECTED_TEST_MODE)
                or type(obj["updated_at_ms"]) is not int
                or not 0 <= now_ms - obj["updated_at_ms"] <= (
                    86_400_000 if obj["phase"] in _TERMINAL else 120_000
                )
                or (obj["last_good_lease_at_ms"] is not None and
                    (type(obj["last_good_lease_at_ms"]) is not int or
                     not 1_600_000_000_000 <= obj["last_good_lease_at_ms"]
                     <= obj["updated_at_ms"]))
                or any(type(obj[k]) is not int or not 0 <= obj[k] <= 100_000_000
                       for k in (
                           "lease_attempts", "healthy_lease_count",
                           "consecutive_lease_failures",
                           "accepted_quote_events_total",
                       ))
                or obj["healthy_lease_count"] > obj["lease_attempts"]
                or obj["consecutive_lease_failures"] > obj["lease_attempts"]
                or obj["last_lease_outcome"] not in (
                    "not_started", "lease_started", "fresh_finite_paper_lease",
                    "lease_degraded_abstain",
                    "unexpected_financial_or_source_claim",
                )
                or type(obj["lease_active"]) is not bool
                or obj["lease_active"] != (obj["phase"] == "lease_started")
                or any(obj[k] is not False for k in (
                    "native_stop_active", "exchange_source_authenticated",
                    "uninterrupted_coverage_verified",
                    "paper_positions_automatically_filled",
                    "j1_state_accessed", "orders_sent",
                    "approved_for_live_use",
                ))):
            raise ValueError("invalid status")
        return obj
    except (DataValidationError, OSError, ValueError, TypeError,
            UnicodeError, OverflowError):
        raise WorkerStatusUnavailable("paper_worker_unavailable") from None
