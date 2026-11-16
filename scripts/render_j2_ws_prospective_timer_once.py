"""J2 #663: render (never install) candidate isolated owner systemd units.

No operations, paths or timestamps are accepted beyond a SHA40 of code
ALREADY merged and verified. The output is text only; a separate gated
release must install and enable the units.
"""
from __future__ import annotations

import argparse
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
OWNER_ROOT = "/home/cia-probe/agent"


def service_unit(sha: str) -> str:
    if type(sha) is not str or _SHA.fullmatch(sha) is None:
        raise ValueError("exact merged SHA40 required")
    code = f"{OWNER_ROOT}/j2-owner-prospective-d362-{sha[:12]}/code"
    return (
        "[Unit]\n"
        "Description=CIA J2 owner ex-ante research one-shot (NOT financial execution)\n"
        "After=cia-j1-n50-ws.service\n"
        "[Service]\n"
        "Type=oneshot\n"
        "User=cia-probe\n"
        "Group=cia-probe\n"
        f"WorkingDirectory={code}\n"
        "Environment=PYTHONDONTWRITEBYTECODE=1\n"
        "Environment=PYTHONNOUSERSITE=1\n"
        f"ExecStart={OWNER_ROOT}/ws-venv/bin/python -B -m "
        "scripts.run_j2_ws_owner_recurring_once "
        "--allow-private-readonly-research --allow-private-ledger-write "
        "--confirm-dedicated-owner-tick\n"
        "TimeoutStartSec=180\n"
        "UMask=0077\n"
        "NoNewPrivileges=yes\n"
        "PrivateNetwork=yes\n"
        "PrivateTmp=yes\n"
        "ProtectSystem=strict\n"
        "ProtectHome=read-only\n"
        f"ReadWritePaths={OWNER_ROOT}/j2-ws-prospective-private\n"
    )


def timer_unit() -> str:
    return (
        "[Unit]\n"
        "Description=CIA J2 research owner hourly attempt, no backlog or catch-up\n"
        "[Timer]\n"
        "OnCalendar=*-*-* *:07:00 UTC\n"
        "AccuracySec=5s\n"
        "RandomizedDelaySec=0\n"
        "Persistent=false\n"
        "Unit=cia-j2-owner-prospective.service\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--merged-sha", required=True)
    p.add_argument("--unit", choices=("service", "timer"), required=True)
    args = p.parse_args(argv)
    # Require the SHA even for timer, so planning always pins one commit.
    if _SHA.fullmatch(args.merged_sha) is None:
        p.error("exact merged SHA40 required")
    print(service_unit(args.merged_sha) if args.unit == "service"
          else timer_unit(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
