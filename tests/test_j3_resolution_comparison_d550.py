"""D550: real report contract, using synthetic financial fixtures only."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
import unittest

from crypto_intelligence_agent.j3_long_history_d528 import DAY, HOUR_MS
from crypto_intelligence_agent.j3_resolution_comparison_d550 import (
    HORIZONS, STRESS, compare_annual_reports,
)
from crypto_intelligence_agent.market_data import DataValidationError

NAMES = ["squeeze_bb_20_2_strict", "squeeze_bb_20_2_strict_rsi", "sq_w04_v2",
         "sq_w04_v15", "sq_sma_30_60", "sq_sma_10_30", "sq_ema_9_21", "sq_pivot"]
EXITS = ["owner_baseline", "runner_a", "runner_b", "runner_c", "runner_d", "runner_e"]
END = 20_700 * DAY


def raw(d):
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()


def order(n, before, matched=None):
    matched = n if matched is None else matched
    before = Decimal(before)
    matched_before = before if matched == n else before * matched / n
    money = lambda x: format(x, "f")
    d = {"conditional_before_funding_quote": money(before) if n else None,
         "funding_matched_path_count": matched, "funding_unavailable_path_count": n-matched,
         "funding_observed_event_count": matched,
         "funding_no_observed_events_path_count": 0,
         "funding_matched_positive_low_count": int(matched > 0 and matched_before > matched)*matched,
         "funding_matched_positive_high_count": int(matched > 0 and matched_before > 0)*matched,
         "funding_matched_before_quote": money(matched_before) if matched else None,
         "funding_observed_cost_low_quote": "0" if matched else None,
         "funding_observed_cost_high_quote": str(matched) if matched else None,
         "funding_matched_net_low_quote": money(matched_before-matched) if matched else None,
         "funding_matched_net_high_quote": money(matched_before) if matched else None,
         "residual_at_horizon_count": int(n > 0), "fully_exited_count": n-int(n > 0),
         "unrealized_gross_quote": "1" if n else None,
         "open_after_assumed_exit_cost_quote": "1" if n else None,
         "realized_after_incurred_cost_quote": money(before-1) if n else None}
    for bps in STRESS:
        p = f"stress_{bps}bps_"
        breach = min(matched, bps//50)
        d.update({p+"evaluated_count": matched, p+"unavailable_count": n-matched,
                  p+"possible_breach_count": breach, p+"no_observed_breach_count": matched-breach,
                  p+"positive_before_funding_with_possible_breach_count": 0,
                  p+"checked_bars": matched})
    return d


def row(name, n, before, matched=None):
    base = {"candidate_count": 5, "complete_path_count": n, "missing_path_count": 5-n,
            "adverse_first": order(n, before, matched),
            "favorable_first": order(n, before, matched)}
    return dict(deepcopy(base), name=name,
                directions={"LONG": 5, "SHORT": 0, "covered_LONG": n, "covered_SHORT": 0},
                by_month={"2026-05": deepcopy(base)}, by_btc_regime={"BTC_up": deepcopy(base)})


def report(resolution, n=4, before="12", matched=None):
    members = ["BTCUSDT"] + [f"ASSET{i}USDT" for i in range(49)]
    data = {}
    for symbol in members:
        m = {"1h": {"count": 100, "sha256": "a"*64}}
        if symbol != "BTCUSDT":
            if resolution == "5m":
                m["5m"] = {"count": 1200, "sha256": "b"*64}
            m["observed_funding"] = {"funding_rows_sha256": "c"*64,
                "mark_rows_sha256": ("d" if resolution == "1h" else "e")*64,
                "funding_row_count": 10, "mark_row_count": 100 if resolution == "1h" else 1200,
                "funding_query_coverage_complete": True, "mark_query_coverage_complete": True,
                "range_ms": [END-365*DAY, END-36*DAY], "funding_calendar_verified": False}
        data[symbol] = m
    return {"schema_version": "d529-retrospective-cohort-replay-v1",
            "status": "exploratory_replay_completed", "partition": "development",
            "requested_days": 365, "resolution": resolution, "scenario_count": 240,
            "horizons_hours": list(HORIZONS), "research_max_horizon_hours": 2160,
            "stop_grid_bps": [150], "maintenance_stress_bps": list(STRESS),
            "profile_revision": "f"*64,
            "preserve_recent_90d": True, "separate_open_mark": True,
            "target_diagnostics": True, "observed_funding": True,
            "horizons_require_longest_complete_path": True,
            "historical_marketwide_top50_verified": False,
            "funding_missing_queries_not_zero": True, "leverage_at_intent": 50,
            "all_horizons_share_same_decision_grid": True, "partition_crossing_paths_excluded": True,
            "maintenance_stress_is_not_venue_liquidation": True,
            "maintenance_stress_rewrites_pnl": False, "public_gets": 0,
            **{k: False for k in ("orders_sent", "profile_modified", "portfolio_simulated",
                "winner_selected", "out_of_sample_results_validated", "funding_calendar_verified",
                "funding_settlement_verified", "liquidation_verified", "historical_risk_tiers_verified")},
            "partition_ranges_ms": {"development": [END-365*DAY, END-36*DAY],
                "validation": [END-36*DAY, END-18*DAY], "holdout": [END-18*DAY, END]},
            "decision_range_ms": [END-365*DAY, END-36*DAY-2160*HOUR_MS],
            "common_research_filters": {"period": 20}, "common_exit_policy": {"fee": "5"},
            "exit_variants": {e: {"name": e} for e in EXITS},
            "indicator_state": "continuous", "cohort_origin": "survivors",
            "regime_definition": "BTC regime", "entry_reference": "next open",
            "protect_and_trail_activation": "next bar", "funding_method": "observed",
            "maintenance_stress_method": "hypothetical", "warmup_hours": 50,
            "expected_symbol_hours_after_launch": 100, "eligible_symbol_hours": 90,
            "excluded_missing_warmup_or_btc": 10,
            "covered_symbol_hours_by_horizon": {str(h): n*10 for h in HORIZONS},
            "manifest": {"plan_sha256": "1"*64, "matrix_sha256": "2"*64,
                "entry_experiments_sha256": "3"*64, "exit_experiments_sha256": "4"*64,
                "selected_strategy_names": NAMES, "data": data},
            "scenarios": [{"horizon_hours": h, "stop_bps": 150, "exit_variant": e,
                "common_covered_symbol_hours": n*10,
                "rows": [row(name, n, before, matched) for name in NAMES]}
                for h in HORIZONS for e in EXITS]}


class ResolutionComparisonTests(unittest.TestCase):
    def test_smaller_sample_and_sign_change_not_paired(self):
        a, b = raw(report("1h")), raw(report("5m", 3, "-3"))
        result = compare_annual_reports(a, b)
        self.assertEqual(result["scenario_count"], 240)
        self.assertEqual(result["hourly_report_sha256"], sha256(a).hexdigest())
        self.assertFalse(result["paired_effect_estimated"])
        self.assertFalse(result["path_membership_independently_verified"])
        self.assertEqual(result["conditional_sign_transitions_by_horizon"]["48"],
                         {"positive_to_negative": 48})
        sample = result["rows"][0]
        self.assertFalse(sample["complete_path_counts_equal"])
        self.assertEqual(sample["hourly"]["conditional_net_range_quote"], ["8", "12"])
        self.assertEqual(sample["five_minute"]["conditional_net_range_quote"], ["-6", "-3"])
        self.assertEqual(sample["five_minute"]["orders"]["adverse_first"]["stress"]["150"]
                         ["possible_breach_percent_of_evaluated"], "100.000000")

    def test_same_counts_do_not_prove_same_paths_and_partial_funding_unavailable(self):
        result = compare_annual_reports(raw(report("1h")), raw(report("5m", 4, "8", 3)))
        sample = result["rows"][0]
        self.assertTrue(sample["complete_path_counts_equal"])
        self.assertFalse(result["paired_effect_estimated"])
        self.assertIsNone(sample["five_minute"]["conditional_net_range_quote"])
        self.assertIsNone(sample["five_minute"]["conditional_mean_per_complete_path_quote"])
        self.assertEqual(result["conditional_sign_transitions_by_horizon"]["48"],
                         {"positive_to_unavailable": 48})

    def test_reject_configuration_data_and_coverage_mismatch(self):
        a = raw(report("1h"))
        changes = [
            lambda b: b.update(profile_revision="0"*64),
            lambda b: b.update(partition="holdout"),
            lambda b: b["manifest"]["data"]["BTCUSDT"]["1h"].update(sha256="0"*64),
            lambda b: b["manifest"]["data"]["ASSET0USDT"]["observed_funding"]
                       .update(funding_rows_sha256="0"*64),
            lambda b: b["manifest"].update(selected_strategy_names=NAMES[::-1]),
            lambda b: b["covered_symbol_hours_by_horizon"].update({"48": 41}),
            lambda b: b["scenarios"][0]["rows"][0].update(name="unknown"),
        ]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                b = report("5m")
                mutate(b)
                with self.assertRaises(DataValidationError):
                    compare_annual_reports(a, raw(b))

    def test_reject_duplicate_json_and_reversed_inputs(self):
        with self.assertRaises(DataValidationError):
            compare_annual_reports(b'{"a":1,"a":2}', raw(report("5m")))
        with self.assertRaises(DataValidationError):
            compare_annual_reports(raw(report("5m")), raw(report("1h")))


if __name__ == "__main__":
    unittest.main()
