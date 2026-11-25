"""D536 retrospective funding rates and mark-price bars; not venue fills.

A saved page is evidence of a public query, not proof of a complete settlement
calendar. Saturated funding windows are bisected without assuming ordering.
Mark candles have no invented trade volume. The same D528 owner lock must
cover collection/readback, preserving one shared network research job.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, Context, localcontext
from hashlib import sha256
from pathlib import Path
import os
import re
import shutil
import tempfile

from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, research_funding_url, research_mark_url,
)
from .decimal_json import decode_public_market_json_exact, positive_market_decimal
from .j3_long_history_d528 import (
    DAY, HOUR_MS, MAX_BATCH_MS, MAX_PLAN_AGE_MS, MIN_FREE_BYTES, canonical,
    decode_plan, windows, read_window,
)
from .j4_automatic_entry_materializer_d448 import _read_owner_bytes
from .market_data import DataValidationError, interval_duration_ms
from .synthetic_intrabar_barriers import ResearchDirection

SCHEMA="d536-derivatives-history-page-v1"
KINDS=("funding","mark-1h","mark-5m")
MAX_PAGE_BYTES=524288
MAX_GETS=100
_RATE=re.compile(r"-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,24})?\Z")
_SHA=re.compile(r"[0-9a-f]{64}\Z")
_CTX=Context(prec=128)


def _timestamp(x):
    if type(x) is not str or not 1<=len(x)<=13 or not x.isascii() or not x.isdecimal():
        raise DataValidationError("D536 invalid timestamp")
    t=int(x)
    if not 0<t<=4_000_000_000_000 or str(t)!=x:
        raise DataValidationError("D536 invalid timestamp")
    return t


def _rate(x):
    if type(x) is not str or _RATE.fullmatch(x) is None:
        raise DataValidationError("D536 invalid funding rate")
    d=Decimal(x)
    if abs(d)>1:
        raise DataValidationError("D536 funding rate outside supported fraction")
    return d


def _price(x):
    if type(x) is not str:
        raise DataValidationError("D536 mark price must be exact string")
    return positive_market_decimal(x,"mark")


def normalize_page(payload,kind,symbol,start,end):
    if (type(payload) is not dict or type(payload.get("retCode")) is not int
            or payload["retCode"]!=0 or type(payload.get("result")) is not dict):
        raise DataValidationError("D536 invalid public envelope")
    result=payload["result"]
    if (result.get("category")!="linear" or type(result.get("list")) is not list
            or (kind!="funding" and result.get("symbol")!=symbol)
            or (kind=="funding" and "symbol" in result and result["symbol"]!=symbol)):
        raise DataValidationError("D536 response identity mismatch")
    rows=result["list"]
    limit=200 if kind=="funding" else (end-start)//interval_duration_ms(kind[5:])
    if len(rows)>limit:
        raise DataValidationError("D536 response exceeded page size")
    output=[]
    for row in rows:
        if kind=="funding":
            if type(row) is not dict or row.get("symbol")!=symbol:
                raise DataValidationError("D536 funding symbol mismatch")
            t=_timestamp(row.get("fundingRateTimestamp"))
            v=_rate(row.get("fundingRate"))
            output.append([t,str(v)])
        else:
            if type(row) is not list or len(row)!=5:
                raise DataValidationError("D536 mark OHLC requires five fields")
            t=_timestamp(row[0])
            op,hi,lo,cl=map(_price,row[1:])
            if t%interval_duration_ms(kind[5:]) or lo>min(op,cl,hi) or hi<max(op,cl,lo):
                raise DataValidationError("D536 invalid mark grid or OHLC")
            output.append([t,*map(str,(op,hi,lo,cl))])
        if not start<=t<end:
            raise DataValidationError("D536 row outside requested interval")
    output.sort(key=lambda x:x[0])
    if any(a[0]>=b[0] for a,b in zip(output,output[1:])):
        raise DataValidationError("D536 duplicate row time")
    return output


def _page_name(plan,kind,symbol,start,end):
    key=sha256(canonical([plan.digest,kind,symbol,start,end])).hexdigest()
    return "d536-"+key+".json"


def _atomic_page(home,name,raw):
    # Private, single-writer D528 lock held by caller; no replacement of an
    # existing page. Directory fsync preserves already completed checkpoints.
    if not 2<=len(raw)<=MAX_PAGE_BYTES or (home/name).exists() or (home/name).is_symlink():
        raise DataValidationError("D536 invalid or existing page")
    fd,tmp=tempfile.mkstemp(prefix=".d536-",dir=home)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        # link does not overwrite, including a conflicting symlink.
        os.link(tmp,home/name)
        os.unlink(tmp)
        dirfd=os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _page(home,plan,kind,symbol,start,end,*,client,wall_ms,budget,started):
    name=_page_name(plan,kind,symbol,start,end)
    identity=[plan.digest,kind,symbol,start,end,plan.source_mode]
    target=home/name
    if target.exists() or target.is_symlink():
        raw=_read_owner_bytes(home,name,MAX_PAGE_BYTES)
        env=decode_public_market_json_exact(raw,max_bytes=MAX_PAGE_BYTES)
        body=env.get("payload")
        if (set(env)!={"schema","payload","sha256"} or env["schema"]!=SCHEMA
                or type(body) is not dict or env["sha256"]!=sha256(canonical(body)).hexdigest()
                or raw!=canonical(env) or set(body)!={"identity","received_ms","raw_sha256","rows"}
                or body["identity"]!=identity or type(body["received_ms"]) is not int
                or not plan.observed_at_ms<=body["received_ms"]<plan.observed_at_ms+MAX_PLAN_AGE_MS
                or type(body["raw_sha256"]) is not str or _SHA.fullmatch(body["raw_sha256"]) is None
                or type(body["rows"]) is not list):
            raise DataValidationError("D536 saved page identity/integrity")
        # Revalidate stored records using the same source contract.
        try:
            rows=body["rows"]
            provider=([{"symbol":symbol,"fundingRateTimestamp":str(t),"fundingRate":v}
                       for t,v in rows] if kind=="funding" else
                      [[str(t),*v] for t,*v in rows])
            checked=normalize_page({"retCode":0,"result":{"category":"linear","symbol":symbol,
                                      "list":provider}},kind,symbol,start,end)
        except (TypeError,ValueError,IndexError) as exc:
            raise DataValidationError("D536 malformed stored rows") from exc
        if checked!=rows:
            raise DataValidationError("D536 noncanonical stored rows")
        return rows
    if (client is None or client.requests_attempted>=budget
            or wall_ms()>=started+MAX_BATCH_MS or shutil.disk_usage(home).free<MIN_FREE_BYTES):
        return None
    url=(research_funding_url(symbol,start,end) if kind=="funding"
         else research_mark_url(symbol,kind[5:],start,end))
    raw,payload=client.get(url)
    received=wall_ms()
    if not started<=received<min(started+MAX_BATCH_MS+60_000,
                                  plan.observed_at_ms+MAX_PLAN_AGE_MS):
        raise DataValidationError("D536 retrieval outside batch")
    rows=normalize_page(payload,kind,symbol,start,end)
    body={"identity":identity,"received_ms":received,
          "raw_sha256":sha256(raw).hexdigest(),"rows":rows}
    env={"schema":SCHEMA,"payload":body,"sha256":sha256(canonical(body)).hexdigest()}
    _atomic_page(home,name,canonical(env))
    return rows


def jobs(plan,days,kind):
    if kind not in KINDS:
        raise DataValidationError("D536 explicit dataset")
    interval="1h" if kind=="funding" else kind[5:]
    for start,end,symbol,first in sorted(windows(plan,days,interval),
                                       key=lambda j:(j[0],j[2])):
        if kind=="funding":
            yield symbol,max(start,dict(plan.members)[symbol]),end
        else:
            step=1000*interval_duration_ms(interval)
            for a in range(first,end,step):
                yield symbol,a,min(a+step,end)


def collect_derivatives(*,home,plan,days,kind,client=None,wall_ms,budget=MAX_GETS):
    """Network only on explicit bounded client; otherwise read existing pages."""
    plan=decode_plan(plan.encode())
    started=wall_ms()
    if (type(budget) is not int or not 1<=budget<=MAX_GETS or kind not in KINDS
            or (client is not None and
                (type(client) is not BoundedBybitPublicClient
                 or not client.allow_derivatives_history_research or client.requests_attempted!=0
                 or not plan.observed_at_ms<=started<plan.observed_at_ms+MAX_PLAN_AGE_MS
                 or (client.transport is None)!=(plan.source_mode=="public_rest_observed_unverified")))):
        raise DataValidationError("D536 invalid collection scope")
    counts={"planned_windows":0,"query_complete_windows":0,"missing_windows":0,
            "mark_gap_windows":0,"funding_saturated_pages":0,"saved_rows":0,"expected_mark_rows":0}
    def visit(symbol,start,end):
        rows=_page(home,plan,kind,symbol,start,end,client=client,
                   wall_ms=wall_ms,budget=budget,started=started)
        if rows is None:
            counts["missing_windows"]+=1
            return False
        if kind=="funding" and len(rows)==200:
            # Do not assume an undocumented ordering or use the truncated
            # parent records as settlements. Disjoint half-open child windows.
            counts["funding_saturated_pages"]+=1
            mid=(start+end)//2
            if mid==start or mid==end:
                raise DataValidationError("D536 saturated indivisible funding window")
            left=visit(symbol,start,mid)
            right=visit(symbol,mid,end)
            return left and right
        counts["saved_rows"]+=len(rows)
        if kind!="funding" and len(rows)!=(end-start)//interval_duration_ms(kind[5:]):
            counts["mark_gap_windows"]+=1
            return False
        return True
    for symbol,start,end in jobs(plan,days,kind):
        counts["planned_windows"]+=1
        if kind!="funding":
            counts["expected_mark_rows"]+=(end-start)//interval_duration_ms(kind[5:])
        counts["query_complete_windows"]+=int(visit(symbol,start,end))
    return {"schema_version":"d536-derivatives-coverage-v1","dataset":kind,"requested_days":days,
            "planned_days":min(730,((days+29)//30)*30),"plan_sha256":plan.digest,
            "status":"query_coverage_complete" if counts["planned_windows"]>0 and
            counts["planned_windows"]==counts["query_complete_windows"] else "query_coverage_partial",
            **counts,"public_gets":0 if client is None else client.requests_attempted,
            "funding_calendar_verified":False,"historical_risk_tiers_verified":False,
            "liquidation_verified":False,"orders_sent":False,"j1_touched":False}


def trade_coverage(home,plan,days,interval):
    """No GET; count validated D528 rows for exact requested dates, not shards."""
    if type(days) is not int or not 1<=days<=730 or interval not in ("1h","5m"):
        raise DataValidationError("D536 explicit trade history range")
    plan=decode_plan(plan.encode())
    dt=interval_duration_ms(interval)
    start=plan.cutoff_ms-days*DAY
    expected=saved=0
    for symbol,launch in plan.members:
        first=max(start,((launch+dt-1)//dt)*dt)
        if first>=plan.cutoff_ms:
            continue
        expected+=(plan.cutoff_ms-first)//dt
        saved+=len(read_window(home,plan,symbol,interval,first,plan.cutoff_ms,allow_gaps=True))
    return {"dataset":"trade-"+interval,"requested_days":days,"expected_candles":expected,
            "saved_candles":saved,"missing_candles":expected-saved,"public_gets":0}


@dataclass(frozen=True)
class FundingExposure:
    """Conditional exposure at one observed rate time, using mark bounds.

    Quantity bounds allow an uncertain partial-exit ordering within a bar.
    A rate is dimensionless (0.0001 = 0.01%), not bps or percent.
    """
    at_ms:int
    rate:Decimal
    quantity_min:Decimal
    quantity_max:Decimal
    mark_low:Decimal
    mark_high:Decimal

    def __post_init__(self):
        if type(self.at_ms) is not int or not 0<self.at_ms<=4_000_000_000_000:
            raise DataValidationError("D536 invalid funding exposure time")
        for x in (self.rate,self.quantity_min,self.quantity_max,self.mark_low,self.mark_high):
            if type(x) is not Decimal or not x.is_finite() or len(x.as_tuple().digits)>40 or not -24<=x.as_tuple().exponent<=24:
                raise DataValidationError("D536 invalid exact exposure values")
        if (abs(self.rate)>1 or not 0<=self.quantity_min<=self.quantity_max
                or not 0<self.mark_low<=self.mark_high):
            raise DataValidationError("D536 invalid funding exposure bounds")


def funding_cost_bounds(direction,events,*,expected_timestamps):
    """Positive=paid, negative=received. No missing calendar event becomes zero.

    Caller must provide an independently established settlement calendar;
    query coverage alone cannot supply this proof. Bounds are conditional,
    not an account settlement or a liquidation model.
    """
    if (type(direction) is not ResearchDirection or type(events) is not tuple
            or type(expected_timestamps) is not tuple or len(events)>180*24*60
            or any(type(e) is not FundingExposure for e in events)
            or any(type(t) is not int or not 0<t<=4_000_000_000_000 for t in expected_timestamps)
            or tuple(e.at_ms for e in events)!=expected_timestamps
            or any(a>=b for a,b in zip(expected_timestamps,expected_timestamps[1:]))):
        raise DataValidationError("D536 explicit complete funding event sequence required")
    with localcontext(_CTX):
        sign=Decimal(1) if direction is ResearchDirection.LONG else Decimal(-1)
        low=high=Decimal(0)
        for e in events:
            a=sign*e.rate*e.quantity_min*e.mark_low
            b=sign*e.rate*e.quantity_max*e.mark_high
            low+=min(a,b)
            high+=max(a,b)
        return low,high
