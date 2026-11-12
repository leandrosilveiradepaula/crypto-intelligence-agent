"""D306: reversible N2->N50 recover-once cutover for the verified 08:01 HALT.

This is an explicit root-only RELEASE, never a background loop from CI.
A normal call performs preflight without modifications. To apply, both release
flags must be given and the call must begin early in HH:01 of a UTC close.
On any error, disable N50 and re-enable the existing N2 timer. The owner-only
fresh census writes a DIFFERENT epoch; the halted SQLite is not touched.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
try:
    import pwd
except ImportError:  # Windows/offline may inspect and import release policy.
    pwd = None
import signal
import socket
import subprocess
import time

from scripts.install_j1_n50_cutover_once import (
    _call, _show, N2_SERVICE, N2_TIMER, N50_TIMER, N50_SERVICE,
    FALLBACK_SERVICE, HOSTNAME, EXPECTED_ORIGIN, EXPECTED_N2_UNIT_HASH,
    UNIT_ROOT,
)
from scripts.render_j1_n50_managed_systemd import render_n50_managed_systemd
from scripts.preflight_j1_n50_systemd_isolation import (
    n50_systemd_n2_quiescence,
)

OWNER="cia-probe"
ROOT=Path("/home/cia-probe/agent/j1-n50-managed-d296-private")
PYTHON=Path("/home/cia-probe/agent/ws-venv/bin/python")
ORIGINAL_EPOCH="epoch-1794456000000"
ORIGINAL_SCOPE_DIGEST="c4673a4fc3edac4c6e30a7bcdde3b452b5950746371bba3b7b1a2f2a9bd25afa"
EXPECTED_N50_UNIT_SHA256={
    N50_SERVICE:"071a8b3a60489f206caa2115aaa30bb1c870f48052a2dcb84a064f1b1836e90f",
    N50_TIMER:"477ac621744c9ca180f6be4a94e6f33b5e280f57fc64434a0e5d23590662dc69",
    FALLBACK_SERVICE:"bc6c0c32e13ce2a2442cec7b85c62bb7553d63909919b1a7a2d5cc96492e3ac0",
}


def _state(unit: str) -> dict[str,str]:
    return _show(unit)


def _owner_report(*, source: Path, module: str, args: list[str],
                  allow_dataerr: bool = False) -> dict:
    command=[
        "/usr/sbin/runuser","-u",OWNER,"--",
        "/usr/bin/env","PYTHONPATH="+str(source),str(PYTHON),
        "-m",module,*args,
    ]
    # Even a failed owner capture emits a sanitized JSON status with the
    # number of GETs and (D303) whitelisted failure class. Do not discard it.
    cp=subprocess.run(command,capture_output=True,text=True,timeout=890,
                      shell=False,check=False)
    if (cp.returncode not in ((0,65) if allow_dataerr else (0,))
            or not 0<len(cp.stdout)<=10_000):
        raise RuntimeError("owner_operation_or_output_failed")
    obj=json.loads(cp.stdout)
    if type(obj) is not dict:
        raise ValueError("owner_report_invalid")
    if cp.returncode==65 and obj.get("status")=="new_epoch_sealed_old_halt_preserved":
        raise ValueError("owner_exit_status_mismatch")
    return obj


def _valid_old_forensic(report: dict) -> bool:
    return (type(report) is dict
            and report.get("schema_version")=="j1-n50-halted-owner-forensic-v1"
            and report.get("status")=="halted_owner_review_verified"
            and report.get("halted_reason")=="provider_denied_owner_review"
            and report.get("saved_rows_integrity_verified") is True
            and report.get("resume_authorized") is False
            and report.get("scope_digest_sha256")==ORIGINAL_SCOPE_DIGEST
            and report.get("stored_candles")==1306
            and report.get("published_hours")==3
            and report.get("partial_contracts_at_next_hour")==6
            and report.get("historical_missing_publication_hours")==0
            and report.get("orders_sent") is False
            and report.get("network_requests")==0
            and report.get("database_mutation_statements")==0
            and report.get("systemd_modified") is False)


def _audit_live_n2_recovery(*, source: Path) -> dict:
    """Recheck the ACTUAL continuous N2 owner journal without a 21-gap constant.

    The original D297 gate pinned 21 missing historical PITs at first cutover.
    After its correct failback at 08:01, four additional N2 PITs were absent
    while N50 was running. The restored N2 audit now truthfully reports 25
    missing checkpoints; those are not corrupt rows or permission to fake PIT.
    """
    obj=_owner_report(
        source=source,
        module="scripts.audit_j1_rest_resume_readiness",
        args=[
            "--output-directory",
            "/home/cia-probe/agent/j1-rest-m3-20261109/canary",
            "--expected-members","2","--allow-private-readonly-audit",
        ],
    )
    now=time.time_ns()//1_000_000
    missing=obj.get("historical_unpublished_hours")
    initial=obj.get("initial_end_ms")
    last=obj.get("last_published_end_ms")
    published=obj.get("published_hours")
    stored=obj.get("stored_candles")
    hour_ms=3_600_000
    if (obj.get("schema_version")!="j1_rest_resume_readiness_v1"
            or obj.get("journal_integrity_verified") is not True
            or obj.get("reviewed_research_contracts")!=2
            or obj.get("research_closed_24h_ranked_contracts")!=2
            or obj.get("orders_sent") is not False
            or obj.get("live_trading_authorized") is not False
            or obj.get("marketwide_top50_verified") is not False
            or obj.get("historical_checkpoint_gaps_present") is not True
            or obj.get("status")!="historical_checkpoint_gaps_require_review"
            or type(missing) is not int or not 21<=missing<=72
            or type(initial) is not int or initial%hour_ms
            or type(last) is not int or last%hour_ms or last<=initial
            or not 0<=now-last<=2*hour_ms
            or type(published) is not int or published<39
            or type(stored) is not int
            or stored!=2*(24+(last-initial)//hour_ms)
            or published+missing != 1+(last-initial)//hour_ms):
        raise ValueError("owner_n2_recovery_readiness_gate_failed")
    return obj


def _owner_old(source: Path) -> dict:
    return _owner_report(
        source=source,
        module="scripts.audit_j1_n50_halted_owner_once",
        args=["--allow-private-readonly-audit"],
    )


def preflight(*, source: Path, expected_sha: str) -> dict:
    if (os.name!="posix" or pwd is None or os.getuid()!=0 or os.geteuid()!=0
            or socket.gethostname()!=HOSTNAME):
        raise PermissionError("wrong_host_or_root_uid")
    if (not isinstance(source,Path) or not source.is_absolute()
            or source.is_symlink() or not source.is_dir()
            or not isinstance(expected_sha,str)
            or len(expected_sha)!=40
            or any(c not in "0123456789abcdef" for c in expected_sha)
            or PYTHON.resolve(strict=True)!=Path("/usr/bin/python3.12")):
        raise ValueError("release_code_or_python_invalid")
    if _call(["/usr/bin/timedatectl","show",
              "--property=NTPSynchronized","--value"])!="yes":
        raise ValueError("ntp_not_synchronized")
    git=["/usr/sbin/runuser","-u",OWNER,"--",
         "/usr/bin/git","-C",str(source)]
    if (_call(git+["rev-parse","HEAD"])!=expected_sha
            or _call(git+["status","--porcelain"])
            or _call(git+["remote","get-url","origin"])!=EXPECTED_ORIGIN):
        raise ValueError("release_sha_or_worktree_drift")
    uid=pwd.getpwnam(OWNER).pw_uid
    for part in (ROOT,ROOT/"lease",ROOT/"epochs"):
        st=part.lstat()
        if (not part.is_dir() or part.is_symlink()
                or st.st_uid!=uid or st.st_mode&0o777!=0o700):
            raise ValueError("owner_root_invalid")
    old=ROOT/"epochs"/ORIGINAL_EPOCH
    for part in (old,old/"scope",old/"journal"):
        st=part.lstat()
        if (not part.is_dir() or part.is_symlink()
                or st.st_uid!=uid or st.st_mode&0o777!=0o700):
            raise ValueError("halted_old_epoch_path_invalid")
    for name,digest in EXPECTED_N2_UNIT_HASH.items():
        path=UNIT_ROOT/name
        if (path.is_symlink() or not path.is_file()
                or _call(["/usr/bin/git","hash-object",str(path)])!=digest):
            raise ValueError("n2_unit_drift")
    for name,digest in EXPECTED_N50_UNIT_SHA256.items():
        path=UNIT_ROOT/name
        if (path.is_symlink() or not path.is_file()
                or sha256(path.read_bytes()).hexdigest()!=digest):
            raise ValueError("n50_unit_drift")
    if (_state(N2_TIMER)!={"LoadState":"loaded","ActiveState":"active",
                           "UnitFileState":"enabled"}
            or _state(N2_SERVICE)!={"LoadState":"loaded","ActiveState":"inactive",
                                   "UnitFileState":"static"}
            or _state(N50_TIMER)!={"LoadState":"loaded","ActiveState":"inactive",
                                  "UnitFileState":"disabled"}
            or _state(N50_SERVICE)["LoadState"]!="loaded"
            or _state(N50_SERVICE)["ActiveState"] not in ("failed","inactive")
            or _state(FALLBACK_SERVICE)["LoadState"]!="loaded"):
        raise ValueError("expected_failback_systemd_state_missing")
    n2=_audit_live_n2_recovery(source=source)
    old_report=_owner_old(source)
    if not _valid_old_forensic(old_report):
        raise ValueError("old_halt_forensic_mismatch")
    new_service, _ = render_n50_managed_systemd(
        owner=OWNER, repo=str(source), python=str(PYTHON), root=str(ROOT),
    )
    after="After=network-online.target\n"
    if new_service.count(after)!=1:
        raise ValueError("unit_service_template_drift")
    new_service=new_service.replace(
        after, after+"OnFailure="+FALLBACK_SERVICE+"\n",
    )
    original=(UNIT_ROOT/N50_SERVICE).read_text("ascii")
    if (new_service.count("OnFailure="+FALLBACK_SERVICE+"\n")!=1
            or new_service.count("WorkingDirectory="+str(source)+"\n")!=1
            or original.count("OnFailure="+FALLBACK_SERVICE+"\n")!=1):
        raise ValueError("recovery_service_template_invalid")
    # Existing unit hash was independently pinned above. This cutover may
    # ONLY repoint the code worktree; service hardening/OnFailure/timers must
    # remain byte-for-byte identical to the installed known-good D298 unit.
    old_source="/home/cia-probe/agent/j1-n50-managed-d298-code"
    if (original.count(old_source)!=1
            or original.replace(old_source,str(source))!=new_service):
        raise ValueError("n50_unit_repoint_only_invariant_failed")
    return {
        "service_text":new_service,
        "original_service_text":original,
        "n2_ok":True,
        "n2_last_published_end_ms":n2["last_published_end_ms"],
        "n2_stored_candles":n2["stored_candles"],
        "n2_historical_unpublished_hours":n2["historical_unpublished_hours"],
        "old_halt_verified":True,
        "old_stored_candles":1306,
        "old_published_hours":3,
        "old_partial_candles":6,
        "old_scope_digest_sha256":ORIGINAL_SCOPE_DIGEST,
        "expected_sha":expected_sha,
        "n2_timer_before":"active",
        "n50_timer_before":"disabled",
        "zero_orders":True,
    }


def _atomic_service_replace(body: str, *, suffix: str) -> None:
    """Single pinned service, no symlinks, fsync + replace. Caller owns rollback."""
    target=UNIT_ROOT/N50_SERVICE
    tmp=UNIT_ROOT/("."+N50_SERVICE+"."+suffix)
    if (target.is_symlink() or not target.is_file()
            or tmp.exists() or tmp.is_symlink()):
        raise ValueError("service_destination_untrusted")
    raw=body.encode("ascii")
    if not 100<len(raw)<16_000:
        raise ValueError("service_text_size_invalid")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL
               |getattr(os,"O_NOFOLLOW",0),0o644)
    try:
        os.fchmod(fd,0o644)
        with os.fdopen(fd,"wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp,target)
        directory_fd=os.open(UNIT_ROOT,os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()


def _restore_original_service(text: str) -> bool:
    try:
        _atomic_service_replace(text,suffix="d306-restore")
        _call(["/usr/bin/systemctl","daemon-reload"],timeout=30)
        return True
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired):
        return False


def _return_to_n2() -> bool:
    ok=True
    for args in (
        ["/usr/bin/systemctl","disable","--now",N50_TIMER],
        ["/usr/bin/systemctl","stop",N50_SERVICE],
        ["/usr/bin/systemctl","enable","--now",N2_TIMER],
    ):
        try:
            _call(args,timeout=40)
        except (OSError,RuntimeError,subprocess.TimeoutExpired):
            ok=False
    try:
        ok=ok and _state(N2_TIMER)=={
            "LoadState":"loaded","ActiveState":"active","UnitFileState":"enabled",
        }
    except (ValueError,RuntimeError,OSError):
        ok=False
    return ok


def execute(*,source: Path,expected_sha: str,
            confirm_recovery_cutover: bool=False,
            allow_systemd_modifications: bool=False) -> dict:
    out={
        "schema_version":"j1-n50-recovery-release-v1",
        "status":"blocked",
        "preflight_verified":False,
        "old_halt_preserved":False,
        "new_epoch_started":False,
        "n50_timer_enabled":False,
        "n50_service_repointed":False,
        "previous_service_restored":None,
        "n2_restored_after_failure":None,
        "systemd_modified":False,
        "network_requests":0,
        "failure_category":None,
        "database_mutation_statements":0,
        "orders_sent":False,
        "live_trading_authorized":False,
        "continuous_collector_verified":False,
    }
    gate=preflight(source=source,expected_sha=expected_sha)
    out["preflight_verified"]=True
    out["old_halt_preserved"]=gate["old_halt_verified"]
    if confirm_recovery_cutover is not True or allow_systemd_modifications is not True:
        out["status"]="preflight_pass_no_changes"
        return out
    now=time.time_ns()//1_000_000
    # One full 372-GET rank rebuild needs nearly 13min. Start EARLY.
    if not 65_000<=now%3_600_000<=110_000:
        out["status"]="early_utc_close_window_required"
        return out
    changed=False
    service_changed=False
    prior=signal.getsignal(signal.SIGTERM)
    def sigterm(_signum,_frame):
        raise InterruptedError("recovery_interrupted")
    signal.signal(signal.SIGTERM,sigterm)
    try:
        # A live N2 tick can never overlap a N50 census.
        if (_state(N2_SERVICE)["ActiveState"]!="inactive"
                or _state(N2_TIMER)["ActiveState"]!="active"):
            raise RuntimeError("n2_not_quiescent_before_disable")
        changed=True
        _call(["/usr/bin/systemctl","disable","--now",N2_TIMER],timeout=40)
        isolation=n50_systemd_n2_quiescence(require_n2_quiesced=True)
        if isolation.get("status")!="n2_quiesced_preflight_only":
            raise RuntimeError("n2_isolation_failed")
        result=_owner_report(
            source=source,
            module="scripts.recover_j1_n50_halted_epoch_once",
            args=["--confirm-halt-reviewed","--allow-fresh-public-census"],
            allow_dataerr=True,
        )
        attempts=result.get("requests_attempted")
        if type(attempts) is int and 0<=attempts<=500:
            out["network_requests"]=attempts
        failure=result.get("failure_category")
        from crypto_intelligence_agent.j1_rest_incremental_owner import _ALLOWED_FAILURES
        if type(failure) is str and failure in _ALLOWED_FAILURES:
            out["failure_category"]=failure
        if (result.get("status")!="new_epoch_sealed_old_halt_preserved"
                or result.get("old_epoch_preserved") is not True
                or result.get("old_journal_sha256_unchanged") is not True
                or result.get("old_scope_sha256_unchanged") is not True
                or result.get("new_scope_created") is not True
                or result.get("orders_sent") is not False):
            raise RuntimeError("owner_new_epoch_recovery_failed")
        out["new_epoch_started"]=True
        out["old_halt_preserved"]=True
        # Install the validated D306 owner code for all FUTURE hours, not
        # just the one-off recovery. Preserve the existing OnFailure unit.
        service_changed=True
        _atomic_service_replace(gate["service_text"],suffix="d306-install")
        _call(["/usr/bin/systemctl","daemon-reload"],timeout=30)
        _call(["/usr/bin/systemd-analyze","verify",
               str(UNIT_ROOT/N50_SERVICE),str(UNIT_ROOT/N50_TIMER),
               str(UNIT_ROOT/FALLBACK_SERVICE)],timeout=30)
        out["n50_service_repointed"]=True
        _call(["/usr/bin/systemctl","reset-failed",N50_SERVICE],timeout=20)
        _call(["/usr/bin/systemctl","enable","--now",N50_TIMER],timeout=40)
        if (_state(N2_TIMER)!={"LoadState":"loaded","ActiveState":"inactive",
                              "UnitFileState":"disabled"}
                or _state(N50_TIMER)!={"LoadState":"loaded","ActiveState":"active",
                                      "UnitFileState":"enabled"}
                or _state(N2_SERVICE)["ActiveState"]!="inactive"):
            raise RuntimeError("recovery_systemd_postflight_failed")
        out["status"]="new_n50_epoch_timer_enabled"
        out["n50_timer_enabled"]=True
        out["systemd_modified"]=True
        return out
    except (OSError,ValueError,TypeError,RuntimeError,InterruptedError,
            subprocess.TimeoutExpired):
        if changed:
            out["n2_restored_after_failure"]=_return_to_n2()
            if service_changed:
                out["previous_service_restored"]=_restore_original_service(
                    gate["original_service_text"])
            out["systemd_modified"]=True
            safe=out["n2_restored_after_failure"] and (
                not service_changed or out["previous_service_restored"])
            out["status"]=("rolled_back_to_n2" if safe
                           else "CRITICAL_n2_or_unit_rollback_failed")
        return out
    finally:
        signal.signal(signal.SIGTERM,prior)


def main(argv: list[str] | None=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--expected-sha",required=True)
    p.add_argument("--confirm-recovery-cutover",action="store_true")
    p.add_argument("--allow-systemd-modifications",action="store_true")
    args=p.parse_args(argv)
    try:
        result=execute(**vars(args))
    except (OSError,RuntimeError,ValueError,PermissionError,TypeError,
            subprocess.TimeoutExpired,json.JSONDecodeError):
        result={"schema_version":"j1-n50-recovery-release-v1","status":"blocked",
                "systemd_modified":False,"orders_sent":False}
    print(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if result["status"] in (
        "preflight_pass_no_changes","new_n50_epoch_timer_enabled",
    ) else 65


if __name__=="__main__":
    raise SystemExit(main())
