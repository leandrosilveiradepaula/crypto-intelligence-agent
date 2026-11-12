"""D320: root-only one-time cutover of an ALREADY bootstrapped N50 WS epoch.

This release action is deliberately separate from GitHub merges and from the
read-only MCP broker. Opt-in is explicit; it never retrieves market data,
replays the halted N50 REST DB, creates orders, or changes the old REST N50
units. On failures after isolation, N2 is restored.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:  # Windows/offline CI only
    pwd = None
import re
import socket
import stat
import subprocess
import time
from typing import Any

from scripts.render_j1_n50_ws_systemd import render_n50_ws_systemd

OWNER = "cia-probe"
HOSTNAME = "srv1319424"
PYTHON = "/home/cia-probe/agent/ws-venv/bin/python"
UNIT_DIR = Path("/etc/systemd/system")
N2_TIMER = "cia-j1-rest-hourly.timer"
N2_SERVICE = "cia-j1-rest-hourly.service"
OLD_N50_TIMER = "cia-j1-n50-managed.timer"
OLD_N50_SERVICE = "cia-j1-n50-managed.service"
WS_TIMER = "cia-j1-n50-ws.timer"
WS_SERVICE = "cia-j1-n50-ws.service"
WS_FALLBACK = "cia-j1-n50-ws-fallback.service"

# Baseline audited by the bounded VPS broker (12 Nov 2026 UTC).
EXISTING_UNIT_SHA256 = {
    N2_TIMER: "94aad413a27e4c5f73699c641c36ff55bd380f87b03e1a7e95748e1e0e44bbcf",
    N2_SERVICE: "0f010d323ad36c43d2e09a817deb455aa0f18fbd1a2779b756d6d6b3116db5d5",
    OLD_N50_TIMER: "477ac621744c9ca180f6be4a94e6f33b5e280f57fc64434a0e5d23590662dc69",
    OLD_N50_SERVICE: "41db7486de1f007a78f95cd44fd90091b6bc616376d3f7c15aefdc1de1c82de2",
    "cia-j1-n50-fallback.service":
        "bc6c0c32e13ce2a2442cec7b85c62bb7553d63909919b1a7a2d5cc96492e3ac0",
}
_SAFE_PATH = re.compile(r"/home/cia-probe/agent/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _base(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-ws-d320-root-release-v1",
        "status": status,
        "preflight_verified": False,
        "owner_scope_cache_verified": False,
        "units_created": False,
        "n2_quiesced": False,
        "n50_ws_timer_enabled": False,
        "n2_restored_after_failure": None,
        "old_n50_rest_units_modified": False,
        "old_n50_rest_database_modified": False,
        "orders_sent": False,
        "live_trading_authorized": False,
        "marketwide_top50_verified": False,
    }


def _run(argv: list[str], *, cwd: str | None = None,
         timeout: int = 25) -> str:
    result = subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if result.returncode != 0 or len(result.stdout) > 30_000:
        raise RuntimeError("release_command_failed")
    return result.stdout.strip()


def _show(unit: str) -> dict[str, str]:
    stdout = _run([
        "/usr/bin/systemctl", "show", unit,
        "--property=LoadState", "--property=ActiveState",
        "--property=UnitFileState", "--no-pager",
    ])
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if line.count("=") != 1:
            raise ValueError("systemd_state_malformed")
        key, value = line.split("=", 1)
        if key not in ("LoadState", "ActiveState", "UnitFileState") or key in values:
            raise ValueError("systemd_state_malformed")
        values[key] = value
    if set(values) != {"LoadState", "ActiveState", "UnitFileState"}:
        raise ValueError("systemd_state_malformed")
    return values


def _safe_owner_dir(path: Path, uid: int) -> None:
    if (type(path) is not Path or not path.is_absolute()
            or _SAFE_PATH.fullmatch(str(path)) is None
            or path.resolve(strict=True) != path):
        raise ValueError("owner_directory_path_invalid")
    s = path.lstat()
    if (not stat.S_ISDIR(s.st_mode)
            or s.st_uid != uid or stat.S_IMODE(s.st_mode) != 0o700):
        raise ValueError("owner_directory_DAC_mismatch")


def _owner_verification(source: Path, manifest: Path, ws_dir: Path) -> None:
    program = (
        "import os, time;"
        "from pathlib import Path;"
        "from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope;"
        "from crypto_intelligence_agent.j1_n50_ws_private_cache import load_n50_ws_dynamic_admission;"
        "t=time.time_ns()//1000000;"
        "s=load_private_ranked_scope(Path(os.environ['CIA_MANIFEST']),now_ms=t);"
        "a=load_n50_ws_dynamic_admission("
        "directory=Path(os.environ['CIA_WS']),current_at_ms=t,"
        "expected_ranked_scope_sha256=s['scope_digest_sha256'],"
        "allow_private_scope_read=True);"
        "assert a.status=='private_n50_ws_admission_loaded_revalidated';"
        "assert a.ranked_scope==s and a.admission.selected_contracts==50;"
        "print('OWNER_SCOPE_CACHE_50_VERIFIED')"
    )
    out = _run([
        "/usr/sbin/runuser", "-u", OWNER, "--",
        "/usr/bin/env", "PYTHONDONTWRITEBYTECODE=1",
        "CIA_MANIFEST=" + str(manifest),
        "CIA_WS=" + str(ws_dir),
        PYTHON, "-c", program,
    ], cwd=str(source), timeout=35)
    if out != "OWNER_SCOPE_CACHE_50_VERIFIED":
        raise ValueError("owner_cache_proof_missing")


def _old_units_and_collectors_ok() -> bool:
    for name, expected_hash in EXISTING_UNIT_SHA256.items():
        file = UNIT_DIR / name
        if (file.is_symlink() or not file.is_file()
                or sha256(file.read_bytes()).hexdigest() != expected_hash):
            return False
    return (
        _show(N2_TIMER) == {
            "LoadState": "loaded", "ActiveState": "active",
            "UnitFileState": "enabled",
        }
        and _show(N2_SERVICE) == {
            "LoadState": "loaded", "ActiveState": "inactive",
            "UnitFileState": "static",
        }
        and _show(OLD_N50_TIMER) == {
            "LoadState": "loaded", "ActiveState": "inactive",
            "UnitFileState": "disabled",
        }
        and _show(OLD_N50_SERVICE) in (
            {"LoadState": "loaded", "ActiveState": "failed",
             "UnitFileState": "static"},
            {"LoadState": "loaded", "ActiveState": "inactive",
             "UnitFileState": "static"},
        )
    )


def preflight(*, source: Path, expected_sha: str,
              manifest: Path, ws_dir: Path) -> tuple[str, str, str]:
    """No side effects. Must pass before ANY systemd installation."""
    if (os.name != "posix" or pwd is None or os.getuid() != 0 or os.geteuid() != 0
            or socket.gethostname() != HOSTNAME
            or type(expected_sha) is not str
            or _SHA.fullmatch(expected_sha) is None):
        raise PermissionError("root_host_sha_required")
    uid = pwd.getpwnam(OWNER).pw_uid
    for path in (source, manifest, ws_dir):
        _safe_owner_dir(path, uid)
    if len({source, manifest, ws_dir}) != 3:
        raise ValueError("owner_directories_not_isolated")
    if (not Path(PYTHON).is_file()
            or _run([
                "/usr/bin/timedatectl", "show",
                "--property=NTPSynchronized", "--value",
            ]) != "yes"):
        raise ValueError("ntp_or_python_unavailable")
    for name in (WS_SERVICE, WS_TIMER, WS_FALLBACK):
        if (UNIT_DIR / name).exists() or (UNIT_DIR / name).is_symlink():
            raise ValueError("ws_service_already_installed")
        if _show(name)["LoadState"] != "not-found":
            raise ValueError("ws_service_preexisting")
    if not _old_units_and_collectors_ok():
        raise ValueError("old_unit_sha_or_N2_state_drift")
    git = ["/usr/sbin/runuser", "-u", OWNER, "--",
           "/usr/bin/git", "-C", str(source)]
    if (_run(git + ["rev-parse", "HEAD"]) != expected_sha
            or _run(git + ["status", "--porcelain"])
            or _run(git + ["remote", "get-url", "origin"])
                != "https://github.com/leandrosilveiradepaula/crypto-intelligence-agent.git"):
        raise ValueError("source_rev_or_origin_drift")
    _owner_verification(source, manifest, ws_dir)
    service, timer, fallback = render_n50_ws_systemd(
        owner=OWNER, repo=str(source), python=PYTHON,
        manifest=str(manifest), ws_directory=str(ws_dir),
    )
    if len(service) > 16_000 or len(timer) > 4_000 or len(fallback) > 4_000:
        raise ValueError("unit_render_bounds")
    return service, timer, fallback


def _write_new_unit_once(name: str, text: str) -> None:
    if name not in (WS_SERVICE, WS_TIMER, WS_FALLBACK):
        raise ValueError("unit_not_allowlisted")
    file = UNIT_DIR / name
    data = text.encode("ascii")
    fd = os.open(
        file, os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0), 0o644,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _rollback() -> bool:
    """Never modify the old REST N50 units; recover only the N2 timer."""
    try:
        _run(["/usr/bin/systemctl", "disable", "--now", WS_TIMER])
    except (OSError, RuntimeError, subprocess.SubprocessError):
        pass
    try:
        _run(["/usr/bin/systemctl", "enable", "--now", N2_TIMER])
        return _show(N2_TIMER) == {
            "LoadState": "loaded", "ActiveState": "active",
            "UnitFileState": "enabled",
        }
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        return False


def execute(
    *, source: Path, expected_sha: str,
    manifest: Path, ws_dir: Path,
    confirm_n50_ws_cutover: bool = False,
    allow_systemd_modifications: bool = False,
) -> dict[str, Any]:
    out = _base("blocked")
    try:
        units = preflight(source=source, expected_sha=expected_sha,
                          manifest=manifest, ws_dir=ws_dir)
    except (OSError, ValueError, TypeError, PermissionError,
            subprocess.SubprocessError, RuntimeError):
        out["status"] = "preflight_blocked_N2_untouched"
        return out
    out["preflight_verified"] = True
    out["owner_scope_cache_verified"] = True
    if not (confirm_n50_ws_cutover is True
            and allow_systemd_modifications is True):
        out["status"] = "preflight_pass_no_changes"
        return out
    n2_was_changed = False
    try:
        for name, content in zip(
            (WS_SERVICE, WS_TIMER, WS_FALLBACK), units,
        ):
            _write_new_unit_once(name, content)
        out["units_created"] = True
        _run(["/usr/bin/systemctl", "daemon-reload"])
        for name in (WS_SERVICE, WS_TIMER, WS_FALLBACK):
            if _show(name)["LoadState"] != "loaded":
                raise RuntimeError("ws_unit_not_loaded")
        # One last baseline check, before switching ANY active collector.
        if not _old_units_and_collectors_ok():
            raise RuntimeError("old_unit_drift_before_cutover")
        # Roll back N2 even if systemctl returns a failure after partially
        # disabling the timer.
        n2_was_changed = True
        _run(["/usr/bin/systemctl", "disable", "--now", N2_TIMER])
        _run(["/usr/bin/systemctl", "enable", "--now", WS_TIMER])
        if (_show(WS_TIMER) != {
                "LoadState": "loaded", "ActiveState": "active",
                "UnitFileState": "enabled"}
                or _show(N2_TIMER) != {
                    "LoadState": "loaded", "ActiveState": "inactive",
                    "UnitFileState": "disabled"}
                or _show(OLD_N50_TIMER)["ActiveState"] != "inactive"):
            raise RuntimeError("ws_cutover_state_unexpected")
        out.update(
            status="n50_ws_timer_enabled_N2_fallback_preserved",
            n2_quiesced=True, n50_ws_timer_enabled=True,
        )
        return out
    except (OSError, ValueError, TypeError, RuntimeError,
            subprocess.SubprocessError):
        if n2_was_changed:
            out["n2_restored_after_failure"] = _rollback()
            out["status"] = ("rolled_back_to_N2" if out["n2_restored_after_failure"]
                             else "rollback_N2_requires_owner_action")
        else:
            out["status"] = "ws_unit_install_failed_N2_untouched"
        return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ws-dir", type=Path, required=True)
    parser.add_argument("--confirm-n50-ws-cutover", action="store_true")
    parser.add_argument("--allow-systemd-modifications", action="store_true")
    args = parser.parse_args(argv)
    out = execute(
        source=args.source, expected_sha=args.expected_sha,
        manifest=args.manifest, ws_dir=args.ws_dir,
        confirm_n50_ws_cutover=args.confirm_n50_ws_cutover,
        allow_systemd_modifications=args.allow_systemd_modifications,
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if out["status"] in (
        "preflight_pass_no_changes",
        "n50_ws_timer_enabled_N2_fallback_preserved",
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
