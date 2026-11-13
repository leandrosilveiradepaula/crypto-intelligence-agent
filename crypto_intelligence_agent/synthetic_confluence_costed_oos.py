"""J3: synthetic paired OOS ablation of BTC breakout versus confluence.

Only ex-post reference marks, never fills, approved signals or actual PnL.
Both arms share exact purged folds, fixed costs and closed causal prefixes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .synthetic_ab_costed_oos import (
    SyntheticABCostAssumptions, SyntheticABEvent, _event,
)
from .synthetic_entry_confluence import (
    SyntheticConfluenceConfig, ConfluenceDisposition,
    research_synthetic_entry_confluence,
)
from .synthetic_feature_engine import validate_synthetic_closed_candles
from .synthetic_label_purging import (
    SyntheticLabelHorizonConfig, SyntheticPurgedPlan,
    purge_synthetic_label_horizons,
)
from .synthetic_oos_replay import MAX_REPLAY_EVENTS
from .synthetic_walk_forward import SyntheticWalkForwardPlan

_EXACT = Context(prec=512)
_BASE = "btc_breakout_screen"
_CONFLUENCE = "btc_breakout_plus_current_pullback"


@dataclass(frozen=True)
class ConfluenceOOSFold:
    number: int
    eligible_indices: tuple[int, ...]
    baseline_events: tuple[SyntheticABEvent, ...]
    confluence_events: tuple[SyntheticABEvent, ...]


@dataclass(frozen=True)
class ConfluenceOOSComparison:
    folds: tuple[ConfluenceOOSFold, ...]
    evaluated_asset_count: int
    horizon_bars: int

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def out_of_sample_results_validated(self) -> bool:
        return False

    def sanitized_report(self) -> dict[str, object]:
        def arm(events: list[SyntheticABEvent]) -> dict[str, object]:
            with localcontext(_EXACT):
                gross = sum((e.ex_post_gross_mark_change_quote_units for e in events), Decimal(0))
                paid = sum((e.assumed_total_signed_cost_quote_units for e in events), Decimal(0))
                net = sum((e.ex_post_net_mark_change_quote_units for e in events), Decimal(0))
            return {
                "count": len(events),
                "ex_post_gross_mark_units": format(gross, "f"),
                "assumed_cost_units": format(paid, "f"),
                "ex_post_net_mark_units": format(net, "f"),
                "positive_ex_post_net_marks": sum(
                    e.ex_post_net_mark_change_quote_units > 0 for e in events),
            }

        baseline = [e for f in self.folds for e in f.baseline_events]
        confluence = [e for f in self.folds for e in f.confluence_events]
        return {
            "schema_version": "j3-synthetic-confluence-paired-oos-v1",
            "quality": "synthetic_ex_post_reference_only",
            "evaluated_asset_count": self.evaluated_asset_count,
            "folds": len(self.folds),
            "horizon_bars": self.horizon_bars,
            "same_calendar_opportunities": sum(
                len(f.eligible_indices) * self.evaluated_asset_count for f in self.folds),
            "baseline": arm(baseline),
            "confluence": arm(confluence),
            "excluded_by_confluence": len(baseline) - len(confluence),
            "per_fold": [
                {"number": f.number, "opportunity_count": len(f.eligible_indices)
                 * self.evaluated_asset_count,
                 "baseline_count": len(f.baseline_events),
                 "confluence_count": len(f.confluence_events)}
                for f in self.folds
            ],
            "fill_prices_verified": False,
            "intrabar_liquidation_validated": False,
            "fees_and_funding_venue_verified": False,
            "out_of_sample_results_validated": False,
            "financial_backtest_approved": False,
            "approved_for_signals": False,
            "approved_for_live_use": False,
            "orders_sent": False,
            "network_requests": 0,
        }


def compare_synthetic_confluence_costed_oos(
    btc_candles: Sequence[ClosedCandle],
    asset_series: Sequence[Sequence[ClosedCandle]],
    *,
    plan: SyntheticWalkForwardPlan,
    purged: SyntheticPurgedPlan,
    horizon: SyntheticLabelHorizonConfig,
    config: SyntheticConfluenceConfig,
    costs: SyntheticABCostAssumptions,
) -> ConfluenceOOSComparison:
    """Use same candidate times, future-mark horizon and fixed costs for both arms.

    A screen candidate may appear in the baseline, but only an identical
    current-bar pullback vote survives the confluence arm. It cannot add
    candidates. Every candidate decision sees candles through index i only.
    """
    if (type(plan) is not SyntheticWalkForwardPlan
            or type(purged) is not SyntheticPurgedPlan
            or type(horizon) is not SyntheticLabelHorizonConfig
            or type(config) is not SyntheticConfluenceConfig
            or type(costs) is not SyntheticABCostAssumptions
            or type(asset_series) not in (tuple, list)
            or not 1 <= len(asset_series) <= 1000):
        raise DataValidationError("typed bounded synthetic OOS comparison required")

    reference = tuple(btc_candles)
    if not reference or type(reference[0]) is not ClosedCandle:
        raise DataValidationError("BTC closed fixture series required")
    btc = validate_synthetic_closed_candles(
        reference, decision_at_ms=plan.decision_at_ms,
        close_safety_ms=plan.close_safety_ms)
    if btc[0].symbol != "BTCUSDT" or btc[0].quality != "synthetic_fixture":
        raise DataValidationError("BTC synthetic benchmark required")

    assets: list[tuple[ClosedCandle, ...]] = []
    seen = {"BTCUSDT"}
    for source in asset_series:
        if type(source) not in (tuple, list) or not source:
            raise DataValidationError("nonempty asset fixture series required")
        cs = validate_synthetic_closed_candles(
            source, decision_at_ms=plan.decision_at_ms,
            close_safety_ms=plan.close_safety_ms)
        symbol = cs[0].symbol
        if (symbol in seen or len(cs) != len(btc)
                or cs[0].exchange != btc[0].exchange
                or cs[0].market != btc[0].market
                or cs[0].interval != btc[0].interval
                or cs[0].quality != "synthetic_fixture"
                or any(a.open_time_ms != b.open_time_ms
                       or a.close_time_ms != b.close_time_ms
                       for a, b in zip(cs, btc))):
            raise DataValidationError("unique, precisely UTC-aligned synthetic assets required")
        seen.add(symbol)
        assets.append(cs)

    # Revalidate the source's complete timeline and recompute purging before
    # scoring; no user-supplied fold or label boundaries are trusted.
    expected = purge_synthetic_label_horizons(assets[0], plan=plan, config=horizon)
    if purged != expected:
        raise DataValidationError("stale or incompatible purged OOS schedule")
    if sum(len(f.oos_indices) for f in purged.folds) * len(assets) > MAX_REPLAY_EVENTS:
        raise DataValidationError("paired OOS opportunity budget exceeded")

    result = []
    for fold in purged.folds:
        base_events: list[SyntheticABEvent] = []
        confluence_events: list[SyntheticABEvent] = []
        for i in fold.oos_indices:
            at = btc[i].close_time_ms + plan.close_safety_ms
            observation = research_synthetic_entry_confluence(
                btc[:i + 1], tuple(cs[:i + 1] for cs in assets),
                config=config, decision_at_ms=at,
                close_safety_ms=plan.close_safety_ms,
            )
            if observation.last_closed_at_ms != btc[i].close_time_ms:
                raise DataValidationError("research candle does not match OOS timestamp")
            for asset_number, item in enumerate(observation.items):
                if item.breakout_research_rank is None:
                    continue
                series = next((cs for cs in assets if cs[0].symbol == item.symbol), None)
                if series is None or item.breakout_side is None:
                    raise DataValidationError("unmatched current BTC screen candidate")
                event = _event(
                    side=item.breakout_side,
                    signal_close=series[i].close,
                    outcome_close=series[i + horizon.horizon_bars].close,
                    available_at_ms=at,
                    outcome_at_ms=series[i + horizon.horizon_bars].close_time_ms,
                    fold_number=fold.number, entry_index=i,
                    outcome_index=i + horizon.horizon_bars,
                    strategy_id=_BASE, costs=costs,
                )
                base_events.append(event)
                if item.disposition is ConfluenceDisposition.CONFLUENT_RESEARCH_ONLY:
                    confluence_events.append(
                        SyntheticABEvent(
                            fold_number=event.fold_number,
                            entry_index=event.entry_index,
                            outcome_index=event.outcome_index,
                            strategy_id=_CONFLUENCE,
                            side=event.side,
                            observed_at_ms=event.observed_at_ms,
                            matured_at_ms=event.matured_at_ms,
                            ex_post_gross_mark_change_quote_units=event.ex_post_gross_mark_change_quote_units,
                            assumed_total_signed_cost_quote_units=event.assumed_total_signed_cost_quote_units,
                            ex_post_net_mark_change_quote_units=event.ex_post_net_mark_change_quote_units,
                        ))
        result.append(ConfluenceOOSFold(
            number=fold.number, eligible_indices=fold.oos_indices,
            baseline_events=tuple(base_events),
            confluence_events=tuple(confluence_events),
        ))
    return ConfluenceOOSComparison(
        folds=tuple(result), evaluated_asset_count=len(assets),
        horizon_bars=horizon.horizon_bars,
    )
