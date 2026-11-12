"""D295: read-only systemd N2 state gate for a separate managed N50 service.

No service modification; fail closed on unavailable systemctl, unexpected
status, active N2 timer/worker or missing explicit opt-in. Never trades.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any

_SYSTEMCTL = "/usr/bin/systemctl"
_N2 = ("cia-j1-rest-hourly.timer", "cia-j1-rest-hourly.service")


def n50_systemd_n2_quiescence(
    *, require_n2_quiesced: bool = False,
    command_runner=None,
) -> dict[str, Any]:
    out = {
        "schema_version":"j1-n50-n2-isolation-preflight-v1",
        "status":"optin_required",
        "n2_timer_inactive":False,
        "n2_service_inactive":False,
        "n50_start_authorized":False,
        "n50_systemd_modified":False,
        "n2_systemd_modified":False,
        "network_requests":0,
        "orders_sent":False,
        "marketwide_top50_verified":False,
    }
    if require_n2_quiesced is not True:
        return out
    out["status"]="blocked"
    runner = subprocess.run if command_runner is None else command_runner
    try:
        for unit in _N2:
            cp = runner(
                [_SYSTEMCTL,"show",unit,"--property=ActiveState","--value",
                 "--no-pager"],
                capture_output=True,text=True,timeout=3,check=False,
            )
            # Check both exit status AND exact canonical state. A failed,
            # unknown, activating, waiting or active service is not a gate.
            if (type(cp.returncode) is not int or cp.returncode != 0
                    or type(cp.stdout) is not str
                    or cp.stdout.strip() != "inactive"
                    or type(cp.stderr) is not str or cp.stderr.strip()):
                return out
            if unit.endswith(".timer"):
                out["n2_timer_inactive"]=True
            else:
                out["n2_service_inactive"]=True
    except (subprocess.SubprocessError, OSError, ValueError, TypeError):
        return out
    out["status"]="n2_quiesced_preflight_only"
    # This is a read-only prerequisite; it never grants activation.
    return out


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--require-n2-quiesced",action="store_true")
    args=p.parse_args(argv)
    out=n50_systemd_n2_quiescence(**vars(args))
    print(json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if out["status"]=="n2_quiesced_preflight_only" else 65


if __name__=="__main__":
    raise SystemExit(main())
