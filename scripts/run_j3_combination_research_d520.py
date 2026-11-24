"""Owner-only, read-only batch research on already saved D516/D518 data."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from crypto_intelligence_agent.j3_combination_research_d520 import MAX_MATRIX_BYTES, run_matrix
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--historical-directory",type=Path,required=True)
    p.add_argument("--policy-file",type=Path,required=True)
    p.add_argument("--matrix-file",type=Path,default=Path(__file__).resolve().parents[1]/
                   "docs/examples/d520_indicator_research_matrix.json")
    p.add_argument("--as-of-ms",type=int,required=True)
    p.add_argument("--horizon-hours",type=int,choices=range(1,13),default=4)
    p.add_argument("--min-complete",type=int,default=20)
    p.add_argument("--min-coverage-bps",type=int,default=7000)
    p.add_argument("--full-json",action="store_true")
    a=p.parse_args(argv)
    try:
        if not 0<a.as_of_ms<=time.time_ns()//1_000_000:
            raise DataValidationError("D520 invalid frozen input cutoff")
        with a.matrix_file.open("rb") as f:
            raw=f.read(MAX_MATRIX_BYTES+1)
        report=run_matrix(directory=a.historical_directory,
            owner_policy=read_owner_paper_policy(a.policy_file),matrix_raw=raw,
            as_of_ms=a.as_of_ms,horizon_hours=a.horizon_hours,
            min_complete=a.min_complete,min_coverage_bps=a.min_coverage_bps)
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
