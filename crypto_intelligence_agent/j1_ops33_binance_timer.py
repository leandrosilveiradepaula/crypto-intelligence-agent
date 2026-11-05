"""OPS33: owner-only, one-claim, one-time Binance shadow launch.

Only a sanitized child report reaches journald.  Failed claims cannot retry.
No continuous service, REST, storage, orders or market access by default.
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

from .j1_ops23_once_timer import _SHA, _safe_path, check_git_sha, check_utc_synced
from .j1_ops31_shadow_timer import timer_schedule, no_competing_collectors

START_GRACE_SECONDS = 15
LAUNCH_LEAD_SECONDS = 60
CHILD_TIMEOUT_SECONDS = 205
CLAIM_NAME = "ops33-binance-one-shot-attempt.claim"
FRAMES = 1024
SECONDS = 180
_ALLOWED = frozenset({
    "binance_closes_observed_unverified", "binance_no_ack_abstain",
    "binance_no_close_abstain", "binance_partial_close_abstain",
    "binance_configuration_abstain", "binance_clock_abstain",
    "binance_envelope_abstain", "binance_control_abstain",
    "binance_ack_invalid_abstain", "binance_preack_budget_abstain",
    "binance_row_abstain", "binance_closed_causal_abstain",
    "binance_open_invalid_abstain", "binance_duplicate_conflict_abstain",
    "binance_frame_budget_abstain", "binance_receive_budget_abstain",
    "binance_transport_or_validation_abstain",
    "binance_unexpected_abstain",
})
_ADDITIONAL_COMPETITORS = (
    "cia-j1-ops31-shadow-once.service", "cia-j1-ops31-shadow-once.timer",
    "cia-j1-ops31-shadow.service", "cia-j1-ops31-shadow.timer",
)


@dataclass(frozen=True)
class Ops33LaunchReport:
    status: str
    launched: bool = False
    observer_status: str | None = None
    frames_seen: int = 0
    unique_closed: int = 0
    preack_discarded: int = 0
    duplicate_closes: int = 0
    closed_event_delay_over_1000ms: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "probe_launched": self.launched,
            "observer_status": self.observer_status,
            "frames_seen": self.frames_seen,
            "unique_closed": self.unique_closed,
            "preack_discarded": self.preack_discarded,
            "duplicate_closes": self.duplicate_closes,
            "closed_event_delay_over_1000ms": self.closed_event_delay_over_1000ms,
            "rest_gets": 0, "storage_writes": 0, "orders_sent": False,
            "source_authenticated": False,
            "usdm_contract_verified": False,
            "canonical_ohlcv_approved": False,
            "marketwide_top50_verified": False,
            "continuous_collector_authorized": False,
            "live_trading_authorized": False,
        }


def no_competing_collectors_ops33(*, run: Callable = subprocess.run) -> bool:
    if not no_competing_collectors(run=run):
        return False
    try:
        for name in _ADDITIONAL_COMPETITORS:
            p = run(["systemctl", "is-active", name], capture_output=True,
                    text=True, timeout=5, check=False)
            if (p.returncode not in (3, 4) or
                    p.stdout.strip() not in ("inactive", "failed", "unknown")):
                return False
        return True
    except (OSError, subprocess.SubprocessError, AttributeError):
        return False


def validated_observer_report(raw, *, returncode: int) -> dict | None:
    if type(raw) is not dict or raw.get("status") not in _ALLOWED:
        return None
    successful = raw["status"] == "binance_closes_observed_unverified"
    if (type(returncode) is not int or
            (successful and returncode != 0) or
            (not successful and returncode == 0)):
        return None
    if any(raw.get(key) is not expected for key, expected in (
        ("rest_gets", 0), ("storage_writes", 0), ("orders_sent", False),
        ("source_authenticated", False), ("usdm_contract_verified", False),
        ("canonical_ohlcv_approved", False),
        ("marketwide_top50_verified", False),
        ("continuous_collector_authorized", False),
        ("live_trading_authorized", False),
    )):
        return None
    for key, limit in (
        ("frames_seen", FRAMES), ("preack_discarded", 129),
        ("postack_market_frames", FRAMES), ("topics_observed", 2),
        ("open_updates", FRAMES), ("unique_closed", 2),
        ("duplicate_closes", FRAMES),
        ("closed_event_delay_over_1000ms", 2),
    ):
        if type(raw.get(key)) is not int or not 0 <= raw[key] <= limit:
            return None
    if type(raw.get("subscription_acknowledged")) is not bool:
        return None
    if (raw["postack_market_frames"] + raw["preack_discarded"] > raw["frames_seen"]
            or raw["open_updates"] > raw["postack_market_frames"]
            or raw["unique_closed"] > raw["topics_observed"]
            or raw["closed_event_delay_over_1000ms"] > raw["unique_closed"]
            or (successful and (not raw["subscription_acknowledged"]
                                or raw["unique_closed"] != 2))
            or (not raw["subscription_acknowledged"]
                and raw["postack_market_frames"] != 0)):
        return None
    return raw


def launch_binance_once(
    *, target_utc: str, expected_sha: str, repo_root: str,
    python_bin: str, state_dir: str,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ntp_check: Callable[[], bool] = check_utc_synced,
    git_check: Callable[[Path, str], bool] = check_git_sha,
    concurrency_check: Callable[[], bool] = no_competing_collectors_ops33,
    runner: Callable = subprocess.run,
    owner_check: Callable[[], bool] = lambda: os.name == "posix" and os.geteuid() != 0,
) -> Ops33LaunchReport:
    try:
        close, launch = timer_schedule(target_utc)
        repo, python, state = map(_safe_path, (repo_root, python_bin, state_dir))
        if (type(expected_sha) is not str or not _SHA.fullmatch(expected_sha)
                or not owner_check() or state == repo
                or repo in state.parents or state in repo.parents):
            return Ops33LaunchReport("ops33_config_abstain")
        current = now()
        if (type(current) is not datetime or current.tzinfo is None
                or not launch <= current.astimezone(timezone.utc)
                <= launch + timedelta(seconds=START_GRACE_SECONDS)):
            return Ops33LaunchReport("ops33_window_abstain")
        if not ntp_check():
            return Ops33LaunchReport("ops33_ntp_abstain")
        if not git_check(repo, expected_sha):
            return Ops33LaunchReport("ops33_sha_or_tree_abstain")
        if not concurrency_check():
            return Ops33LaunchReport("ops33_concurrent_abstain")
        info = state.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o700
                or info.st_uid != os.geteuid()):
            return Ops33LaunchReport("ops33_state_permissions_abstain")
        claim = state / CLAIM_NAME
        try:
            fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            return Ops33LaunchReport("ops33_already_attempted_abstain")
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
            return Ops33LaunchReport("ops33_claim_io_abstain")
        args = [
            str(python), "-m", "scripts.observe_j1_binance_shadow_once",
            "--allow-public-network", "--allow-public-websocket",
            "--confirm-region-and-personal-research",
            "--seconds", str(SECONDS), "--frames", str(FRAMES),
        ]
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/home/cia-probe",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
        }
        try:
            child = runner(args, cwd=repo, env=env,
                           timeout=CHILD_TIMEOUT_SECONDS, capture_output=True,
                           text=True, check=False)
        except (OSError, subprocess.SubprocessError):
            return Ops33LaunchReport("ops33_child_failed_abstain", True)
        try:
            raw = validated_observer_report(
                json.loads(child.stdout), returncode=child.returncode)
        except (TypeError, ValueError):
            raw = None
        if raw is None:
            return Ops33LaunchReport("ops33_report_invalid_abstain", True)
        counts = (raw["frames_seen"], raw["unique_closed"],
                  raw["preack_discarded"], raw["duplicate_closes"],
                  raw["closed_event_delay_over_1000ms"])
        return Ops33LaunchReport(
            "ops33_shadow_observed_unverified" if
            raw["status"] == "binance_closes_observed_unverified" else
            "ops33_shadow_abstained", True, raw["status"], *counts,
        )
    except (OSError, TypeError, ValueError, AttributeError,
            subprocess.SubprocessError):
        return Ops33LaunchReport("ops33_launcher_abstain")
