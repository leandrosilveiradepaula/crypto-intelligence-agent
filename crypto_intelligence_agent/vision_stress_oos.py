"""J3 OOS conditional stress audit on historical research data, NEVER real fills."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json

from .market_data import DataValidationError
from .offline_vision_series import assemble_offline_vision_months
from .vision_costed_oos import causal_oos_bar_choice, costed_vision_monthly_oos
from .vision_intrabar_stress import VisionStressAssumptions, stress_vision_candle

_CTX = Context(prec=512)
_ZERO = Decimal(0)


@dataclass(frozen=True)
class MatchedLongBenchmark:
    """LONG on precisely the selected OOS strategy exposure bars."""
    exposures: int
    ambiguous_count: int
    liquidation_possible_count: int
    stop_touched_count: int
    target_touched_count: int
    worst_net_quote: Decimal
    best_net_quote: Decimal
    worst_cumulative_net_over_margin: Decimal
    best_cumulative_net_over_margin: Decimal
    worst_drawdown_proxy_quote: Decimal
    best_drawdown_proxy_quote: Decimal
    max_single_bar_loss_over_margin: Decimal
    strategy_worst_minus_matched_best_quote: Decimal
    strategy_best_minus_matched_worst_quote: Decimal

    def sanitized_report(self) -> dict:
        return {k: str(v) if type(v) is Decimal else v for k,v in vars(self).items()}


@dataclass(frozen=True)
class VisionStressFoldAudit:
    """Monthly OOS observations. Neither branch is an executable fill path."""
    test_month_number: int
    bars_scored: int
    strategy_exposures: int
    benchmark_exposures: int
    strategy_ambiguous_count: int
    benchmark_ambiguous_count: int
    strategy_liquidation_possible_count: int
    benchmark_liquidation_possible_count: int
    strategy_stop_touched_count: int
    strategy_target_touched_count: int
    benchmark_stop_touched_count: int
    benchmark_target_touched_count: int
    strategy_abstention_count: int
    strategy_worst_net_quote: Decimal
    strategy_best_net_quote: Decimal
    benchmark_worst_net_quote: Decimal
    benchmark_best_net_quote: Decimal
    # Sum of conditional net per hypothetical fixed margin for EACH exposure.
    # NOT portfolio ROI, capital compounding or realized liquidation PnL.
    strategy_worst_cumulative_net_over_margin: Decimal
    strategy_best_cumulative_net_over_margin: Decimal
    benchmark_worst_cumulative_net_over_margin: Decimal
    benchmark_best_cumulative_net_over_margin: Decimal
    strategy_worst_drawdown_proxy_quote: Decimal
    strategy_best_drawdown_proxy_quote: Decimal
    benchmark_worst_drawdown_proxy_quote: Decimal
    benchmark_best_drawdown_proxy_quote: Decimal
    strategy_max_single_bar_loss_over_margin: Decimal
    benchmark_max_single_bar_loss_over_margin: Decimal
    decision_fingerprint_sha256: str = ""
    matched_long: MatchedLongBenchmark | None = None

    def sanitized_report(self) -> dict:
        return {
            key: (value.sanitized_report() if type(value) is MatchedLongBenchmark
                  else str(value) if type(value) is Decimal else value)
            for key, value in vars(self).items()
        }


@dataclass(frozen=True)
class VisionStressOOS:
    stressed_count: int
    ambiguous_count: int
    liquidation_possible_count: int
    worst_net_quote: Decimal
    best_net_quote: Decimal
    digest_sha256: str
    benchmark_worst_net_quote: Decimal = _ZERO
    benchmark_best_net_quote: Decimal = _ZERO
    worst_drawdown_proxy_quote: Decimal = _ZERO
    best_drawdown_proxy_quote: Decimal = _ZERO
    benchmark_worst_drawdown_proxy_quote: Decimal = _ZERO
    benchmark_best_drawdown_proxy_quote: Decimal = _ZERO
    fold_reports: tuple[VisionStressFoldAudit, ...] = ()
    benchmark_ambiguous_count: int = 0
    benchmark_liquidation_possible_count: int = 0
    strategy_max_single_bar_loss_over_margin: Decimal = _ZERO
    benchmark_max_single_bar_loss_over_margin: Decimal = _ZERO
    stop_touched_count: int = 0
    target_touched_count: int = 0
    abstention_count: int = 0
    benchmark_stop_touched_count: int = 0
    benchmark_target_touched_count: int = 0
    strategy_worst_cumulative_net_over_margin: Decimal = _ZERO
    strategy_best_cumulative_net_over_margin: Decimal = _ZERO
    benchmark_worst_cumulative_net_over_margin: Decimal = _ZERO
    benchmark_best_cumulative_net_over_margin: Decimal = _ZERO
    decision_fingerprint_sha256: str = ""
    matched_long: MatchedLongBenchmark | None = None

    def sanitized_report(self) -> dict:
        return {
            "status": "offline_oos_conditional_intrabar_stress_only",
            "stressed_count": self.stressed_count,
            "ambiguous_count": self.ambiguous_count,
            "liquidation_possible_count": self.liquidation_possible_count,
            "worst_net_quote": str(self.worst_net_quote),
            "best_net_quote": str(self.best_net_quote),
            "benchmark_worst_net_quote": str(self.benchmark_worst_net_quote),
            "benchmark_best_net_quote": str(self.benchmark_best_net_quote),
            "worst_drawdown_proxy_quote": str(self.worst_drawdown_proxy_quote),
            "best_drawdown_proxy_quote": str(self.best_drawdown_proxy_quote),
            "benchmark_worst_drawdown_proxy_quote": str(self.benchmark_worst_drawdown_proxy_quote),
            "benchmark_best_drawdown_proxy_quote": str(self.benchmark_best_drawdown_proxy_quote),
            "strategy_max_single_bar_loss_over_margin": str(self.strategy_max_single_bar_loss_over_margin),
            "benchmark_max_single_bar_loss_over_margin": str(self.benchmark_max_single_bar_loss_over_margin),
            "benchmark_ambiguous_count": self.benchmark_ambiguous_count,
            "benchmark_liquidation_possible_count": self.benchmark_liquidation_possible_count,
            "stop_touched_count": self.stop_touched_count,
            "target_touched_count": self.target_touched_count,
            "abstention_count": self.abstention_count,
            "benchmark_stop_touched_count": self.benchmark_stop_touched_count,
            "benchmark_target_touched_count": self.benchmark_target_touched_count,
            "strategy_worst_cumulative_net_over_margin": str(self.strategy_worst_cumulative_net_over_margin),
            "strategy_best_cumulative_net_over_margin": str(self.strategy_best_cumulative_net_over_margin),
            "benchmark_worst_cumulative_net_over_margin": str(self.benchmark_worst_cumulative_net_over_margin),
            "benchmark_best_cumulative_net_over_margin": str(self.benchmark_best_cumulative_net_over_margin),
            "fold_coverage": [fold.sanitized_report() for fold in self.fold_reports],
            "digest_sha256": self.digest_sha256,
            "decision_fingerprint_sha256": self.decision_fingerprint_sha256,
            "matched_long": (self.matched_long.sanitized_report()
                             if self.matched_long is not None else None),
            "financial_backtest_approved": False,
            "marketwide_top50_verified": False,
            "source_authenticated": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def audit_costed_vision_intrabar_oos(
    month_groups: tuple[tuple, ...], *, as_of_ms: int,
    cost_bps_per_side: Decimal, assumptions: VisionStressAssumptions,
) -> VisionStressOOS:
    if type(assumptions) is not VisionStressAssumptions:
        raise DataValidationError("explicit synthetic stress assumptions required")
    baseline = costed_vision_monthly_oos(
        month_groups, as_of_ms=as_of_ms, cost_bps_per_side=cost_bps_per_side)
    series = tuple(
        assemble_offline_vision_months(group, as_of_ms=as_of_ms)
        for group in month_groups
    )
    bounds = [0]
    for month in month_groups[0]:
        bounds.append(bounds[-1] + len(month.candles))
    with localcontext(_CTX):
        totals = [_ZERO for _ in range(4)]
        equities = [_ZERO for _ in range(4)]
        peaks = [_ZERO for _ in range(4)]
        drawdowns = [_ZERO for _ in range(4)]
        matched_totals = [_ZERO, _ZERO]
        matched_equities = [_ZERO, _ZERO]
        matched_peaks = [_ZERO, _ZERO]
        matched_drawdowns = [_ZERO, _ZERO]
        n = ambiguous = liquidations = benchmark_ambiguous = benchmark_liquidations = 0
        stops = targets = abstentions = benchmark_stops = benchmark_targets = 0
        strategy_max_loss = benchmark_max_loss = matched_max_loss = _ZERO
        matched_amb = matched_liq = matched_stops = matched_targets = 0
        folds = []
        decision_digest = sha256()
        digest = sha256()
        digest.update(json.dumps([
            "vision-stress-oos-v2", baseline.digest_sha256,
            sorted(s.series_manifest_sha256 for s in series),
            as_of_ms, str(cost_bps_per_side),
            str(assumptions.margin.requested_margin_quote),
            assumptions.margin.leverage_at_intent,
            str(assumptions.margin.entry_notional_quote),
            assumptions.margin.quote_currency,
            *[str(getattr(assumptions, attr)) for attr in (
                "stop_fraction", "target_fraction", "maintenance_bps",
                "entry_fee_bps", "exit_fee_bps", "entry_slippage_bps",
                "exit_slippage_bps", "signed_funding_bps")],
        ], separators=(",", ":")).encode("ascii"))

        def track(index: int, change: Decimal, monthly_eq: list,
                  monthly_peak: list, monthly_dd: list) -> None:
            totals[index] += change
            equities[index] += change
            peaks[index] = max(peaks[index], equities[index])
            drawdowns[index] = min(drawdowns[index], equities[index] - peaks[index])
            monthly_eq[index] += change
            monthly_peak[index] = max(monthly_peak[index], monthly_eq[index])
            monthly_dd[index] = min(monthly_dd[index], monthly_eq[index] - monthly_peak[index])

        def matched_track(index: int, change: Decimal, eq: list,
                          peak: list, dd: list) -> None:
            matched_totals[index] += change
            matched_equities[index] += change
            matched_peaks[index] = max(matched_peaks[index], matched_equities[index])
            matched_drawdowns[index] = min(
                matched_drawdowns[index], matched_equities[index] - matched_peaks[index])
            eq[index] += change
            peak[index] = max(peak[index], eq[index])
            dd[index] = min(dd[index], eq[index] - peak[index])

        for k, fold in enumerate(baseline.folds, 1):
            fold_decision_digest = sha256()
            month_totals_start = totals.copy()
            monthly_eq = [_ZERO for _ in range(4)]
            monthly_peak = [_ZERO for _ in range(4)]
            monthly_dd = [_ZERO for _ in range(4)]
            matched_start = matched_totals.copy()
            matched_eq = [_ZERO, _ZERO]
            matched_peak = [_ZERO, _ZERO]
            matched_dd = [_ZERO, _ZERO]
            m_amb = m_liq = m_stop = m_target = 0
            fold_matched_max = _ZERO
            bars = exposures = amb = liq = b_amb = b_liq = 0
            stop = target = abstain = b_stop = b_target = 0
            fold_strategy_max_loss = fold_benchmark_max_loss = _ZERO
            for i in range(bounds[k], bounds[k + 1]):
                # Prior 24 CLOSED hourly bars only, never the target bar.
                selected_index, direction = causal_oos_bar_choice(series, i)
                selected = series[selected_index].candles
                # This trail is independent of leverage/costs and covers
                # abstentions too. An opaque per-series identity is sufficient
                # for equality; no symbol/path/price is emitted.
                action = ("abstain" if direction == 0 or
                          fold.selected_rule == "abstain" else
                          ("long" if (direction > 0) ==
                           (fold.selected_rule == "continuation") else "short"))
                event = json.dumps([
                    "j3-pre24-decision-v1", k, i,
                    series[selected_index].series_manifest_sha256,
                    direction, fold.selected_rule, action,
                ], separators=(",", ":")).encode("ascii") + b"\n"
                fold_decision_digest.update(event)
                decision_digest.update(event)
                bars += 1
                # Fixed LONG benchmark observes every OOS bar, even while the
                # trained strategy abstains. Exposure counts disclose asymmetry.
                benchmark = stress_vision_candle(
                    selected[i], long=True, assumptions=assumptions)
                track(2, benchmark.worst_net_quote, monthly_eq, monthly_peak, monthly_dd)
                track(3, benchmark.best_net_quote, monthly_eq, monthly_peak, monthly_dd)
                b_amb += int(benchmark.intrabar_ambiguous)
                b_liq += int(benchmark.touched_liquidation_proxy)
                b_stop += int(benchmark.touched_stop)
                b_target += int(benchmark.touched_target)
                fold_benchmark_max_loss = max(
                    fold_benchmark_max_loss,
                    -benchmark.worst_net_quote / assumptions.margin.requested_margin_quote,
                    _ZERO)
                if direction == 0 or fold.selected_rule == "abstain":
                    abstain += 1
                    continue
                # Reuse exactly the existing LONG result for this selected
                # bar, but record it only when the strategy actually exposes.
                matched_track(0, benchmark.worst_net_quote,
                              matched_eq, matched_peak, matched_dd)
                matched_track(1, benchmark.best_net_quote,
                              matched_eq, matched_peak, matched_dd)
                m_amb += int(benchmark.intrabar_ambiguous)
                m_liq += int(benchmark.touched_liquidation_proxy)
                m_stop += int(benchmark.touched_stop)
                m_target += int(benchmark.touched_target)
                fold_matched_max = max(
                    fold_matched_max,
                    -benchmark.worst_net_quote / assumptions.margin.requested_margin_quote,
                    _ZERO)
                long = (direction > 0) == (fold.selected_rule == "continuation")
                outcome = stress_vision_candle(selected[i], long=long,
                                               assumptions=assumptions)
                exposures += 1
                amb += int(outcome.intrabar_ambiguous)
                liq += int(outcome.touched_liquidation_proxy)
                stop += int(outcome.touched_stop)
                target += int(outcome.touched_target)
                track(0, outcome.worst_net_quote, monthly_eq, monthly_peak, monthly_dd)
                track(1, outcome.best_net_quote, monthly_eq, monthly_peak, monthly_dd)
                fold_strategy_max_loss = max(
                    fold_strategy_max_loss,
                    -outcome.worst_net_quote / assumptions.margin.requested_margin_quote,
                    _ZERO)
                digest.update(json.dumps([
                    k, i, int(long),
                    str(outcome.worst_net_quote), str(outcome.best_net_quote),
                    int(outcome.intrabar_ambiguous),
                    int(outcome.touched_liquidation_proxy),
                ], separators=(",", ":")).encode("ascii") + b"\n")
            n += exposures
            ambiguous += amb
            liquidations += liq
            benchmark_ambiguous += b_amb
            benchmark_liquidations += b_liq
            stops += stop
            targets += target
            abstentions += abstain
            benchmark_stops += b_stop
            benchmark_targets += b_target
            strategy_max_loss = max(strategy_max_loss, fold_strategy_max_loss)
            benchmark_max_loss = max(benchmark_max_loss, fold_benchmark_max_loss)
            matched_amb += m_amb
            matched_liq += m_liq
            matched_stops += m_stop
            matched_targets += m_target
            matched_max_loss = max(matched_max_loss, fold_matched_max)
            month_nets = tuple(totals[j] - month_totals_start[j] for j in range(4))
            margin_quote = assumptions.margin.requested_margin_quote
            m_nets = tuple(matched_totals[j] - matched_start[j] for j in range(2))
            fold_matched = MatchedLongBenchmark(
                exposures, m_amb, m_liq, m_stop, m_target,
                *m_nets, *(v / margin_quote for v in m_nets),
                *matched_dd, fold_matched_max,
                month_nets[0] - m_nets[1], month_nets[1] - m_nets[0])
            fold_audit = VisionStressFoldAudit(
                k, bars, exposures, bars, amb, b_amb, liq, b_liq,
                stop, target, b_stop, b_target, abstain,
                *month_nets,
                *(net / margin_quote for net in month_nets),
                *monthly_dd, fold_strategy_max_loss, fold_benchmark_max_loss,
                fold_decision_digest.hexdigest(), fold_matched)
            folds.append(fold_audit)
            # Keep the historical PRE21 financial digest byte-compatible:
            # the new selection commitment has its OWN independent field.
            legacy_fold = fold_audit.sanitized_report()
            legacy_fold.pop("decision_fingerprint_sha256")
            legacy_fold.pop("matched_long")
            digest.update(json.dumps(
                legacy_fold, sort_keys=True,
                separators=(",", ":")).encode("ascii"))
        margin_quote = assumptions.margin.requested_margin_quote
        matched_aggregate = MatchedLongBenchmark(
            n, matched_amb, matched_liq, matched_stops, matched_targets,
            *matched_totals, *(v / margin_quote for v in matched_totals),
            *matched_drawdowns, matched_max_loss,
            totals[0] - matched_totals[1], totals[1] - matched_totals[0])
        return VisionStressOOS(
            n, ambiguous, liquidations, totals[0], totals[1], digest.hexdigest(),
            totals[2], totals[3], drawdowns[0], drawdowns[1],
            drawdowns[2], drawdowns[3], tuple(folds),
            benchmark_ambiguous, benchmark_liquidations,
            strategy_max_loss, benchmark_max_loss,
            stops, targets, abstentions, benchmark_stops, benchmark_targets,
            *(net / assumptions.margin.requested_margin_quote for net in totals),
            decision_fingerprint_sha256=decision_digest.hexdigest(),
            matched_long=matched_aggregate)
