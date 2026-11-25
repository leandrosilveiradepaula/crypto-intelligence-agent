"""Owner-only D536 acquisition/coverage, no account, credentials or orders."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient,J1BybitCaptureError
from crypto_intelligence_agent.j3_long_history_d528 import load_plan
from crypto_intelligence_agent.j3_derivatives_history_d536 import collect_derivatives,trade_coverage,KINDS
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _private_directory
from crypto_intelligence_agent.market_data import MarketDataError
from scripts.run_j3_long_history_d528 import owner_lock,SAFE_FAILURES


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--days",type=int,choices=range(1,731),default=365,metavar="1..730")
    p.add_argument("--dataset",choices=(*KINDS,"trade-1h","trade-5m"),required=True)
    p.add_argument("--collect",action="store_true")
    p.add_argument("--max-gets",type=int,choices=range(1,101),default=100)
    p.add_argument("--request-spacing-seconds",type=int,choices=range(10,13),default=10)
    p.add_argument("--low-priority",action="store_true")
    for flag in ("allow-public-network","confirm-personal-readonly-research",
                 "confirm-region-eligible","confirm-public-data-rights"):
        p.add_argument("--"+flag,action="store_true")
    a=p.parse_args(argv)
    client=None
    try:
        os.umask(0o077)
        home=_private_directory(a.directory)
        if not home.name.startswith("d528-history") or any(x.startswith("j1-") for x in home.parts) or os.geteuid()!=os.getuid():
            raise ValueError("D536 separate research owner directory required")
        if a.low_priority:
            os.nice(10)
        with owner_lock(home):
            plan=load_plan(home)
            if plan.source_mode!="public_rest_observed_unverified":
                raise ValueError("D536 public retrospective plan required")
            if a.collect:
                if a.dataset not in KINDS or not all((a.allow_public_network,
                    a.confirm_personal_readonly_research,a.confirm_region_eligible,a.confirm_public_data_rights)):
                    raise ValueError("D536 explicit public research authorization required")
                client=BoundedBybitPublicClient(allow_derivatives_history_research=True,
                                               min_interval_seconds=a.request_spacing_seconds)
            if a.dataset.startswith("trade-"):
                out=trade_coverage(home,plan,a.days,a.dataset[6:])
            else:
                out=collect_derivatives(home=home,plan=plan,days=a.days,kind=a.dataset,client=client,
                      wall_ms=lambda:time.time_ns()//1_000_000,budget=a.max_gets)
        print(json.dumps(out,sort_keys=True,separators=(",",":")))
        return 0
    except (MarketDataError,J1BybitCaptureError,OSError,ValueError,TypeError,ArithmeticError) as exc:
        out={"status":"d536_stopped","error_type":type(exc).__name__,
             "completed_pages_preserved":True,"automatic_retry":False,"orders_sent":False,"j1_touched":False}
        if isinstance(exc,J1BybitCaptureError):
            out["failure_code"]=str(exc) if str(exc) in SAFE_FAILURES else "unclassified_capture_error_no_retry"
        if client is not None:
            out["requests_attempted"]=client.requests_attempted
            out["provider_retcode"]=client.last_provider_retcode
            out.update(client.sanitized_quota_fields())
        print(json.dumps(out,sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
