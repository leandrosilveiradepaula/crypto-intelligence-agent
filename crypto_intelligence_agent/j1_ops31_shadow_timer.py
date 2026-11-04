"""J1/OPS31: fail-closed, one-claim UTC shadow WS launch (no REST or writes).

The already reviewed OPS30 CLI owns all network budgets. This supervisor
uses one absolute UTC window, a SHA pin and one private O_EXCL claim before
launching the child. Only vetted counters are ever printed to journald.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Callable

from .j1_ops23_once_timer import (
    _SHA, _safe_path, check_git_sha, check_utc_synced, timer_date,
)

LAUNCH_LEAD_SECONDS = 60
START_GRACE_SECONDS = 15
CHILD_TIMEOUT_SECONDS = 205
SHADOW_SECONDS = 180
SHADOW_FRAMES = 1024
CLAIM_NAME = "ops31-shadow-one-shot-attempt.claim"
EXPECTED_TOPICS = 2

_ALLOWED = frozenset({
    "shadow_closes_observed_quarantined",
    "shadow_no_closed_candle_unverified",
    "shadow_no_ack_abstain",
    "shadow_configuration_abstain",
    "shadow_clock_abstain",
    "shadow_pong_timeout_abstain",
    "shadow_envelope_abstain",
    "shadow_ack_invalid_abstain",
    "shadow_control_abstain",
    "shadow_preack_budget_abstain",
    "shadow_row_abstain",
    "shadow_frame_budget_abstain",
    "shadow_receive_budget_abstain",
    "shadow_transport_or_validation_abstain",
    "shadow_unexpected_abstain",
})
_BANDS = frozenset({
    "within_interval", "overrun_1ms", "overrun_2_to_1000ms",
    "overrun_1001_to_5000ms", "overrun_over_5000ms",
})
_NO_CONCURRENT = (
    "cia-j1-ws-owner.service", "cia-j1-ops22-once.service",
    "cia-j1-ops25-retest2.service", "cia-j1-ops26-retest3.service",
)


@dataclass(frozen=True)
class ShadowLaunchResult:
    status: str
    launched: bool = False
    observer_status: str | None = None
    frames_seen: int = 0
    unique_closed: int = 0
    preack_discarded: int = 0
    duplicate_closes: int = 0
    closed_overrun: int = 0
    open_overrun: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "probe_launched": self.launched,
            "observer_status": self.observer_status,
            "frames_seen": self.frames_seen,
            "unique_closed": self.unique_closed,
            "preack_discarded": self.preack_discarded,
            "duplicate_closes": self.duplicate_closes,
            "closed_overrun": self.closed_overrun,
            "open_overrun": self.open_overrun,
            "rest_gets": 0,
            "storage_writes": 0,
            "orders_sent": False,
            "continuous_collector_authorized": False,
            "canonical_ohlcv_approved": False,
            "marketwide_top50_verified": False,
            "source_authenticated": False,
            "live_trading_authorized": False,
        }


def timer_schedule(target_utc: str) -> tuple[datetime, datetime]:
    close, _ = timer_date(target_utc)
    return close, close - timedelta(seconds=LAUNCH_LEAD_SECONDS)


def no_competing_collectors(*, run: Callable = subprocess.run) -> bool:
    """Do not launch with a known collector/service active.

    Failure to interrogate systemd is itself a veto.
    """
    try:
        for name in _NO_CONCURRENT:
            p = run(["systemctl", "is-active", name], capture_output=True,
                    text=True, timeout=5, check=False)
            if p.returncode not in (3, 4) or p.stdout.strip() not in (
                "inactive", "failed", "unknown",
            ):
                return False
        return True
    except (OSError, subprocess.SubprocessError, AttributeError):
        return False


def _validated_shadow_report(raw, *, returncode: int) -> dict | None:
    if type(raw) is not dict or raw.get("status") not in _ALLOWED:
        return None
    if type(returncode) is not int:
        return None
    success = raw["status"] in (
        "shadow_closes_observed_quarantined",
        "shadow_no_closed_candle_unverified",
    )
    if (success and returncode != 0) or (not success and returncode == 0):
        return None
    if any(raw.get(k) is not expected for k, expected in (
        ("rest_gets", 0), ("storage_writes", 0),
        ("orders_sent", False),
        ("continuous_collector_authorized", False),
        ("canonical_ohlcv_approved", False),
        ("marketwide_top50_verified", False),
        ("source_authenticated", False),
        ("live_trading_authorized", False),
    )):
        return None
    counts = (
        ("frames_seen", SHADOW_FRAMES), ("preack_discarded", 128),
        ("postack_market_frames", SHADOW_FRAMES),
        ("topics_observed", EXPECTED_TOPICS),
        ("unique_closed", EXPECTED_TOPICS),
        ("duplicate_closes", SHADOW_FRAMES),
        ("open_rows", SHADOW_FRAMES * 8),
        ("pong_frames", SHADOW_FRAMES),
    )
    if any(type(raw.get(k)) is not int or not 0 <= raw[k] <= maximum
           for k, maximum in counts):
        return None
    for key, limit in (("closed_timestamp_bands", EXPECTED_TOPICS),
                       ("open_timestamp_bands", SHADOW_FRAMES * 8)):
        obj = raw.get(key)
        if type(obj) is not dict or set(obj) != _BANDS:
            return None
        if any(type(v) is not int or not 0 <= v <= limit
               for v in obj.values()):
            return None
    if (sum(raw["closed_timestamp_bands"].values()) != raw["unique_closed"]
            or sum(raw["open_timestamp_bands"].values()) != raw["open_rows"]
            or raw["postack_market_frames"] > raw["frames_seen"]
            or raw["preack_discarded"] > raw["frames_seen"]
            or raw["unique_closed"] > raw["postack_market_frames"]):
        return None
    return raw


def launch_shadow_once(
    *, target_utc: str, expected_sha: str, repo_root: str,
    python_bin: str, state_dir: str,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ntp_check: Callable[[], bool] = check_utc_synced,
    git_check: Callable[[Path, str], bool] = check_git_sha,
    concurrency_check: Callable[[], bool] = no_competing_collectors,
    runner: Callable = subprocess.run,
    owner_check: Callable[[], bool] = lambda: os.name == "posix" and os.geteuid() != 0,
) -> ShadowLaunchResult:
    try:
        close, start = timer_schedule(target_utc)
        repo, python, state = map(_safe_path, (repo_root, python_bin, state_dir))
        if (type(expected_sha) is not str or not _SHA.fullmatch(expected_sha)
                or not owner_check() or state == repo
                or state in repo.parents or repo in state.parents):
            return ShadowLaunchResult("config_abstain")
        current = now()
        if (type(current) is not datetime or current.tzinfo is None
                or not start <= current.astimezone(timezone.utc)
                <= start + timedelta(seconds=START_GRACE_SECONDS)):
            return ShadowLaunchResult("window_abstain")
        if not ntp_check():
            return ShadowLaunchResult("ntp_unsynced_abstain")
        if not git_check(repo, expected_sha):
            return ShadowLaunchResult("sha_or_tree_abstain")
        if not concurrency_check():
            return ShadowLaunchResult("competing_or_unknown_service_abstain")
        info = state.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o700
                or info.st_uid != os.geteuid()):
            return ShadowLaunchResult("state_permissions_abstain")
        flag = state / CLAIM_NAME
        try:
            fd = os.open(flag, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            return ShadowLaunchResult("already_attempted_abstain")
        try:
            with os.fdopen(fd, "w", encoding="ascii") as fp:
                fp.write(f"{target_utc} {expected_sha}\n")
                fp.flush()
                os.fsync(fp.fileno())
            dirfd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except OSError:
            return ShadowLaunchResult("claim_io_abstain")
        env = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/home/cia-probe",
        }
        argv = [
            str(python), "-m", "scripts.observe_j1_ws_shadow_once",
            "--allow-public-network", "--allow-public-websocket",
            "--confirm-region-and-personal-research",
            "--topic", "kline.60.BTCUSDT",
            "--topic", "kline.60.ETHUSDT",
            "--seconds", str(SHADOW_SECONDS),
            "--frames", str(SHADOW_FRAMES),
        ]
        try:
            child = runner(argv, cwd=repo, env=env,
                           timeout=CHILD_TIMEOUT_SECONDS, capture_output=True,
                           text=True, check=False)
        except (OSError, subprocess.SubprocessError):
            return ShadowLaunchResult("shadow_child_failed_abstain", True)
        try:
            report = _validated_shadow_report(
                json.loads(child.stdout), returncode=child.returncode)
        except (TypeError, ValueError):
            report = None
        if report is None:
            return ShadowLaunchResult("shadow_report_invalid_abstain", True)
        closed = report["closed_timestamp_bands"]
        opened = report["open_timestamp_bands"]
        counters = (
            report["frames_seen"], report["unique_closed"],
            report["preack_discarded"], report["duplicate_closes"],
            sum(closed.values()) - closed["within_interval"],
            sum(opened.values()) - opened["within_interval"],
        )
        if report["status"] == "shadow_closes_observed_quarantined":
            return ShadowLaunchResult("shadow_observed_quarantined", True,
                                      report["status"], *counters)
        if report["status"] == "shadow_no_closed_candle_unverified":
            return ShadowLaunchResult("shadow_no_close_unverified", True,
                                      report["status"], *counters)
        return ShadowLaunchResult("shadow_abstained", True,
                                  report["status"], *counters)
    except (OSError, TypeError, ValueError, AttributeError,
            subprocess.SubprocessError):
        return ShadowLaunchResult("launcher_abstain")
