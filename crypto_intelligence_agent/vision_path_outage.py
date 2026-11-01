"""J3/PRE27: two conditional intrabar paths with unavailable STOP research.

Exact hypothetical arithmetic only. OHLC does not identify actual intrabar
ordering or fill price; liquidation is not a venue margin formula. Never
passes a risk/trading gate and never sends orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json

from .market_data import DataValidationError
from .offline_vision_month import OfflineVisionCandle
from .offline_vision_series import assemble_offline_vision_months
from .vision_costed_oos import causal_oos_bar_choice, costed_vision_monthly_oos
from .vision_intrabar_stress import VisionStressAssumptions, stress_vision_candle
from .vision_stress_sensitivity import VisionStressSensitivity

_CTX = Context(prec=512)
_BPS = Decimal(10000)
_ZERO = Decimal(0)
_PATHS = ("high_first", "low_first")
_STOPS = ("available", "unavailable")


@dataclass(frozen=True)
class PathOutageOutcome:
    path: str
    stop_state: str
    terminal: str
    conditional_net_quote: Decimal
    liquidation_proxy_touched: bool

    def sanitized_report(self) -> dict:
        return {
            "path": self.path, "stop_state": self.stop_state,
            "terminal": self.terminal,
            "conditional_net_quote": str(self.conditional_net_quote),
            "liquidation_proxy_touched": self.liquidation_proxy_touched,
        }


def simulate_vision_path_outage(
    candle: OfflineVisionCandle, *,
    long: bool, assumptions: VisionStressAssumptions,
) -> tuple[PathOutageOutcome, ...]:
    """Conditional OPEN/HIGH/LOW/CLOSE paths, both hypothetical STOP states.

    A crossed threshold is assigned its *assumed* price, not an observed fill.
    The first crossed price is selected; equal crossings give liquidation
    precedence. Gaps, queues, actual stop outages and real funding unknown.
    """
    if (type(candle) is not OfflineVisionCandle or type(long) is not bool
            or type(assumptions) is not VisionStressAssumptions):
        raise DataValidationError("typed hypothetical OHLC path inputs required")
    # Reuse PRE21 validation, but do not use its financial envelope as a fill.
    stress_vision_candle(candle, long=long, assumptions=assumptions)
    with localcontext(_CTX):
        e = candle.open
        margin = assumptions.margin
        n = margin.entry_notional_quote
        q = n / e
        direction = Decimal(1 if long else -1)
        stop = e * (Decimal(1) - direction * assumptions.stop_fraction)
        target = e * (Decimal(1) + direction * assumptions.target_fraction)
        entry_cost = n * (assumptions.entry_fee_bps +
                          assumptions.entry_slippage_bps) / _BPS
        funding = n * assumptions.signed_funding_bps * direction / _BPS
        reserve = n * (assumptions.maintenance_bps +
                       assumptions.exit_fee_bps +
                       assumptions.exit_slippage_bps) / _BPS
        liq = e + direction * (
            reserve + entry_cost + funding -
            margin.requested_margin_quote) / q

        def conditional_net(price: Decimal, liquidation: bool) -> Decimal:
            if liquidation:
                # Same PRE21 conservative liquidation proxy branch:
                # never count a booked fill, never credit favorable funding.
                exit_cost_at_entry = n * (
                    assumptions.exit_fee_bps + assumptions.exit_slippage_bps) / _BPS
                return (-margin.requested_margin_quote - entry_cost
                        - exit_cost_at_entry - max(funding, _ZERO))
            exit_n = q * price
            exit_cost = exit_n * (
                assumptions.exit_fee_bps + assumptions.exit_slippage_bps) / _BPS
            return direction * (price - e) * q - entry_cost - exit_cost - funding

        results = []
        for path, points in (
            ("high_first", (e, candle.high, candle.low, candle.close)),
            ("low_first", (e, candle.low, candle.high, candle.close)),
        ):
            for stop_state in _STOPS:
                levels = [("target", target)]
                if stop_state == "available":
                    levels.append(("stop", stop))
                # The proxy is physically relevant only at a positive level.
                if liq > _ZERO:
                    levels.append(("liquidation_proxy", liq))
                terminal = "close"
                exit_price = candle.close
                for first, second in zip(points, points[1:]):
                    hits = []
                    for name, level in levels:
                        if (first <= level <= second if first <= second
                                else second <= level <= first):
                            distance = abs(level - first)
                            hits.append((distance, 0 if name == "liquidation_proxy"
                                         else 1 if name == "stop" else 2,
                                         name, level))
                    if hits:
                        _, _, terminal, exit_price = min(hits)
                        break
                liquidated = terminal == "liquidation_proxy"
                results.append(PathOutageOutcome(
                    path, stop_state, terminal,
                    conditional_net(exit_price, liquidated), liquidated))
        return tuple(results)


@dataclass(frozen=True)
class PathOutageFold:
    month_number: int
    exposures: int
    losses_vs_legacy_worst: int
    terminal_liquidations: int
    nets: tuple[Decimal, ...]
    worst_drawdowns: tuple[Decimal, ...]

    def sanitized_report(self) -> dict:
        return {
            "test_month_number": self.month_number,
            "exposures": self.exposures,
            "outage_worse_than_legacy_worst_count": self.losses_vs_legacy_worst,
            "terminal_liquidation_proxy_count": self.terminal_liquidations,
            "conditional_net_by_path_stop": [str(x) for x in self.nets],
            "worst_drawdown_by_path_stop": [str(x) for x in self.worst_drawdowns],
        }


@dataclass(frozen=True)
class PathOutageScenario:
    ordinal: int
    leverage_at_intent: int
    selection_fingerprint_sha256: str
    folds: tuple[PathOutageFold, ...]
    net_by_path_stop: tuple[Decimal, ...]
    worst_drawdown_by_path_stop: tuple[Decimal, ...]

    def sanitized_report(self) -> dict:
        return {
            "ordinal": self.ordinal,
            "leverage_at_intent": self.leverage_at_intent,
            "decision_fingerprint_sha256": self.selection_fingerprint_sha256,
            "exposures": sum(f.exposures for f in self.folds),
            "outage_worse_than_legacy_worst_count": sum(
                f.losses_vs_legacy_worst for f in self.folds),
            "conditional_net_by_path_stop": [str(x) for x in self.net_by_path_stop],
            "worst_drawdown_by_path_stop": [str(x) for x in self.worst_drawdown_by_path_stop],
            "folds": [f.sanitized_report() for f in self.folds],
        }


@dataclass(frozen=True)
class PathOutageOOSAudit:
    scenarios: tuple[PathOutageScenario, ...]
    digest_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "j3_pre27_path_outage_oos_v1",
            "status": "hypothetical_intrabar_stop_outage_research_only",
            "path_order": list(_PATHS),
            "stop_state_order": list(_STOPS),
            "scenario_count": len(self.scenarios),
            "same_oos_selection": True,
            "scenarios": [x.sanitized_report() for x in self.scenarios],
            "digest_sha256": self.digest_sha256,
            "intrabar_path_verified": False,
            "fill_price_verified": False,
            "liquidation_formula_verified": False,
            "financial_backtest_approved": False,
            "net_pnl_verified": False,
            "recommended_leverage": None,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }


def audit_vision_oos_path_outage(
    month_groups: tuple[tuple, ...], *,
    as_of_ms: int, cost_bps_per_side: Decimal,
    comparison: VisionStressSensitivity,
) -> PathOutageOOSAudit:
    """Compare four conditional models on the frozen PRE22 OOS decisions.

    Keep PRE21/PRE22 metrics unchanged. Recompute only the selection identity
    from prior closes; compare its commitment against PRE22, fail closed if
    mismatched. No choosing the best among paths or stop-availability states.
    """
    if (type(comparison) is not VisionStressSensitivity
            or not 2 <= len(comparison.scenarios) <= 6):
        raise DataValidationError("typed bounded PRE22 comparison required")
    baseline = costed_vision_monthly_oos(
        month_groups, as_of_ms=as_of_ms, cost_bps_per_side=cost_bps_per_side)
    series = tuple(assemble_offline_vision_months(g, as_of_ms=as_of_ms)
                   for g in month_groups)
    boundaries = [0]
    for month in month_groups[0]:
        boundaries.append(boundaries[-1] + len(month.candles))
    results = []
    with localcontext(_CTX):
        for ordinal, case in enumerate(comparison.scenarios, 1):
            a = case.audit
            if (case.ordinal != ordinal or len(a.fold_reports) != len(baseline.folds)
                    or a.matched_long is None or
                    a.matched_long.exposures != a.stressed_count):
                raise DataValidationError("OOS path comparison evidence mismatch")
            accumulator = [_ZERO] * 4
            equity = [_ZERO] * 4
            peaks = [_ZERO] * 4
            drawdowns = [_ZERO] * 4
            overall_fingerprint = sha256()
            folds = []
            for k, (fold, reference_fold) in enumerate(
                    zip(baseline.folds, a.fold_reports), 1):
                digest = sha256()
                monthly_nets = [_ZERO] * 4
                monthly_eq = [_ZERO] * 4
                monthly_peaks = [_ZERO] * 4
                monthly_dd = [_ZERO] * 4
                exposures = outages = liqs = abstentions = 0
                for i in range(boundaries[k], boundaries[k + 1]):
                    j, direction = causal_oos_bar_choice(series, i)
                    action = ("abstain" if direction == 0 or
                              fold.selected_rule == "abstain" else
                              ("long" if (direction > 0) ==
                               (fold.selected_rule == "continuation") else "short"))
                    event = json.dumps([
                        "j3-pre24-decision-v1", k, i,
                        series[j].series_manifest_sha256,
                        direction, fold.selected_rule, action,
                    ], separators=(",", ":")).encode("ascii") + b"\n"
                    digest.update(event)
                    overall_fingerprint.update(event)
                    if action == "abstain":
                        abstentions += 1
                        continue
                    exposures += 1
                    long = action == "long"
                    bar = series[j].candles[i]
                    outcomes = simulate_vision_path_outage(
                        bar, long=long, assumptions=case.assumptions)
                    original = stress_vision_candle(
                        bar, long=long, assumptions=case.assumptions)
                    if min(o.conditional_net_quote for o in outcomes
                           if o.stop_state == "unavailable") < original.worst_net_quote:
                        outages += 1
                    liqs += sum(x.liquidation_proxy_touched for x in outcomes)
                    for idx, event_outcome in enumerate(outcomes):
                        pnl = event_outcome.conditional_net_quote
                        accumulator[idx] += pnl
                        equity[idx] += pnl
                        peaks[idx] = max(peaks[idx], equity[idx])
                        drawdowns[idx] = min(drawdowns[idx], equity[idx] - peaks[idx])
                        monthly_nets[idx] += pnl
                        monthly_eq[idx] += pnl
                        monthly_peaks[idx] = max(monthly_peaks[idx], monthly_eq[idx])
                        monthly_dd[idx] = min(monthly_dd[idx],
                                              monthly_eq[idx] - monthly_peaks[idx])
                if (reference_fold.decision_fingerprint_sha256 != digest.hexdigest()
                        or reference_fold.test_month_number != k
                        or reference_fold.bars_scored != boundaries[k+1]-boundaries[k]
                        or reference_fold.strategy_exposures != exposures
                        or reference_fold.strategy_abstention_count != abstentions):
                    raise DataValidationError("conditional path changed frozen OOS fold selection")
                folds.append(PathOutageFold(
                    k, exposures, outages, liqs,
                    tuple(monthly_nets), tuple(monthly_dd)))
            if (a.decision_fingerprint_sha256 != overall_fingerprint.hexdigest()
                    or sum(x.exposures for x in folds) != a.stressed_count):
                raise DataValidationError("conditional path changed OOS decisions")
            results.append(PathOutageScenario(
                ordinal, case.assumptions.margin.leverage_at_intent,
                overall_fingerprint.hexdigest(), tuple(folds),
                tuple(accumulator), tuple(drawdowns)))
        payload = {
            "schema": "j3_pre27_path_outage_oos_v1",
            "source": comparison.digest_sha256,
            "scenarios": [x.sanitized_report() for x in results],
        }
        digest = sha256(json.dumps(
            payload, separators=(",", ":"), sort_keys=True).encode("ascii")).hexdigest()
    return PathOutageOOSAudit(tuple(results), digest)
