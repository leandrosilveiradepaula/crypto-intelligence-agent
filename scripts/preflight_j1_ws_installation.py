"""J1/D268: OFF-by-default, read-only WS installation readiness survey.

The service template is already versioned. This auditor never provisions its
directory, installs/enables/starts systemd units, opens WebSockets or writes
market data. It cannot approve production activation or crypto-only identity.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Callable, Any

from crypto_intelligence_agent.j1_ws_operational_preflight import (
    _parse_systemd, _systemctl_once,
)
from scripts.render_j1_ws_service import render_j1_ws_unit

SHA = re.compile(r"[0-9a-f]{40}\Z")
OWNER = "cia-probe"
UNIT = "cia-j1-ws-owner.service"
_DIR_MAX = 240
_FORBIDDEN_ARGS = ("systemctl start", "systemctl enable", "daemon-reload")
_ROOT_PATH = Path("/home/cia-probe/agent")
_REPO = _ROOT_PATH / "repo"
_PYTHON = _ROOT_PATH / "ws-venv" / "bin" / "python"


def _default() -> dict[str, Any]:
    return {
        "schema_version": "j1-d268-ws-install-readonly-v1",
        "status": "abstain",
        "installation_blocker": "owner_optin_required",
        "service_present": False,
        "private_directory_ready": False,
        "repo_clean_at_expected_sha": False,
        "unit_template_valid": False,
        "scope_expiry_requires_separate_renewal": True,
        "service_activated": False,
        "deployment_authorized": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "source_authenticated": False,
        "network_requests": 0,
        "database_modified": False,
        "orders_sent": False,
    }


def _safe_dir(path: Path, *, owner_uid: int) -> str:
    """No path mutation; reject symlinks and dangerous inode/mode/owner."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "missing"
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner_uid:
        return "unsafe"
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_nlink < 1:
        return "unsafe"
    return "ready"


def _validate_unit(unit: str, *, repo: Path, python: Path,
                   private_dir: Path) -> None:
    if type(unit) is not str or len(unit) > 6000:
        raise ValueError("unit_invalid")
    required = (
        f"User={OWNER}", f"WorkingDirectory={repo}",
        "NoNewPrivileges=true", "ProtectSystem=strict",
        f"ReadWritePaths={private_dir}", "UMask=0077",
        "RestartPreventExitStatus=64 65 66 77 130",
        "RestartSec=30s", "StartLimitBurst=6",
        f"ExecStart={python} -m scripts.run_j1_ws_service ",
        "--allow-public-network --allow-public-websocket",
        "--allow-private-storage --confirm-region-and-personal-research",
    )
    if any(needle not in unit for needle in required):
        raise ValueError("unit_missing_safety")
    if any(needle in unit for needle in _FORBIDDEN_ARGS):
        raise ValueError("unit_mutation_invalid")
    if "Restart=always" not in unit:
        raise ValueError("unit_restart_contract_changed")
    for line in unit.splitlines():
        if line.startswith(("ExecStart=", "ExecStartPre=", "ExecStartPost=",
                            "ExecStopPost=")) and not line.startswith(
                                f"ExecStart={python} -m scripts.run_j1_ws_service "):
            raise ValueError("unit_extra_exec")


def installation_preflight(*, private_directory: Path,
                           expected_sha: str, allow_readonly: bool = False,
                           owner_ok: bool | None = None,
                           repo: Path = _REPO, python: Path = _PYTHON,
                           owner_uid: int | None = None,
                           service_reader: Callable[[], str] = _systemctl_once,
                           git_reader: Callable[[Path], tuple[str, bool]] | None = None,
                           renderer: Callable[..., str] = render_j1_ws_unit) -> dict:
    out = _default()
    owner = (os.name == "posix" and hasattr(os, "getuid")
             and os.getuid() == os.geteuid()
             and os.getuid() != 0) if owner_ok is None else owner_ok
    if (allow_readonly is not True or owner is not True
            or type(expected_sha) is not str or SHA.fullmatch(expected_sha) is None
            or not isinstance(private_directory, Path)
            or not private_directory.is_absolute()
            or not isinstance(repo, Path) or not isinstance(python, Path)
            or not repo.is_absolute() or not python.is_absolute()):
        return out
    try:
        resolved = str(private_directory)
        if (not resolved.startswith("/home/cia-probe/agent/")
                or len(resolved) > _DIR_MAX or
                ".." in private_directory.parts
                or private_directory == repo
                or repo in private_directory.parents
                or private_directory in repo.parents
                or private_directory == python
                or python in private_directory.parents
                or private_directory in python.parents
                or resolved.endswith("/run")
                or " " in resolved):
            raise ValueError("unsafe_private_path")
        uid = os.getuid() if owner_uid is None else owner_uid
        if type(uid) is not int or uid <= 0:
            raise ValueError("owner_uid_invalid")
        # An absent target is expected and must NOT be created here.
        # Every existing ancestor from agent/ downward must be a real directory.
        ancestor = _ROOT_PATH
        for part in private_directory.relative_to(_ROOT_PATH).parts:
            if ancestor.is_symlink():
                raise ValueError("symlink_ancestor")
            ancestor = ancestor / part
        if ancestor.is_symlink():
            raise ValueError("symlink_ancestor")
        dir_state = _safe_dir(private_directory, owner_uid=uid)
        if dir_state == "unsafe":
            raise ValueError("unsafe_private_directory")
        if not repo.is_dir() or not python.is_file():
            raise ValueError("repo_or_interpreter_missing")
        unit = renderer(username=OWNER, repo_root=str(repo),
                        python_bin=str(python), private_dir=resolved)
        _validate_unit(unit, repo=repo, python=python,
                       private_dir=private_directory)
        out["unit_template_valid"] = True
        if git_reader is None:
            git_reader = _readonly_git
        actual_sha, clean = git_reader(repo)
        if type(actual_sha) is not str or not SHA.fullmatch(actual_sha) or type(clean) is not bool:
            raise ValueError("git_reply_invalid")
        out["repo_clean_at_expected_sha"] = actual_sha == expected_sha and clean
        fields = _parse_systemd(service_reader())
        out["service_present"] = fields["LoadState"] != "not-found"
        out["private_directory_ready"] = dir_state == "ready"
        out["status"] = "read_only_installation_preflight"
        if out["service_present"]:
            out["installation_blocker"] = "existing_service_requires_review"
        elif not out["repo_clean_at_expected_sha"]:
            out["installation_blocker"] = "repo_not_at_expected_sha"
        elif not out["private_directory_ready"]:
            out["installation_blocker"] = "private_directory_requires_owner_provisioning"
        else:
            out["installation_blocker"] = "separate_activation_gate_required"
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        out["status"] = "abstain"
        out["installation_blocker"] = "environment_or_configuration_invalid"
        out["unit_template_valid"] = False
        out["repo_clean_at_expected_sha"] = False
        out["private_directory_ready"] = False
    return out


def _readonly_git(repo: Path) -> tuple[str, bool]:
    """Only two bounded local git reads, no fetch/pull/checkout."""
    base = ("git", "-C", str(repo))
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C",
           "GIT_OPTIONAL_LOCKS": "0"}
    results = []
    for args in (("rev-parse", "HEAD"), ("status", "--porcelain")):
        p = subprocess.run(
            base + args, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=3, check=False, text=True, encoding="ascii",
            errors="strict", env=env, close_fds=True)
        if p.returncode != 0 or len(p.stdout) > 4096:
            raise ValueError("git_read_failed")
        results.append(p.stdout.strip())
    return results[0], results[1] == ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-directory", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--allow-readonly-preflight", action="store_true")
    args = parser.parse_args(argv)
    report = installation_preflight(
        private_directory=args.private_directory,
        expected_sha=args.expected_sha,
        allow_readonly=args.allow_readonly_preflight,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "read_only_installation_preflight" else 2


if __name__ == "__main__":
    raise SystemExit(main())
