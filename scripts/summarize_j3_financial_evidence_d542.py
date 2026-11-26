"""Read one owner-only D529 JSON report; no backtest, network or writes."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from crypto_intelligence_agent.j3_financial_evidence_d542 import summarize_financial_replay
from crypto_intelligence_agent.j3_compact_financial_d544 import compact_financial_summary
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _private_directory,_owner_file
from crypto_intelligence_agent.market_data import MarketDataError

MAX_BYTES=128*1024*1024
_NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.json\Z")
_ANNUAL=re.compile(r"annual-[0-9]{8}T[0-9]{6}-[0-9]{1,12}\.json\Z")


def _unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:
            raise ValueError("duplicate field")
        out[k]=v
    return out


def _bad_number(_):
    raise ValueError("nonfinite number")


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument("--report",type=Path)
    source.add_argument("--annual-directory",type=Path,help="Select the only completed annual report; refuse ambiguity")
    p.add_argument("--compact",action="store_true",help="Bounded aggregate JSON lines for research journal")
    a=p.parse_args(argv)
    try:
        if a.annual_directory is not None:
            home=_private_directory(a.annual_directory)
            names=sorted(p.name for p in home.iterdir() if _ANNUAL.fullmatch(p.name))
            if len(names)!=1:
                raise ValueError("D544 exactly one completed annual report required")
            a.report=home/names[0]
        home=_private_directory(a.report.parent)
        if _NAME.fullmatch(a.report.name) is None:
            raise ValueError("invalid report name")
        fd=_owner_file(home,a.report.name)
        with os.fdopen(fd,"rb") as stream:
            before=os.fstat(stream.fileno())
            if not 2<=before.st_size<=MAX_BYTES:
                raise ValueError("report size")
            raw=stream.read(MAX_BYTES+1)
            after=os.fstat(stream.fileno())
            if len(raw)!=before.st_size or before.st_mtime_ns!=after.st_mtime_ns or before.st_size!=after.st_size:
                raise ValueError("report changed")
        report=json.loads(raw,object_pairs_hook=_unique,parse_constant=_bad_number)
        result=summarize_financial_replay(report)
        result["source_report_sha256"]=sha256(raw).hexdigest()
        if a.compact:
            for row in compact_financial_summary(result):
                print(json.dumps(row,sort_keys=True,separators=(",",":")))
        else:
            print(json.dumps(result,sort_keys=True,separators=(",",":")))
        return 0
    except (MarketDataError,OSError,ValueError,TypeError,ArithmeticError,RecursionError) as exc:
        print(json.dumps({"status":"d542_report_unavailable","error_type":type(exc).__name__,
                          "orders_sent":False,"profile_modified":False}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
