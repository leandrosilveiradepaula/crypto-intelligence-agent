"""J1/D321: bounded owner N50 WS epoch refresh, independently scheduled.

One 36h-eligible attempt per prior cohort, no immediate/periodic provider
retry after 10006. The old epoch remains active until a COMPLETE new
D287/D314/D316 candidate is atomically committed. No service or orders.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Callable, Iterator

from crypto_intelligence_agent.bybit_ws_owner_lock import _safe_stat
from crypto_intelligence_agent.j1_n50_ws_epoch_rotation import (
    FILE_NAME,LOCK_NAME,MIN_ROTATION_AGE_MS,
    _OWNER_ROOT,_owner_path,_read_bytes,activate_n50_ws_epoch_once,
)
from crypto_intelligence_agent.j1_n50_ws_metadata_bootstrap import (
    cache_current_n50_ws_metadata_once,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.run_j1_current_ranked_epoch_once import (
    capture_and_seal_current_rank_once,
)

_ATTEMPT_PREFIX="rotation-attempt-"
_NAME=re.compile(r"j1-n50-ws-(?:manifest|private)-[0-9]{13}\Z")


def _report(status:str)->dict[str,Any]:
    return {
        "schema_version":"j1-n50-ws-owner-rotation-once-v1",
        "status":status,"rotation_due":False,
        "attempt_claimed":False,
        "rank_network_requests":0,
        "metadata_network_requests":0,
        "new_epoch_activated":False,
        "ranked_scope_sha256":None,
        "ws_metadata_sha256":None,
        "old_epoch_preserved":True,
        "rest_database_modified":False,"systemd_modified":False,
        "orders_sent":False,"live_trading_authorized":False,
        "marketwide_top50_verified":False,
    }


@contextmanager
def _lock_rotation(state_directory:Path)->Iterator[None]:
    from fcntl import LOCK_EX,LOCK_NB,LOCK_UN,flock
    file=state_directory/".rotation-owner-run.lock"
    fd=os.open(file,os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0)
               |getattr(os,"O_CLOEXEC",0),0o600)
    try:
        before=os.fstat(fd)
        after=_safe_stat(file,directory=False)
        if ((before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino)
                or before.st_uid!=os.geteuid()
                or before.st_nlink!=1
                or stat.S_IMODE(before.st_mode)!=0o600):
            raise DataValidationError("N50 rotation lease unsafe")
        flock(fd,LOCK_EX|LOCK_NB)
        try:
            yield
        finally:
            flock(fd,LOCK_UN)
    finally:
        os.close(fd)


def rotate_n50_ws_owner_epoch_once(
    *, state_directory:Path,epoch_root:Path,
    allow_private_rotation:bool=False,
    allow_public_network:bool=False,
    confirm_region_and_personal_research:bool=False,
    allow_private_manifest_write:bool=False,
    allow_private_ws_cache_write:bool=False,
    clock_ms:Callable[[],int]=lambda:time.time_ns()//1_000_000,
) -> dict[str,Any]:
    out=_report("owner_optin_required")
    if not all((
        allow_private_rotation is True,
        allow_public_network is True,
        confirm_region_and_personal_research is True,
        allow_private_manifest_write is True,
        allow_private_ws_cache_write is True,
    )):
        return out
    out["status"]="n50_ws_rotation_preflight_abstain"
    if (os.name!="posix" or os.getuid()!=os.geteuid()
            or os.geteuid()==0 or not callable(clock_ms)):
        return out
    try:
        _owner_path(state_directory)
        _owner_path(epoch_root)
        if (epoch_root!=_OWNER_ROOT
                or not state_directory.is_relative_to(epoch_root)
                or epoch_root==state_directory):
            return out
        with _lock_rotation(state_directory):
            now=clock_ms()
            if type(now) is not int or now<=0:
                return out
            # Only HH:02:15..HH:03:00 UTC. First ensure current hour is
            # actually closed before a fresh causal D287 public capture.
            phase=now%3_600_000
            if not 135_000<=phase<=180_000:
                out["status"]="n50_ws_rotation_outside_causal_window"
                return out
            old=None
            if (state_directory/FILE_NAME).exists() or (
                    state_directory/FILE_NAME).is_symlink():
                old=_read_bytes(state_directory)
                if now<old["activated_at_ms"]:
                    return out
                if now-old["activated_at_ms"]<MIN_ROTATION_AGE_MS:
                    out["status"]="n50_ws_rotation_not_due_no_get"
                    return out
            out["rotation_due"]=True
            # No extra attempt this same epoch. A 10006 or quota failure
            # is terminal for this cohort until human review; old WS data
            # remains intact and its 48h expiry fails closed to N2.
            cohort_id=(old["pointer_sha256"][:24] if old is not None
                       else "initial-bootstrap")
            marker=state_directory/(_ATTEMPT_PREFIX+cohort_id+".claim")
            if marker.exists() or marker.is_symlink():
                out["status"]="n50_ws_rotation_already_attempted_no_get"
                return out
            fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL
                       |getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"wb") as stream:
                stream.write(json.dumps(
                    {"started_ms":now,"status":"claimed"},
                    sort_keys=True,separators=(",",":"),
                ).encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
            _safe_stat(marker,directory=False)
            out["attempt_claimed"]=True
            man=epoch_root/("j1-n50-ws-manifest-%013d"%now)
            ws=epoch_root/("j1-n50-ws-private-%013d"%now)
            for d in (man,ws):
                if d.exists() or d.is_symlink():
                    return out
            man.mkdir(mode=0o700)
            ws.mkdir(mode=0o700)
            _owner_path(man)
            _owner_path(ws)
            rank=capture_and_seal_current_rank_once(
                scope_directory=man,
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                allow_private_manifest_write=True,
                clock_ms=clock_ms,
            )
            out["rank_network_requests"]=rank.get("requests_attempted",0)
            if rank.get("status")!="sealed_current_auto_rank_research_scope_only":
                out["status"]="n50_ws_rotation_rank_abstain_no_retry"
                return out
            catalog=cache_current_n50_ws_metadata_once(
                manifest_directory=man,
                ws_directory=ws,
                allow_public_network=True,
                confirm_region_and_personal_research=True,
                enable_n50_ws_metadata_capture=True,
                allow_private_manifest_read=True,
                allow_private_ws_cache_write=True,
                clock_ms=clock_ms,
            )
            out["metadata_network_requests"]=catalog.get("catalog_gets",0)
            if catalog.get("status")!="ws_metadata_owner_n50_cached_for_ws_research":
                out["status"]="n50_ws_rotation_metadata_abstain_no_retry"
                return out
            done=activate_n50_ws_epoch_once(
                state_directory=state_directory,
                manifest_directory=man,ws_directory=ws,
                current_at_ms=clock_ms(),
                allow_private_pointer_write=True,
                require_due_after_36h=True,
            )
            if done.status not in (
                "active_n50_ws_epoch_rotated",
                "active_n50_ws_epoch_bootstrapped",
            ):
                out["status"]="n50_ws_rotation_activation_abstain"
                return out
            out["new_epoch_activated"]=True
            out["ranked_scope_sha256"]=done.ranked_scope_sha256
            out["ws_metadata_sha256"]=done.ws_metadata_sha256
            out["status"]="n50_ws_epoch_rotation_complete"
            return out
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,
            OverflowError,UnicodeError,DataValidationError):
        out["status"]="n50_ws_rotation_integrity_abstain"
        return out


def main(argv:list[str]|None=None)->int:
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-directory",type=Path,required=True)
    p.add_argument("--epoch-root",type=Path,required=True)
    p.add_argument("--allow-private-rotation",action="store_true")
    p.add_argument("--allow-public-network",action="store_true")
    p.add_argument("--confirm-region-and-personal-research",action="store_true")
    p.add_argument("--allow-private-manifest-write",action="store_true")
    p.add_argument("--allow-private-ws-cache-write",action="store_true")
    a=p.parse_args(argv)
    report=rotate_n50_ws_owner_epoch_once(
        state_directory=a.state_directory,epoch_root=a.epoch_root,
        allow_private_rotation=a.allow_private_rotation,
        allow_public_network=a.allow_public_network,
        confirm_region_and_personal_research=a.confirm_region_and_personal_research,
        allow_private_manifest_write=a.allow_private_manifest_write,
        allow_private_ws_cache_write=a.allow_private_ws_cache_write,
    )
    print(json.dumps(report,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if report["status"] in (
        "n50_ws_epoch_rotation_complete",
        "n50_ws_rotation_not_due_no_get",
        "n50_ws_rotation_already_attempted_no_get",
        "n50_ws_rotation_outside_causal_window",
    ) else 65


if __name__=="__main__":
    raise SystemExit(main())
