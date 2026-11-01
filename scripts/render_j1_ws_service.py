"""Render, but NEVER install/enable, an owner-only J1 WS systemd unit.

All inputs must be explicitly supplied. The rendered unit is printed only;
no state, network, filesystem or service-manager action is performed.
"""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import re

_TEMPLATE = (Path(__file__).resolve().parent.parent / "deploy" / "systemd"
             / "cia-j1-ws-owner.service.template")
_USERNAME = re.compile(r"[a-z_][a-z0-9_-]{0,31}\Z")
_PATH = re.compile(r"/[A-Za-z0-9_./-]+\Z")


def _path(value: str) -> PurePosixPath:
    if (type(value) is not str or len(value) > 240
            or _PATH.fullmatch(value) is None
            or ".." in PurePosixPath(value).parts or "//" in value or value == "/"):
        raise ValueError("unsafe absolute service path")
    return PurePosixPath(value)


def render_j1_ws_unit(*, username: str, repo_root: str,
                      python_bin: str, private_dir: str,
                      template: str | None = None) -> str:
    if type(username) is not str or _USERNAME.fullmatch(username) is None:
        raise ValueError("unsafe owner name")
    repo = _path(repo_root)
    python = _path(python_bin)
    private = _path(private_dir)
    if repo == private or repo in private.parents or private in repo.parents:
        raise ValueError("journal must be separate from the public repository")
    if template is None:
        template = _TEMPLATE.read_text(encoding="ascii")
    substitutions = {
        "@OWNER_USER@": username, "@REPO_ROOT@": str(repo),
        "@PYTHON_BIN@": str(python), "@PRIVATE_DIR@": str(private),
    }
    for needle, replacement in substitutions.items():
        if needle not in template:
            raise ValueError("systemd service template is incomplete")
        template = template.replace(needle, replacement)
    if "@" in template:
        raise ValueError("unexpected systemd template placeholder")
    return template


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-user", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--python-bin", required=True)
    parser.add_argument("--private-dir", required=True)
    args = parser.parse_args(argv)
    try:
        body = render_j1_ws_unit(username=args.owner_user,
                                 repo_root=args.repo_root,
                                 python_bin=args.python_bin,
                                 private_dir=args.private_dir)
    except ValueError:
        parser.error("unsafe or incompatible service configuration")
    print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())