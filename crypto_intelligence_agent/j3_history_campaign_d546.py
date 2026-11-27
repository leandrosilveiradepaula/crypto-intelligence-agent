"""D546 bounded continuation of successful exact-history batches.

No network implementation or retry is added here. The caller supplies the
existing D543 collector, holds the owner lock for the entire campaign, and
emits compact aggregate progress. A failed, ambiguous or stalled batch ends
the campaign. Existing D543 transactions remain the durable resume point.
"""
from __future__ import annotations

from .market_data import DataValidationError

MAX_BATCHES=80
GETS_PER_BATCH=50
REQUEST_SPACING_SECONDS=10
COOLDOWN_SECONDS=300
MAX_CAMPAIGN_SECONDS=20*3600
# Reserve the D528 30-minute batch budget plus one minute before starting.
MIN_BATCH_SECONDS=31*60
PAGE_LIMIT=1000


def run_campaign(*,days,plan_sha256,cutoff_ms,baseline,expected,collect,emit,
                 clock,sleep,max_batches=MAX_BATCHES,
                 wall_seconds=MAX_CAMPAIGN_SECONDS):
    if (type(days) is not int or days not in (365,730)
            or type(plan_sha256) is not str or len(plan_sha256)!=64
            or any(c not in "0123456789abcdef" for c in plan_sha256)
            or type(cutoff_ms) is not int or cutoff_ms<=0
            or any(type(x) is not int for x in (baseline,expected,max_batches,wall_seconds))
            or not 0<=baseline<=expected or expected<=0
            or not 1<=max_batches<=MAX_BATCHES
            or not MIN_BATCH_SECONDS<=wall_seconds<=MAX_CAMPAIGN_SECONDS):
        raise DataValidationError("D546 invalid campaign scope")
    started=clock()
    saved=baseline
    gets=batches=0

    def finish(status,reason):
        return {"kind":"d546_campaign_final","status":status,"reason":reason,
                "dataset":"trade-5m","requested_days":days,
                "plan_sha256":plan_sha256,"cutoff_ms":cutoff_ms,
                "baseline_candles":baseline,"saved_candles":saved,
                "expected_candles":expected,"missing_candles":expected-saved,
                "new_candles_confirmed":saved-baseline,
                "completed_batches":batches,"completed_batch_gets":gets,
                "automatic_retry":False,"orders_sent":False,"j1_touched":False,
                "profile_modified":False}

    if saved==expected:
        return finish("campaign_complete","already_complete")
    for _ in range(max_batches):
        if clock()-started+MIN_BATCH_SECONDS>wall_seconds:
            return finish("campaign_budget_reached","wall_budget")
        d=collect()
        if (type(d) is not dict or d.get("schema_version")!="d543-exact-history-coverage-v1"
                or d.get("plan_sha256")!=plan_sha256 or d.get("cutoff_ms")!=cutoff_ms
                or d.get("requested_days")!=days or d.get("planned_days")!=days
                or d.get("interval")!="5m"
                or d.get("actual_rows_determine_missing_pages") is not True
                or any(d.get(k) is not False for k in
                       ("orders_sent","j1_touched","profile_modified","legacy_checkpoint_modified"))
                or d.get("status") not in ("coverage_complete","coverage_partial")
                or type(d.get("gap_member_shards")) is not list):
            raise DataValidationError("D546 invalid batch identity")
        n,missing,new,used,total=(d.get(k) for k in
            ("saved_candles","missing_candles","new_candles_committed",
             "public_gets","expected_candles_after_launch"))
        if (any(type(x) is not int for x in (n,missing,new,used,total))
                or total!=expected or not saved<=n<=expected
                or missing!=expected-n or new!=n-saved or not 0<=used<=GETS_PER_BATCH
                or not 0<=new<=PAGE_LIMIT*used
                or (d["status"]=="coverage_complete")!=(missing==0)):
            raise DataValidationError("D546 inconsistent batch progress")
        batches+=1
        gets+=used
        saved=n
        gaps=len(d["gap_member_shards"])
        emit({"kind":"d546_campaign_batch","status":d["status"],
              "batch":batches,"dataset":"trade-5m","requested_days":days,
              "plan_sha256":plan_sha256,"saved_candles":saved,
              "expected_candles":expected,"missing_candles":missing,
              "new_candles_committed":new,"public_gets":used,
              "gap_member_shard_count":gaps,
              "orders_sent":False,"j1_touched":False,"profile_modified":False})
        if gaps:
            return finish("campaign_stopped","provider_gap")
        if not missing:
            return finish("campaign_complete","all_expected_rows_present")
        if not new or not used:
            return finish("campaign_stopped","no_progress")
        if batches==max_batches:
            return finish("campaign_budget_reached","batch_budget")
        if clock()-started+COOLDOWN_SECONDS+MIN_BATCH_SECONDS>wall_seconds:
            return finish("campaign_budget_reached","wall_budget")
        sleep(COOLDOWN_SECONDS)
    raise AssertionError("D546 unreachable")
