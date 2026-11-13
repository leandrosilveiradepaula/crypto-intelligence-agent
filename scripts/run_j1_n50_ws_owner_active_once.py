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


def _bounded_degraded_continuation(report: object) -> bool:
    """Continue only 47..49 confirmed/50 with explicit gap replay enabled.

    This is NOT a successful PIT or 24h certificate. True integrity,
    broken ACK, no session, 46/50 or worse still triggers systemd failback.
    """
    if type(report) is not dict:
        return False
    confirmed = report.get("confirmed_contracts")
    missing = report.get("missing_contracts")
    acknowledgements = report.get("subscription_acks")
    sessions = report.get("ws_sessions_attempted")
    return (
        report.get("status") == "ws_owner_hour_incomplete_no_pit"
        and type(confirmed) is int and 47 <= confirmed <= 49
        and type(missing) is int and missing == 50 - confirmed
        and type(acknowledgements) is int and acknowledgements >= 1
        and type(sessions) is int and sessions >= 1
        and report.get("declared_ws_gap_append_enabled") is True
        and report.get("rest_gap_reconciliation_required") is True
        and report.get("owner_lock_acquired") is True
        and report.get("failure_category") is None
        and report.get("hour_evidence_sha256") is None
        and report.get("source_provenance") is None
        and report.get("http_gets") == 0
        and report.get("rest_database_modified") is False
        and report.get("systemd_modified") is False
        and report.get("orders_sent") is False
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
            allow_declared_ws_gap=True,
        )
    except (OSError,ValueError,RuntimeError,TypeError,ImportError,
            OverflowError,KeyError,UnicodeError):
        out["status"]="ws_owner_window_integrity_abstain"
    # One missing WS candle must not permanently disable N50; its absence
    # stays visible in SQLite and D324 targets it separately. Never promote
    # a partial hour to complete evidence or suppress severe failures.
    bounded_degraded = _bounded_degraded_continuation(out)
    out["ws_timer_continuation_with_gap_allowed"] = bounded_degraded
    print(json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if (out["status"]=="ws_owner_hour_50_observed_local_only"
                 or bounded_degraded) else 65


if __name__=="__main__":
    raise SystemExit(main())
