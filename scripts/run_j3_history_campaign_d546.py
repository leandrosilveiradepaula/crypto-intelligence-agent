"""Explicit owner-only D546 public trade-5m campaign; no service changes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import time

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient,J1BybitCaptureError
from crypto_intelligence_agent.j3_exact_history_d543 import collect_exact_batch
from crypto_intelligence_agent.j3_long_history_d528 import load_plan
from crypto_intelligence_agent.j3_derivatives_history_d536 import trade_coverage
from crypto_intelligence_agent.j3_history_campaign_d546 import run_campaign,GETS_PER_BATCH,REQUEST_SPACING_SECONDS
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _private_directory
from crypto_intelligence_agent.market_data import MarketDataError,DataValidationError
from scripts.run_j3_long_history_d528 import owner_lock,SAFE_FAILURES


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--days",type=int,choices=(365,730),required=True)
    for flag in ("allow-public-network","confirm-personal-readonly-research",
                 "confirm-region-eligible","confirm-public-data-rights"):
        p.add_argument("--"+flag,action="store_true")
    a=p.parse_args(argv)
    client=None
    last=None
    plan=None
    def emit(d):
        nonlocal last
        if d["kind"]=="d546_campaign_batch":
            last=d
        print(json.dumps(d,sort_keys=True,separators=(",",":")),flush=True)
    try:
        if not all((a.allow_public_network,a.confirm_personal_readonly_research,
                    a.confirm_region_eligible,a.confirm_public_data_rights)):
            raise DataValidationError("D546 explicit public research authorizations required")
        os.umask(0o077)
        home=_private_directory(a.directory)
        if (not home.name.startswith("d528-history") or any(x.startswith("j1-") for x in home.parts)
                or os.geteuid()!=os.getuid()):
            raise DataValidationError("D546 separate research owner directory required")
        with owner_lock(home):
            plan=load_plan(home)
            if plan.source_mode!="public_rest_observed_unverified":
                raise DataValidationError("D546 public retrospective plan required")
            before=trade_coverage(home,plan,a.days,"5m")
            def collect():
                nonlocal client
                if load_plan(home).digest!=plan.digest:
                    raise DataValidationError("D546 history plan changed")
                client=BoundedBybitPublicClient(allow_long_history_research=True,
                                    min_interval_seconds=REQUEST_SPACING_SECONDS)
                return collect_exact_batch(home=home,plan=plan,days=a.days,interval="5m",
                            client=client,wall_ms=lambda:time.time_ns()//1_000_000,
                            max_gets=GETS_PER_BATCH,oldest_first=False)
            out=run_campaign(days=a.days,plan_sha256=plan.digest,cutoff_ms=plan.cutoff_ms,
                            baseline=before["saved_candles"],expected=before["expected_candles"],
                            collect=collect,emit=emit,clock=time.monotonic,sleep=time.sleep)
        emit(out)
        return 1 if out["status"]=="campaign_stopped" else 0
    except (MarketDataError,J1BybitCaptureError,OSError,ValueError,TypeError,ArithmeticError,sqlite3.Error) as exc:
        out={"kind":"d546_campaign_final","status":"campaign_stopped","reason":"batch_or_preflight_error",
             "error_type":type(exc).__name__,"dataset":"trade-5m","requested_days":a.days,
             "plan_sha256":None if plan is None else plan.digest,
             "last_confirmed_saved_candles":None if last is None else last["saved_candles"],
             "completed_pages_preserved":True,"automatic_retry":False,
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
