"""D543: exact requested-window backfill from actual D528 stored rows.

Do not extend a legacy checkpoint across a gap or change its lineage. Each
validated missing page is atomic in the same D528 shard, independently of
legacy prefix checkpoints. After opting in, use this row-based collector for
subsequent acquisitions; D528 legacy mode can otherwise request saved rows.
The D529 reader still validates every candle and splits gaps as before.
"""
from __future__ import annotations

import shutil
import sqlite3

from .backfill import _validate_exact_page
from .bybit_public_j1_transport import BoundedBybitPublicClient
from .j3_long_history_d528 import (
    DAY, MAX_PLAN_AGE_MS, MAX_BATCH_MS, MIN_FREE_BYTES, PAGE, EXCHANGE, MARKET,
    QUALITY, HistorySource, BatchLimit, ProviderGap, decode_plan, windows,
    shard_path, _store,
)
from .market_data import DataValidationError, interval_duration_ms
from .storage import _candle_values

MAX_EXACT_GETS=50


def exact_windows(plan,days,interval):
    """Keep the original shard file identity, clip only requested rows."""
    jobs=tuple(windows(plan,days,interval))
    lower=plan.cutoff_ms-days*DAY
    return tuple((start,end,symbol,max(first,lower))
                 for start,end,symbol,first in jobs if max(first,lower)<end)


def missing_pages(rows,*,symbol,interval,start,end):
    """No request may include a stored row, even with disjoint saved ranges."""
    dt=interval_duration_ms(interval)
    if type(start) is not int or type(end) is not int or start>=end or start%dt or end%dt:
        raise DataValidationError("D543 invalid exact window")
    cursor=start
    pages=[]
    def add(a,b):
        for t in range(a,b,PAGE*dt):
            pages.append((t,min(t+PAGE*dt,b)))
    for c in rows:
        if ((c.exchange,c.market,c.symbol,c.interval,c.quality)!=(EXCHANGE,MARKET,symbol,interval,QUALITY)
                or c.open_time_ms<cursor or c.open_time_ms>=end
                or c.open_time_ms%dt or c.close_time_ms!=c.open_time_ms+dt-1):
            raise DataValidationError("D543 invalid stored row or provenance")
        add(cursor,c.open_time_ms)
        cursor=c.open_time_ms+dt
    add(cursor,end)
    return tuple(pages)


def _commit_missing_page(store,rows,*,symbol,interval,start,end):
    """Research-only INSERT; do not replace candle or legacy checkpoint."""
    dt=interval_duration_ms(interval)
    _validate_exact_page(rows,EXCHANGE,MARKET,symbol,interval,start,end,dt)
    if any(c.quality!=QUALITY for c in rows):
        raise DataValidationError("D543 wrong research provenance")
    try:
        with store._transaction() as db:
            # A competing or inconsistent page must fail closed; no IGNORE or REPLACE.
            db.executemany("INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (_candle_values(c) for c in rows))
    except sqlite3.IntegrityError as exc:
        raise DataValidationError("D543 missing page conflicts with storage") from exc


def collect_exact_batch(*,home,plan,days,interval,client,wall_ms,
                        max_gets=MAX_EXACT_GETS,oldest_first=False):
    plan=decode_plan(plan.encode())
    started=wall_ms()
    if (type(oldest_first) is not bool or type(max_gets) is not int
            or not 1<=max_gets<=MAX_EXACT_GETS
            or not plan.observed_at_ms<=started<plan.observed_at_ms+MAX_PLAN_AGE_MS
            or type(client) is not BoundedBybitPublicClient or not client.allow_long_history_research
            or client.requests_attempted!=0
            or (client.transport is None)!=(plan.source_mode=="public_rest_observed_unverified")):
        raise DataValidationError("D543 invalid batch scope")
    jobs=exact_windows(plan,days,interval)
    if oldest_first:
        jobs=tuple(sorted(jobs,key=lambda x:(x[0],x[2])))
    source=HistorySource(plan,client,wall_ms,started,max_gets,home)
    dt=interval_duration_ms(interval)
    stats={s:{"expected":0,"saved":0,"complete_shards":0,"gap_shards":0}
           for s,_ in plan.members}
    limited=False
    last=None
    store=None
    gaps=[]
    new_rows=0
    for shard_start,end,symbol,first in jobs:
        row=stats[symbol]
        expected=(end-first)//dt
        row["expected"]+=expected
        path=shard_path(home,plan,shard_start,interval)
        if path!=last:
            last=path
            store=None
            if path.exists() or path.is_symlink():
                store=_store(path)
            elif (not limited and source.gets<max_gets
                  and wall_ms()<started+MAX_BATCH_MS
                  and shutil.disk_usage(home).free>=MIN_FREE_BYTES):
                store=_store(path)
            else:
                limited=True
        if store is None:
            continue
        saved=store.candles(exchange=EXCHANGE,market=MARKET,symbol=symbol,interval=interval,
                            start_open_ms=first,end_open_ms=end)
        pages=missing_pages(saved,symbol=symbol,interval=interval,start=first,end=end)
        n=len(saved)
        had_gap=False
        if not limited:
            for a,b in pages:
                try:
                    fetched=source.closed_candles(symbol,interval,observed_at_ms=started,
                                start_time_ms=a,end_time_ms=b-1,limit=PAGE)
                except BatchLimit:
                    limited=True
                    break
                except ProviderGap:
                    # No retry of this failed page; other independent pages may progress.
                    had_gap=True
                    continue
                _commit_missing_page(store,fetched,symbol=symbol,interval=interval,start=a,end=b)
                n+=len(fetched)
                new_rows+=len(fetched)
        row["saved"]+=n
        row["complete_shards"]+=int(n==expected)
        if had_gap:
            row["gap_shards"]+=1
            gaps.append({"symbol":symbol,"shard_start_ms":shard_start,"shard_end_ms":end})
    expected=sum(x["expected"] for x in stats.values())
    saved=sum(x["saved"] for x in stats.values())
    complete=sum(x["complete_shards"] for x in stats.values())
    return {"schema_version":"d543-exact-history-coverage-v1",
            "status":"coverage_complete" if complete==len(jobs) and expected>0 else "coverage_partial",
            "plan_sha256":plan.digest,"requested_days":days,"planned_days":days,
            "cutoff_ms":plan.cutoff_ms,"interval":interval,"cohort_size":len(plan.members),
            "expected_candles_after_launch":expected,"saved_candles":saved,
            "missing_candles":expected-saved,"new_candles_committed":new_rows,
            "complete_member_shards":complete,"expected_member_shards":len(jobs),
            "public_gets":source.gets,"batch_limit_reached":limited,
            "by_symbol":stats,"gap_member_shards":gaps,
            "collection_order":"oldest_first" if oldest_first else "newest_first",
            "legacy_checkpoint_modified":False,"actual_rows_determine_missing_pages":True,
            "cohort_origin":"current_D451_provisional_survivors",
            "historical_marketwide_top50_verified":False,
            "retrospective_not_contemporaneous":True,"orders_sent":False,
            "profile_modified":False,"j1_touched":False}
