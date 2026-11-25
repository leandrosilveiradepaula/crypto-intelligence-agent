"""Offline owner research over D528 history; never contacts the exchange."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from crypto_intelligence_agent.j3_combination_research_d520 import MAX_MATRIX_BYTES
from crypto_intelligence_agent.j3_entry_research_d530 import MAX_BYTES as MAX_ENTRY_BYTES
from crypto_intelligence_agent.j3_exit_research_d531 import MAX_BYTES as MAX_EXIT_BYTES
from crypto_intelligence_agent.j3_long_history_d528 import load_plan
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay, DEFAULT_STOPS, DEFAULT_HORIZONS
from crypto_intelligence_agent.market_data import MarketDataError
from crypto_intelligence_agent.paper_profile_d487 import snapshot
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy
from scripts.run_j3_long_history_d528 import owner_lock


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--policy-file",type=Path,required=True)
    p.add_argument("--matrix-file",type=Path,default=Path(__file__).resolve().parents[1]/
                   "docs/examples/d526_rsi_filter_research_matrix.json")
    p.add_argument("--entry-experiments-file",type=Path)
    p.add_argument("--exit-experiments-file",type=Path)
    p.add_argument("--strategy-names",nargs="+")
    p.add_argument("--research-max-horizon-hours",type=int,choices=(72,168),default=72)
    p.add_argument("--target-diagnostics",action="store_true")
    p.add_argument("--days",type=int,default=90)
    p.add_argument("--partition",choices=("development","validation","holdout"),default="development")
    p.add_argument("--horizon-hours",type=int,nargs="+",default=DEFAULT_HORIZONS)
    p.add_argument("--stop-grid-bps",type=int,nargs="+",default=DEFAULT_STOPS)
    p.add_argument("--resolution",choices=("1h","5m"),default="1h")
    p.add_argument("--confirm-frozen-hypotheses",action="store_true")
    p.add_argument("--low-priority",action="store_true")
    a=p.parse_args(argv)
    try:
        if a.low_priority and os.name=="posix":
            os.nice(10)
        plan=load_plan(a.directory)
        if plan.source_mode!="public_rest_observed_unverified":
            raise ValueError("D529 real research requires real retrospective plan")
        rev=snapshot(a.policy_file)["revision"]
        policy=read_owner_paper_policy(a.policy_file)
        if snapshot(a.policy_file)["revision"]!=rev:
            raise ValueError("profile changed during read")
        with a.matrix_file.open("rb") as f:
            matrix=f.read(MAX_MATRIX_BYTES+1)
        extra=None
        if a.entry_experiments_file is not None:
            with a.entry_experiments_file.open("rb") as f:
                extra=f.read(MAX_ENTRY_BYTES+1)
        exit_extra=None
        if a.exit_experiments_file is not None:
            with a.exit_experiments_file.open("rb") as f:
                exit_extra=f.read(MAX_EXIT_BYTES+1)
        with owner_lock(a.directory):
            report=run_long_replay(home=a.directory,plan=plan,owner_policy=policy,
                matrix_raw=matrix,days=a.days,partition=a.partition,
                horizons=a.horizon_hours,stops=a.stop_grid_bps,resolution=a.resolution,
                confirm_frozen_hypotheses=a.confirm_frozen_hypotheses,
                entry_experiments_raw=extra,exit_experiments_raw=exit_extra,
                strategy_names=a.strategy_names,
                research_max_horizon_hours=a.research_max_horizon_hours,
                target_diagnostics=a.target_diagnostics,
                progress=lambda n,total:print("D529 symbols processed: %d/%d"%(n,total),
                                             file=sys.stderr,flush=True))
        if snapshot(a.policy_file)["revision"]!=rev:
            raise ValueError("profile changed during replay")
        report["profile_revision"]=rev
        print(json.dumps(report,default=str,sort_keys=True,separators=(",",":")))
        return 0 if report["status"]=="exploratory_replay_completed" else 2
    except (MarketDataError,OSError,TypeError,ValueError,ArithmeticError) as exc:
        print(json.dumps({"status":"d529_replay_unavailable","error_type":type(exc).__name__,
                          "orders_sent":False,"profile_modified":False}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
