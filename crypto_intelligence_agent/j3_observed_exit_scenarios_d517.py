"""D517: conditional stop and partial-exit scenarios on observed OHLC bars.

A trade-range candle is not a mark-price tick, an order fill, or the actual
intrabar path. Evaluate two explicit extrema orderings, never choose the
favorable ordering, never attach fabricated timestamps or write a ledger.
The next observed open is the entry reference, not an executable quote.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .market_data import ClosedCandle, DataGapError, DataValidationError, interval_duration_ms
from .j4_automatic_entry_materializer_d448 import PaperEntryExitPolicy
from .synthetic_cost_scenarios import (
    BPS_DENOMINATOR, SyntheticCostScenario, evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_margin_envelope import SyntheticMarginBasis
from .synthetic_partial_exits import SyntheticExitPlan, plan_synthetic_partial_exits

SCHEMA = "d517-observed-ohlc-exit-scenarios-v1"
QUALITY = "bybit_public_rest_historical_closed_unverified"
_CTX = Context(prec=128, rounding=ROUND_HALF_EVEN)
_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(frozen=True)
class ResearchStopManagement:
    """D531 next-bar protection only. Entry-price stop is not net breakeven."""
    protect_after_targets: int | None = None
    trail_after_targets: int | None = None
    trail_distance_bps: Decimal | None = None

    def __post_init__(self):
        for n in (self.protect_after_targets,self.trail_after_targets):
            if n is not None and (type(n) is not int or not 1<=n<=8):
                raise DataValidationError("D531 target trigger out of range")
        if (self.trail_after_targets is None)!=(self.trail_distance_bps is None):
            raise DataValidationError("D531 paired trailing parameters required")
        d=self.trail_distance_bps
        if d is not None and (type(d) is not Decimal or not d.is_finite() or not 1<=d<=1000):
            raise DataValidationError("D531 trailing distance invalid")
        if self.protect_after_targets is None and self.trail_after_targets is None:
            raise DataValidationError("D531 explicit stop management required")


@dataclass(frozen=True)
class ExitScenario:
    targets_reached: int
    target_fraction: Decimal
    stopped_fraction: Decimal
    horizon_residual_fraction: Decimal
    gross_reference_quote: Decimal
    assumed_fee_slippage_quote: Decimal
    conditional_before_funding_quote: Decimal
    loss_at_least_requested_margin: bool
    stop_bar_index: int | None = field(default=None, compare=False)


def _validate_path(candles, decision_end_ms, now_ms, research_max_horizon_hours=12):
    if type(research_max_horizon_hours) is not int or research_max_horizon_hours not in (12,72):
        raise DataValidationError("D529 invalid explicit research horizon cap")
    limit = 864 if research_max_horizon_hours == 72 else 720
    if (type(candles) is not tuple or not 1 <= len(candles) <= limit
            or type(decision_end_ms) is not int or type(now_ms) is not int
            or not 0 < decision_end_ms < now_ms
            or any(type(c) is not ClosedCandle for c in candles)):
        raise DataValidationError("D517 bounded observed closed path required")
    first = candles[0]
    if (first.exchange != "bybit_v5_public" or first.market != "linear_perpetual"
            or not first.symbol.endswith("USDT")
            or first.interval not in ("1m", "5m", "15m", "1h")):
        raise DataValidationError("D517 unsupported observed Bybit path")
    duration = interval_duration_ms(first.interval)
    if (research_max_horizon_hours == 72 and first.interval not in ("1h","5m")
            or len(candles) * duration > research_max_horizon_hours * 3_600_000):
        raise DataValidationError("D517/D529 research horizon exceeds explicit cap")
    for i, bar in enumerate(candles):
        if ((bar.exchange, bar.market, bar.symbol, bar.interval) !=
                (first.exchange, first.market, first.symbol, first.interval)
                or bar.quality != QUALITY
                or type(bar.open_time_ms) is not int
                or type(bar.close_time_ms) is not int
                or bar.open_time_ms != decision_end_ms+i*duration
                or bar.open_time_ms % duration
                or bar.close_time_ms != bar.open_time_ms+duration-1
                or bar.close_time_ms >= now_ms):
            raise DataGapError("D517 path has missing, future or mixed candle")
        values = (bar.open, bar.high, bar.low, bar.close)
        if (any(type(v) is not Decimal or not v.is_finite() or v <= 0
                for v in values)
                or bar.low > min(bar.open, bar.close, bar.high)
                or bar.high < max(bar.open, bar.close, bar.low)):
            raise DataValidationError("D517 invalid observed OHLC")
    return candles


def compare_exit_scenarios(
    candles: tuple[ClosedCandle, ...], *,
    direction: ResearchDirection, decision_end_ms: int, now_ms: int,
    margin: SyntheticMarginBasis, policy: PaperEntryExitPolicy,
    research_max_horizon_hours: int = 12,
    management: ResearchStopManagement | None = None,
) -> dict[str, ExitScenario]:
    """Two scenario references, each with conserved normalized exit quantities.

    At an opening gap through the stop, use that observed open (not the better
    stop threshold). A favorable gap uses target levels, not gap improvement.
    Target fractions come from PRE1, including remaining-balance semantics.
    A stop consumes ALL remaining exposure including the runner. Any exposure
    surviving the horizon is marked at the final close with assumed exit
    costs; that is not an instruction to close an actual runner. Fees/slippage
    use PRE2 over initial notional and the weighted exit reference notional.
    """
    if (type(direction) is not ResearchDirection
            or type(policy) is not PaperEntryExitPolicy
            or type(margin) is not SyntheticMarginBasis):
        raise DataValidationError("D517 explicit immutable research terms required")
    if management is not None and (type(management) is not ResearchStopManagement
            or any(n is not None and n>len(policy.target_distances_bps)
                   for n in (management.protect_after_targets,management.trail_after_targets))):
        raise DataValidationError("D531 stop management incompatible with targets")
    bars = _validate_path(candles, decision_end_ms, now_ms, research_max_horizon_hours)
    schedule = plan_synthetic_partial_exits(
        SyntheticExitPlan(_ONE, policy.tranches, policy.runner_floor_percent)
    )
    sign = _ONE if direction is ResearchDirection.LONG else -_ONE
    with localcontext(_CTX):
        entry = bars[0].open
        initial_stop = entry * (_ONE-sign*policy.stop_distance_bps/BPS_DENOMINATOR)
        targets = tuple(entry*(_ONE+sign*d/BPS_DENOMINATOR)
                        for d in policy.target_distances_bps)
        notional = margin.entry_notional_quote

        def run(adverse_first):
            stop = initial_stop
            remaining = _ONE
            target_fraction = stopped_fraction = exit_value = _ZERO
            hit = 0
            stop_bar_index = None

            def stop_at(price, *, gap=False):
                nonlocal remaining, stopped_fraction, exit_value, stop_bar_index
                if remaining and sign*(price-stop) <= 0:
                    exit_value += remaining*(price if gap else stop)
                    stopped_fraction += remaining
                    stop_bar_index = bar_index
                    remaining = _ZERO

            def targets_at(price):
                nonlocal hit, remaining, target_fraction, exit_value
                while (remaining and hit < len(targets)
                       and sign*(price-targets[hit]) >= 0):
                    quantity = schedule.allocations[hit].exit_units
                    if quantity > remaining:
                        raise DataValidationError("D517 exit fraction exceeds remainder")
                    exit_value += quantity*targets[hit]
                    remaining -= quantity
                    target_fraction += quantity
                    hit += 1

            for bar_index, bar in enumerate(bars):
                if not remaining:
                    break
                stop_at(bar.open, gap=True)
                targets_at(bar.open)
                adverse = bar.low if sign > 0 else bar.high
                favorable = bar.high if sign > 0 else bar.low
                if adverse_first:
                    stop_at(adverse)
                    targets_at(favorable)
                else:
                    targets_at(favorable)
                    stop_at(adverse)
                # D531 protection only becomes effective on the NEXT bar,
                # never using a favorable extreme to retroactively stop this bar.
                if remaining and management is not None:
                    def tighten(candidate):
                        return max(stop,candidate) if sign>0 else min(stop,candidate)
                    if (management.protect_after_targets is not None
                            and hit>=management.protect_after_targets):
                        stop=tighten(entry)
                    if (management.trail_after_targets is not None
                            and hit>=management.trail_after_targets):
                        candidate=favorable*(_ONE-sign*management.trail_distance_bps/BPS_DENOMINATOR)
                        stop=tighten(candidate)
            residual = remaining
            exit_value += residual*bars[-1].close
            if target_fraction+stopped_fraction+residual != _ONE:
                raise DataValidationError("D517 normalized quantity not conserved")
            # PRE2 accepts monetary inputs with <=18 decimal places. Round
            # the total exit reference once, not every tranche independently.
            exit_notional = (notional*exit_value/entry).quantize(Decimal("1e-18")).normalize()
            gross = sign*(exit_notional-notional)
            costs = evaluate_synthetic_costs(SyntheticCostScenario(
                direction=direction,
                # These are the accounting horizon boundaries, NOT timestamps
                # assigned to hypothetical intra-bar fills. No funding events.
                entry_at_ms=decision_end_ms, exit_at_ms=bars[-1].close_time_ms,
                entry_hypothetical_notional_quote_units=notional,
                exit_hypothetical_notional_quote_units=exit_notional,
                entry_fee_bps=policy.entry_fee_bps,
                exit_fee_bps=policy.exit_fee_bps,
                entry_adverse_slippage_bps=policy.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=policy.exit_adverse_slippage_bps,
            )).fees_and_slippage_units
            net = gross-costs
            return ExitScenario(hit, target_fraction, stopped_fraction, residual,
                                gross, costs, net, net <= -margin.requested_margin_quote,
                                stop_bar_index)

        return {"adverse_first": run(True), "favorable_first": run(False)}


def empty_replay_totals(*, include_payoff=False) -> dict:
    if type(include_payoff) is not bool:
        raise DataValidationError("D531 explicit payoff flag required")
    return {
        "candidate_count": 0, "complete_path_count": 0, "missing_path_count": 0,
        "ordering_sensitive_count": 0,
        **{name: {"positive_count": 0, "negative_count": 0, "flat_count": 0,
                  "stop_count": 0, "with_targets_count": 0,
                  "residual_at_horizon_count": 0, "loss_at_least_margin_count": 0,
                  "stop_before_tp1_count": 0, "stop_before_tp1_first_hour_count": 0,
                  "stop_before_tp1_then_later_tp1_count": 0, "positive_with_stop_count": 0,
                  "full_path_mae_bps_sum": _ZERO, "full_path_mfe_bps_sum": _ZERO,
                  "gross_reference_quote": _ZERO, "assumed_fee_slippage_quote": _ZERO,
                  "conditional_before_funding_quote": _ZERO,
                  **({"positive_net_quote_sum":_ZERO,"negative_net_quote_sum":_ZERO}
                     if include_payoff else {})}
           for name in ("adverse_first", "favorable_first")},
    }


def accumulate_replay(totals: dict, candles, *, direction, decision_end_ms,
                      now_ms, margin, policy, research_max_horizon_hours=12,
                      management=None) -> None:
    totals["candidate_count"] += 1
    if candles is None:
        totals["missing_path_count"] += 1
        return
    outcomes = compare_exit_scenarios(
        candles, direction=direction, decision_end_ms=decision_end_ms,
        now_ms=now_ms, margin=margin, policy=policy,
        research_max_horizon_hours=research_max_horizon_hours,management=management)
    totals["complete_path_count"] += 1
    totals["ordering_sensitive_count"] += int(
        outcomes["adverse_first"] != outcomes["favorable_first"])
    with localcontext(_CTX):
        entry = candles[0].open
        long = direction is ResearchDirection.LONG
        sign = _ONE if long else -_ONE
        favorable = max(b.high for b in candles) if long else min(b.low for b in candles)
        adverse = min(b.low for b in candles) if long else max(b.high for b in candles)
        mae = max(_ZERO, -sign*(adverse/entry-1)*BPS_DENOMINATOR)
        mfe = max(_ZERO, sign*(favorable/entry-1)*BPS_DENOMINATOR)
        tp1 = entry*(_ONE+sign*policy.target_distances_bps[0]/BPS_DENOMINATOR)
        duration = interval_duration_ms(candles[0].interval)
        for name, result in outcomes.items():
            row = totals[name]
            net = result.conditional_before_funding_quote
            row["positive_count" if net > 0 else "negative_count" if net < 0 else "flat_count"] += 1
            if "positive_net_quote_sum" in row:
                row["positive_net_quote_sum"]+=max(_ZERO,net)
                row["negative_net_quote_sum"]+=max(_ZERO,-net)
            row["stop_count"] += int(result.stopped_fraction > 0)
            row["with_targets_count"] += int(result.targets_reached > 0)
            row["positive_with_stop_count"] += int(result.stopped_fraction > 0 and net > 0)
            row["full_path_mae_bps_sum"] += mae
            row["full_path_mfe_bps_sum"] += mfe
            index = result.stop_bar_index
            if index is not None and result.targets_reached == 0:
                row["stop_before_tp1_count"] += 1
                row["stop_before_tp1_first_hour_count"] += int(index*duration < 3_600_000)
                # Only a strictly later bar touching TP1 counts as recovery.
                row["stop_before_tp1_then_later_tp1_count"] += int(any(
                    sign*((b.high if long else b.low)-tp1) >= 0
                    for b in candles[index+1:]))
            row["residual_at_horizon_count"] += int(result.horizon_residual_fraction > 0)
            row["loss_at_least_margin_count"] += int(result.loss_at_least_requested_margin)
            for key in ("gross_reference_quote", "assumed_fee_slippage_quote",
                        "conditional_before_funding_quote"):
                row[key] += getattr(result, key)


def summarize_replay(totals: dict, *, margin: SyntheticMarginBasis) -> dict:
    count = totals["complete_path_count"]
    result = {k:v for k,v in totals.items() if not isinstance(v, dict)}
    with localcontext(_CTX):
        for name in ("adverse_first", "favorable_first"):
            row = dict(totals[name])
            net = row["conditional_before_funding_quote"]
            for metric in ("mae", "mfe"):
                total = row.pop("full_path_"+metric+"_bps_sum")
                row["mean_full_path_"+metric+"_bps"] = (format((total/count).quantize(Decimal("0.01")), "f") if count else None)
            row["average_before_funding_bps"] = (format(
                (net/margin.entry_notional_quote*BPS_DENOMINATOR/count).quantize(
                    Decimal("0.01")), "f") if count else None)
            if "positive_net_quote_sum" in row:
                gain=row["positive_net_quote_sum"]
                loss=row["negative_net_quote_sum"]
                if gain-loss!=net:
                    raise DataValidationError("D531 inconsistent payoff decomposition")
                def ratio(a,b):
                    return format((a/b).quantize(Decimal("0.0001")),"f") if b else None
                row["profit_factor"]=ratio(gain,loss)
                row["mean_winner_bps"]=ratio(gain*BPS_DENOMINATOR,
                    margin.entry_notional_quote*row["positive_count"])
                row["mean_loser_abs_bps"]=ratio(loss*BPS_DENOMINATOR,
                    margin.entry_notional_quote*row["negative_count"])
                row["payoff_ratio"]=ratio(gain*row["negative_count"],
                    loss*row["positive_count"])
                row["positive_net_quote_sum"]=format(gain,"f") if count else None
                row["negative_net_quote_sum"]=format(loss,"f") if count else None
            for key in ("gross_reference_quote", "assumed_fee_slippage_quote",
                        "conditional_before_funding_quote"):
                row[key] = format(row[key], "f") if count else None
            result[name] = row
    return result
