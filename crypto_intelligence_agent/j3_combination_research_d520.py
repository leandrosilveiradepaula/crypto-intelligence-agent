"""D520: exploratory fixed-matrix research, not an optimizer or a trading policy."""
from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
import json
from pathlib import Path
import re

from .j2_configurable_indicators_d513 import (
    IndicatorSelection, MovingAverageSlot, PivotSuperTrend, parse_bollinger,
)
from .j3_archived_strategy_comparison_d512 import (
    compare_archived_strategies, read_comparison_archives,
)
from .j3_intrahour_replay_d518 import read_latest_intrahour
from .j3_retrospective_warmup_d516 import read_latest_supplement
from .market_data import DataValidationError
from .synthetic_margin_envelope import SyntheticMarginBasis

MATRIX_SCHEMA = "d520-indicator-research-matrix-v1"
REPORT_SCHEMA = "d520-exploratory-combination-research-v1"
RESERVED = {"breakout", "ema_cross", "indicator_combo", "reference_long"}
MAX_MATRIX_BYTES = 65536


def _unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise DataValidationError("D520 repeated matrix field")
        result[k] = v
    return result


def _periods(values, *, min_count=0):
    if (type(values) is not list or not min_count <= len(values) <= 3
            or any(type(v) is not int or not 2 <= v <= 120 for v in values)
            or any(a >= b for a, b in zip(values, values[1:]))):
        raise DataValidationError("D520 ordered integer periods required")
    return tuple(values)


def _decimal(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{1,4}(?:[.][0-9]{1,6})?", value) is None:
        raise DataValidationError("D520 decimal string required")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise DataValidationError("D520 invalid decimal") from exc


def _slots(periods):
    return tuple(MovingAverageSlot(True, n) for n in periods) + tuple(
        MovingAverageSlot(False, 2) for _ in range(3-len(periods)))


def parse_matrix(raw: bytes) -> tuple[tuple[int, int, int], tuple, dict]:
    """A versioned editable hypothesis list; no saved PAPER configuration changes."""
    if type(raw) is not bytes or not 2 <= len(raw) <= MAX_MATRIX_BYTES:
        raise DataValidationError("D520 bounded matrix file required")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise DataValidationError("D520 invalid matrix JSON") from exc
    if (type(doc) is not dict or set(doc) != {"schema", "ema_reference_periods", "profiles"}
            or doc["schema"] != MATRIX_SCHEMA or type(doc["profiles"]) is not list
            or not 1 <= len(doc["profiles"]) <= 24):
        raise DataValidationError("D520 explicit 1..24 profile matrix required")
    ref = _periods(doc["ema_reference_periods"], min_count=3)
    labels = {"breakout": "Rompimento + FR", "ema_cross": "EMA legado " + "/".join(map(str, ref)) + " + FR"}
    profiles = []
    seen = set(RESERVED)
    fingerprints = set()
    for row in doc["profiles"]:
        required = {"name","label","ema","sma","pivot","relative_strength_bps"}
        if type(row) is not dict or set(row) not in (required, required | {"bollinger"}):
            raise DataValidationError("D520 invalid profile fields")
        name = row["name"]
        label = row["label"]
        if (type(name) is not str or re.fullmatch(r"[a-z][a-z0-9_]{1,39}",name) is None
                or name in seen or type(label) is not str or not 1 <= len(label) <= 100
                or any(ord(c) < 32 for c in label)):
            raise DataValidationError("D520 unique name and bounded label required")
        p = row["pivot"]
        if p is None:
            pivot = PivotSuperTrend(False,2,10,Decimal(3))
        else:
            if type(p) is not dict or set(p) != {"pivot_period","atr_period","atr_factor"}:
                raise DataValidationError("D520 exact pivot settings required")
            pivot = PivotSuperTrend(True,p["pivot_period"],p["atr_period"],_decimal(p["atr_factor"]))
        bb = row.get("bollinger")
        if bb is not None and (type(bb) is not dict or set(bb) != {"period","deviations","mode"}):
            raise DataValidationError("D521 exact matrix Bollinger settings required")
        selection = IndicatorSelection(_slots(_periods(row["ema"])),
                                       _slots(_periods(row["sma"])),pivot,
                                       parse_bollinger({"enabled":True,**bb}) if bb is not None else None)
        threshold = _decimal(row["relative_strength_bps"])
        if not selection.active or not 0 <= threshold <= 1000:
            raise DataValidationError("D520 active indicators and RS threshold 0..1000 bps required")
        fingerprint = (selection,threshold)
        if fingerprint in fingerprints:
            raise DataValidationError("D520 duplicate hypothesis")
        fingerprints.add(fingerprint)
        seen.add(name)
        profiles.append((name,selection,threshold))
        labels[name] = label
    return ref,tuple(profiles),labels


def summarize_matrix(report, labels, *, min_complete=20, min_coverage_bps=7000):
    """Order for inspection only; low-sample rows stay visible; no winner is selected."""
    if (type(min_complete) is not int or not 1 <= min_complete <= 1176
            or type(min_coverage_bps) is not int or not 0 <= min_coverage_bps <= 10000):
        raise DataValidationError("D520 invalid descriptive screen thresholds")
    replay = report["exit_replay"]
    if not replay or replay["interval"] != "5m":
        raise DataValidationError("D520 requires the corroborated 5m replay")
    by_strategy = replay["results"]
    common = by_strategy["reference_long"]["complete_path_count"]
    rows = []
    with localcontext() as ctx:
        ctx.prec = 50
        for name, label in labels.items():
            r = by_strategy[name]
            n = r["candidate_count"]
            complete = r["complete_path_count"]
            adverse = r["adverse_first"]
            favorable = r["favorable_first"]
            if complete > common:
                raise DataValidationError("D520 inconsistent common path coverage")
            directions = report["batch_entry_counts"][name]
            if (directions["LONG"]+directions["SHORT"] != n
                    or directions["covered_LONG"]+directions["covered_SHORT"] != complete):
                raise DataValidationError("D520 inconsistent directional counts")
            eligible = complete >= min_complete and complete*10000 >= n*min_coverage_bps
            coverage = (format((Decimal(complete)*100/n).quantize(Decimal("0.01")),"f")
                        if n else None)
            rate = (format((Decimal(adverse["positive_count"])*100/complete)
                           .quantize(Decimal("0.01")),"f") if complete else None)
            net = adverse["conditional_before_funding_quote"]
            rows.append({
                "name":name,"label":label,"candidates":n,"complete":complete,
                "coverage_pct":coverage,"long":directions["LONG"],"short":directions["SHORT"],
                "covered_long":directions["covered_LONG"],"covered_short":directions["covered_SHORT"],
                "positive":adverse["positive_count"],"negative":adverse["negative_count"],
                "positive_pct":rate,"stop_count":adverse["stop_count"],
                "with_targets":adverse["with_targets_count"],
                "residual_at_horizon":adverse["residual_at_horizon_count"],
                "loss_at_least_margin":adverse["loss_at_least_margin_count"],
                "ambiguous_count":r["ordering_sensitive_count"],
                "gross_adverse":adverse["gross_reference_quote"],
                "cost_adverse":adverse["assumed_fee_slippage_quote"],
                "net_adverse":net,"net_favorable":favorable["conditional_before_funding_quote"],
                "mean_adverse_bps":adverse["average_before_funding_bps"],
                "mean_favorable_bps":favorable["average_before_funding_bps"],
                # Normalize to the same covered opportunity universe, not portfolio capital.
                "net_per_common_covered_slot":(format((Decimal(net)/common)
                    .quantize(Decimal("0.000001")),"f") if common and net is not None else None),
                "descriptive_sample_screen_met":eligible,
                "entry_examples":report["batch_entry_examples"][name],
            })
    # Mean adverse result after estimated costs, not the optimistic scenario.
    # Show ALL rows, including those with no signals or insufficient coverage.
    rows.sort(key=lambda r:(
        not r["descriptive_sample_screen_met"],
        r["mean_adverse_bps"] is None,
        -Decimal(r["mean_adverse_bps"] or "0"),
        r["name"]))
    return {"common_covered_symbol_hours":common,
            "minimum_complete_for_descriptive_screen":min_complete,
            "minimum_coverage_bps_for_descriptive_screen":min_coverage_bps,
            "ordered_by":"sample_screen_then_adverse_mean_after_costs_desc",
            "winner_selected":False,"rows":rows}


def run_matrix(*, directory: Path, owner_policy, matrix_raw: bytes,
               as_of_ms: int, horizon_hours: int, min_complete=20,
               min_coverage_bps=7000) -> dict:
    """Read existing archives once, evaluate every hypothesis in one pass. No GET or writes."""
    ref,profiles,labels = parse_matrix(matrix_raw)
    archives = read_comparison_archives(directory,now_ms=as_of_ms)
    warmup = read_latest_supplement(directory,now_ms=as_of_ms)
    intrahour = read_latest_intrahour(directory,now_ms=as_of_ms)
    if warmup is None or intrahour is None:
        raise DataValidationError("D520 saved D516 and D518 supplements required")
    # The saved strategy choice is NOT a research candidate by default. Preserve
    # all common feature filters and economic terms; matrix is independent.
    cfg = replace(owner_policy.research,entry_mode="breakout",indicators=None)
    exit_policy = owner_policy.exits
    notional = owner_policy.margin_quote*Decimal(owner_policy.leverage.for_new_positions)
    margin = SyntheticMarginBasis(owner_policy.margin_quote,
        owner_policy.leverage.for_new_positions,notional,"SYNTHETIC_USDT")
    report = compare_archived_strategies(
        archives,config=cfg,ema_periods=ref,reference_notional=notional,
        entry_fee_bps=exit_policy.entry_fee_bps,exit_fee_bps=exit_policy.exit_fee_bps,
        entry_slippage_bps=exit_policy.entry_adverse_slippage_bps,
        exit_slippage_bps=exit_policy.exit_adverse_slippage_bps,
        stop_distance_bps=exit_policy.stop_distance_bps,
        target_distances_bps=exit_policy.target_distances_bps,now_ms=as_of_ms,
        warmup_supplement=warmup,replay_horizon_hours=horizon_hours,
        replay_margin=margin,exit_policy=exit_policy,intrahour_supplement=intrahour,
        additional_profiles=profiles)
    screen = summarize_matrix(report,labels,min_complete=min_complete,
                              min_coverage_bps=min_coverage_bps)
    manifest = {
        "archive_digests":[[h.window_end_ms,h.digest_sha256] for h in archives],
        "warmup_sha256":warmup.digest_sha256,"intrahour_sha256":intrahour.digest_sha256,
        "matrix_sha256":sha256(matrix_raw).hexdigest(),
    }
    return {
        "schema_version":REPORT_SCHEMA,
        "status":"exploratory_matrix_completed" if screen["common_covered_symbol_hours"] else "no_complete_common_paths",
        "as_of_ms":as_of_ms,"archive_count":report["archive_count"],
        "paired_decision_hours":report["paired_decision_hours"],
        "common_eligible_symbol_hours":report["common_eligible_symbol_hours"],
        "common_warmup_hours":report["required_warmup_hours"],
        "horizon_hours":horizon_hours,"resolution":"5m","manifest":manifest,
        "relative_strength_definition":"asset_24h_open_to_close_return_minus_BTC_24h_return",
        "relative_strength_gate":"strict_directional_threshold_on_indicator_transition",
        "common_research_filters":asdict(cfg),
        "common_exit_policy":asdict(exit_policy),
        "requested_margin_quote":format(margin.requested_margin_quote,"f"),
        "reference_notional_quote":format(notional,"f"),
        "leverage_at_intent":margin.leverage_at_intent,
        "public_gets":0,"profile_modified":False,"orders_sent":False,
        "out_of_sample_results_validated":False,"financial_backtest_approved":False,
        "approved_for_live_use":False,"funding_settlement_verified":False,
        "liquidation_verified":False,"intrabar_path_verified":False,
        **screen,"comparison":report,
    }
