"""J3/PRE5 offline OOS replay: prefix isolation and non-trading contracts."""
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError, MARKET
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, research_synthetic_compression_breakouts,
)
from crypto_intelligence_agent.synthetic_label_purging import (
    SyntheticLabelHorizonConfig, purge_synthetic_label_horizons,
)
from crypto_intelligence_agent.synthetic_oos_replay import (
    DirectionalObservation, audit_synthetic_oos_hypotheses,
)
from crypto_intelligence_agent.synthetic_walk_forward import (
    SyntheticWalkForwardConfig, plan_synthetic_walk_forward,
)

D = Decimal
H = 3_600_000
LONG = (
    ("100","110","90","10"), ("101","111","91","10"),
    ("101","102","100","10"), ("101","102","100","10"),
    ("101","102","100","10"), ("105","106","101","50"),
    ("111","112","104","100"),
)
SHORT = (
    ("100","110","90","10"), ("99","109","89","10"),
    ("99","100","98","10"), ("99","100","98","10"),
    ("99","100","98","10"), ("95","99","94","50"),
    ("90","96","89","100"),
)


def candles(spec=LONG, n=12):
    values = list(spec)
    while len(values) < n:
        c = values[-1][0]
        values.append((c, str(D(c)+1), str(D(c)-1), "10"))
    return tuple(ClosedCandle(
        exchange="fixture_exchange", market=MARKET, symbol="BTCUSDT",
        interval="1h", open_time_ms=(10+i)*H,
        close_time_ms=(11+i)*H-1, open=D(close), high=D(high),
        low=D(low), close=D(close), base_volume=D(1),
        quote_volume=D(volume), quality="synthetic_fixture",
    ) for i, (close, high, low, volume) in enumerate(values))


def strategy():
    return CompressionBreakoutConfig(
        features=FeatureConfig(2, 2, 2, 2), compression_bars=2,
        baseline_bars=2, max_atr_ratio=D("0.6"),
        min_quote_volume_ratio=D(2), cooldown_bars=1,
    )


def build(cs):
    p = plan_synthetic_walk_forward(
        cs, config=SyntheticWalkForwardConfig(4, 1, 2, 2),
        decision_at_ms=cs[-1].close_time_ms+1000,
    )
    h = SyntheticLabelHorizonConfig(1)
    return p, purge_synthetic_label_horizons(cs, plan=p, config=h), h


def audit(cs, **overrides):
    p, q, h = build(cs)
    args = dict(plan=p, purged=q, horizon=h, strategy=strategy())
    args.update(overrides)
    return audit_synthetic_oos_hypotheses(cs, **args)


class SyntheticOOSReplayTests(unittest.TestCase):
    def test_long_reference_and_abstentions(self):
        a = audit(candles())
        self.assertEqual(a.quality, "synthetic_fixture_ex_post_only")
        self.assertEqual([f.eligible_indices for f in a.folds], [(5,), (7,), (9,)])
        self.assertEqual(a.folds[0].abstained_indices, ())
        self.assertEqual([o.outcome for o in a.folds[0].observations],
                         [DirectionalObservation.ALIGNED])
        x = a.folds[0].observations[0]
        self.assertEqual((x.candidate_index, x.outcome_index), (5, 6))
        self.assertEqual(x.hypothesis.close, D(105))
        self.assertEqual(x.hypothesis.earliest_research_at_ms,
                         candles()[5].close_time_ms+1000)
        self.assertFalse(a.financial_backtest_approved)
        self.assertFalse(a.out_of_sample_results_validated)
        self.assertFalse(a.approved_for_live_use)
        self.assertFalse(a.orders_sent)
        self.assertFalse(hasattr(a, "pnl"))

    def test_short_and_future_changes_do_not_rewrite_signal(self):
        cs = candles(SHORT)
        first = audit(cs).folds[0].observations[0]
        self.assertEqual(first.outcome, DirectionalObservation.ALIGNED)
        changed = cs[:6] + (replace(cs[6], open=D(100), high=D(101),
                                   low=D(99), close=D(100)),) + cs[7:]
        other = audit(changed).folds[0].observations[0]
        self.assertEqual(first.hypothesis, other.hypothesis)
        self.assertEqual(other.outcome, DirectionalObservation.CONTRARY)

    def test_unchanged_future_has_separate_category(self):
        cs = candles()
        changed = cs[:6] + (replace(cs[6], open=D(105), high=D(106),
                                   low=D(104), close=D(105)),) + cs[7:]
        a = audit(changed)
        self.assertEqual(a.folds[0].observations[0].outcome,
                         DirectionalObservation.UNCHANGED)

    def test_engine_sees_only_causally_closed_prefix(self):
        cs = candles()
        seen = []
        def spy(prefix, *, config, decision_at_ms, close_safety_ms):
            seen.append((len(prefix), decision_at_ms, prefix[-1].close_time_ms))
            return research_synthetic_compression_breakouts(
                prefix, config=config, decision_at_ms=decision_at_ms,
                close_safety_ms=close_safety_ms,
            )
        with patch("crypto_intelligence_agent.synthetic_oos_replay.research_synthetic_compression_breakouts",
                   side_effect=spy):
            audit(cs)
        self.assertEqual([x[0] for x in seen], [6, 8, 10])
        self.assertTrue(all(t == end+1000 for _, t, end in seen))

    def test_inconsistent_purged_or_plan_fail_closed(self):
        cs = candles()
        p, q, h = build(cs)
        with self.assertRaises(DataValidationError):
            audit(cs, purged=replace(q, folds=q.folds[:-1]))
        with self.assertRaises(DataValidationError):
            audit(cs, plan=replace(p, folds=p.folds[:-1]))
        with self.assertRaises(DataValidationError):
            audit(cs, strategy="unverified")
        with self.assertRaises(DataValidationError):
            audit(cs, horizon="1")
        with self.assertRaises(DataValidationError):
            audit(cs[:-1], plan=p, purged=q, horizon=h)
        bad = cs[:3] + (replace(cs[3], symbol="ETHUSDT"),) + cs[4:]
        with self.assertRaises(DataValidationError):
            audit(bad, plan=p, purged=q, horizon=h)

    def test_no_network_or_orders_and_reproducibility(self):
        cs = candles()
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                self.assertEqual(audit(cs), audit(cs))


if __name__ == "__main__":
    unittest.main()
