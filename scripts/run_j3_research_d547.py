"""Owner-only D547 mark campaign and offline fine replay readiness."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import time

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient,J1BybitCaptureError
from crypto_intelligence_agent.j3_derivatives_history_d536 import collect_derivatives,trade_coverage
from crypto_intelligence_agent.j3_history_campaign_d546 import GETS_PER_BATCH,REQUEST_SPACING_SECONDS
from crypto_intelligence_agent.j3_long_history_d528 import load_plan
from crypto_intelligence_agent.j3_mark_campaign_d547 import run_mark_campaign,replay_readiness
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _private_directory
from crypto_intelligence_agent.market_data import MarketDataError,DataValidationError
from scripts.run_j3_long_history_d528 import owner_lock,SAFE_FAILURES


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--task",choices=("campaign-mark-5m-365","preflight-annual-5m"),required=True)
    for flag in ("allow-public-network","confirm-personal-readonly-research",
                 "confirm-region-eligible","confirm-public-data-rights"):
        p.add_argument("--"+flag,action="store_true")
    a=p.parse_args(argv)
    client=None
    last=None
    def emit(d):
        nonlocal last
        if d.get("kind")=="d547_mark_batch":
            last=d
        print(json.dumps(d,sort_keys=True,separators=(",",":")),flush=True)
    try:
        network=a.task=="campaign-mark-5m-365"
        flags=(a.allow_public_network,a.confirm_personal_readonly_research,
               a.confirm_region_eligible,a.confirm_public_data_rights)
        if (network and not all(flags)) or (not network and any(flags)):
            raise DataValidationError("D547 explicit mode and public authorization required")
        os.umask(0o077)
        home=_private_directory(a.directory)
        if (not home.name.startswith("d528-history") or any(x.startswith("j1-") for x in home.parts)
                or os.geteuid()!=os.getuid() or os.geteuid()==0):
            raise DataValidationError("D547 private research owner required")
        with owner_lock(home):
            plan=load_plan(home)
            if plan.source_mode!="public_rest_observed_unverified":
                raise DataValidationError("D547 real retrospective plan required")
            def derivatives(kind,client=None):
                if load_plan(home).digest!=plan.digest:
                    raise DataValidationError("D547 plan changed")
                return collect_derivatives(home=home,plan=plan,days=365,kind=kind,
                    client=client,wall_ms=lambda:time.time_ns()//1_000_000,budget=GETS_PER_BATCH)
            trade=trade_coverage(home,plan,365,"5m")
            mark=derivatives("mark-5m")
            if network:
                if trade["missing_candles"]!=0:
                    raise DataValidationError("D547 complete annual trade-5m first")
                def collect():
                    nonlocal client
                    client=BoundedBybitPublicClient(allow_derivatives_history_research=True,
                                    min_interval_seconds=REQUEST_SPACING_SECONDS)
                    return derivatives("mark-5m",client)
                out=run_mark_campaign(digest=plan.digest,baseline=mark,collect=collect,
                            emit=emit,clock=time.monotonic,sleep=time.sleep)
                code=1 if out["status"]=="campaign_stopped" else 0
            else:
                out=replay_readiness(digest=plan.digest,trade=trade,mark=mark,
                                     funding=derivatives("funding"))
                code=0 if out["status"]=="ready" else 2
        emit(out)
        return code
    except (MarketDataError,J1BybitCaptureError,OSError,ValueError,TypeError,
            ArithmeticError,sqlite3.Error) as exc:
        out={"kind":"d547_research_stopped","task":a.task,"status":"stopped",
             "error_type":type(exc).__name__,"automatic_retry":False,
             "last_confirmed_mark_rows":None if last is None else last["saved_rows"],
             "orders_sent":False,"j1_touched":False,"profile_modified":False}
        if isinstance(exc,J1BybitCaptureError):
            out["failure_code"]=str(exc) if str(exc) in SAFE_FAILURES else "unclassified_capture_error_no_retry"
        if client is not None:
            out["requests_attempted_in_last_batch"]=client.requests_attempted
            out["provider_retcode"]=client.last_provider_retcode
            out.update(client.sanitized_quota_fields())
        emit(out)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
