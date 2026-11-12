"""J1/D321: immutable N50 WS epoch pointer; atomic owner-only 36h rotation.

This is an offline epoch switch, NOT a service installation or live trade.
A candidate must already have a freshly sealed D287 manifest and an
immutable D316 cache. Old directories/journals remain untouched forever.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any

from .bybit_ws_owner_lock import _safe_stat
from .j1_n50_ws_private_cache import load_n50_ws_dynamic_admission
from .market_data import DataValidationError, DataGapError
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

SCHEMA="j1-n50-ws-active-owner-epoch-v1"
FILE_NAME="active-n50-ws-epoch.json"
LOCK_NAME=".active-n50-ws-epoch.lock"
MIN_ROTATION_AGE_MS=36*3_600_000
MAX_POINTER_BYTES=4096
_SHA=re.compile(r"[0-9a-f]{64}\Z")
_FIELDS=frozenset((
    "schema_version","manifest_directory","ws_directory",
    "ranked_scope_sha256","ws_metadata_sha256",
    "activated_at_ms","pointer_sha256",
))
_REST_HALT=Path("/home/cia-probe/agent/j1-n50-managed-d296-private")


def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj,sort_keys=True,ensure_ascii=True,allow_nan=False,
        separators=(",",":"),
    ).encode("ascii")


def _unique_pairs(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise DataValidationError("N50 epoch pointer duplicate key")
        out[key]=value
    return out


def _digest(data: dict) -> str:
    return sha256(_canonical({k:v for k,v in data.items()
                              if k!="pointer_sha256"})).hexdigest()


def _owner_path(path: Path, *, directory: bool=True):
    if (os.name!="posix" or os.getuid()!=os.geteuid()
            or os.geteuid()==0
            or not isinstance(path,Path)
            or not path.is_absolute() or ".." in path.parts
            or path.resolve(strict=True)!=path
            or path==_REST_HALT or _REST_HALT in path.parents):
        raise DataValidationError("N50 owner private path denied")
    return _safe_stat(path,directory=directory)


@dataclass(frozen=True)
class ActiveN50WSEpoch:
    status: str
    manifest_directory: Path | None = field(default=None,repr=False)
    ws_directory: Path | None = field(default=None,repr=False)
    ranked_scope_sha256: str | None = None
    ws_metadata_sha256: str | None = None
    activated_at_ms: int | None = None
    rotation_performed: bool = False

    def sanitized_report(self) -> dict:
        return {
            "schema_version":SCHEMA,"status":self.status,
            "ranked_scope_sha256":self.ranked_scope_sha256,
            "ws_metadata_sha256":self.ws_metadata_sha256,
            "activated_at_ms":self.activated_at_ms,
            "rotation_performed":self.rotation_performed,
            "http_gets":0,"systemd_modified":False,
            "rest_database_modified":False,"orders_sent":False,
            "marketwide_top50_verified":False,
            "live_trading_authorized":False,
        }


def _read_bytes(state_directory: Path) -> dict:
    file=state_directory/FILE_NAME
    before=_owner_path(file,directory=False)
    if not 1<=before.st_size<=MAX_POINTER_BYTES:
        raise DataValidationError("N50 pointer size invalid")
    fd=os.open(file,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
               |getattr(os,"O_CLOEXEC",0))
    with os.fdopen(fd,"rb") as stream:
        inside=os.fstat(stream.fileno())
        if ((inside.st_dev,inside.st_ino)!=(before.st_dev,before.st_ino)
                or inside.st_uid!=os.geteuid()
                or not stat.S_ISREG(inside.st_mode)
                or inside.st_nlink!=1
                or stat.S_IMODE(inside.st_mode)!=0o600):
            raise DataValidationError("N50 owner pointer inode changed")
        raw=stream.read(MAX_POINTER_BYTES+1)
    if not 1<=len(raw)<=MAX_POINTER_BYTES:
        raise DataValidationError("N50 pointer invalid length")
    obj=json.loads(raw.decode("ascii"),object_pairs_hook=_unique_pairs,
                   parse_constant=lambda _: (_ for _ in ()).throw(
                       DataValidationError("N50 pointer nonfinite")))
    if (type(obj) is not dict or set(obj)!=_FIELDS
            or _canonical(obj)!=raw
            or obj["schema_version"]!=SCHEMA
            or type(obj["activated_at_ms"]) is not int
            or any(type(obj[k]) is not str or _SHA.fullmatch(obj[k]) is None
                   for k in ("pointer_sha256","ranked_scope_sha256",
                             "ws_metadata_sha256"))
            or _digest(obj)!=obj["pointer_sha256"]):
        raise DataValidationError("N50 pointer digest/schema invalid")
    for key in ("manifest_directory","ws_directory"):
        val=obj[key]
        if (type(val) is not str or len(val)>300
                or not val.startswith("/home/cia-probe/agent/")):
            raise DataValidationError("N50 pointer stored path invalid")
    if obj["manifest_directory"]==obj["ws_directory"]:
        raise DataValidationError("N50 pointer directories not isolated")
    return obj


def _resolve_current(state_directory: Path,now_ms: int) -> tuple[dict,dict,Any]:
    obj=_read_bytes(state_directory)
    if not obj["activated_at_ms"]<=now_ms:
        raise DataValidationError("N50 pointer activated in future")
    manifest=Path(obj["manifest_directory"])
    ws=Path(obj["ws_directory"])
    _owner_path(manifest)
    _owner_path(ws)
    if manifest in ws.parents or ws in manifest.parents:
        raise DataValidationError("N50 pointer overlapping directories")
    ranked=load_private_ranked_scope(manifest,now_ms=now_ms)
    if ranked["scope_digest_sha256"]!=obj["ranked_scope_sha256"]:
        raise DataValidationError("N50 pointer ranked digest mismatch")
    cache=load_n50_ws_dynamic_admission(
        directory=ws,current_at_ms=now_ms,
        expected_ranked_scope_sha256=obj["ranked_scope_sha256"],
        allow_private_scope_read=True,
    )
    if (cache.status!="private_n50_ws_admission_loaded_revalidated"
            or cache.admission is None or cache.ranked_scope!=ranked
            or cache.admission.metadata_sha256!=obj["ws_metadata_sha256"]):
        raise DataValidationError("N50 pointer cached admission mismatch")
    return obj,ranked,cache


def load_active_n50_ws_epoch(
    *,state_directory:Path,current_at_ms:int,
    allow_private_pointer_read:bool=False,
) -> ActiveN50WSEpoch:
    if allow_private_pointer_read is not True:
        return ActiveN50WSEpoch("owner_optin_required")
    try:
        if type(current_at_ms) is not int or current_at_ms<=0:
            raise DataValidationError("N50 pointer clock invalid")
        _owner_path(state_directory)
        obj,_,_=_resolve_current(state_directory,current_at_ms)
        return ActiveN50WSEpoch(
            "active_n50_ws_epoch_revalidated",
            Path(obj["manifest_directory"]),Path(obj["ws_directory"]),
            obj["ranked_scope_sha256"],obj["ws_metadata_sha256"],
            obj["activated_at_ms"],False,
        )
    except (OSError,ValueError,TypeError,KeyError,
            UnicodeError,OverflowError,DataValidationError,DataGapError):
        return ActiveN50WSEpoch("active_n50_ws_epoch_read_abstain")


def activate_n50_ws_epoch_once(
    *,state_directory:Path,manifest_directory:Path,ws_directory:Path,
    current_at_ms:int,allow_private_pointer_write:bool=False,
    require_due_after_36h:bool=True,
) -> ActiveN50WSEpoch:
    """Swap pointer only after validation of a DIFFERENT new private epoch.

    Single nonblocking flock prevents two rotation jobs. Reader sees either
    complete prior immutable JSON or complete new JSON, never a partial file.
    """
    out=ActiveN50WSEpoch("owner_optin_required")
    if allow_private_pointer_write is not True:
        return out
    out=ActiveN50WSEpoch("active_n50_ws_epoch_write_abstain")
    if (type(current_at_ms) is not int or current_at_ms<=0
            or type(require_due_after_36h) is not bool):
        return out
    temp=None
    try:
        _owner_path(state_directory)
        _owner_path(manifest_directory)
        _owner_path(ws_directory)
        if (len({state_directory,manifest_directory,ws_directory})!=3
                or manifest_directory in ws_directory.parents
                or ws_directory in manifest_directory.parents
                or state_directory in manifest_directory.parents
                or state_directory in ws_directory.parents):
            return out
        from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
        lock=state_directory/LOCK_NAME
        fd=os.open(lock,os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0)
                   |getattr(os,"O_CLOEXEC",0),0o600)
        try:
            inside=os.fstat(fd)
            onpath=_safe_stat(lock,directory=False)
            if ((inside.st_dev,inside.st_ino)!=(onpath.st_dev,onpath.st_ino)
                    or inside.st_uid!=os.geteuid()
                    or inside.st_nlink!=1 or
                    stat.S_IMODE(inside.st_mode)!=0o600):
                raise DataValidationError("N50 owner pointer lease unsafe")
            flock(fd,LOCK_EX|LOCK_NB)
            try:
                prior=None
                if (state_directory/FILE_NAME).exists() or (
                    state_directory/FILE_NAME).is_symlink():
                    prior=_read_bytes(state_directory)
                    if (current_at_ms<prior["activated_at_ms"]
                            or (require_due_after_36h and
                                current_at_ms-prior["activated_at_ms"]
                                <MIN_ROTATION_AGE_MS)):
                        return ActiveN50WSEpoch("active_n50_ws_not_due_no_get")
                    if (prior["manifest_directory"]==str(manifest_directory)
                            or prior["ws_directory"]==str(ws_directory)):
                        return out
                ranked=load_private_ranked_scope(
                    manifest_directory,now_ms=current_at_ms)
                cache=load_n50_ws_dynamic_admission(
                    directory=ws_directory,current_at_ms=current_at_ms,
                    expected_ranked_scope_sha256=ranked["scope_digest_sha256"],
                    allow_private_scope_read=True,
                )
                if (cache.status!="private_n50_ws_admission_loaded_revalidated"
                        or cache.admission is None
                        or cache.ranked_scope!=ranked
                        or cache.admission.selected_contracts!=50):
                    return out
                new={
                    "schema_version":SCHEMA,
                    "manifest_directory":str(manifest_directory),
                    "ws_directory":str(ws_directory),
                    "ranked_scope_sha256":ranked["scope_digest_sha256"],
                    "ws_metadata_sha256":cache.admission.metadata_sha256,
                    "activated_at_ms":current_at_ms,
                }
                new["pointer_sha256"]=_digest(new)
                data=_canonical(new)
                if len(data)>MAX_POINTER_BYTES:
                    return out
                temp=state_directory/(".epoch-txn-%d-%d.tmp"
                                      %(os.getpid(),time.monotonic_ns()))
                wf=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL
                           |getattr(os,"O_NOFOLLOW",0),0o600)
                with os.fdopen(wf,"wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                _safe_stat(temp,directory=False)
                os.replace(temp,state_directory/FILE_NAME)
                temp=None
                dfd=os.open(state_directory,os.O_RDONLY|
                            getattr(os,"O_DIRECTORY",0))
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
                return ActiveN50WSEpoch(
                    "active_n50_ws_epoch_rotated" if prior else
                    "active_n50_ws_epoch_bootstrapped",
                    manifest_directory,ws_directory,
                    ranked["scope_digest_sha256"],
                    cache.admission.metadata_sha256,current_at_ms,True,
                )
            finally:
                flock(fd,LOCK_UN)
        finally:
            os.close(fd)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,
            OverflowError,DataValidationError,DataGapError):
        return out
    finally:
        if temp is not None:
            try:
                temp.unlink()
            except OSError:
                pass
