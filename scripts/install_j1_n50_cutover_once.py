"""D297: explicit, reversible cutover from the live N2 timer to managed N50.

Owner/root local release operation, NEVER called by CI, a timer, or the N50
worker. Fail closed before changing systemd; rollback on any failed postflight.
No orders, credentials, private API calls, migrations or database writes.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import sqlite3
import stat
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:  # Windows CI imports the module but cannot deploy it.
    pwd = None
import signal
import socket
import subprocess
import time

from scripts.render_j1_n50_managed_systemd import render_n50_managed_systemd

N2_TIMER = "cia-j1-rest-hourly.timer"
N2_SERVICE = "cia-j1-rest-hourly.service"
N50_TIMER = "cia-j1-n50-managed.timer"
N50_SERVICE = "cia-j1-n50-managed.service"
FALLBACK_SERVICE = "cia-j1-n50-fallback.service"
UNIT_ROOT = Path("/etc/systemd/system")
EXPECTED_N2_UNIT_HASH = {
    N2_TIMER: "d7e91d88ea6ed6f1f20b074345dd2f9ad6429dce",
    N2_SERVICE: "61d3e7e0bdb0c0dc97fdaba306d9e9f6c648e209",
}
EXPECTED_ORIGIN = "https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git"
HOSTNAME = "srv1319424"


def _call(argv: list[str], *, timeout: int = 20) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          check=False, shell=False)
    if proc.returncode != 0 or len(proc.stdout) > 12_000:
        raise RuntimeError("fixed_command_failed")
    return proc.stdout.strip()


def _show(unit: str) -> dict[str, str]:
    raw = _call(["/usr/bin/systemctl", "show", unit,
                 "--property=LoadState", "--property=ActiveState",
                 "--property=UnitFileState", "--no-pager"])
    result: dict[str, str] = {}
    for line in raw.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key in result or key not in {
            "LoadState", "ActiveState", "UnitFileState",
        }:
            raise ValueError("systemd_fields_invalid")
        result[key] = value
    if set(result) != {"LoadState", "ActiveState", "UnitFileState"}:
        raise ValueError("systemd_fields_missing")
    return result


def _audit_n2(*, source: Path, python: Path) -> dict:
    raw = _call([
        "/usr/sbin/runuser", "-u", "cia-probe", "--",
        "/usr/bin/env", "PYTHONPATH=" + str(source), str(python),
        "-m", "scripts.audit_j1_rest_resume_readiness",
        "--output-directory",
        "/home/cia-probe/agent/j1-rest-m3-20261109/canary",
        "--expected-members", "2", "--allow-private-readonly-audit",
    ], timeout=90)
    obj = json.loads(raw)
    now = time.time_ns() // 1_000_000
    if (type(obj) is not dict
            or obj.get("schema_version") != "j1_rest_resume_readiness_v1"
            or obj.get("journal_integrity_verified") is not True
            or obj.get("reviewed_research_contracts") != 2
            or obj.get("research_closed_24h_ranked_contracts") != 2
            or obj.get("orders_sent") is not False
            or obj.get("live_trading_authorized") is not False
            or obj.get("historical_checkpoint_gaps_present") is not True
            or obj.get("historical_unpublished_hours") != 21
            or obj.get("status") != "historical_checkpoint_gaps_require_review"
            or type(obj.get("last_published_end_ms")) is not int
            or not 0 <= now - obj["last_published_end_ms"] <= 2*3_600_000):
        raise ValueError("owner_n2_sqlite_readiness_gate_failed")
    return obj


def preflight(*, source: Path, root: Path, python: Path, sha: str) -> dict:
    if (os.name != "posix" or pwd is None or os.geteuid() != 0 or os.getuid() != 0
            or socket.gethostname() != HOSTNAME):
        raise PermissionError("wrong_host_or_uid")
    # The verified Python venv entrypoint is intentionally a symlink to
    # the OS-owned interpreter. Refuse any other symlink or interpreter.
    approved_python = Path("/home/cia-probe/agent/ws-venv/bin/python")
    if (not all(isinstance(p, Path) and p.is_absolute()
                and not p.is_symlink() for p in (source, root))
            or python != approved_python
            or not python.is_file()
            or python.resolve(strict=True) != Path("/usr/bin/python3.12")
            or not source.is_dir()
            or not root.is_dir() or root in source.parents
            or source in root.parents):
        raise ValueError("invalid_release_paths")
    expected_owner = pwd.getpwnam("cia-probe").pw_uid
    for path in (root, root / "lease", root / "epochs"):
        st = path.lstat()
        if (not path.is_dir() or path.is_symlink()
                or st.st_uid != expected_owner
                or st.st_mode & 0o777 != 0o700):
            raise ValueError("owner_root_untrusted")
    if next((root / "lease").iterdir(), None) is not None or (
            next((root / "epochs").iterdir(), None) is not None):
        raise ValueError("release_root_not_new_empty")
    if _call(["/usr/bin/timedatectl", "show",
              "--property=NTPSynchronized", "--value"]) != "yes":
        raise ValueError("ntp_unavailable")
    # Root's Git refuses a cia-probe-owned repository as dubious
    # ownership. Read Git metadata *as the actual worktree owner*;
    # never weaken safe.directory or root's global Git configuration.
    owner_git = ["/usr/sbin/runuser", "-u", "cia-probe", "--",
                 "/usr/bin/git", "-C", str(source)]
    if _call(owner_git + ["rev-parse", "HEAD"]) != sha:
        raise ValueError("release_sha_drift")
    if _call(owner_git + ["status", "--porcelain"]):
        raise ValueError("release_source_dirty")
    if _call(owner_git + ["remote", "get-url", "origin"]) != EXPECTED_ORIGIN:
        raise ValueError("remote_drift")
    for unit, digest in EXPECTED_N2_UNIT_HASH.items():
        path = UNIT_ROOT / unit
        if path.is_symlink() or not path.is_file():
            raise ValueError("n2_unit_path_drift")
        if _call(["/usr/bin/git", "hash-object", str(path)]) != digest:
            raise ValueError("n2_unit_sha_drift")
    n2_timer, n2_service = _show(N2_TIMER), _show(N2_SERVICE)
    if (n2_timer != {"LoadState": "loaded", "ActiveState": "active",
                     "UnitFileState": "enabled"}
            or n2_service != {"LoadState": "loaded", "ActiveState": "inactive",
                              "UnitFileState": "static"}):
        raise ValueError("unexpected_live_n2_state")
    for name in (N50_TIMER, N50_SERVICE, FALLBACK_SERVICE):
        if ((UNIT_ROOT / name).exists() or (UNIT_ROOT / name).is_symlink()
                or _show(name)["LoadState"] != "not-found"):
            raise ValueError("n50_already_installed")
    audit = _audit_n2(source=source, python=python)
    # A separately owner-created N2 rollback snapshot is mandatory.
    # Never trust the gateway's obsolete finite-only audit for this gate.
    backup = root / "n2-before-cutover.sqlite"
    if backup.is_symlink() or not backup.is_file():
        raise ValueError("n2_rollback_copy_missing")
    st = backup.lstat()
    if (st.st_uid != expected_owner or st.st_nlink != 1
            or not stat.S_ISREG(st.st_mode)
            or stat.S_IMODE(st.st_mode) != 0o600
            or not 0 < st.st_size <= 16 * 1024 * 1024):
        raise ValueError("n2_rollback_copy_permissions_invalid")
    with closing(sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True,
                                timeout=2)) as check:
        check.execute("PRAGMA query_only=ON")
        if (check.execute("PRAGMA integrity_check").fetchone() != ("ok",)
                or check.execute("SELECT COUNT(*) FROM candles").fetchone() !=
                   (audit["stored_candles"],)
                or check.execute("SELECT COUNT(*) FROM published_hour").fetchone()
                   != (audit["published_hours"],)):
            raise ValueError("n2_rollback_copy_stale_or_invalid")
    backup_digest = sha256(backup.read_bytes()).hexdigest()
    service, timer = render_n50_managed_systemd(
        owner="cia-probe", repo=str(source), python=str(python), root=str(root))
    if service.count("After=network-online.target\n") != 1:
        raise ValueError("service_template_drift")
    service = service.replace("After=network-online.target\n",
                              "After=network-online.target\n"
                              "OnFailure=" + FALLBACK_SERVICE + "\n")
    fallback = (source / "deploy/systemd" /
                "cia-j1-n50-fallback.service.template").read_text("ascii")
    if (fallback.count("User=root\n") != 1
            or fallback.count("ExecStart=-/usr/bin/systemctl disable --now "
                              + N50_TIMER + "\n") != 1
            or fallback.count("ExecStartPost=/usr/bin/systemctl enable --now "
                              + N2_TIMER + "\n") != 1
            or "ExecStart=/bin/" in fallback):
        raise ValueError("fallback_template_drift")
    return {"source_sha": sha, "n2_integrity": True,
            "n2_published_hours": audit["published_hours"],
            "n2_stored_candles": audit["stored_candles"],
            "backup_sha256": backup_digest,
            "known_historical_gaps": 21,
            "n50_root_private_and_empty": True,
            "service_text": service, "timer_text": timer,
            "fallback_text": fallback}


def _unit_write(name: str, body: str) -> None:
    dest = UNIT_ROOT / name
    temp = UNIT_ROOT / ("." + name + ".d297-new")
    if dest.exists() or dest.is_symlink() or temp.exists() or temp.is_symlink():
        raise ValueError("unit_destination_not_empty")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as out:
            out.write(body.encode("ascii"))
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, dest)
    finally:
        if temp.exists():
            temp.unlink()
    directory_fd = os.open(UNIT_ROOT, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _rollback() -> bool:
    ok = True
    # A failed first unit write may leave neither N50 unit installed.
    # Missing units are not a rollback error, and must not prevent N2 restore.
    for name, argv in (
        (N50_TIMER, ["/usr/bin/systemctl", "disable", "--now", N50_TIMER]),
        (N50_SERVICE, ["/usr/bin/systemctl", "stop", N50_SERVICE]),
    ):
        if (UNIT_ROOT / name).is_file():
            try:
                _call(argv, timeout=30)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                ok = False
    for name in (N50_TIMER, N50_SERVICE, FALLBACK_SERVICE):
        path = UNIT_ROOT / name
        if path.is_file() and not path.is_symlink():
            try:
                path.unlink()
            except OSError:
                ok = False
    try:
        _call(["/usr/bin/systemctl", "daemon-reload"], timeout=30)
        _call(["/usr/bin/systemctl", "enable", "--now", N2_TIMER], timeout=30)
        if (_show(N2_TIMER).get("ActiveState") != "active"
                or _show(N2_TIMER).get("UnitFileState") != "enabled"):
            ok = False
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError):
        ok = False
    return ok


def execute(*, source: Path, root: Path, python: Path, sha: str,
            confirm_controlled_cutover: bool = False,
            allow_systemd_modifications: bool = False) -> dict:
    result = {
        "schema_version": "j1-n50-release-d297-v1",
        "status": "blocked", "n2_integrity_checked": False,
        "systemd_modified": False, "n50_timer_enabled": False,
        "rollback_succeeded": None, "orders_sent": False,
        "live_trading_authorized": False, "continuous_collector_verified": False,
    }
    # Preflight/plan reads real N2 and GitHub-pinned source but changes nothing.
    plan = preflight(source=source, root=root, python=python, sha=sha)
    result["n2_integrity_checked"] = True
    result["n2_stored_candles"] = plan["n2_stored_candles"]
    result["n2_rollback_backup_sha256"] = plan["backup_sha256"]
    if confirm_controlled_cutover is not True or allow_systemd_modifications is not True:
        result["status"] = "preflight_pass_no_changes"
        return result
    changed = False
    previous_term = signal.getsignal(signal.SIGTERM)
    def terminated(_signum, _frame):
        raise InterruptedError("cutover_interrupted")
    signal.signal(signal.SIGTERM, terminated)
    try:
        changed = True
        _unit_write(FALLBACK_SERVICE, plan["fallback_text"])
        _unit_write(N50_SERVICE, plan["service_text"])
        _unit_write(N50_TIMER, plan["timer_text"])
        _call(["/usr/bin/systemctl", "daemon-reload"], timeout=30)
        _call(["/usr/bin/systemd-analyze", "verify",
               str(UNIT_ROOT/N50_SERVICE), str(UNIT_ROOT/N50_TIMER),
               str(UNIT_ROOT/FALLBACK_SERVICE)],
              timeout=30)
        if _show(N2_SERVICE)["ActiveState"] != "inactive":
            raise RuntimeError("n2_became_active")
        _call(["/usr/bin/systemctl", "disable", "--now", N2_TIMER], timeout=30)
        if _show(N2_SERVICE)["ActiveState"] != "inactive":
            raise RuntimeError("n2_service_not_quiesced")
        from scripts.preflight_j1_n50_systemd_isolation import (
            n50_systemd_n2_quiescence,
        )
        if n50_systemd_n2_quiescence(
                require_n2_quiesced=True)["status"] != "n2_quiesced_preflight_only":
            raise RuntimeError("n2_quiescence_not_verified")
        _call(["/usr/bin/systemctl", "enable", "--now", N50_TIMER], timeout=30)
        n50 = _show(N50_TIMER)
        n2 = _show(N2_TIMER)
        if (n50 != {"LoadState": "loaded", "ActiveState": "active",
                    "UnitFileState": "enabled"}
                or n2 != {"LoadState": "loaded", "ActiveState": "inactive",
                          "UnitFileState": "disabled"}
                or _show(N2_SERVICE)["ActiveState"] != "inactive"):
            raise RuntimeError("postflight_cutover_failed")
        result["status"] = "n50_timer_enabled_waiting_first_hour"
        result["systemd_modified"] = True
        result["n50_timer_enabled"] = True
        return result
    except (OSError, RuntimeError, ValueError, PermissionError,
            subprocess.TimeoutExpired, InterruptedError):
        if changed:
            result["rollback_succeeded"] = _rollback()
            result["status"] = ("rolled_back_to_n2" if result["rollback_succeeded"]
                                else "CRITICAL_rollback_failed")
        return result
    finally:
        signal.signal(signal.SIGTERM, previous_term)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--python", type=Path, required=True)
    p.add_argument("--expected-sha", required=True, dest="sha")
    p.add_argument("--confirm-controlled-cutover", action="store_true")
    p.add_argument("--allow-systemd-modifications", action="store_true")
    args = p.parse_args(argv)
    try:
        out = execute(**vars(args))
    except (OSError, ValueError, PermissionError, RuntimeError,
            subprocess.TimeoutExpired, json.JSONDecodeError):
        out = {"schema_version": "j1-n50-release-d297-v1", "status": "blocked",
               "orders_sent": False, "live_trading_authorized": False,
               "systemd_modified": False}
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if out["status"] in (
        "preflight_pass_no_changes", "n50_timer_enabled_waiting_first_hour"
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
