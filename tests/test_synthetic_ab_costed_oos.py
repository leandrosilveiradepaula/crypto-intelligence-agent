"""J3 A/B ex-post costed marks, common causal OOS plan, synthetic only."""
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataValidationError,
)
from crypto_intelligence_agent.synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, research_synthetic_compression_breakouts,
)
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_label_purging import (
    SyntheticLabelHorizonConfig, purge_synthetic_label_horizons,
)
from crypto_intelligence_agent.synthetic_trend_pullback import (
    TrendPullbackConfig, research_synthetic_trend_pullbacks,
)
from crypto_intelligence_agent.synthetic_walk_forward import (
    SyntheticWalkForwardConfig, plan_synthetic_walk_forward,
)
from crypto_intelligence_agent.synthetic_ab_costed_oos import (
    SyntheticABCostAssumptions, compare_synthetic_ab_costed_oos,
)

H = 3_600_000
T = 1_800_000_000_000


def candles(closes=(10,11,12,13,12,14,15,15,15,15,15,15)):
    values=[]
    for i,value in enumerate(closes):
        p=D(value)
        values.append(ClosedCandle(
            exchange="bybit", market="linear_perpetual", symbol="BTCUSDT",
            interval="1h", open_time_ms=T+i*H,
            close_time_ms=T+(i+1)*H-1, open=p,
            high=p+D("0.2"), low=p-D("0.2"),
            close=p, base_volume=D(10), quote_volume=D(100),
            quality="synthetic_fixture",
        ))
    return tuple(values)


def config_a():
    return CompressionBreakoutConfig(
        features=FeatureConfig(2,2,2,2),
        compression_bars=2, baseline_bars=2,
        max_atr_ratio=D("0.6"), min_quote_volume_ratio=D(2),
    )


def config_b():
    return TrendPullbackConfig(
        features=FeatureConfig(2,2,2,2),
        min_ema_slope_atr=D("0.01"),
        min_volume_ratio=D("0.5"),
        max_trigger_extension_atr=D(10),
    )


def costs(*, fee="3", slip="2", funding="0"):
    return SyntheticABCostAssumptions(
        entry_notional_quote_units=D(1000),
        entry_fee_bps=D(fee), exit_fee_bps=D(fee),
        entry_slippage_bps=D(slip), exit_slippage_bps=D(slip),
        signed_funding_rate_bps=D(funding),
    )


def setup(cs):
    plan=plan_synthetic_walk_forward(
        cs, config=SyntheticWalkForwardConfig(
            train_bars=3, gap_bars=1, test_bars=3, stride_bars=3,
        ), decision_at_ms=cs[-1].close_time_ms+1000,
    )
    horizon=SyntheticLabelHorizonConfig(1)
    return plan, purge_synthetic_label_horizons(
        cs, plan=plan, config=horizon,
    ), horizon


def audit(cs, **kwargs):
    p,q,h=setup(cs)
    inputs=dict(plan=p, purged=q, horizon=h,
                strategy_a=config_a(), strategy_b=config_b(),
                costs=costs())
    inputs.update(kwargs)
    return compare_synthetic_ab_costed_oos(cs, **inputs)


class ABCommonPurgedFoldTests(unittest.TestCase):
    def test_same_oos_calendar_and_distinct_abstentions(self):
        cs=candles()
        result=audit(cs)
        self.assertEqual(result.folds[0].eligible_indices,(4,5))
        self.assertEqual([x.entry_index for x in result.folds[0].strategy_b], [5])
        self.assertEqual(result.folds[0].strategy_a, ())
        self.assertEqual(result.folds[0].strategy_b[0].outcome_index, 6)
        self.assertEqual(result.folds[0].strategy_b[0].side.value, "LONG")
        report=result.sanitized_report()
        self.assertEqual(report["strategy_a"]["candidate_count"],0)
        self.assertGreaterEqual(report["strategy_b"]["candidate_count"],1)
        self.assertEqual(report["identical_oos_candidate_opportunity_count"],
                         sum(len(f.eligible_indices) for f in result.folds))
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["financial_backtest_approved"])
        self.assertFalse(result.out_of_sample_results_validated)
        self.assertFalse(result.approved_for_live_use)
        self.assertNotIn("BTCUSDT",str(report))

    def test_future_outcome_changes_ex_post_but_never_trigger(self):
        cs=candles()
        before=audit(cs).folds[0].strategy_b[0]
        changed=cs[:6]+(
            replace(cs[6],open=D(9),high=D("9.2"),low=D("8.8"),close=D(9)),
        )+cs[7:]
        after=audit(changed).folds[0].strategy_b[0]
        self.assertEqual(before.observed_at_ms,after.observed_at_ms)
        self.assertEqual(before.entry_index,after.entry_index)
        self.assertEqual(before.side,after.side)
        self.assertGreater(before.ex_post_net_mark_change_quote_units,0)
        self.assertLess(after.ex_post_net_mark_change_quote_units,0)

    def test_same_marks_different_explicit_costs_flip_outcome(self):
        cs=candles()
        a=audit(cs,costs=costs(fee="0",slip="0")).folds[0].strategy_b[0]
        b=audit(cs,costs=costs(fee="1000",slip="0")).folds[0].strategy_b[0]
        self.assertEqual(a.ex_post_gross_mark_change_quote_units,
                         b.ex_post_gross_mark_change_quote_units)
        self.assertEqual(a.assumed_total_signed_cost_quote_units,D(0))
        self.assertGreater(b.assumed_total_signed_cost_quote_units,D(0))
        self.assertLess(b.ex_post_net_mark_change_quote_units,0)
        self.assertFalse(a.financial_backtest_approved)

    def test_assumed_long_funding_positive_is_extra_cost(self):
        cs=candles()
        no=audit(cs,costs=costs(funding="0")).folds[0].strategy_b[0]
        yes=audit(cs,costs=costs(funding="10")).folds[0].strategy_b[0]
        self.assertEqual(
            yes.assumed_total_signed_cost_quote_units -
            no.assumed_total_signed_cost_quote_units, D(1),
        )

    def test_prefix_only_causal_strategy_calls(self):
        cs=candles()
        observations=[]
        def a_spy(prefix, *, config, decision_at_ms, close_safety_ms):
            observations.append(("A",len(prefix),decision_at_ms))
            return research_synthetic_compression_breakouts(
                prefix,config=config,decision_at_ms=decision_at_ms,
                close_safety_ms=close_safety_ms,
            )
        def b_spy(prefix, *, config, decision_at_ms, close_safety_ms):
            observations.append(("B",len(prefix),decision_at_ms))
            return research_synthetic_trend_pullbacks(
                prefix,config=config,decision_at_ms=decision_at_ms,
                close_safety_ms=close_safety_ms,
            )
        with patch("crypto_intelligence_agent.synthetic_ab_costed_oos.research_synthetic_compression_breakouts", side_effect=a_spy):
            with patch("crypto_intelligence_agent.synthetic_ab_costed_oos.research_synthetic_trend_pullbacks", side_effect=b_spy):
                audit(cs)
        self.assertEqual(
            observations[0:4],
            [("A",5,cs[4].close_time_ms+1000),
             ("B",5,cs[4].close_time_ms+1000),
             ("A",6,cs[5].close_time_ms+1000),
             ("B",6,cs[5].close_time_ms+1000)],
        )
        self.assertTrue(all(t==cs[n-1].close_time_ms+1000
                            for _,n,t in observations))

    def test_stale_purged_plan_wrong_type_future_data_fail_closed(self):
        cs=candles()
        p,q,h=setup(cs)
        with self.assertRaises(DataValidationError):
            audit(cs,purged=replace(q,folds=()))
        with self.assertRaises(DataValidationError):
            audit(cs,plan=replace(p,folds=()))
        with self.assertRaises(DataValidationError):
            audit(cs,horizon="future")
        with self.assertRaises(DataValidationError):
            audit(cs,strategy_b="not a strategy")
        with self.assertRaises(DataValidationError):
            audit(cs,costs="unknown")
        with self.assertRaises(DataValidationError):
            audit(cs[:-1],plan=p,purged=q,horizon=h)
        with self.assertRaises(DataValidationError):
            audit(cs[:5]+(replace(cs[5],symbol="ETHUSDT"),)+cs[6:])

    def test_bad_cost_inputs_rejected_no_floats(self):
        for v in (D("NaN"),D(0),-D(1),1000.0):
            with self.subTest(v=v), self.assertRaises(DataValidationError):
                SyntheticABCostAssumptions(
                    entry_notional_quote_units=v,entry_fee_bps=D(1),
                    exit_fee_bps=D(1),entry_slippage_bps=D(1),
                    exit_slippage_bps=D(1),
                )
        for fee in (D("NaN"),D(-1),D("10001"),1.1):
            with self.subTest(fee=fee),self.assertRaises(DataValidationError):
                SyntheticABCostAssumptions(
                    entry_notional_quote_units=D(1000),entry_fee_bps=fee,
                    exit_fee_bps=D(1),entry_slippage_bps=D(1),
                    exit_slippage_bps=D(1),
                )

    def test_offline_determinism_no_external_actions(self):
        cs=candles()
        with patch("urllib.request.urlopen",side_effect=AssertionError("HTTP")):
            with patch("socket.create_connection",side_effect=AssertionError("NET")):
                with patch("sqlite3.connect",side_effect=AssertionError("DB")):
                    self.assertEqual(audit(cs),audit(cs))


if __name__ == "__main__":
    unittest.main()
