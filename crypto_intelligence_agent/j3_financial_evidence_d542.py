"""D542: interpret D529 conditional financial reports without replaying data.

Compare exits only on the same D529 strategy/horizon/stop and with full
observed-funding coverage of the complete trade paths in BOTH orderings.
Equal partial counts do not establish equal path membership. A report hash
is not proof of provenance, nor is this a portfolio or historical liquidation.
"""
from __future__ import annotations

from decimal import Context, Decimal, localcontext
from itertools import combinations
import re

from .j3_maintenance_stress_d538 import parse_maintenance_grid
from .j3_stress_attribution_d545 import decode_attribution
from .market_data import DataValidationError

ORDERS=("adverse_first","favorable_first")
MAX_SCENARIOS=3000
_CTX=Context(prec=128)
_ZERO=Decimal(0)
_NAME=re.compile(r"[a-z][a-z0-9_]{0,95}\Z")
_MONTH=re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])\Z")
_AMOUNT=re.compile(r"-?[0-9]{1,70}(?:\.[0-9]{1,54})?\Z")


def _require(ok):
    if not ok:
        raise DataValidationError("D542 inconsistent or unsupported research report")


def _count(x):
    _require(type(x) is int and 0<=x<=100_000_000)
    return x


def _name(x):
    _require(type(x) is str and _NAME.fullmatch(x) is not None)
    return x


def _amount(x,available):
    if not available:
        _require(x is None)
        return None
    _require(type(x) is str and _AMOUNT.fullmatch(x) is not None)
    return Decimal(x)


def _money(x):
    return None if x is None else format(x,"f")


def _range(values):
    return [_money(min(x[0] for x in values)),_money(max(x[1] for x in values))]


def _paths(row):
    n=_count(row["complete_path_count"])
    candidate=_count(row["candidate_count"])
    missing=_count(row["missing_path_count"])
    _require(n+missing==candidate)
    return n,candidate,missing


def _order(row,n,grid,open_mark):
    matched=_count(row["funding_matched_path_count"])
    unavailable=_count(row["funding_unavailable_path_count"])
    events=_count(row["funding_observed_event_count"])
    no_events=_count(row["funding_no_observed_events_path_count"])
    positive_low=_count(row["funding_matched_positive_low_count"])
    positive_high=_count(row["funding_matched_positive_high_count"])
    _require(matched+unavailable==n and no_events<=matched
             and events>=matched-no_events
             and positive_low<=positive_high<=matched)
    pre=_amount(row["conditional_before_funding_quote"],n)
    before=_amount(row["funding_matched_before_quote"],matched)
    cost_low=_amount(row["funding_observed_cost_low_quote"],matched)
    cost_high=_amount(row["funding_observed_cost_high_quote"],matched)
    low=_amount(row["funding_matched_net_low_quote"],matched)
    high=_amount(row["funding_matched_net_high_quote"],matched)
    if matched:
        _require(cost_low<=cost_high and low==before-cost_high
                 and high==before-cost_low and low<=high)
        if matched==n:
            _require(before==pre)
    elif not matched:
        _require(events==0)
    stress={}
    previous=-1
    evaluated=None
    for bps in grid:
        p=f"stress_{bps}bps_"
        a=_count(row[p+"evaluated_count"])
        u=_count(row[p+"unavailable_count"])
        b=_count(row[p+"possible_breach_count"])
        good=_count(row[p+"no_observed_breach_count"])
        wins=_count(row[p+"positive_before_funding_with_possible_breach_count"])
        checked=_count(row[p+"checked_bars"])
        _require(a+u==n and b+good==a and wins<=b and a<=matched
                 and checked>=a and previous<=b
                 and (evaluated is None or evaluated==a))
        previous=b
        evaluated=a
        stress[str(bps)]={"evaluated":a,"unavailable":u,
                          "possible_breaches":b,
                          "positive_pre_funding_with_possible_breach":wins}
        attribution=decode_attribution(row,p)
        if attribution is not None:
            stress[str(bps)]["conditional_attribution"]=attribution
    opened=_count(row["residual_at_horizon_count"])
    _require(opened<=n)
    result={"funding_matched_paths":matched,"funding_unavailable_paths":unavailable,
            "observed_funding_events":events,"paths_without_observed_events":no_events,
            "pre_funding_all_paths_quote":_money(pre),
            "pre_funding_matched_quote":_money(before),
            "observed_funding_cost_interval_quote":[_money(cost_low),_money(cost_high)],
            "conditional_net_interval_quote":[_money(low),_money(high)],
            "conditional_positive_count_interval":[positive_low,positive_high],
            "open_at_horizon":opened,"stress":stress}
    if open_mark:
        realized=_amount(row["realized_after_incurred_cost_quote"],n)
        open_net=_amount(row["open_after_assumed_exit_cost_quote"],n)
        unrealized=_amount(row["unrealized_gross_quote"],n)
        _require(_count(row["fully_exited_count"])+opened==n
                 and (not n or realized+open_net==pre))
        result["pre_funding_realized_after_cost_quote"]=_money(realized)
        result["pre_funding_open_after_assumed_exit_cost_quote"]=_money(open_net)
        result["pre_funding_unrealized_gross_quote"]=_money(unrealized)
    return result,(low,high)


def _monthly(row,n,candidate,grid,open_mark):
    months=row["by_month"]
    _require(type(months) is dict and len(months)<=26
             and all(type(m) is str and _MONTH.fullmatch(m) for m in months))
    covered=0
    seen_candidates=0
    eligible_months=positive=negative=uncertain=unavailable=0
    signature=[]
    for month,item in sorted(months.items()):
        count,cand,_=_paths(item)
        covered+=count
        seen_candidates+=cand
        signature.append((month,count,cand))
        if not count:
            continue
        eligible_months+=1
        rows=[_order(item[order],count,grid,open_mark) for order in ORDERS]
        if any(x[0]["funding_matched_paths"]!=count for x in rows):
            unavailable+=1
            continue
        lo=min(x[1][0] for x in rows)
        hi=max(x[1][1] for x in rows)
        if lo>0:
            positive+=1
        elif hi<0:
            negative+=1
        else:
            uncertain+=1
    _require(covered==n and seen_candidates==candidate)
    return {"entry_months_with_complete_paths":eligible_months,
            "entry_months_fully_matched_both_orders":eligible_months-unavailable,
            "positive_lower_bound_months":positive,
            "negative_upper_bound_months":negative,
            "mixed_or_zero_bound_months":uncertain,
            "incomplete_funding_months":unavailable},tuple(signature)


def summarize_financial_replay(report):
    """Aggregate-only conditional evidence, no winners or automatic tuning.

    The two reference orders are alternatives, not all admissible paths.
    Paired comparisons assume an intact report produced by the D529 engine.
    Missing trade paths remain excluded even when all funding is matched.
    """
    try:
        with localcontext(_CTX):
            return _summarize(report)
    except (KeyError,TypeError,ValueError,ArithmeticError,AttributeError) as exc:
        raise DataValidationError("D542 malformed financial research report") from exc


def _summarize(report):
    _require(type(report) is dict
             and report.get("schema_version")=="d529-retrospective-cohort-replay-v1"
             and report.get("status")=="exploratory_replay_completed"
             and report.get("partition")=="development"
             and report.get("observed_funding") is True
             and report.get("funding_missing_queries_not_zero") is True
             and report.get("leverage_at_intent")==50
             and report.get("resolution") in ("1h","5m")
             and report.get("all_horizons_share_same_decision_grid") is True
             and report.get("partition_crossing_paths_excluded") is True
             and report.get("public_gets")==0
             and all(report.get(k) is False for k in (
                 "orders_sent","profile_modified","portfolio_simulated",
                 "winner_selected","out_of_sample_results_validated",
                 "funding_calendar_verified","funding_settlement_verified",
                 "liquidation_verified")))
    grid=parse_maintenance_grid(report.get("maintenance_stress_bps",()))
    if grid:
        _require(report.get("maintenance_stress_is_not_venue_liquidation") is True
                 and report.get("maintenance_stress_rewrites_pnl") is False
                 and report.get("historical_risk_tiers_verified") is False)
    open_mark=report.get("separate_open_mark",False)
    _require(type(open_mark) is bool)
    days=_count(report["requested_days"])
    _require(30<=days<=730)
    count=_count(report["scenario_count"])
    scenarios=report["scenarios"]
    _require(type(scenarios) is list and 1<=len(scenarios)<=count<=MAX_SCENARIOS)
    horizons=report["horizons_hours"]
    stops=report["stop_grid_bps"]
    _require(type(horizons) is list and 1<=len(horizons)<=6
             and all(type(h) is int and 1<=h<=4320 for h in horizons)
             and horizons==sorted(set(horizons))
             and type(stops) is list and 1<=len(stops)<=8
             and all(type(s) is int and 1<=s<=1000 for s in stops)
             and stops==sorted(set(stops)))
    groups={}
    entries=[]
    for scenario in scenarios:
        h,stop=scenario["horizon_hours"],scenario["stop_bps"]
        _require(type(h) is int and h in horizons and type(stop) is int and stop in stops)
        variant=_name(scenario.get("exit_variant","owner_baseline"))
        slots=_count(scenario["common_covered_symbol_hours"])
        rows=scenario["rows"]
        _require(type(rows) is list and bool(rows))
        for row in rows:
            name=_name(row["name"])
            n,candidate,missing=_paths(row)
            _require(n<=slots)
            direction=row["directions"]
            direction_signature=tuple(_count(direction[k]) for k in ("LONG","SHORT","covered_LONG","covered_SHORT"))
            _require(sum(direction_signature[:2])==candidate
                     and sum(direction_signature[2:])==n)
            metrics={}
            bounds={}
            for order in ORDERS:
                metrics[order],bounds[order]=_order(row[order],n,grid,open_mark)
            full=n>0 and all(metrics[o]["funding_matched_paths"]==n for o in ORDERS)
            months,month_signature=_monthly(row,n,candidate,grid,open_mark)
            entry={"strategy":name,"horizon_hours":h,"stop_bps":stop,"exit_variant":variant,
                   "candidate_count":candidate,"complete_trade_paths":n,"missing_trade_paths":missing,
                   "full_funding_match_both_orders":full,
                   "full_match_conditional_net_range_quote":_range(tuple(bounds.values())) if full else None,
                   "orders":metrics,"monthly_entry_cohorts":months}
            if report.get("exposure_diagnostics") is True:
                diagnostics=row["exposure_diagnostics"]
                entry["concentration_pre_funding"]={}
                for order in ORDERS:
                    diag=diagnostics[order]
                    _require(_count(diag["path_count"])==n)
                    entry["concentration_pre_funding"][order]={
                        "peak_concurrent_paths":_count(diag["peak_concurrent_paths"]),
                        "peak_concurrent_assets":_count(diag["peak_concurrent_assets"]),
                        "top_5_positive_path_share_percent":_money(_amount(
                            diag["top_5_positive_path_share_percent"],
                            diag["top_5_positive_path_share_percent"] is not None)),
                        "net_without_top_5_positive_paths_quote":_money(_amount(
                            diag["pre_funding_net_without_top_5_positive_paths_quote"],True))}
            group=groups.setdefault((name,h,stop),{})
            _require(variant not in group)
            group[variant]=(entry,bounds,(n,candidate,missing,slots,direction_signature,month_signature))
            entries.append(entry)
            _require(len(entries)<=count)
    _require(len(entries)==count)
    comparisons=[]
    for (name,h,stop),group in sorted(groups.items()):
        # All exits in a D529 scenario use the same accepted signal path.
        # Divergent signatures mean the report is inconsistent; never infer
        # membership merely from the number of partially matched paths.
        signatures={x[2] for x in group.values()}
        _require(len(signatures)==1)
        for left,right in combinations(sorted(group),2):
            a,ab,_=group[left]
            b,bb,_=group[right]
            pair={"strategy":name,"horizon_hours":h,"stop_bps":stop,
                  "left_exit":left,"right_exit":right,
                  "complete_trade_paths":a["complete_trade_paths"]}
            if not (a["full_funding_match_both_orders"] and b["full_funding_match_both_orders"]):
                pair.update({"status":"insufficient_paired_funding_evidence",
                             "left_minus_right_quote":None})
            else:
                # Compare consistent ordering against itself; no crossing
                # adverse-first from one side with favorable-first from the other.
                differences=tuple((ab[o][0]-bb[o][1],ab[o][1]-bb[o][0]) for o in ORDERS)
                pair.update({"status":"full_match_conditional_comparison",
                             "left_minus_right_quote":_range(differences)})
            comparisons.append(pair)
    entries.sort(key=lambda x:(x["horizon_hours"],x["strategy"],x["stop_bps"],x["exit_variant"]))
    return {"schema_version":"d542-financial-evidence-v1","status":"conditional_report_summarized",
            "requested_days":days,"resolution":report["resolution"],"scenario_count":count,
            "maintenance_stress_bps":list(grid),
            "fully_matched_scenario_count":sum(x["full_funding_match_both_orders"] for x in entries),
            "paired_comparison_count":sum(x["status"]=="full_match_conditional_comparison" for x in comparisons),
            "comparison_method":"same_report_same_strategy_horizon_stop_full_funding_match_both_orders",
            "monthly_cohort_method":"grouped_by_entry_month_not_realized_cashflow_month",
            "bounds_cover_all_intrabar_paths":False,"funding_calendar_verified":False,
            "liquidation_verified":False,"portfolio_simulated":False,
            "winner_selected":False,"out_of_sample_results_validated":False,
            "orders_sent":False,"rows":entries,"paired_exit_comparisons":comparisons}
