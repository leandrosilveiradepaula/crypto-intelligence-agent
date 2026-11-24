"""Owner-only D528 long history: bounded collection, no services or orders."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from contextlib import contextmanager

from crypto_intelligence_agent.j3_long_history_d528 import (
    collect_batch, freeze_cohort, load_plan, save_plan, MAX_BATCH_GETS, PLAN_FILE,
)
from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient, J1BybitCaptureError
from crypto_intelligence_agent.j2_dynamic_public_n50_d451 import capture_dynamic_public_n50
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _private_directory, _owner_file
from crypto_intelligence_agent.market_data import MarketDataError


@contextmanager
def owner_lock(home):
    import fcntl
    name = ".d528-collect.lock"
    if not (home/name).exists() and not (home/name).is_symlink():
        try:
            os.close(os.open(home/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
        except FileExistsError:
            pass
    fd = _owner_file(home,name)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--days",type=int,default=90,choices=range(1,731),metavar="1..730")
    p.add_argument("--interval",choices=("1h","5m"),default="1h")
    p.add_argument("--max-gets",type=int,default=MAX_BATCH_GETS,choices=range(1,MAX_BATCH_GETS+1),metavar="1..400")
    p.add_argument("--init",action="store_true",help="Freeze a new provisional cohort, never replace an existing one")
    p.add_argument("--low-priority",action="store_true")
    for flag in ("allow-public-network","confirm-personal-readonly-research",
                 "confirm-region-eligible","confirm-public-data-rights"):
        p.add_argument("--"+flag,action="store_true")
    a=p.parse_args(argv)
    try:
        if not all((a.allow_public_network,a.confirm_personal_readonly_research,
                    a.confirm_region_eligible,a.confirm_public_data_rights)):
            raise ValueError("explicit public research authorizations required")
        os.umask(0o077)
        home=_private_directory(a.directory)
        if (not home.name.startswith("d528-history") or any(x.startswith("j1-") for x in home.parts)
                or os.geteuid()!=os.getuid()):
            raise ValueError("separate D528 owner history directory required")
        if a.low_priority:
            os.nice(10)
        with owner_lock(home):
            if a.init:
                if (home/PLAN_FILE).exists() or (home/PLAN_FILE).is_symlink():
                    raise ValueError("cohort exists; resume without --init")
                snapshot=capture_dynamic_public_n50(allow_public_network=True,
                    confirm_personal_readonly_research=True,confirm_region_eligible=True,
                    confirm_public_data_rights=True)
                plan=freeze_cohort(snapshot)
                save_plan(home,plan)
                # Separate D451 client: preserve pacing across the transition.
                time.sleep(2)
            else:
                plan=load_plan(home)
            client=BoundedBybitPublicClient(allow_long_history_research=True)
            result=collect_batch(home=home,plan=plan,days=a.days,interval=a.interval,
                client=client,wall_ms=lambda:time.time_ns()//1_000_000,max_gets=a.max_gets)
        print(json.dumps(result,sort_keys=True,separators=(",",":")))
        return 0
    except (MarketDataError,J1BybitCaptureError,OSError,ValueError,TypeError,ArithmeticError) as exc:
        print(json.dumps({"status":"d528_batch_stopped","error_type":type(exc).__name__,
                          "completed_pages_preserved":True,
                          "automatic_retry":False,"orders_sent":False,"j1_touched":False}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
