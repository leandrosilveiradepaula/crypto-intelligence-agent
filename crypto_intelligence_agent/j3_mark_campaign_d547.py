"""D547: bounded mark-5m acquisition using D536's existing immutable pages."""
from __future__ import annotations

from .j3_history_campaign_d546 import (
    MAX_BATCHES, GETS_PER_BATCH, COOLDOWN_SECONDS, MAX_CAMPAIGN_SECONDS,
    MIN_BATCH_SECONDS, PAGE_LIMIT,
)
from .market_data import DataValidationError


def mark_counts(d, digest):
    if (type(d) is not dict or d.get("schema_version")!="d536-derivatives-coverage-v1"
            or d.get("dataset")!="mark-5m" or d.get("requested_days")!=365
            or d.get("planned_days")!=390 or d.get("plan_sha256")!=digest
            or any(d.get(k) is not False for k in
                   ("orders_sent","j1_touched","funding_calendar_verified",
                    "historical_risk_tiers_verified","liquidation_verified"))):
        raise DataValidationError("D547 invalid mark coverage identity")
    total,complete,missing,gaps,saved,expected,gets=(d.get(k) for k in
        ("planned_windows","query_complete_windows","missing_windows",
         "mark_gap_windows","saved_rows","expected_mark_rows","public_gets"))
    if (any(type(x) is not int or x<0 for x in
            (total,complete,missing,gaps,saved,expected,gets))
            or not total or complete+missing+gaps!=total
            or not 0<expected<=PAGE_LIMIT*total or saved>expected
            or not 0<=gets<=GETS_PER_BATCH
            or d.get("status")!=("query_coverage_complete" if complete==total
                                 else "query_coverage_partial")
            or (complete==total)!=(saved==expected)):
        raise DataValidationError("D547 inconsistent mark coverage")
    return total,complete,missing,gaps,saved,expected,gets


def run_mark_campaign(*,digest,baseline,collect,emit,clock,sleep,
                      max_batches=MAX_BATCHES,wall_seconds=MAX_CAMPAIGN_SECONDS):
    if (type(digest) is not str or len(digest)!=64
            or any(c not in "0123456789abcdef" for c in digest)
            or type(max_batches) is not int or not 1<=max_batches<=MAX_BATCHES
            or type(wall_seconds) is not int
            or not MIN_BATCH_SECONDS<=wall_seconds<=MAX_CAMPAIGN_SECONDS):
        raise DataValidationError("D547 invalid campaign limits")
    total,complete,missing,gaps,saved,expected,gets=mark_counts(baseline,digest)
    if gets:
        raise DataValidationError("D547 baseline must be offline")
    initial=saved
    started=clock()
    batches=used=0

    def finish(status,reason):
        return {"kind":"d547_mark_final","status":status,"reason":reason,
                "dataset":"mark-5m","requested_days":365,"planned_days":390,
                "plan_sha256":digest,"saved_rows":saved,"expected_rows":expected,
                "missing_windows":missing,"gap_windows":gaps,
                "new_rows_confirmed":saved-initial,"completed_batches":batches,
                "completed_batch_gets":used,"automatic_retry":False,
                "orders_sent":False,"j1_touched":False,"profile_modified":False}

    if gaps:
        return finish("campaign_stopped","existing_provider_gap")
    if not missing:
        return finish("campaign_complete","already_complete")
    while batches<max_batches:
        if clock()-started+MIN_BATCH_SECONDS>wall_seconds:
            return finish("campaign_budget_reached","wall_budget")
        t,c,m,g,n,e,k=mark_counts(collect(),digest)
        if (t!=total or e!=expected or c<complete or g<gaps
                or n<saved or m>missing or missing-m!=k
                or n-saved>PAGE_LIMIT*k):
            raise DataValidationError("D547 inconsistent mark batch progress")
        gain=n-saved
        complete,missing,gaps,saved=c,m,g,n
        batches+=1
        used+=k
        emit({**finish("batch_completed","observed"),"kind":"d547_mark_batch",
              "new_rows_in_batch":gain,"public_gets":k})
        if gaps:
            return finish("campaign_stopped","provider_gap")
        if not missing:
            return finish("campaign_complete","all_windows_complete")
        if not k or not gain:
            return finish("campaign_stopped","no_progress")
        if batches==max_batches:
            return finish("campaign_budget_reached","batch_budget")
        if clock()-started+COOLDOWN_SECONDS+MIN_BATCH_SECONDS>wall_seconds:
            return finish("campaign_budget_reached","wall_budget")
        sleep(COOLDOWN_SECONDS)
    raise AssertionError("D547 unreachable")


def replay_readiness(*,digest,trade,mark,funding):
    _,_,missing,gaps,saved,expected,gets=mark_counts(mark,digest)
    if gets or type(trade) is not dict or type(funding) is not dict:
        raise DataValidationError("D547 readiness requires offline coverage")
    if (trade.get("dataset")!="trade-5m" or trade.get("requested_days")!=365
            or trade.get("public_gets")!=0
            or any(type(trade.get(k)) is not int or trade[k]<0 for k in
                   ("saved_candles","missing_candles","expected_candles"))
            or trade["saved_candles"]+trade["missing_candles"]!=trade["expected_candles"]
            or not trade["expected_candles"]):
        raise DataValidationError("D547 invalid trade coverage")
    if (funding.get("schema_version")!="d536-derivatives-coverage-v1"
            or funding.get("dataset")!="funding" or funding.get("requested_days")!=365
            or funding.get("plan_sha256")!=digest or funding.get("public_gets")!=0
            or funding.get("funding_calendar_verified") is not False
            or type(funding.get("planned_windows")) is not int
            or type(funding.get("query_complete_windows")) is not int
            or not 0<=funding["query_complete_windows"]<=funding["planned_windows"]
            or funding["planned_windows"]<=0):
        raise DataValidationError("D547 invalid funding coverage")
    ready=(trade["missing_candles"]==0 and missing==0 and saved>0
           and funding["query_complete_windows"]==funding["planned_windows"]
           and funding.get("status")=="query_coverage_complete")
    return {"kind":"d547_fine_replay_preflight","status":"ready" if ready else "incomplete",
            "trade_saved":trade["saved_candles"],"trade_expected":trade["expected_candles"],
            "mark_saved":saved,"mark_expected_390d":expected,"mark_missing_windows":missing,
            "mark_gap_windows":gaps,"funding_query_complete":funding["query_complete_windows"],
            "funding_planned":funding["planned_windows"],"plan_sha256":digest,
            "orders_sent":False,"liquidation_verified":False,"oos_verified":False}
