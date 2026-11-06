"""J3/PRE28: causal direction-adjusted mark correlation is research-only."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D, localcontext
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_portfolio_correlation_gate import (
    SyntheticCorrelationGate, audit_synthetic_causal_correlation,
)
from test_synthetic_portfolio_replay import leg
from test_synthetic_portfolio_risk_limits import limits
from test_synthetic_mark_replay import T


def observe(*legs, cap="0.8", minimum=3, risk=None):
    return audit_synthetic_causal_correlation(
        tuple(legs),
        risk_limits=risk if risk is not None else limits(),
        correlation_gate=SyntheticCorrelationGate(D(cap), minimum),
        as_of_ms=legs[0].ticks[-1].at_ms,
        max_tick_gap_ms=60000,
    )


MARKS = ("100", "100.2", "100.6", "100.1", "100.9", "100.5", "101.2")


class CorrelationResearchGateTests(unittest.TestCase):
    def test_two_aligned_longs_block_only_after_enough_causal_returns(self):
        a, b = leg("alpha", marks=MARKS), leg("beta", marks=MARKS)
        result = observe(a, b)
        self.assertEqual(len(result.checkpoints), len(MARKS))
        self.assertEqual([r.state for r in result.checkpoints[:3]], [
            "insufficient_or_flat_pair_history_abstain"] * 3)
        self.assertEqual(result.checkpoints[3].state,
                         "positive_correlation_limit_exceeded")
        self.assertEqual(result.checkpoints[3].evaluated_pairs, 1)
        self.assertEqual(result.checkpoints[3].max_signed_pair_correlation, D("1"))
        self.assertTrue(all(not x.new_position_research_allowed
                            for x in result.checkpoints))
        self.assertFalse(result.new_position_research_allowed)
        output = result.sanitized_report()
        self.assertFalse(output["live_trading_authorized"])
        self.assertFalse(output["correlation_predicts_liquidation"])
        self.assertFalse(output["orders_sent"])
        self.assertEqual(output["network_requests"], 0)
        self.assertNotIn("fixture_", json.dumps(output))

    def test_same_marks_opposite_side_are_not_positive_coloss(self):
        a=leg("alpha",ResearchDirection.LONG,marks=MARKS)
        b=leg("beta",ResearchDirection.SHORT,marks=MARKS)
        result=observe(a,b)
        self.assertEqual(result.checkpoints[2].state,
                         "insufficient_or_flat_pair_history_abstain")
        self.assertEqual(result.checkpoints[3].state,
                         "within_correlation_limit")
        self.assertEqual(result.checkpoints[3].max_signed_pair_correlation, D("-1"))
        self.assertTrue(result.new_position_research_allowed)

    def test_two_shorts_with_identical_marks_are_correlated_co_loss(self):
        a=leg("alpha",ResearchDirection.SHORT,marks=MARKS)
        b=leg("beta",ResearchDirection.SHORT,marks=MARKS)
        result=observe(a,b)
        self.assertEqual(result.checkpoints[3].state,
                         "positive_correlation_limit_exceeded")

    def test_flat_marks_do_not_create_diversification_evidence(self):
        a=leg("alpha",marks=("100",)*6)
        b=leg("beta",marks=("100",)*6)
        result=observe(a,b)
        self.assertEqual(result.aggregate_state,
                         "insufficient_or_flat_pair_history_abstain")
        self.assertEqual(result.checkpoints[-1].unmeasurable_pairs,1)
        self.assertIsNone(result.checkpoints[-1].max_signed_pair_correlation)
        self.assertFalse(result.new_position_research_allowed)

    def test_future_price_changes_never_rewrite_earlier_gate(self):
        a=leg("alpha",marks=MARKS)
        b=leg("beta",ResearchDirection.SHORT,marks=MARKS)
        changed=list(MARKS)
        changed[-1]="98.5"
        mutated=leg("beta",ResearchDirection.SHORT,marks=tuple(changed))
        baseline=observe(a,b)
        after=observe(a,mutated)
        self.assertEqual(baseline.checkpoints[:-1],after.checkpoints[:-1])

    def test_closed_leg_is_not_treated_as_still_open(self):
        a=leg("alpha",marks=MARKS)
        b=leg("beta",marks=MARKS,
              trades=("100","110","100","100","100","100","100"))
        report=observe(a,b)
        self.assertEqual(report.checkpoints[0].state,
                         "insufficient_or_flat_pair_history_abstain")
        self.assertEqual(report.checkpoints[1].state,"no_open_pair")
        self.assertEqual(report.checkpoints[-1].state,"no_open_pair")
        self.assertTrue(report.new_position_research_allowed)

    def test_prior_breach_is_sticky_and_does_not_claim_live_risk(self):
        a=leg("alpha",marks=MARKS)
        b=leg("beta",marks=MARKS)
        result=observe(a,b,cap="0.99")
        self.assertTrue(all(x.state=="positive_correlation_limit_exceeded"
                            for x in result.checkpoints[3:]))
        self.assertFalse(result.sanitized_report()["net_pnl_verified"])

    def test_existing_risk_and_unknown_liquidation_veto(self):
        a=leg("alpha",marks=MARKS)
        b=leg("beta",ResearchDirection.SHORT,marks=MARKS)
        risk=limits(max_open_gross_notional_quote=D("399"))
        report=observe(a,b,risk=risk)
        self.assertEqual(report.aggregate_state,"existing_portfolio_risk_block")
        self.assertFalse(report.new_position_research_allowed)
        liquidation=leg("alpha",marks=("97","100"),trades=("110","100"),
                        leverage=50,margin="4")
        second=leg("beta",marks=("97","100"),trades=("110","100"),
                   leverage=50,margin="4")
        uncertain=observe(liquidation,second)
        self.assertEqual(uncertain.aggregate_state,"unknown_liquidation_abstain")
        self.assertFalse(uncertain.new_position_research_allowed)

    def test_one_leg_still_respects_existing_global_risk_gate(self):
        a=leg("alpha",marks=MARKS)
        self.assertTrue(observe(a).new_position_research_allowed)
        self.assertEqual(observe(a).aggregate_state,"no_open_pair")
        denied=observe(a,risk=limits(max_entry_gross_notional_quote=D("199")))
        self.assertFalse(denied.new_position_research_allowed)
        self.assertEqual(denied.aggregate_state,"existing_portfolio_risk_block")

    def test_determinism_precision_reordering_and_no_network(self):
        a=leg("alpha",marks=MARKS)
        b=leg("beta",ResearchDirection.SHORT,marks=MARKS)
        expected=observe(a,b)
        self.assertEqual(expected,observe(b,a))
        with patch("socket.create_connection",side_effect=AssertionError("no network")):
            self.assertEqual(expected,observe(a,b))
        for precision in (2,4,28):
            with localcontext() as c:
                c.prec=precision
                self.assertEqual(expected,observe(a,b))

    def test_type_bounds_and_fixture_clocks_fail_closed(self):
        for ratio in (D("NaN"),D("Infinity"),D("-0.1"),D("1.1"),
                      D("1e-19"),1,True,0.8,"0.8"):
            with self.subTest(ratio=ratio),self.assertRaises(DataValidationError):
                SyntheticCorrelationGate(ratio,3)
        for count in (True,0,2,129,3.0,D("3")):
            with self.subTest(count=count),self.assertRaises(DataValidationError):
                SyntheticCorrelationGate(D("0.8"),count)
        with self.assertRaises(DataValidationError):
            observe(leg("alpha"),leg("alpha"))
        with self.assertRaises(DataValidationError):
            audit_synthetic_causal_correlation(
                (leg("alpha"),), risk_limits=limits(),
                correlation_gate=None,as_of_ms=T+4000,max_tick_gap_ms=60000)

    def test_tick_budget_is_bounded_even_when_base_replay_allows_more(self):
        marks=("100",)*257
        a=leg("alpha",marks=marks,trades=marks,
              times=tuple(T+1000*(i+1) for i in range(257)))
        with self.assertRaises(DataValidationError):
            observe(a)


if __name__=="__main__":
    unittest.main()
