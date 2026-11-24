"""D522: one bounded owner-local research job, not a service or trading executor."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

from .j3_combination_research_d520 import MAX_MATRIX_BYTES, REPORT_SCHEMA, parse_matrix
from .market_data import DataValidationError
from .paper_profile_d487 import snapshot

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_MATRIX=ROOT/"docs/examples/d520_indicator_research_matrix.json"
JOB_SCHEMA="d522-owner-local-research-job-v1"
MAX_REPORT_BYTES=512_000
TIMEOUT_SECONDS=300


class ResearchBusy(RuntimeError):
    pass


class ResearchJob:
    """One process at a time, no external network, files or profile changes.

    Child executes only a fixed repository module with typed bounded inputs.
    Reports live in memory, replaced on an explicit new run, lost on restart.
    """
    def __init__(self, *, policy_file:Path, history_directory:Path):
        self._policy=policy_file
        self._history=history_directory
        self._lock=threading.Lock()
        self._state=self._status("idle")

    @staticmethod
    def _status(status,**fields):
        return {"schema_version":JOB_SCHEMA,"status":status,
                "orders_sent":False,"profile_modified":False,**fields}

    def status(self):
        with self._lock:
            return dict(self._state)

    def start(self, data):
        if (type(data) is not dict or not {"horizon_hours"}<=set(data)
                or set(data)-{"horizon_hours","as_of_ms","matrix"}):
            raise DataValidationError("D522 invalid job request")
        horizon=data["horizon_hours"]
        cutoff=data.get("as_of_ms")
        if (type(horizon) is not int or not 1<=horizon<=12
                or (cutoff is not None and (type(cutoff) is not int
                     or not 0<cutoff<=time.time_ns()//1_000_000))):
            raise DataValidationError("D522 invalid horizon or cutoff")
        with self._lock:
            if self._state["status"]=="running":
                raise ResearchBusy("D522 one research job at a time")
            if data.get("matrix") is None:
                with DEFAULT_MATRIX.open("rb") as fp:
                    raw=fp.read(MAX_MATRIX_BYTES+1)
            else:
                raw=json.dumps(data["matrix"],ensure_ascii=True,
                               sort_keys=True,separators=(",",":")).encode("ascii")
            _,profiles,_=parse_matrix(raw)
            revision=snapshot(self._policy)["revision"]
            job_id=uuid4().hex
            fields={"job_id":job_id,"horizon_hours":horizon,"requested_as_of_ms":cutoff,
                    "profile_revision":revision,"matrix_sha256":sha256(raw).hexdigest(),
                    "strategy_count":len(profiles)+2}
            self._state=self._status("running",**fields)
            # No shell, arbitrary path, credentials, network flag or user code.
            cmd=[sys.executable,"-m","scripts.run_j3_combination_research_d520",
                 "--historical-directory",str(self._history),"--policy-file",str(self._policy),
                 "--matrix-stdin","--horizon-hours",str(horizon),
                 "--expected-policy-revision",revision,"--low-priority"]
            if cutoff is None:
                cmd.append("--latest-saved")
            else:
                cmd.extend(["--as-of-ms",str(cutoff)])
            try:
                thread=threading.Thread(target=self._run,args=(cmd,raw,fields),daemon=True)
                thread.start()
            except RuntimeError:
                self._state=self._status("failed",**fields,error="worker_start_failed")
            return dict(self._state)

    def _run(self,cmd,raw,fields):
        try:
            result=subprocess.run(cmd,input=raw,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,timeout=TIMEOUT_SECONDS,check=False,cwd=ROOT)
            if result.returncode not in (0,2) or not 2<=len(result.stdout)<=MAX_REPORT_BYTES:
                raise DataValidationError("D522 worker report unavailable")
            report=json.loads(result.stdout)
            flags=("orders_sent","profile_modified","out_of_sample_results_validated",
                   "approved_for_live_use","financial_backtest_approved","funding_settlement_verified",
                   "liquidation_verified","intrabar_path_verified","winner_selected")
            expected="exploratory_matrix_completed" if result.returncode==0 else "no_complete_common_paths"
            if (type(report) is not dict or report.get("schema_version")!=REPORT_SCHEMA
                    or report.get("status")!=expected or report.get("public_gets")!=0
                    or report.get("profile_revision")!=fields["profile_revision"]
                    or report.get("horizon_hours")!=fields["horizon_hours"]
                    or (fields["requested_as_of_ms"] is not None
                        and report.get("as_of_ms")!=fields["requested_as_of_ms"])
                    or report.get("manifest",{}).get("matrix_sha256")!=fields["matrix_sha256"]
                    or type(report.get("rows")) is not list
                    or len(report["rows"])!=fields["strategy_count"]
                    or any(report.get(flag) is not False for flag in flags)):
                raise DataValidationError("D522 report contract invalid")
            next_state=self._status("completed",**fields,report=report)
        except subprocess.TimeoutExpired:
            next_state=self._status("failed",**fields,error="research_timeout")
        except (OSError,ValueError,TypeError,DataValidationError,ArithmeticError):
            next_state=self._status("failed",**fields,error="research_unavailable")
        with self._lock:
            self._state=next_state
