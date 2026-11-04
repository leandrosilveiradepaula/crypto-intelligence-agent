"""J1/OPS23: one-shot UTC VPS launcher, disabled until explicitly installed.

The CLI is only a supervisor; the existing OPS22 script owns all WS/REST
budgets and its sanitized output. No retry, secrets, or data are persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_TARGET = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:00:00Z\Z")
LEAD_SECONDS = 900
START_GRACE_SECONDS = 15
MAX_WAIT_SECONDS = 1200

# Finite status vocabulary from the reviewed OPS22 runner. Never reflect arbitrary
# child output, paths, HTTP bodies, OHLCV, or exception text to journald.
_ALLOWED_PROBE_STATUSES = frozenset({
    "ws_rest_match_unverified", "ws_rest_diverge_abstain",
    "ws_no_qualifying_close_abstain", "ws_pong_timeout_abstain",
    "ws_ack_invalid_abstain", "ws_ack_missing_abstain",
    "ws_preack_budget_abstain", "ws_preack_envelope_abstain",
    "ws_unexpected_control_abstain",
    "ws_preack_abstain", "ws_envelope_abstain",
    "ws_envelope_keys_abstain", "ws_envelope_topic_abstain",
    "ws_envelope_metadata_abstain", "ws_envelope_rows_abstain",
    "ws_envelope_row_type_abstain", "ws_multiple_closed_abstain",
    "ws_row_abstain",
    "ws_close_chronology_abstain", "rest_window_abstain",
    "rest_clock_abstain", "rest_rate_limit_abstain",
    "rest_http_abstain", "rest_transport_abstain",
    "rest_envelope_abstain", "rest_rejected_abstain",
    "validation_abstain", "ws_transport_abstain", "unexpected_abstain",
    "owner_opt_in_required", "owner_nonroot_required",
    "registry_invalid_abstain", "capability_abstain", "clock_abstain",
})



@dataclass(frozen=True)
class VPSOneShotResult:
    status: str
    launched: bool = False
    probe_status: str | None = None
    ws_frames: int = 0
    rest_gets: int = 0
    fields_compared: int = 0
    fields_equal: int = 0

    def sanitized_report(self) -> dict:
        return {"status": self.status, "probe_launched": self.launched,
                "data_stored_by_supervisor": False, "orders_sent": False,
                "live_trading_authorized": False,
                "probe_status": self.probe_status, "ws_frames": self.ws_frames,
                "rest_gets": self.rest_gets,
                "fields_compared": self.fields_compared,
                "fields_equal": self.fields_equal}


def timer_date(target_utc: str) -> tuple[datetime, datetime]:
    """One specific UTC close, never a recurring hour/minute calendar."""
    if type(target_utc) is not str or not _TARGET.fullmatch(target_utc):
        raise ValueError("target must be an exact UTC hour")
    try:
        close = datetime.strptime(target_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("target UTC calendar invalid") from exc
    if close.year < 2026 or close.year > 2099:
        raise ValueError("target UTC year unsupported")
    return close, close - timedelta(seconds=LEAD_SECONDS)


def _safe_path(value: str) -> Path:
    if (type(value) is not str or not value.startswith("/") or len(value) > 240
            or "//" in value or ".." in Path(value).parts
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value)):
        raise ValueError("unsafe service path")
    return Path(value)


def check_utc_synced(*, run: Callable = subprocess.run) -> bool:
    """Fail closed when systemd cannot confirm synchronized UTC."""
    try:
        result = run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                     capture_output=True, text=True, timeout=4, check=False)
        return result.returncode == 0 and result.stdout.strip() == "yes"
    except (OSError, subprocess.SubprocessError):
        return False


def check_git_sha(repo_root: Path, expected_sha: str, *, run: Callable = subprocess.run) -> bool:
    if type(expected_sha) is not str or not _SHA.fullmatch(expected_sha):
        return False
    try:
        result = run(["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"],
                     capture_output=True, text=True, timeout=5, check=False)
        if result.returncode != 0 or result.stdout.strip() != expected_sha:
            return False
        clean = run(["git", "-C", str(repo_root), "status", "--porcelain"],
                    capture_output=True, text=True, timeout=5, check=False)
        return clean.returncode == 0 and not clean.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False


def launch_once(*, target_utc: str, expected_sha: str, repo_root: str,
                python_bin: str, state_dir: str,
                now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                ntp_check: Callable[[], bool] = check_utc_synced,
                git_check: Callable[[Path, str], bool] = check_git_sha,
                runner: Callable = subprocess.run,
                owner_check: Callable[[], bool] = lambda: os.name == "posix" and os.geteuid() != 0,
                ) -> VPSOneShotResult:
    """Claim the one-shot before network activity; never catch up a missed close."""
    try:
        close, launch = timer_date(target_utc)
        repo, python, state = map(_safe_path, (repo_root, python_bin, state_dir))
        if (not _SHA.fullmatch(expected_sha) or not owner_check()
                or state == repo or state in repo.parents or repo in state.parents):
            return VPSOneShotResult("config_abstain")
        current = now()
        if (not isinstance(current, datetime) or current.tzinfo is None or
                not launch <= current.astimezone(timezone.utc) <=
                launch + timedelta(seconds=START_GRACE_SECONDS)):
            return VPSOneShotResult("window_abstain")
        if not ntp_check():
            return VPSOneShotResult("ntp_unsynced_abstain")
        if not git_check(repo, expected_sha):
            return VPSOneShotResult("sha_or_tree_abstain")
        entry = state.lstat()
        if (not state.is_dir() or entry.st_mode & 0o077
                or entry.st_uid != os.geteuid() or state.is_symlink()):
            return VPSOneShotResult("state_permissions_abstain")
        flag = state / "ops22-one-shot-attempt.claim"
        try:
            fd = os.open(flag, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
        except FileExistsError:
            return VPSOneShotResult("already_attempted_abstain")
        try:
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(f"{target_utc} {expected_sha}\n")
                handle.flush()
                os.fsync(handle.fileno())
            dirfd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except OSError:
            return VPSOneShotResult("claim_io_abstain")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
        wait = runner([str(python), "-m", "scripts.wait_j1_ws_utc_close"],
                      cwd=repo, env=env, timeout=MAX_WAIT_SECONDS,
                      capture_output=True, text=True, check=False)
        if wait.returncode != 0:
            return VPSOneShotResult("utc_wait_abstain")
        if not ntp_check():
            return VPSOneShotResult("ntp_lost_abstain")
        probe = runner([str(python), "-m", "scripts.probe_j1_ws_rest_one_candle",
                        "--allow-public-network", "--allow-public-websocket",
                        "--allow-one-public-rest-get", "--confirm-region-and-personal-research"],
                       cwd=repo, env=env, timeout=120,
                       capture_output=True, text=True, check=False)
        try:
            report = json.loads(probe.stdout)
        except (ValueError, TypeError):
            return VPSOneShotResult(
                "probe_abstained" if probe.returncode else "probe_report_invalid_abstain", True)
        if (type(report) is not dict
                or report.get("status") not in _ALLOWED_PROBE_STATUSES
                or any(type(report.get(key)) is not int or not 0 <= report[key] <= cap
                       for key, cap in (
                           ("ws_frames", 256), ("rest_gets", 1),
                           ("fields_compared", 6), ("fields_equal", 6)))
                or report["fields_equal"] > report["fields_compared"]
                or report.get("ws_candle_approved") is not False
                or report.get("canonical_ohlcv_approved") is not False
                or report.get("source_authenticated") is not False
                or report.get("orders_sent") is not False
                or report.get("data_stored") is not False):
            return VPSOneShotResult("probe_report_invalid_abstain", True)
        fields = (report["status"], report["ws_frames"], report["rest_gets"],
                  report["fields_compared"], report["fields_equal"])
        is_match = (probe.returncode == 0
                    and report["status"] == "ws_rest_match_unverified"
                    and report["rest_gets"] == 1
                    and report["fields_compared"] == report["fields_equal"] == 6)
        return VPSOneShotResult(
            "probe_completed_unverified" if is_match else "probe_abstained",
            True, *fields)
    except (ValueError, TypeError, OSError, subprocess.SubprocessError):
        return VPSOneShotResult("launcher_failure_abstain")
