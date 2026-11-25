"""D529: continuous causal research on D528 retrospective REST history.

Never fabricate contemporary D461 memberships. Missing bars reset indicators.
Research only; trades are independent conditional paths, not a portfolio.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal, Context, localcontext
from hashlib import sha256

from .j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from .j2_observed_bybit_research import evaluate_observed_bybit_research, _RETROSPECTIVE_STATUS
from .j2_configurable_indicators_d513 import rsi_directions
from .j3_archived_strategy_comparison_d512 import _warmup
from .j3_combination_research_d520 import parse_matrix, parse_stop_grid
from .j3_intrahour_replay_d518 import refine_hourly_path, FIVE_MS
from .j3_long_history_d528 import DAY, HOUR_MS, MAX_DAYS, read_window, decode_plan, canonical
from .j3_observed_exit_scenarios_d517 import empty_replay_totals, accumulate_replay, summarize_replay
from .market_data import DataValidationError
from .j3_entry_research_d530 import EntryExperiment, parse_experiments, entry_events
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_margin_envelope import SyntheticMarginBasis

SCHEMA = "d529-retrospective-cohort-replay-v1"
DEFAULT_STOPS = (50,75,100,125,150,200,250)
DEFAULT_HORIZONS = (24,48,72)
_CTX = Context(prec=128)
_PARTS = ("development","validation","holdout")


def partitions(plan, days):
    if type(days) is not int or not 30 <= days <= MAX_DAYS:
        raise DataValidationError("D529 use 30..730 historical days")
    start = plan.cutoff_ms-days*DAY
    a = start+(days*60//100)*DAY
    b = start+(days*80//100)*DAY
    return dict(zip(_PARTS,((start,a),(a,b),(b,plan.cutoff_ms))))


def contiguous_runs(bars):
    start = 0
    for i in range(1,len(bars)):
        if bars[i].open_time_ms != bars[i-1].open_time_ms+HOUR_MS:
            yield bars[start:i]
            start = i
    if bars:
        yield bars[start:]


def bars_digest(bars):
    h=sha256()
    for b in bars:
        h.update(canonical([b.exchange,b.market,b.symbol,b.interval,b.open_time_ms,
            b.close_time_ms,str(b.open),str(b.high),str(b.low),str(b.close),
            str(b.base_volume),str(b.quote_volume),b.quality])+b"\n")
    return h.hexdigest()


def btc_returns(bars):
    out={}
    with localcontext(_CTX):
        for run in contiguous_runs(bars):
            for i in range(23,len(run)):
                out[run[i].close_time_ms+1]=run[i].close/run[i-23].open-1
    return out


def make_policies(owner,matrix_raw,entry_experiments_raw=None):
    periods,profiles,labels=parse_matrix(matrix_raw)
    base=replace(owner.research,entry_mode="breakout",indicators=None)
    cross=replace(base,entry_mode="ema_cross",ema_cross_periods=periods)
    settings={"breakout":(base,Decimal(0),None),"ema_cross":(cross,Decimal(0),None)}
    warmup=_warmup(base,periods)
    for item in profiles:
        name,selection,threshold=item[:3]
        veto=item[3] if len(item)==4 else None
        if selection is not None and selection.rsi is not None and selection.rsi.enabled:
            raise DataValidationError("D529 RSI is confirmation only, not a trigger")
        cfg=base if selection is None else replace(base,entry_mode="indicator_combo",indicators=selection)
        settings[name]=(cfg,threshold,veto)
        if selection is not None:
            warmup=max(warmup,selection.minimum_closed_bars(cfg.features.quote_volume_period))
        if veto is not None:
            warmup=max(warmup,veto.period+2)
    if entry_experiments_raw is not None:
        for name,label,cfg,threshold,veto in parse_experiments(entry_experiments_raw):
            if name in settings:
                raise DataValidationError("D530 experiment name collides with base matrix")
            settings[name]=(cfg,threshold,veto)
            labels[name]=label
            warmup=max(warmup,cfg.warmup,veto.period+2 if veto is not None else 0)
    return settings,labels,warmup


def _add(dst,src):
    with localcontext(_CTX):
        for k,v in src.items():
            if isinstance(v,dict):
                for n,value in v.items():
                    dst[k][n]+=value
            else:
                dst[k]+=v


def _regime(ret):
    return "BTC_up" if ret>Decimal(".01") else "BTC_down" if ret<Decimal("-.01") else "BTC_sideways"


def run_long_replay(*,home,plan,owner_policy,matrix_raw,days=90,
                    partition="development",horizons=DEFAULT_HORIZONS,
                    stops=DEFAULT_STOPS,resolution="1h",
                    confirm_frozen_hypotheses=False,progress=None,
                    entry_experiments_raw=None):
    plan=decode_plan(plan.encode())
    if (partition not in _PARTS or type(confirm_frozen_hypotheses) is not bool
            or (partition=="holdout" and not confirm_frozen_hypotheses)
            or resolution not in ("1h","5m") or type(horizons) not in (tuple,list)
            or not 1<=len(horizons)<=4
            or any(type(x) is not int or not 1<=x<=72 for x in horizons)
            or tuple(sorted(set(horizons)))!=tuple(horizons)
            or owner_policy.leverage.for_new_positions!=50):
        raise DataValidationError("D529 explicit partition, resolution, ordered horizons and 50x required")
    grid=parse_stop_grid(stops)
    if not grid:
        raise DataValidationError("D529 explicit stop grid required")
    horizons=tuple(horizons)
    splits=partitions(plan,days)
    base_start=splits["development"][0]
    start,end=splits[partition]
    last_decision=end-max(horizons)*HOUR_MS
    settings,labels,warmup=make_policies(owner_policy,matrix_raw,entry_experiments_raw)
    notional=owner_policy.margin_quote*Decimal(50)
    margin=SyntheticMarginBasis(owner_policy.margin_quote,50,notional,"SYNTHETIC_USDT")
    exits={stop:replace(owner_policy.exits,stop_distance_bps=Decimal(stop)) for stop in grid}
    btc=read_window(home,plan,"BTCUSDT","1h",base_start,end,allow_gaps=True)
    manifest={"BTCUSDT":{"1h":{"count":len(btc),"sha256":bars_digest(btc)}}}
    market=btc_returns(btc)
    totals={}
    veto_counts={}
    directions={}
    expected=eligible=0
    covered={h:0 for h in horizons}
    monthly_coverage={}
    def record(key,one):
        if key not in totals:
            totals[key]=empty_replay_totals()
        _add(totals[key],one)
    for symbol,launch in plan.members:
        if symbol=="BTCUSDT":
            continue
        launch_open=((launch+HOUR_MS-1)//HOUR_MS)*HOUR_MS
        first_decision=max(start,max(base_start,launch_open)+warmup*HOUR_MS)
        expected+=max(0,(last_decision-first_decision)//HOUR_MS+1)
        hourly=read_window(home,plan,symbol,"1h",base_start,end,allow_gaps=True)
        manifest[symbol]={"1h":{"count":len(hourly),"sha256":bars_digest(hourly)}}
        if any(b.open_time_ms<launch_open for b in hourly):
            raise DataValidationError("D529 prelaunch candle")
        fine_index={}
        good_hours=set()
        if resolution=="5m":
            finer=read_window(home,plan,symbol,"5m",start,end,allow_gaps=True)
            manifest[symbol]["5m"]={"count":len(finer),"sha256":bars_digest(finer)}
            fine_index={b.open_time_ms:b for b in finer}
            wrapped={symbol:fine_index}
            good_hours={b.open_time_ms for b in hourly if b.open_time_ms>=start
                        and refine_hourly_path((b,),wrapped) is not None}
        for run in contiguous_runs(hourly):
            if len(run)<warmup:
                continue
            series=BybitClosedResearchSeries(run,bars_digest(run),plan.digest,_RETROSPECTIVE_STATUS)
            by_config={}
            gates={}
            closes=tuple(b.close for b in run)
            for cfg,threshold,veto in settings.values():
                if cfg not in by_config:
                    if type(cfg) is EntryExperiment:
                        by_config[cfg]=entry_events(run,cfg)
                    else:
                        found=evaluate_observed_bybit_research(series,config=cfg,
                            decision_at_ms=run[-1].close_time_ms+1,close_safety_ms=1,
                            allow_rest_historical_research=True,all_retrospective_hypotheses=True)
                        by_config[cfg]={h.earliest_research_at_ms:h.side.value for h in found.hypotheses}
                if veto is not None and veto not in gates:
                    gates[veto]=rsi_directions(closes,veto)
            for i in range(warmup-1,len(run)):
                at=run[i].close_time_ms+1
                if not first_decision<=at<=last_decision or at not in market:
                    continue
                eligible+=1
                month=datetime.fromtimestamp(at//1000,timezone.utc).strftime("%Y-%m")
                groups=("all","month:"+month,"regime:"+_regime(market[at]))
                bucket=monthly_coverage.setdefault(month,{"eligible":0,"covered":{h:0 for h in horizons}})
                bucket["eligible"]+=1
                availability={}
                for h in horizons:
                    hp=run[i+1:i+1+h]
                    ok=len(hp)==h and (resolution=="1h" or
                        all(b.open_time_ms in good_hours for b in hp))
                    availability[h]=ok
                    covered[h]+=int(ok)
                    bucket["covered"][h]+=int(ok)
                with localcontext(_CTX):
                    relative=run[i].close/run[i-23].open-1-market[at]
                accepted={}
                for name,(cfg,threshold,veto) in settings.items():
                    side=by_config[cfg].get(at)
                    t=threshold/Decimal(10000)
                    if not (side=="LONG" and relative>t or side=="SHORT" and relative<-t):
                        continue
                    if veto is not None:
                        ok=gates[veto][i]==(1 if side=="LONG" else -1)
                        for h in horizons:
                            v=veto_counts.setdefault((h,name),{"checked":0,"rejected":0,
                                "covered_checked":0,"covered_rejected":0})
                            v["checked"]+=1
                            v["rejected"]+=int(not ok)
                            v["covered_checked"]+=int(availability[h])
                            v["covered_rejected"]+=int(availability[h] and not ok)
                        if not ok:
                            continue
                    accepted.setdefault(side,[]).append(name)
                    for h in horizons:
                        counts=directions.setdefault((h,name),{"LONG":0,"SHORT":0,
                            "covered_LONG":0,"covered_SHORT":0})
                        counts[side]+=1
                        counts["covered_"+side]+=int(availability[h])
                for h in horizons if accepted else ():
                    path=None
                    if availability[h]:
                        path=(run[i+1:i+1+h] if resolution=="1h" else
                              tuple(fine_index[t] for t in range(at,at+h*HOUR_MS,FIVE_MS)))
                    for side,names in accepted.items():
                        for stop,policy in exits.items():
                            one=empty_replay_totals()
                            accumulate_replay(one,path,direction=ResearchDirection(side),
                                decision_end_ms=at,now_ms=plan.observed_at_ms,margin=margin,
                                policy=policy,research_max_horizon_hours=72)
                            for name in names:
                                for group in groups:
                                    record((h,stop,name,group),one)
        if progress is not None:
            progress(len(manifest),len(plan.members))
    def summary(key,group):
        return summarize_replay(totals.get((*key,group),empty_replay_totals()),margin=margin)
    result=[]
    for h in horizons:
        for stop in grid:
            rows=[]
            for name,label in labels.items():
                key=(h,stop,name)
                row=summary(key,"all")
                counts=directions.get((h,name),{"LONG":0,"SHORT":0,"covered_LONG":0,"covered_SHORT":0})
                if (counts["LONG"]+counts["SHORT"]!=row["candidate_count"]
                        or counts["covered_LONG"]+counts["covered_SHORT"]!=row["complete_path_count"]):
                    raise DataValidationError("D529 inconsistent signal/path counts")
                v=veto_counts.get((h,name))
                if v is not None and (v["checked"]-v["rejected"]!=row["candidate_count"]
                    or v["covered_checked"]-v["covered_rejected"]!=row["complete_path_count"]):
                    raise DataValidationError("D529 RSI veto count mismatch")
                rows.append({"name":name,"label":label,**row,"directions":counts,"rsi_veto":v,
                    "by_month":{m:summary(key,"month:"+m) for m in sorted(monthly_coverage)},
                    "by_btc_regime":{g:summary(key,"regime:"+g)
                                     for g in ("BTC_up","BTC_down","BTC_sideways")}})
            result.append({"horizon_hours":h,"stop_bps":stop,"rows":rows,
                           "common_covered_symbol_hours":covered[h]})
    return {"schema_version":SCHEMA,
            "status":"exploratory_replay_completed" if any(covered.values()) else "no_complete_common_paths",
            "requested_days":days,"partition":partition,"partition_ranges_ms":splits,
            "decision_range_ms":[start,last_decision],"horizons_hours":list(horizons),
            "stop_grid_bps":list(grid),"scenario_count":len(labels)*len(horizons)*len(grid),
            "resolution":resolution,"leverage_at_intent":50,"warmup_hours":warmup,
            "expected_symbol_hours_after_launch":expected,"eligible_symbol_hours":eligible,
            "excluded_missing_warmup_or_btc":expected-eligible,
            "covered_symbol_hours_by_horizon":covered,"monthly_coverage":monthly_coverage,
            "manifest":{"plan_sha256":plan.digest,"matrix_sha256":sha256(matrix_raw).hexdigest(),
                        "data":manifest,
                        **({"entry_experiments_sha256":sha256(entry_experiments_raw).hexdigest()}
                           if entry_experiments_raw is not None else {})},
            "common_research_filters":asdict(owner_policy.research),
            "common_exit_policy":asdict(owner_policy.exits),
            "indicator_state":"continuous_causal_per_contiguous_run_not_D526_rolling_reseed",
            "cohort_origin":"current_D451_provisional_survivors",
            "historical_marketwide_top50_verified":False,
            "regime_definition":"descriptive BTC trailing 24h return above/below +/-1 percent",
            "entry_reference":"next_trade_bar_open_ex_post",
            "all_horizons_share_same_decision_grid":True,"partition_crossing_paths_excluded":True,
            "winner_selected":False,"out_of_sample_results_validated":False,
            "portfolio_simulated":False,"funding_settlement_verified":False,
            "liquidation_verified":False,"intrabar_path_verified":False,
            "stops_200_250_bps_counterfactual_at_50x":True,
            "public_gets":0,"profile_modified":False,"orders_sent":False,"scenarios":result}
