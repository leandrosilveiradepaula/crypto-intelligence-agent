"""J3 #667: print candidate scoring-only systemd units; never install them."""
from __future__ import annotations

import argparse
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
OWNER_ROOT = "/home/cia-probe/agent"


def service_unit(sha: str) -> str:
    if type(sha) is not str or _SHA.fullmatch(sha) is None:
        raise ValueError("SHA40 pin required")
    code = f"{OWNER_ROOT}/j2-owner-prospective-d362-{sha[:12]}/code"
    return (
        "[Unit]\n"
        "Description=CIA J3 prospective 1h 4h 8h read-only reference scoring\n"
        "After=cia-j1-n50-ws.service\n"
        "[Service]\n"
        "Type=oneshot\n"
        "User=cia-probe\n"
        "Group=cia-probe\n"
        f"WorkingDirectory={code}\n"
        "Environment=PYTHONDONTWRITEBYTECODE=1\n"
        "Environment=PYTHONNOUSERSITE=1\n"
        f"ExecStart={OWNER_ROOT}/ws-venv/bin/python -B -m scripts.run_j3_ws_owner_forward_tick_once "
        "--allow-private-readonly-research --allow-private-ledger-read "
        "--confirm-dedicated-owner-score-tick --notional 100 "
        "--entry-fee-bps 4 --exit-fee-bps 6 "
        "--entry-slippage-bps 2 --exit-slippage-bps 3\n"
        "TimeoutStartSec=270\n"
        "UMask=0077\n"
        "NoNewPrivileges=yes\n"
        "PrivateNetwork=yes\n"
        "PrivateTmp=yes\n"
        "ProtectSystem=strict\n"
        "ProtectHome=read-only\n"
    )


def timer_unit() -> str:
    return (
        "[Unit]\n"
        "Description=CIA J3 hourly readonly prospective scoring attempt\n"
        "[Timer]\n"
        "OnCalendar=*-*-* *:17:00 UTC\n"
        "AccuracySec=5s\n"
        "RandomizedDelaySec=0\n"
        "Persistent=false\n"
        "Unit=cia-j3-owner-forward.service\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged-sha", required=True)
    parser.add_argument("--unit", choices=("service", "timer"), required=True)
    args = parser.parse_args(argv)
    if _SHA.fullmatch(args.merged_sha) is None:
        parser.error("SHA40 pin required")
    print(service_unit(args.merged_sha) if args.unit == "service"
          else timer_unit(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
