"""Owner-only, read-only batch research on already saved D516/D518 data."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
import time

from crypto_intelligence_agent.j3_combination_research_d520 import MAX_MATRIX_BYTES, run_matrix
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from crypto_intelligence_agent.j3_intrahour_replay_d518 import read_latest_intrahour
from crypto_intelligence_agent.paper_profile_d487 import snapshot
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--historical-directory",type=Path,required=True)
    p.add_argument("--policy-file",type=Path,required=True)
    matrix=p.add_mutually_exclusive_group()
    matrix.add_argument("--matrix-file",type=Path)
    matrix.add_argument("--matrix-stdin",action="store_true")
    cutoff=p.add_mutually_exclusive_group(required=True)
    cutoff.add_argument("--as-of-ms",type=int)
    cutoff.add_argument("--latest-saved",action="store_true")
    p.add_argument("--expected-policy-revision")
    p.add_argument("--low-priority",action="store_true")
    p.add_argument("--horizon-hours",type=int,choices=range(1,13),default=4)
    p.add_argument("--min-complete",type=int,default=20)
    p.add_argument("--min-coverage-bps",type=int,default=7000)
    p.add_argument("--full-json",action="store_true")
    a=p.parse_args(argv)
    try:
        if a.low_priority and os.name == "posix":
            os.nice(10)
        now=time.time_ns()//1_000_000
        as_of=a.as_of_ms
        if a.latest_saved:
            latest=read_latest_intrahour(a.historical_directory,now_ms=now)
            if latest is None:
                raise DataValidationError("D522 saved intrahour data unavailable")
            as_of=latest.created_at_ms
        if not 0<as_of<=now:
            raise DataValidationError("D520 invalid frozen input cutoff")
        if a.matrix_stdin:
            raw=sys.stdin.buffer.read(MAX_MATRIX_BYTES+1)
        else:
            matrix_file=a.matrix_file or (Path(__file__).resolve().parents[1]/
                         "docs/examples/d520_indicator_research_matrix.json")
            with matrix_file.open("rb") as f:
                raw=f.read(MAX_MATRIX_BYTES+1)
        revision=snapshot(a.policy_file)["revision"]
        if a.expected_policy_revision is not None and revision!=a.expected_policy_revision:
            raise DataValidationError("D522 profile changed before research")
        policy=read_owner_paper_policy(a.policy_file)
        if snapshot(a.policy_file)["revision"]!=revision:
            raise DataValidationError("D522 profile changed while reading")
        report=run_matrix(directory=a.historical_directory,owner_policy=policy,matrix_raw=raw,
            as_of_ms=as_of,horizon_hours=a.horizon_hours,
            min_complete=a.min_complete,min_coverage_bps=a.min_coverage_bps)
        if snapshot(a.policy_file)["revision"]!=revision:
            raise DataValidationError("D522 profile changed during research")
        report["profile_revision"]=revision
        if not a.full_json:
            report.pop("comparison")
            report["manifest"].pop("archive_digests")
        print(json.dumps(report,default=str,sort_keys=True,ensure_ascii=True,separators=(",",":")))
        return 0 if report["status"]=="exploratory_matrix_completed" else 2
    except (DataValidationError,DataGapError,OSError,ValueError,TypeError,ArithmeticError) as exc:
        print(json.dumps({"status":"matrix_research_unavailable",
            "error_type":type(exc).__name__,"orders_sent":False},sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
