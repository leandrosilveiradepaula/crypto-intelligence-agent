"""OPS31: render off-by-default one-shot systemd units; never install/start."""
from __future__ import annotations

import argparse
from pathlib import Path

from crypto_intelligence_agent.j1_ops23_once_timer import _safe_path, _SHA
from crypto_intelligence_agent.j1_ops31_shadow_timer import timer_schedule
from scripts.render_j1_ops23_timer import _OWNER

TEMPLATES = Path(__file__).resolve().parent.parent / "deploy" / "systemd"


def render_units(*, owner: str, target_utc: str, expected_sha: str,
                 repo_root: str, python_bin: str, state_dir: str,
                 service_template: str | None = None,
                 timer_template: str | None = None) -> tuple[str, str]:
    if type(owner) is not str or not _OWNER.fullmatch(owner) or owner == "root":
        raise ValueError("invalid owner")
    if type(expected_sha) is not str or not _SHA.fullmatch(expected_sha):
        raise ValueError("invalid SHA")
    close, launch = timer_schedule(target_utc)
    repo, py, state = (_safe_path(v) for v in
                       (repo_root, python_bin, state_dir))
    if state == repo or state in repo.parents or repo in state.parents:
        raise ValueError("state must be outside repository")
    service = (service_template if service_template is not None else
               (TEMPLATES / "cia-j1-ops31-shadow-once.service.template")
               .read_text(encoding="ascii"))
    timer = (timer_template if timer_template is not None else
             (TEMPLATES / "cia-j1-ops31-shadow-once.timer.template")
             .read_text(encoding="ascii"))
    replacements = {
        "@OWNER@": owner,
        "@TARGET_UTC@": target_utc,
        "@EXPECTED_SHA@": expected_sha,
        "@REPO_ROOT@": str(repo),
        "@PYTHON_BIN@": str(py),
        "@STATE_DIR@": str(state),
        "@CALENDAR_UTC@": launch.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    for key, value in replacements.items():
        service, timer = service.replace(key, value), timer.replace(key, value)
    if "@" in service or "@" in timer:
        raise ValueError("unresolved placeholder")
    return service, timer


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("owner", "target-utc", "expected-sha", "repo-root",
                "python-bin", "state-dir"):
        p.add_argument("--" + arg, required=True)
    args = p.parse_args(argv)
    service, timer = render_units(**vars(args))
    print("# SERVICE, NOT INSTALLED")
    print(service)
    print("# TIMER, NOT INSTALLED")
    print(timer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
