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
        "n2_timer_disabled":False,
        "n2_service_inactive":False,
        "n2_units_loaded":False,
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
        expected_keys = frozenset(("LoadState", "ActiveState", "UnitFileState"))
        states = {}
        for unit in _N2:
            cp = runner(
                [_SYSTEMCTL, "show", unit, "--property=LoadState",
                 "--property=ActiveState", "--property=UnitFileState",
                 "--no-pager"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            # A missing/unloaded unit can return ActiveState=inactive.
            # In particular, an *enabled but stopped* N2 timer would
            # restart on the next reboot and collide with N50.
            if (type(cp.returncode) is not int or cp.returncode != 0
                    or type(cp.stdout) is not str
                    or not 0 < len(cp.stdout) <= 350
                    or type(cp.stderr) is not str or cp.stderr.strip()):
                return out
            values = {}
            for line in cp.stdout.strip().splitlines():
                if "=" not in line:
                    return out
                key, value = line.split("=", 1)
                if key not in expected_keys or key in values:
                    return out
                values[key] = value
            if (set(values) != expected_keys
                    or values["LoadState"] != "loaded"
                    or values["ActiveState"] != "inactive"):
                return out
            if unit.endswith(".timer"):
                # disable --now is reversible, unlike masking or deletion.
                # Mere inactive is insufficient: enabled restarts on boot.
                if values["UnitFileState"] != "disabled":
                    return out
                out["n2_timer_inactive"] = True
                out["n2_timer_disabled"] = True
            else:
                if values["UnitFileState"] not in ("static", "disabled"):
                    return out
                out["n2_service_inactive"] = True
            states[unit] = values
        out["n2_units_loaded"] = len(states) == len(_N2)
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
