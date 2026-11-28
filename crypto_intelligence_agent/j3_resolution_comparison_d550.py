"""D550 compare existing annual D529 reports, without replay or selection.

The hourly decision grid and funding inputs must match. Fine trajectories may
be a subset of coarse trajectories. Counts and manifests do not identify
individual paths, so this is a descriptive scenario comparison, never a
paired treatment effect or a claim of venue fills.
"""
from __future__ import annotations

from collections import Counter
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import re

from .j3_financial_evidence_d542 import summarize_financial_replay
from .j3_long_history_d528 import DAY, HOUR_MS
from .market_data import DataValidationError

SCHEMA = "d550-annual-resolution-comparison-v1"
MAX_REPORT_BYTES = 128 * 1024 * 1024
HORIZONS = (48, 168, 720, 1440, 2160)
ORDERS = ("adverse_first", "favorable_first")
STRESS = (50, 100, 150)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_CTX = Context(prec=128)


def _require(ok):
    if not ok:
        raise DataValidationError("D550 reports not comparable under frozen annual contract")


def _digest(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _count(value):
    _require(type(value) is int and 0 <= value <= 100_000_000)
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _decode(raw):
    _require(type(raw) is bytes and 2 <= len(raw) <= MAX_REPORT_BYTES)
    def reject(_):
        raise DataValidationError("D550 nonfinite JSON")
    result = json.loads(raw, object_pairs_hook=_unique, parse_constant=reject)
    _require(type(result) is dict)
    return result


def _bar_manifest(value):
    _require(type(value) is dict and set(value) == {"count", "sha256"}
             and _digest(value["sha256"]))
    _count(value["count"])
    return value


def _funding_manifest(value):
    _require(type(value) is dict and _digest(value["funding_rows_sha256"])
             and _digest(value["mark_rows_sha256"])
             and value["funding_calendar_verified"] is False
             and type(value["funding_query_coverage_complete"]) is bool
             and type(value["mark_query_coverage_complete"]) is bool
             and type(value["range_ms"]) is list
             and len(value["range_ms"]) == 2
             and all(type(v) is int for v in value["range_ms"])
             and 0 < value["range_ms"][0] < value["range_ms"][1])
    _count(value["funding_row_count"])
    _count(value["mark_row_count"])
    return tuple(value[k] for k in ("funding_rows_sha256", "funding_row_count",
                     "funding_query_coverage_complete", "range_ms"))


def _contract(coarse, fine):
    for report, resolution in ((coarse, "1h"), (fine, "5m")):
        _require(report["partition"] == "development"
                 and report["requested_days"] == 365
                 and report["resolution"] == resolution
                 and report["scenario_count"] == 240
                 and report["horizons_hours"] == list(HORIZONS)
                 and report["research_max_horizon_hours"] == 2160
                 and report["stop_grid_bps"] == [150]
                 and report["maintenance_stress_bps"] == list(STRESS)
                 and _digest(report["profile_revision"])
                 and all(report.get(k) is True for k in (
                     "preserve_recent_90d", "separate_open_mark",
                     "target_diagnostics", "observed_funding",
                     "horizons_require_longest_complete_path"))
                 and report["historical_marketwide_top50_verified"] is False)
        ranges = report["partition_ranges_ms"]
        cutoff = ranges["holdout"][1]
        _require(type(cutoff) is int and cutoff > 365 * DAY and cutoff % DAY == 0
                 and ranges == {"development": [cutoff - 365 * DAY, cutoff - 36 * DAY],
                                "validation": [cutoff - 36 * DAY, cutoff - 18 * DAY],
                                "holdout": [cutoff - 18 * DAY, cutoff]}
                 and report["decision_range_ms"] ==
                     [cutoff - 365 * DAY, cutoff - 36 * DAY - 2160 * HOUR_MS])
    shared = ("profile_revision", "partition_ranges_ms", "decision_range_ms",
              "common_research_filters", "common_exit_policy", "exit_variants",
              "indicator_state", "cohort_origin", "regime_definition", "entry_reference",
              "protect_and_trail_activation", "funding_method", "maintenance_stress_method",
              "warmup_hours", "expected_symbol_hours_after_launch", "eligible_symbol_hours",
              "excluded_missing_warmup_or_btc")
    _require(all(k in coarse and k in fine and coarse[k] == fine[k] for k in shared))
    a, b = coarse["manifest"], fine["manifest"]
    for key in ("plan_sha256", "matrix_sha256", "entry_experiments_sha256",
                "exit_experiments_sha256"):
        _require(_digest(a[key]) and a[key] == b[key])
    names = a["selected_strategy_names"]
    _require(type(names) is list and len(names) == 8
             and all(type(x) is str for x in names) and len(set(names)) == 8
             and names == b["selected_strategy_names"])
    variants = coarse["exit_variants"]
    _require(type(variants) is dict and len(variants) == 6
             and "owner_baseline" in variants)
    data_a, data_b = a["data"], b["data"]
    _require(type(data_a) is dict and type(data_b) is dict
             and len(data_a) == 50 and data_a.keys() == data_b.keys()
             and "BTCUSDT" in data_a
             and all(_SYMBOL.fullmatch(s) is not None for s in data_a))
    for symbol in data_a:
        x, y = data_a[symbol], data_b[symbol]
        _require(_bar_manifest(x["1h"]) == _bar_manifest(y["1h"]))
        if symbol == "BTCUSDT":
            continue
        _bar_manifest(y["5m"])
        _require(("observed_funding" in x) == ("observed_funding" in y))
        if "observed_funding" in x:
            _require(_funding_manifest(x["observed_funding"]) ==
                     _funding_manifest(y["observed_funding"]))
    expected = _count(coarse["expected_symbol_hours_after_launch"])
    eligible = _count(coarse["eligible_symbol_hours"])
    _require(eligible <= expected and coarse["excluded_missing_warmup_or_btc"] == expected - eligible)
    coverage = {}
    for h in HORIZONS:
        key = str(h)
        c = _count(coarse["covered_symbol_hours_by_horizon"][key])
        f = _count(fine["covered_symbol_hours_by_horizon"][key])
        _require(f <= c <= eligible)
        coverage[key] = {"hourly": c, "five_minute": f}
    return names, variants, coverage


def _key(row):
    return (row["strategy"], row["exit_variant"], row["horizon_hours"], row["stop_bps"])


def _report_index(report):
    result = {}
    for scenario in report["scenarios"]:
        for row in scenario["rows"]:
            k = (row["name"], scenario["exit_variant"],
                 scenario["horizon_hours"], scenario["stop_bps"])
            _require(k not in result)
            result[k] = row
    return result


def _path_signature(a, b):
    _require(a["candidate_count"] == b["candidate_count"]
             and b["complete_path_count"] <= a["complete_path_count"])
    for side in ("LONG", "SHORT"):
        _require(a["directions"][side] == b["directions"][side]
                 and b["directions"]["covered_" + side] <= a["directions"]["covered_" + side])
    for key in ("by_month", "by_btc_regime"):
        left, right = a[key], b[key]
        _require(left.keys() == right.keys())
        for group in left:
            _require(left[group]["candidate_count"] == right[group]["candidate_count"]
                     and _count(right[group]["complete_path_count"]) <=
                         _count(left[group]["complete_path_count"]))


def _percentage(numerator, denominator):
    if denominator == 0:
        return None
    return format((Decimal(numerator) * 100 / denominator).quantize(Decimal(".000001")), "f")


def _describe(row):
    n = row["complete_trade_paths"]
    net = row["full_match_conditional_net_range_quote"]
    sign = "unavailable"
    average = None
    if net is not None:
        lo, hi = map(Decimal, net)
        sign = "positive" if lo > 0 else "negative" if hi < 0 else "mixed_or_zero"
        average = [format((v / n).quantize(Decimal(".000000000001")), "f") for v in (lo, hi)]
    orders = {}
    for order in ORDERS:
        x = row["orders"][order]
        orders[order] = {
            "funding_matched_paths": x["funding_matched_paths"],
            "funding_cost_range_quote": x["observed_funding_cost_interval_quote"],
            "open_at_horizon": x["open_at_horizon"],
            "realized_pre_funding_quote": x["pre_funding_realized_after_cost_quote"],
            "unrealized_gross_pre_funding_quote": x["pre_funding_unrealized_gross_quote"],
            "stress": {bps: {
                "evaluated": v["evaluated"], "possible_breaches": v["possible_breaches"],
                "unavailable": v["unavailable"],
                "possible_breach_percent_of_evaluated": _percentage(v["possible_breaches"], v["evaluated"]),
            } for bps, v in x["stress"].items()},
        }
    return {"complete_trade_paths": n, "missing_trade_paths": row["missing_trade_paths"],
            "conditional_net_range_quote": net,
            "conditional_mean_per_complete_path_quote": average,
            "conditional_sign": sign, "orders": orders,
            "monthly_entry_cohorts": row["monthly_entry_cohorts"]}


def compare_annual_reports(hourly_raw, fine_raw):
    """Return sanitized scenario aggregates; no paired performance delta.

    Source hashes bind bytes, not runtime authenticity. Legacy 1h reports
    need not contain newer stress-attribution or exposure diagnostics.
    """
    try:
        with localcontext(_CTX):
            coarse, fine = _decode(hourly_raw), _decode(fine_raw)
            a = summarize_financial_replay(coarse)
            b = summarize_financial_replay(fine)
            names, variants, coverage = _contract(coarse, fine)
            expected = {(s, v, h, 150) for s in names for v in variants for h in HORIZONS}
            left, right = {_key(x): x for x in a["rows"]}, {_key(x): x for x in b["rows"]}
            raw_a, raw_b = _report_index(coarse), _report_index(fine)
            _require(len(expected) == 240 and expected == left.keys() == right.keys()
                     == raw_a.keys() == raw_b.keys())
            transitions = {h: Counter() for h in HORIZONS}
            rows = []
            for k in sorted(expected, key=lambda x: (x[2], x[0], x[1], x[3])):
                _path_signature(raw_a[k], raw_b[k])
                x, y = _describe(left[k]), _describe(right[k])
                transitions[k[2]][x["conditional_sign"] + "_to_" + y["conditional_sign"]] += 1
                rows.append({"strategy": k[0], "exit_variant": k[1], "horizon_hours": k[2],
                    "stop_bps": k[3], "candidate_count": left[k]["candidate_count"],
                    "complete_path_counts_equal": x["complete_trade_paths"] == y["complete_trade_paths"],
                    "hourly": x, "five_minute": y})
            return {"schema_version": SCHEMA, "status": "descriptive_comparison_completed",
                "hourly_report_sha256": sha256(hourly_raw).hexdigest(),
                "five_minute_report_sha256": sha256(fine_raw).hexdigest(),
                "plan_sha256": coarse["manifest"]["plan_sha256"], "scenario_count": len(rows),
                "same_hourly_inputs_and_configuration": True, "same_observed_funding_inputs": True,
                "path_membership_independently_verified": False, "paired_effect_estimated": False,
                "comparison_scope": "same_scenario_key_separate_resolution_aggregates",
                "coverage_by_horizon": coverage,
                "conditional_sign_transitions_by_horizon":
                    {str(h): dict(sorted(v.items())) for h, v in transitions.items()},
                "winner_selected": False, "liquidation_verified": False,
                "funding_calendar_verified": False, "out_of_sample_results_validated": False,
                "portfolio_simulated": False, "public_gets": 0, "orders_sent": False, "rows": rows}
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError, RecursionError) as exc:
        raise DataValidationError("D550 malformed or incomparable annual reports") from exc
