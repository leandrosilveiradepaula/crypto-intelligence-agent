"""D318: readonly N50 WS systemd guard, OFF unless N2 and old REST N50 stop.

No systemctl write, network, DB write, orders or unit install. The new WS
timer at HH:59:30 can only run if both existing REST collectors are quiesced;
this is not an authorization to disable N2 or start WS.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from typing import Any, Callable

from scripts.preflight_j1_n50_systemd_isolation import n50_systemd_n2_quiescence

_SYSTEMCTL = "/usr/bin/systemctl"
_OLD_REST_TIMER = "cia-j1-n50-managed.timer"
_OLD_REST_SERVICE = "cia-j1-n50-managed.service"


def n50_ws_systemd_isolation(
    *, require_old_collectors_quiesced: bool = False,
    command_runner: Callable | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": "j1-n50-ws-systemd-preflight-v1",
        "status": "optin_required",
        "n2_quiesced": False,
        "old_rest_timer_disabled": False,
        "old_rest_service_stopped": False,
        "n50_ws_start_authorized": False,
        "systemd_modified": False,
        "network_requests": 0,
        "orders_sent": False,
    }
    if require_old_collectors_quiesced is not True:
        return out
    out["status"] = "blocked"
    if os.name != "posix" or os.getuid() != os.geteuid() or os.geteuid() == 0:
        return out
    runner = subprocess.run if command_runner is None else command_runner
    n2 = n50_systemd_n2_quiescence(
        require_n2_quiesced=True, command_runner=runner,
    )
    if n2["status"] != "n2_quiesced_preflight_only":
        return out
    out["n2_quiesced"] = True
    try:
        for unit, allowed_active, expected_file_state in (
            (_OLD_REST_TIMER, {"inactive"}, "disabled"),
            (_OLD_REST_SERVICE, {"inactive", "failed"}, "static"),
        ):
            cp = runner(
                [_SYSTEMCTL, "show", unit,
                 "--property=LoadState", "--property=ActiveState",
                 "--property=UnitFileState", "--no-pager"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            if (type(cp.returncode) is not int or cp.returncode != 0
                    or type(cp.stdout) is not str
                    or not 0 < len(cp.stdout) <= 350
                    or type(cp.stderr) is not str or cp.stderr.strip()):
                return out
            rows = {}
            for line in cp.stdout.strip().splitlines():
                if line.count("=") != 1:
                    return out
                k, v = line.split("=", 1)
                if k not in ("LoadState", "ActiveState", "UnitFileState") or k in rows:
                    return out
                rows[k] = v
            if (set(rows) != {"LoadState", "ActiveState", "UnitFileState"}
                    or rows["LoadState"] != "loaded"
                    or rows["ActiveState"] not in allowed_active
                    or rows["UnitFileState"] != expected_file_state):
                return out
            if unit == _OLD_REST_TIMER:
                out["old_rest_timer_disabled"] = True
            else:
                out["old_rest_service_stopped"] = True
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return out
    out["status"] = "old_collectors_quiesced_preflight_only"
    # This is an audit of present service state, NOT a release authorization.
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--require-old-collectors-quiesced", action="store_true")
    a = p.parse_args(argv)
    out = n50_ws_systemd_isolation(
        require_old_collectors_quiesced=a.require_old_collectors_quiesced,
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if out["status"] == "old_collectors_quiesced_preflight_only" else 65


if __name__ == "__main__":
    raise SystemExit(main())
