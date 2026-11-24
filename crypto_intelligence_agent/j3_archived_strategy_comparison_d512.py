"""D512: chronological research comparison over immutable D461 REST archives.

Use only membership and candles already captured in the decision snapshot
or earlier snapshots for the hypotheses. The next consecutive snapshot is
used solely to observe a future close/price range. Never create an intent,
simulate a fill, choose a winning configuration, or declare OOS validity.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import re

from .bybit_public_j1_transport import HOUR_MS
from .j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from .j2_observed_bybit_research import evaluate_observed_bybit_research
from .j2_rest_n50_history_d461 import (
    RestN50History, reopen_frozen_rest_n50_for_research,
)
from .j4_private_paper_ws_operator_d425 import _private_directory
from .j3_retrospective_warmup_d516 import WarmupSupplement, seed_by_anchor
from .market_data import DataGapError, DataValidationError
from .synthetic_cost_scenarios import SyntheticCostScenario, evaluate_synthetic_costs
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_intrabar_barriers import ResearchDirection

SCHEMA = "d512-archived-rest-strategy-comparison-v1"
_NAME = re.compile(r"rest-history-d461-([0-9a-f]{18})-([0-9]{13})(?:-w([0-9]{2,3}))?[.]json\Z")
MAX_ARCHIVES = 72
MAX_PAIRS = 24
MAX_WARMUP = 122
_SOURCE = "public_rest_observed_unverified"
_QUALITY = "bybit_public_rest_historical_closed_unverified"


def read_comparison_archives(directory: Path, *, now_ms: int) -> tuple[RestN50History, ...]:
    """Read at most one frozen, unambiguous cohort per hour; no network/writes."""
    home = _private_directory(directory)
    hours = {}
    for entry in home.iterdir():
        m = _NAME.fullmatch(entry.name)
        if m is None or entry.is_symlink() or not entry.is_file():
            continue
        end = int(m[2])
        if end > now_ms:
            continue
        hours.setdefault(end, []).append((m[1], int(m[3] or 24), entry.name))
    chosen = []
    for end in sorted(hours)[-MAX_ARCHIVES:]:
        items = hours[end]
        # Do not pick a winning cohort retrospectively where multiple
        # membership fingerprints were saved for the same decision hour.
        if len({item[0] for item in items}) != 1:
            continue
        filename = max(items, key=lambda item: (item[1], item[2]))[2]
        history = reopen_frozen_rest_n50_for_research(
            private_j2_directory=home, filename=filename,
        )
        if history.source_mode == _SOURCE and history.captured_at_ms <= now_ms:
            chosen.append(history)
    return tuple(chosen)


def _warmup(config, periods):
    f = config.features
    return max(24, f.ema_period, f.extrema_period + 1, f.quote_volume_period + 1,
               f.atr_period + config.compression_bars + config.baseline_bars,
               periods[-1] + 2)


def _empty(target_count):
    return {
        "candidates": 0, "scored_marks": 0, "missing_future_marks": 0,
        "positive_marks": 0, "negative_marks": 0, "flat_marks": 0,
        "gross_mark_quote": Decimal(0), "cost_assumed_quote": Decimal(0),
        "conditional_mark_before_funding_quote": Decimal(0),
        "stop_range_touches": 0, "target_range_touches": [0] * target_count,
        "stop_and_target_same_bar": 0,
    }


def _summary(row, notional):
    result = dict(row)
    count = result["scored_marks"]
    for key in ("gross_mark_quote", "cost_assumed_quote",
                "conditional_mark_before_funding_quote"):
        result[key] = format(result[key], "f") if count else None
    result["average_mark_before_funding_bps"] = (
        format((row["conditional_mark_before_funding_quote"] / notional
                * Decimal(10000) / count).quantize(Decimal("0.01")), "f")
        if count else None
    )
    return result


def _accumulate(row, side, reference, future, notional, cost, stop, targets):
    row["candidates"] += 1
    if future is None:
        row["missing_future_marks"] += 1
        return
    row["scored_marks"] += 1
    long = side == "LONG"
    direction = Decimal(1) if long else Decimal(-1)
    gross = notional * direction * (future.close / reference - 1)
    net = gross - cost
    row["gross_mark_quote"] += gross
    row["cost_assumed_quote"] += cost
    row["conditional_mark_before_funding_quote"] += net
    row["positive_marks" if net > 0 else "negative_marks" if net < 0 else "flat_marks"] += 1
    stop_price = reference * (1 - direction * stop / Decimal(10000))
    touched_stop = future.low <= stop_price if long else future.high >= stop_price
    row["stop_range_touches"] += int(touched_stop)
    any_target = False
    for i, distance in enumerate(targets):
        target = reference * (1 + direction * distance / Decimal(10000))
        touched = future.high >= target if long else future.low <= target
        row["target_range_touches"][i] += int(touched)
        any_target = any_target or touched
    row["stop_and_target_same_bar"] += int(touched_stop and any_target)


def compare_archived_strategies(
    histories: tuple[RestN50History, ...], *, config: CompressionBreakoutConfig,
    ema_periods: tuple[int, int, int], reference_notional: Decimal,
    entry_fee_bps: Decimal, exit_fee_bps: Decimal,
    entry_slippage_bps: Decimal, exit_slippage_bps: Decimal,
    stop_distance_bps: Decimal, target_distances_bps: tuple[Decimal, ...],
    now_ms: int, warmup_supplement: WarmupSupplement | None = None,
) -> dict:
    """Compare fixed caller-supplied profiles on the same causal archive slots.

    A 24h archived series can be extended using only older, overlapping
    snapshots. Conflicting candles and missing warmup exclude a symbol from
    BOTH strategies. A disappeared symbol's future mark is unknown, not zero.
    """
    if (type(histories) is not tuple or len(histories) > MAX_ARCHIVES
            or type(config) is not CompressionBreakoutConfig
            or type(now_ms) is not int or now_ms <= 0
            or type(stop_distance_bps) is not Decimal
            or not stop_distance_bps.is_finite()
            or not 0 < stop_distance_bps < 10000
            or type(target_distances_bps) is not tuple
            or not 1 <= len(target_distances_bps) <= 64
            or any(type(d) is not Decimal or not d.is_finite() or not 0 < d < 10000
                   for d in target_distances_bps)
            or any(a >= b for a, b in zip(target_distances_bps, target_distances_bps[1:]))):
        raise DataValidationError("D512 bounded comparison policy required")
    cross = replace(config, entry_mode="ema_cross", ema_cross_periods=ema_periods)
    breakout = replace(config, entry_mode="breakout")
    warmup = _warmup(config, cross.ema_cross_periods)
    policies = [("breakout", breakout), ("ema_cross", cross)]
    if config.indicators is not None:
        custom = replace(config, entry_mode="indicator_combo")
        policies.append(("indicator_combo", custom))
        warmup = max(warmup, custom.indicators.minimum_closed_bars(
            custom.features.quote_volume_period))
    # Same fixed reference notional on both sides, as in D288. Funding
    # events are deliberately not fabricated or settled by this report.
    costs = evaluate_synthetic_costs(SyntheticCostScenario(
        direction=ResearchDirection.LONG, entry_at_ms=1, exit_at_ms=2,
        entry_hypothetical_notional_quote_units=reference_notional,
        exit_hypothetical_notional_quote_units=reference_notional,
        entry_fee_bps=entry_fee_bps, exit_fee_bps=exit_fee_bps,
        entry_adverse_slippage_bps=entry_slippage_bps,
        exit_adverse_slippage_bps=exit_slippage_bps,
    )).fees_and_slippage_units
    for h in histories:
        if (type(h) is not RestN50History or h.source_mode != _SOURCE
                or not 0 < h.window_end_ms <= h.captured_at_ms <= now_ms
                or h.captured_at_ms >= h.window_end_ms + HOUR_MS
                or h.window_end_ms % HOUR_MS
                or not 24 <= h.history_hours <= MAX_WARMUP
                or len(h.series) != 50 or len(set(h.symbols)) != 50
                or "BTCUSDT" not in h.symbols):
            raise DataValidationError("D512 requires observed D461 historical cohorts")
        for symbol, bars in h.series:
            if (len(bars) != h.history_hours
                    or bars[-1].close_time_ms + 1 != h.window_end_ms
                    or any(c.quality != _QUALITY or c.symbol != symbol for c in bars)
                    or any(b.open_time_ms != a.open_time_ms + HOUR_MS
                           for a, b in zip(bars, bars[1:]))):
                raise DataGapError("D512 invalid archive series")
    ordered = sorted(histories, key=lambda h: h.window_end_ms)
    by_end = {h.window_end_ms: h for h in ordered}
    if len(by_end) != len(ordered):
        raise DataValidationError("D512 duplicate decision archive")
    paired_ends = {
        h.window_end_ms for h in ordered if h.window_end_ms + HOUR_MS in by_end
    }
    selected = set(sorted(paired_ends)[-MAX_PAIRS:])
    totals = {k: _empty(len(target_distances_bps))
              for k in [name for name, _ in policies] + ["reference_long"]}
    eligible = rejected = 0
    max_contiguous = 0
    cache = {}
    conflicts = set()
    retrospective_keys = set()
    retrospective_slots = 0
    seeds, rejected_supplements = (
        seed_by_anchor(histories, warmup_supplement, now_ms=now_ms)
        if warmup_supplement is not None else ({}, 0)
    )
    windows = []
    with localcontext() as ctx:
        ctx.prec = 50
        for h in ordered:
            end = h.window_end_ms
            for symbol, bars in h.series:
                for bar in bars:
                    key = (symbol, bar.open_time_ms)
                    if key in cache and cache[key] != bar:
                        conflicts.add(key)
                    else:
                        cache[key] = bar
            for bar in seeds.get(end, ()):
                key = (bar.symbol, bar.open_time_ms)
                if key in cache:
                    if cache[key] != bar:
                        conflicts.add(key)
                else:
                    cache[key] = bar
                    retrospective_keys.add(key)
            if end not in selected:
                continue
            future_archive = by_end[end + HOUR_MS]
            future_series = dict(future_archive.series)
            current_series = dict(h.series)
            btc = current_series["BTCUSDT"]
            btc_return = btc[-1].close / btc[-24].open - 1
            window = {"decision_closed_end_ms": end, "archive_captured_at_ms": h.captured_at_ms,
                      "eligible_symbols": 0, "breakout_candidates": 0,
                      "ema_cross_candidates": 0}
            if config.indicators is not None:
                window["indicator_combo_candidates"] = 0
            for symbol, bars in h.series:
                if symbol == "BTCUSDT":
                    continue
                previous = []
                for j in range(1, min(warmup, MAX_WARMUP) + 1):
                    key = (symbol, end - j * HOUR_MS)
                    if key not in cache or key in conflicts:
                        break
                    previous.append(cache[key])
                max_contiguous = max(max_contiguous, len(previous))
                if len(previous) < warmup:
                    rejected += 1
                    continue
                eligible += 1
                window["eligible_symbols"] += 1
                prefix = tuple(reversed(previous))
                if any((symbol, c.open_time_ms) in retrospective_keys for c in prefix):
                    retrospective_slots += 1
                # Digest identifies the research inputs; it does not claim
                # external authenticity or transform REST into WS confirms.
                digest = sha256((h.digest_sha256 + "|" + symbol + "|" +
                                 "|".join(str(c.open_time_ms) + ":" + str(c.close)
                                          for c in prefix)).encode("ascii")).hexdigest()
                series = BybitClosedResearchSeries(
                    prefix, digest, h.scope_sha256, "research_only_public_closed_series",
                )
                relative = bars[-1].close / bars[-24].open - 1 - btc_return
                next_bars = future_series.get(symbol)
                # A revised overlapping close cannot be scored as if the
                # original historical reference were corroborated.
                future = (next_bars[-1] if next_bars is not None
                          and next_bars[-2] == bars[-1] else None)
                for name, policy in policies:
                    hypothesis = evaluate_observed_bybit_research(
                        series, config=policy, decision_at_ms=end, close_safety_ms=1,
                        allow_rest_historical_research=True,
                    ).hypotheses
                    if not hypothesis:
                        continue
                    side = hypothesis[0].side.value
                    if not ((side == "LONG" and relative > 0)
                            or (side == "SHORT" and relative < 0)):
                        continue
                    window[name + "_candidates"] += 1
                    _accumulate(totals[name], side, bars[-1].close, future,
                                reference_notional, costs, stop_distance_bps, target_distances_bps)
                _accumulate(totals["reference_long"], "LONG", bars[-1].close, future,
                            reference_notional, costs, stop_distance_bps, target_distances_bps)
            windows.append(window)
        results = {k: _summary(v, reference_notional) for k, v in totals.items()}
    return {
        "schema_version": SCHEMA,
        "status": ("historical_conditional_marks_only" if eligible
                   else "insufficient_paired_archives_or_warmup"),
        "source": ("owner_frozen_public_rest_archives_with_retrospective_warmup"
                   if warmup_supplement is not None else "owner_frozen_public_rest_archives"),
        "retrospective_warmup_requested": warmup_supplement is not None,
        "retrospective_warmup_retrieved_at_ms": (
            warmup_supplement.created_at_ms if warmup_supplement is not None else None),
        "retrospective_warmup_symbol_hours": retrospective_slots,
        "retrospective_warmup_rejected_series": rejected_supplements,
        "contemporaneous_capture_for_all_features_verified": False,
        "archive_count": len(histories), "paired_decision_hours": len(selected),
        "required_warmup_hours": warmup, "maximum_contiguous_hours_observed": max_contiguous,
        "common_eligible_symbol_hours": eligible,
        "excluded_warmup_or_conflict_symbol_hours": rejected,
        "ema_periods": list(ema_periods),
        "custom_indicators": config.indicators.as_json() if config.indicators is not None else None,
        "reference_notional_quote": format(reference_notional, "f"),
        "assumed_roundtrip_cost_quote": format(costs, "f"),
        "stop_distance_bps": format(stop_distance_bps, "f"),
        "target_distances_bps": [format(d, "f") for d in target_distances_bps],
        "results": results, "windows": windows,
        "same_decision_slots_for_both_strategies": True,
        "future_mark_interval_hours": 1,
        "funding_settlement_verified": False, "intrabar_path_verified": False,
        "liquidation_verified": False, "exchange_fills_verified": False,
        "out_of_sample_results_validated": False,
        "financial_backtest_approved": False, "orders_sent": False,
        "approved_for_live_use": False,
    }
