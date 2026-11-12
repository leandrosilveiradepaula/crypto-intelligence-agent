"""D318: render OFF-by-default N50 WebSocket preclose systemd units; no install."""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.render_j1_n50_managed_systemd import OWNER_RE, PATH_RE

ROOT = Path(__file__).resolve().parent.parent / "deploy" / "systemd"
_TEMPLATES = (
    "cia-j1-n50-ws.service.template",
    "cia-j1-n50-ws.timer.template",
    "cia-j1-n50-ws-fallback.service.template",
)
_HALT_REST = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")


def render_n50_ws_systemd(
    *, owner: str, repo: str, python: str, manifest: str, ws_directory: str,
) -> tuple[str, str, str]:
    """Render only; never read private data, alter service or enable timer."""
    if (type(owner) is not str or OWNER_RE.fullmatch(owner) is None
            or owner == "root"):
        raise ValueError("unsafe_ws_owner")
    named = (repo, python, manifest, ws_directory)
    if (any(type(p) is not str or PATH_RE.fullmatch(p) is None
            or ".." in Path(p).parts or len(p) > 230 for p in named)
            or len(set(named)) != 4):
        raise ValueError("unsafe_ws_unit_path")
    rp, py, mf, ws = (Path(p) for p in named)
    if (any(ws in path.parents or path in ws.parents for path in (rp, py, mf))
            or rp in mf.parents or mf in rp.parents
            or ws == _HALT_REST or _HALT_REST in ws.parents
            or ws in _HALT_REST.parents
            or ws.is_relative_to(Path("/etc/systemd"))
            or ws.is_relative_to(Path("/usr"))
            or ws.is_relative_to(Path("/tmp"))):
        raise ValueError("ws_unit_directory_conflict")

    service, timer, fallback = (
        (ROOT / name).read_text("ascii") for name in _TEMPLATES
    )
    for key, value in (
        ("OWNER", owner), ("REPO", repo), ("PYTHON", python),
        ("MANIFEST", manifest), ("WS_DIR", ws_directory),
    ):
        service = service.replace("@" + key + "@", value)
    if any("@" in unit for unit in (service, timer, fallback)):
        raise ValueError("unrendered_ws_unit_template")

    expected_exec = (
        "ExecStart=" + python
        + " -m scripts.run_j1_n50_ws_owner_cached_once"
        + " --manifest-directory " + manifest
        + " --ws-directory " + ws_directory
        + " --allow-private-manifest-read --allow-private-ws-scope-read"
        + " --allow-private-ws-writer --allow-public-websocket"
        + " --confirm-region-and-personal-research"
        + " --allow-create-ws-journal\n"
    )
    checks = (
        service.count("ExecStart=") == 1,
        service.count("ExecStartPre=") == 1,
        expected_exec in service,
        ("ExecStartPre=" + python
         + " -m scripts.preflight_j1_n50_ws_systemd"
         + " --require-old-collectors-quiesced\n") in service,
        ("User=" + owner + "\n") in service,
        ("WorkingDirectory=" + repo + "\n") in service,
        ("ReadWritePaths=" + ws_directory + "\n") in service,
        "OnFailure=cia-j1-n50-ws-fallback.service\n" in service,
        "Restart=no\n" in service,
        "OnCalendar=*-*-* *:59:30 UTC\n" in timer,
        "AccuracySec=1s\n" in timer,
        "RandomizedDelaySec=0\n" in timer,
        "Persistent=false\n" in timer,
        "Unit=cia-j1-n50-ws.service\n" in timer,
        "ExecStart=-/usr/bin/systemctl disable --now cia-j1-n50-ws.timer\n" in fallback,
        "ExecStartPost=/usr/bin/systemctl enable --now cia-j1-rest-hourly.timer\n" in fallback,
        "cia-j1-n50-managed.timer" not in timer,
        "scripts.run_j1_n50_managed_once" not in service,
        "scripts.cache_j1_n50_ws_metadata_owner_once" not in service,
        "systemctl enable" not in service + timer,
    )
    if not all(checks):
        raise ValueError("ws_systemd_template_invariant_failed")
    return service, timer, fallback


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--python", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--ws-directory", required=True)
    a = p.parse_args(argv)
    service, timer, fallback = render_n50_ws_systemd(
        owner=a.owner, repo=a.repo, python=a.python,
        manifest=a.manifest, ws_directory=a.ws_directory,
    )
    print("# INERT N50 WS SERVICE (NOT INSTALLED)\n" + service
          + "\n# INERT N50 WS TIMER (NOT INSTALLED)\n" + timer
          + "\n# INERT N50 WS FALLBACK (NOT INSTALLED)\n" + fallback)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
