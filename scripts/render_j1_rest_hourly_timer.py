"""Render J1/M1 inert systemd files. Never install, enable or start."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent / "deploy" / "systemd"
_OWNER = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
_SAFE = re.compile(r"/[A-Za-z0-9_./-]{1,230}\Z")


def render(*, owner: str, repo: str, python: str, frozen: str,
           output: str, max_assets: int = 2) -> tuple[str, str]:
    if (type(owner) is not str or not _OWNER.fullmatch(owner)
            or owner == "root" or type(max_assets) is not int
            or not 1 <= max_assets <= 50):
        raise ValueError("invalid owner or research budget")
    paths = (repo, python, frozen, output)
    if any(type(s) is not str or not _SAFE.fullmatch(s)
           or ".." in Path(s).parts or "//" in s for s in paths):
        raise ValueError("unsafe service path")
    repo_path, python_path, frozen_path, output_path = (Path(s) for s in paths)
    if (len(set(paths)) != 4
            or repo_path in output_path.parents
            or output_path in repo_path.parents
            or frozen_path in output_path.parents
            or output_path in frozen_path.parents
            or python_path in output_path.parents
            or output_path in python_path.parents
            or output_path in frozen_path.parents):
        raise ValueError("output or frozen database overlaps application")
    s = (ROOT / "cia-j1-rest-hourly.service.template").read_text(encoding="ascii")
    t = (ROOT / "cia-j1-rest-hourly.timer.template").read_text(encoding="ascii")
    values = dict(OWNER=owner, REPO=repo, PYTHON=python,
                  FROZEN=frozen, OUTPUT=output, MAX_ASSETS=str(max_assets))
    for k,v in values.items():
        s = s.replace("@"+k+"@", v)
    if "@" in s or "@" in t:
        raise ValueError("incomplete systemd render")
    return s,t


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner",required=True)
    p.add_argument("--repo",required=True)
    p.add_argument("--python",required=True)
    p.add_argument("--frozen",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--max-assets",type=int,default=2)
    args=p.parse_args(argv)
    s,t=render(**vars(args))
    print("# SERVICE - NOT INSTALLED\n"+s+"\n# TIMER - NOT INSTALLED\n"+t)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
