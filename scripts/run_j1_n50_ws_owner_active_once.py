"""J1/D321: run one N50 WS close using an atomic owner epoch pointer.

OFF by default. The active epoch is revalidated under D287+D316, then its
canonical directories are passed to the already-reviewed D317 runner.
No symbol leakage, no REST GET, no service mutation, no orders.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from crypto_intelligence_agent.j1_n50_ws_epoch_rotation import (
    load_active_n50_ws_epoch,
)
from crypto_intelligence_agent.j1_n50_ws_cached_runner import (
    _report,run_cached_n50_ws_owner_window,
)


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-directory",type=Path,required=True)
    p.add_argument("--allow-private-pointer-read",action="store_true")
    p.add_argument("--allow-private-manifest-read",action="store_true")
    p.add_argument("--allow-private-ws-scope-read",action="store_true")
    p.add_argument("--allow-private-ws-writer",action="store_true")
    p.add_argument("--allow-public-websocket",action="store_true")
    p.add_argument("--confirm-region-and-personal-research",action="store_true")
    p.add_argument("--allow-create-ws-journal",action="store_true")
    a=p.parse_args(argv)
    out=_report("ws_owner_window_optin_required")
    if not all((
        a.allow_private_pointer_read,a.allow_private_manifest_read,
        a.allow_private_ws_scope_read,a.allow_private_ws_writer,
        a.allow_public_websocket,
        a.confirm_region_and_personal_research,
    )):
        print(json.dumps(out,sort_keys=True,separators=(",",":")))
        return 77
    try:
        # The pointer must be resolved BEFORE importing/calling a socket
        # factory, so stale/half-rotated epochs never trigger network I/O.
        active=load_active_n50_ws_epoch(
            state_directory=a.state_directory,
            current_at_ms=time.time_ns()//1_000_000,
            allow_private_pointer_read=True,
        )
        if (active.status!="active_n50_ws_epoch_revalidated"
                or active.manifest_directory is None
                or active.ws_directory is None):
            out["status"]="ws_owner_window_epoch_unavailable"
            print(json.dumps(out,sort_keys=True,separators=(",",":")))
            return 65
        from crypto_intelligence_agent.bybit_public_ws_once import (
            _real_session_factory,
        )
        out=run_cached_n50_ws_owner_window(
            manifest_directory=active.manifest_directory,
            ws_directory=active.ws_directory,
            session_factory=_real_session_factory,
            allow_private_manifest_read=True,
            allow_private_ws_scope_read=True,
            allow_private_ws_writer=True,
            allow_injected_public_ws=True,
            allow_create_ws_journal=a.allow_create_ws_journal,
        )
    except (OSError,ValueError,RuntimeError,TypeError,ImportError,
            OverflowError,KeyError,UnicodeError):
        out["status"]="ws_owner_window_integrity_abstain"
    print(json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if out["status"]=="ws_owner_hour_50_observed_local_only" else 65


if __name__=="__main__":
    raise SystemExit(main())
