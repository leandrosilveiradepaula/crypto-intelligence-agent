"""D544 bounded journal summary of a validated D542 report, no replay."""
from decimal import Context, Decimal, localcontext

from .market_data import DataValidationError

_CTX=Context(prec=128)
ORDERS=("adverse_first","favorable_first")
PAIRS={
    ("runner_25_tp4_10","runner_25_wide"):"no_additional_protection",
    ("runner_25_tp4_10_protect_tp3","runner_25_wide_protect_tp3"):"protect_after_tp3",
}
FOCUS="sq_w04_v15"


def compact_financial_summary(summary):
    """Only accept D542 output generated in-process from a validated report.

    A positive bound is conditional on observed funding and two reference
    orders. Descriptive top mean is not a winner selection. Stress remains
    independent; do not subtract hypothetical breaches as liquidation losses.
    """
    if (type(summary) is not dict
            or summary.get("schema_version")!="d542-financial-evidence-v1"
            or summary.get("status")!="conditional_report_summarized"
            or type(summary.get("source_report_sha256")) is not str
            or len(summary["source_report_sha256"])!=64
            or any(c not in "0123456789abcdef" for c in summary["source_report_sha256"])):
        raise DataValidationError("D544 validated D542 summary required")
    rows=summary["rows"]
    if not rows or len(rows)!=summary["scenario_count"] or len(rows)>3000:
        raise DataValidationError("D544 report scenario mismatch")
    with localcontext(_CTX):
        groups={}
        for row in rows:
            groups.setdefault(row["horizon_hours"],[]).append(row)
        if len(groups)>6:
            raise DataValidationError("D544 horizon budget exceeded")
        output=[{"kind":"d544_header","source_report_sha256":summary["source_report_sha256"],
                 "scenario_count":summary["scenario_count"],"fully_matched_scenario_count":summary["fully_matched_scenario_count"],
                 "paired_comparison_count":summary["paired_comparison_count"],
                 "resolution":summary["resolution"],"requested_days":summary["requested_days"],
                 **({"partition":summary["partition"],
                     "financial_validation_contract_sha256":summary["financial_validation_contract_sha256"],
                     "validation_scope":"reserved_short_horizon_conditional_research",
                     "independent_data_access_attested":False}
                    if summary.get("partition") in ("validation","holdout") else {}),
                 "maintenance_stress_bps":summary["maintenance_stress_bps"],
                 "liquidation_verified":False,"funding_calendar_verified":False,
                 "out_of_sample_results_validated":False,"orders_sent":False}]
        for h,items in sorted(groups.items()):
            full=[row for row in items if row["full_funding_match_both_orders"]]
            def bounds(row):
                return tuple(Decimal(x) for x in row["full_match_conditional_net_range_quote"])
            def key(row):
                return bounds(row)[0]/row["complete_trade_paths"],row["strategy"],row["exit_variant"],row["stop_bps"]
            ranked=([] if summary.get("partition") in ("validation","holdout")
                    else sorted(full,key=key,reverse=True))
            top=[]
            for row in ranked[:2]:
                top.append({"strategy":row["strategy"],"exit_variant":row["exit_variant"],"stop_bps":row["stop_bps"],
                            "paths":row["complete_trade_paths"],"missing_trade_paths":row["missing_trade_paths"],
                            "net_range_quote":row["full_match_conditional_net_range_quote"],
                            "lower_net_per_path_quote":format(key(row)[0].quantize(Decimal("0.000001")),"f"),
                            "monthly_entry_cohorts":row["monthly_entry_cohorts"],
                            "adverse_first_stress":row["orders"]["adverse_first"]["stress"],
                            "favorable_first_stress":row["orders"]["favorable_first"]["stress"],
                            "adverse_first_open":row["orders"]["adverse_first"]["open_at_horizon"],
                            "adverse_first_realized_pre_funding_quote":row["orders"]["adverse_first"].get("pre_funding_realized_after_cost_quote"),
                            "adverse_first_unrealized_gross_quote":row["orders"]["adverse_first"].get("pre_funding_unrealized_gross_quote")})
            output.append({"kind":"d544_horizon","hours":h,"scenario_count":len(items),
                           "positive_lower_bound":sum(bounds(x)[0]>0 for x in full),
                           "negative_upper_bound":sum(bounds(x)[1]<0 for x in full),
                           "mixed_or_zero_bound":sum(bounds(x)[0]<=0<=bounds(x)[1] for x in full),
                           "incomplete_or_empty_funding":len(items)-len(full),"descriptive_top_mean":top})
        for names,label in PAIRS.items():
            for h in sorted(groups):
                pairs=[p for p in summary["paired_exit_comparisons"] if p["horizon_hours"]==h
                       and (p["left_exit"],p["right_exit"])==names]
                if not pairs:
                    continue
                full=[p for p in pairs if p["status"]=="full_match_conditional_comparison"]
                # D542 reports fixed TP4 minus free. Reverse the entire interval.
                def delta(p):
                    a,b=map(Decimal,p["left_minus_right_quote"])
                    return -b,-a
                focus=[{"stop_bps":p["stop_bps"],"paths":p["complete_trade_paths"],
                         "free_minus_fixed_quote":[format(x,"f") for x in delta(p)]}
                       for p in full if p["strategy"]==FOCUS]
                output.append({"kind":"d544_paired_exit","hours":h,"protection":label,
                               "pair_count":len(pairs),"full_match_pairs":len(full),
                               "free_positive_difference":sum(delta(p)[0]>0 for p in full),
                               "fixed_positive_difference":sum(delta(p)[1]<0 for p in full),
                               "mixed_or_zero_difference":sum(delta(p)[0]<=0<=delta(p)[1] for p in full),
                               "focus_strategy":FOCUS,"focus_pairs":focus})
        output.append({"kind":"d544_complete","status":"compact_summary_completed",
                       "winner_selected":False,"portfolio_simulated":False,"orders_sent":False})
        return tuple(output)
