"""J1/D322: root-only one-shot D321 rotating N50 WS installation.

Requires a fresh owner active pointer (D321), D287 and D316 proof BEFORE
installing anything. Installs five NEW systemd units, swaps N2 -> N50 WS
and enables 36h rotation at HH:01:15. No orders, no REST HALT modification,
and rollback restores N2 if any cutover operation fails.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from crypto_intelligence_agent.j1_n50_ws_epoch_rotation import (
    FILE_NAME,SCHEMA,MAX_POINTER_BYTES,_OWNER_ROOT,_canonical,_digest,_unique_pairs,
)
from scripts.render_j1_n50_ws_rotating_systemd import (
    render_rotating_ws_systemd,
)
from scripts.release_j1_n50_ws_owner_once import (
    OWNER,PYTHON,UNIT_DIR,N2_TIMER,WS_SERVICE,WS_TIMER,WS_FALLBACK,
    OLD_N50_TIMER,_run,_show,_safe_owner_dir,
    _old_units_and_collectors_ok,preflight as _static_preflight,
)

ROT_TIMER="cia-j1-n50-ws-rotate.timer"
ROT_SERVICE="cia-j1-n50-ws-rotate.service"
_UNIT_ORDER=(WS_SERVICE,WS_TIMER,WS_FALLBACK,ROT_TIMER,ROT_SERVICE)
_MIN_FRESH_POINTER_AGE_MS=15*60_000
_FALLBACK_TEMPLATE=(
    Path(__file__).resolve().parents[1]/"deploy/systemd/"
    "cia-j1-n50-ws-rotating-fallback.service.template"
)


def _report(status:str)->dict:
    return {
        "schema_version":"j1-n50-ws-d322-root-rotating-release-v1",
        "status":status,
        "preflight_verified":False,
        "private_active_epoch_verified":False,
        "units_created":False,
        "n2_quiesced":False,
        "n50_ws_timer_enabled":False,
        "n50_ws_rotation_timer_enabled":False,
        "n2_restored_after_failure":None,
        "old_n50_rest_units_modified":False,
        "old_n50_rest_database_modified":False,
        "orders_sent":False,"live_trading_authorized":False,
        "marketwide_top50_verified":False,
    }


def _owner_active_paths(
    *,state_directory:Path,epoch_root:Path,
)->tuple[Path,Path]:
    # Root reads only fixed-length, owner 0600 JSON, and an independent
    # owner subprocess revalidates D287/D316 and the pointer before release.
    import pwd
    uid=pwd.getpwnam(OWNER).pw_uid
    if epoch_root!=_OWNER_ROOT or state_directory!=epoch_root/"active":
        raise ValueError("N50 rotating root/state mismatch")
    _safe_owner_dir(epoch_root,uid)
    _safe_owner_dir(state_directory,uid)
    p=state_directory/FILE_NAME
    st=p.lstat()
    if (not stat.S_ISREG(st.st_mode)
            or st.st_uid!=uid or st.st_nlink!=1
            or stat.S_IMODE(st.st_mode)!=0o600
            or not 1<=st.st_size<=MAX_POINTER_BYTES):
        raise ValueError("N50 private pointer inode/DAC invalid")
    fd=os.open(p,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    with os.fdopen(fd,"rb") as stream:
        inside=os.fstat(stream.fileno())
        if (inside.st_dev,inside.st_ino)!=(st.st_dev,st.st_ino):
            raise ValueError("N50 private pointer inode drift")
        raw=stream.read(MAX_POINTER_BYTES+1)
    if not 1<=len(raw)<=MAX_POINTER_BYTES:
        raise ValueError("N50 pointer length invalid")
    obj=json.loads(raw.decode("ascii"),object_pairs_hook=_unique_pairs)
    if (type(obj) is not dict or obj.get("schema_version")!=SCHEMA
            or _canonical(obj)!=raw or obj.get("pointer_sha256")!=_digest(obj)
            or type(obj.get("activated_at_ms")) is not int
            or not 0<=time.time_ns()//1_000_000-obj["activated_at_ms"]
                   <=_MIN_FRESH_POINTER_AGE_MS):
        raise ValueError("N50 rotating pointer stale/tampered")
    man=Path(obj["manifest_directory"])
    ws=Path(obj["ws_directory"])
    if (man==ws or man.parent!=epoch_root or ws.parent!=epoch_root
            or man.name.startswith(".") or ws.name.startswith(".")
            or not man.name.startswith("j1-n50-ws-manifest-")
            or not ws.name.startswith("j1-n50-ws-private-")):
        raise ValueError("N50 rotating epoch directory hierarchy invalid")
    _safe_owner_dir(man,uid)
    _safe_owner_dir(ws,uid)
    return man,ws


def _owner_recheck(
    *,source:Path,state_directory:Path,manifest:Path,ws:Path,
)->None:
    # Only an owner process can open the D287/D316 private files; print
    # one fixed PASS token. The stdout never contains paths or symbols.
    program=(
        "import os,time;"
        "from pathlib import Path;"
        "from crypto_intelligence_agent.j1_n50_ws_epoch_rotation "
        "import load_active_n50_ws_epoch;"
        "a=load_active_n50_ws_epoch("
        "state_directory=Path(os.environ['CIA_STATE']),"
        "current_at_ms=time.time_ns()//1000000,"
        "allow_private_pointer_read=True);"
        "print('OWNER_ACTIVE_50_VALID' if ("
        "a.status=='active_n50_ws_epoch_revalidated' and "
        "a.manifest_directory==Path(os.environ['CIA_MAN']) and "
        "a.ws_directory==Path(os.environ['CIA_WS'])) else 'OWNER_ACTIVE_INVALID')"
    )
    result=_run([
        "/usr/sbin/runuser","-u",OWNER,"--",
        "/usr/bin/env","PYTHONDONTWRITEBYTECODE=1",
        "CIA_STATE="+str(state_directory),
        "CIA_MAN="+str(manifest),"CIA_WS="+str(ws),
        PYTHON,"-c",program,
    ],cwd=str(source),timeout=35)
    if result!="OWNER_ACTIVE_50_VALID":
        raise ValueError("N50 rotating owner pointer verification failed")


def _render(
    *,source:Path,state_directory:Path,epoch_root:Path,
    manifest:Path,ws:Path,
)->tuple[str,...]:
    # D320 renderer independently validates old D318 timer and fallback.
    _old_service,timer,_old_fallback=__import__(
        "scripts.render_j1_n50_ws_systemd",fromlist=["render_n50_ws_systemd"],
    ).render_n50_ws_systemd(
        owner=OWNER,repo=str(source),python=PYTHON,
        manifest=str(manifest),ws_directory=str(ws),
    )
    service,rot_timer,rot_service=render_rotating_ws_systemd(
        owner=OWNER,repo=str(source),python=PYTHON,
        state_directory=str(state_directory),epoch_root=str(epoch_root),
    )
    fallback=_FALLBACK_TEMPLATE.read_text("ascii")
    if (fallback.count("ExecStart=")!=2
            or "ExecStart=-/usr/bin/systemctl disable --now "
               +ROT_TIMER+"\n" not in fallback
            or "ExecStart=-/usr/bin/systemctl disable --now "
               +WS_TIMER+"\n" not in fallback
            or "ExecStartPost=/usr/bin/systemctl enable --now "
               +N2_TIMER+"\n" not in fallback
            or "OnFailure="+WS_FALLBACK+"\n" not in service
            or "OnCalendar=*-*-* *:59:30 UTC\n" not in timer
            or "OnCalendar=*-*-* *:01:15 UTC\n" not in rot_timer):
        raise ValueError("N50 rotating root render drift")
    units=(service,timer,fallback,rot_timer,rot_service)
    if any(len(u.encode("ascii"))>16_000 for u in units):
        raise ValueError("N50 rotating unit length bound")
    return units


def preflight(*,source:Path,expected_sha:str,
              state_directory:Path,epoch_root:Path)->tuple[str,...]:
    # First phase never creates units, disables N2 or accesses the venue.
    manifest,ws=_owner_active_paths(
        state_directory=state_directory,epoch_root=epoch_root,
    )
    _static_preflight(
        source=source,expected_sha=expected_sha,
        manifest=manifest,ws_dir=ws,
    )
    for unit in (ROT_TIMER,ROT_SERVICE):
        if (UNIT_DIR/unit).exists() or (UNIT_DIR/unit).is_symlink():
            raise ValueError("N50 rotating systemd unit already installed")
        if _show(unit)["LoadState"]!="not-found":
            raise ValueError("N50 rotating unit already loaded")
    _owner_recheck(
        source=source,state_directory=state_directory,
        manifest=manifest,ws=ws,
    )
    return _render(
        source=source,state_directory=state_directory,epoch_root=epoch_root,
        manifest=manifest,ws=ws,
    )


def _write(name:str,source:str)->None:
    if name not in _UNIT_ORDER:
        raise ValueError("not allowlisted rotating unit")
    data=source.encode("ascii")
    fd=os.open(
        UNIT_DIR/name,
        os.O_WRONLY|os.O_CREAT|os.O_EXCL|
        getattr(os,"O_NOFOLLOW",0),0o644,
    )
    with os.fdopen(fd,"wb") as stream:
        os.fchmod(stream.fileno(),0o644)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _rollback()->bool:
    for name in (ROT_TIMER,WS_TIMER):
        try:
            _run(["/usr/bin/systemctl","disable","--now",name])
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            pass
    try:
        _run(["/usr/bin/systemctl","enable","--now",N2_TIMER])
        return (
            _show(N2_TIMER)=={
                "LoadState":"loaded","ActiveState":"active",
                "UnitFileState":"enabled",
            }
            and all(_show(unit)["ActiveState"]=="inactive"
                    for unit in (ROT_TIMER,WS_TIMER))
        )
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        return False


def execute(
    *,source:Path,expected_sha:str,state_directory:Path,epoch_root:Path,
    confirm_rotating_ws_cutover:bool=False,
    allow_systemd_modifications:bool=False,
)->dict:
    out=_report("blocked")
    try:
        units=preflight(
            source=source,expected_sha=expected_sha,
            state_directory=state_directory,epoch_root=epoch_root,
        )
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,
            PermissionError,subprocess.SubprocessError):
        out["status"]="preflight_blocked_N2_untouched"
        return out
    out["preflight_verified"]=True
    out["private_active_epoch_verified"]=True
    if not (confirm_rotating_ws_cutover is True
            and allow_systemd_modifications is True):
        out["status"]="preflight_pass_no_changes"
        return out
    n2_may_be_changed=False
    try:
        for name,unit in zip(_UNIT_ORDER,units):
            _write(name,unit)
        out["units_created"]=True
        _run(["/usr/bin/systemctl","daemon-reload"])
        for name in _UNIT_ORDER:
            if _show(name)["LoadState"]!="loaded":
                raise RuntimeError("N50 rotating systemd unit not loaded")
        if not _old_units_and_collectors_ok():
            raise RuntimeError("N2 state drift before rotation cutover")
        # Set BEFORE disable call; systemctl can fail after partial mutation.
        n2_may_be_changed=True
        _run(["/usr/bin/systemctl","disable","--now",N2_TIMER])
        _run(["/usr/bin/systemctl","enable","--now",WS_TIMER])
        _run(["/usr/bin/systemctl","enable","--now",ROT_TIMER])
        state={
            name:_show(name) for name in (N2_TIMER,WS_TIMER,ROT_TIMER,OLD_N50_TIMER)
        }
        if (state[N2_TIMER]!={"LoadState":"loaded","ActiveState":"inactive",
                              "UnitFileState":"disabled"}
                or any(state[unit]!={"LoadState":"loaded","ActiveState":"active",
                                    "UnitFileState":"enabled"}
                       for unit in (WS_TIMER,ROT_TIMER))
                or state[OLD_N50_TIMER]["ActiveState"]!="inactive"):
            raise RuntimeError("N50 rotating cutover mismatch")
        out.update(status="n50_ws_with_36h_rotation_enabled",
                   n2_quiesced=True,n50_ws_timer_enabled=True,
                   n50_ws_rotation_timer_enabled=True)
        return out
    except (OSError,ValueError,TypeError,RuntimeError,
            subprocess.SubprocessError):
        if n2_may_be_changed:
            out["n2_restored_after_failure"]=_rollback()
            out["status"]=("rolled_back_to_N2"
                           if out["n2_restored_after_failure"] else
                           "rollback_N2_requires_owner_action")
        else:
            out["status"]="ws_rotating_unit_install_failed_N2_untouched"
        return out


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--expected-sha",required=True)
    p.add_argument("--state-directory",type=Path,required=True)
    p.add_argument("--epoch-root",type=Path,required=True)
    p.add_argument("--confirm-rotating-ws-cutover",action="store_true")
    p.add_argument("--allow-systemd-modifications",action="store_true")
    a=p.parse_args(argv)
    out=execute(
        source=a.source,expected_sha=a.expected_sha,
        state_directory=a.state_directory,epoch_root=a.epoch_root,
        confirm_rotating_ws_cutover=a.confirm_rotating_ws_cutover,
        allow_systemd_modifications=a.allow_systemd_modifications,
    )
    print(json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if out["status"] in (
        "preflight_pass_no_changes",
        "n50_ws_with_36h_rotation_enabled",
    ) else 65


if __name__=="__main__":
    raise SystemExit(main())
