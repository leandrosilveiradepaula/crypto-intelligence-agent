"""Render safe OFF-BY-DEFAULT systemd files; never install, start, or enable."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
from crypto_intelligence_agent.j1_ops23_once_timer import timer_date, _safe_path, _SHA

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "deploy" / "systemd"
_OWNER = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")

def render_units(*, owner: str, target_utc: str, expected_sha: str,
                 repo_root: str, python_bin: str, state_dir: str,
                 service_template: str | None = None,
                 timer_template: str | None = None) -> tuple[str, str]:
    if type(owner) is not str or not _OWNER.fullmatch(owner) or owner == "root":
        raise ValueError("owner invalid")
    if type(expected_sha) is not str or not _SHA.fullmatch(expected_sha):
        raise ValueError("SHA invalid")
    close, launch = timer_date(target_utc)
    repo, python, state = (_safe_path(v) for v in (repo_root, python_bin, state_dir))
    if repo == state or repo in state.parents or state in repo.parents:
        raise ValueError("state must be outside repo")
    service = (service_template if service_template is not None else
               (TEMPLATE_DIR / "cia-j1-ops22-once.service.template").read_text(encoding="ascii"))
    timer = (timer_template if timer_template is not None else
             (TEMPLATE_DIR / "cia-j1-ops22-once.timer.template").read_text(encoding="ascii"))
    values = {
        "@OWNER@": owner, "@TARGET_UTC@": target_utc,
        "@EXPECTED_SHA@": expected_sha, "@REPO_ROOT@": str(repo),
        "@PYTHON_BIN@": str(python), "@STATE_DIR@": str(state),
        "@CALENDAR_UTC@": launch.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    for key, value in values.items():
        service, timer = service.replace(key, value), timer.replace(key, value)
    if "@" in service or "@" in timer:
        raise ValueError("unresolved systemd placeholder")
    return service, timer

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner", required=True)
    p.add_argument("--target-utc", required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--repo-root", required=True)
    p.add_argument("--python-bin", required=True)
    p.add_argument("--state-dir", required=True)
    args = p.parse_args(argv)
    service, timer = render_units(**vars(args))
    print("# START SERVICE (do not install by piping this output)")
    print(service)
    print("# START TIMER (do not install by piping this output)")
    print(timer)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
