"""J3 #375: global synthetic risk limits and liquidation-uncertain gates."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_portfolio_risk_limits import (
    SyntheticPortfolioRiskLimits, audit_synthetic_portfolio_risk,
)
from crypto_intelligence_agent.synthetic_portfolio_replay import (
    replay_synthetic_portfolio,
)
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_synthetic_portfolio_replay import leg
from test_synthetic_mark_replay import T


def limits(**override):
    values = dict(
        max_allocated_margin_quote=D("100"),
        max_margin_per_position_quote=D("50"),
        max_entry_gross_notional_quote=D("1000"),
        max_open_gross_notional_quote=D("1000"),
        max_abs_open_net_notional_quote=D("1000"),
        max_open_notional_per_instrument_quote=D("500"),
        max_open_concentration_fraction=D("1"),
        max_known_prefix_drawdown_quote=D("100"),
        max_leverage_at_entry=50,
    )
    return SyntheticPortfolioRiskLimits(**{**values, **override})


def audit(*legs, rules=None):
    return audit_synthetic_portfolio_risk(
        tuple(legs),limits=rules or limits(),
        as_of_ms=legs[0].ticks[-1].at_ms,max_tick_gap_ms=60000)


class SyntheticPortfolioRiskTests(unittest.TestCase):
    def test_hedged_net_zero_does_not_hide_gross_risk(self):
        a=leg("alpha")
        b=leg("beta",ResearchDirection.SHORT,
              marks=("100","99","101","98"))
        cap=limits(max_open_gross_notional_quote=D("399"))
        result=audit(a,b,rules=cap)
        self.assertEqual(result.aggregate_state,"limits_exceeded")
        self.assertIn("open_gross_notional_exceeded",
                      result.checkpoints[0].violation_codes)
        self.assertEqual(
            replay_synthetic_portfolio((a,b),as_of_ms=T+4000,
                                       max_tick_gap_ms=60000).checkpoints[0].signed_open_notional_quote,
            D("0"))
        self.assertFalse(result.new_position_research_allowed)
        self.assertFalse(result.sanitized_report()["orders_sent"])

    def test_limits_allow_only_research_when_all_checks_satisfied(self):
        a=leg("alpha")
        b=leg("beta",ResearchDirection.SHORT,
              marks=("100","99","101","98"))
        result=audit(a,b)
        self.assertEqual(result.aggregate_state,"within_limits")
        self.assertTrue(result.new_position_research_allowed)
        self.assertTrue(all(c.new_position_research_allowed for c in result.checkpoints))
        self.assertEqual(result,audit(b,a))
        report=result.sanitized_report()
        self.assertNotIn("fixture_pos",str(report))
        self.assertNotIn("fixture_instrument",str(report))
        self.assertFalse(report["live_trading_authorized"])
        self.assertFalse(report["net_pnl_verified"])
        self.assertEqual(report["network_requests"],0)

    def test_entry_margin_notional_and_opening_leverage_are_invariants(self):
        a=leg("alpha",leverage=50,margin="4")
        cases=(
            (limits(max_margin_per_position_quote=D("3")), "margin_per_position_exceeded"),
            (limits(max_allocated_margin_quote=D("3")), "allocated_margin_exceeded"),
            (limits(max_entry_gross_notional_quote=D("199")), "entry_gross_notional_exceeded"),
            (limits(max_open_notional_per_instrument_quote=D("199")),
             "entry_notional_per_instrument_exceeded"),
            (limits(max_leverage_at_entry=49), "opening_leverage_exceeded"),
        )
        for cap,code in cases:
            with self.subTest(code=code):
                result=audit(a,rules=cap)
                self.assertIn(code,result.initial_violation_codes)
                self.assertFalse(result.new_position_research_allowed)
        self.assertEqual(a.plan.margin.leverage_at_intent,50)

    def test_mark_growth_and_concentration_breach_without_double_counting_closed(self):
        a=leg("alpha",marks=("100","101","110","110"),
              trades=("100","100","100","100"))
        b=leg("beta",ResearchDirection.SHORT,
              marks=("100","100","100","100"),
              trades=("100","100","90","100"))
        cap=limits(max_open_notional_per_instrument_quote=D("210"),
                   max_open_concentration_fraction=D("0.6"))
        result=audit(a,b,rules=cap)
        self.assertEqual(result.checkpoints[0].state,"within_limits")
        self.assertEqual(result.checkpoints[1].state,"within_limits")
        self.assertEqual(result.checkpoints[2].state,"limits_exceeded")
        self.assertIn("open_notional_per_instrument_exceeded",
                      result.checkpoints[2].violation_codes)
        self.assertIn("open_concentration_exceeded",
                      result.checkpoints[2].violation_codes)
        self.assertFalse(result.new_position_research_allowed)
        portfolio=replay_synthetic_portfolio((a,b),as_of_ms=T+4000,
                                             max_tick_gap_ms=60000)
        self.assertEqual(portfolio.checkpoints[2].max_open_notional_quote,D("220"))
        self.assertEqual(portfolio.checkpoints[3].max_open_notional_quote,D("220"))
        self.assertEqual(portfolio.checkpoints[3].closed_conditional_count,1)

    def test_drawdown_gate_is_causal_and_sticky(self):
        a=leg("alpha",marks=("100","99","99","100"))
        result=audit(a,rules=limits(max_known_prefix_drawdown_quote=D("1")))
        self.assertEqual(result.checkpoints[0].state,"within_limits")
        self.assertEqual(result.checkpoints[1].state,"limits_exceeded")
        self.assertIn("known_prefix_drawdown_exceeded",
                      result.checkpoints[1].violation_codes)
        self.assertEqual(result.checkpoints[-1].state,"limits_exceeded")

    def test_simultaneous_liquidation_never_assumes_freed_margin_or_loss(self):
        a=leg("alpha",leverage=50,margin="4",marks=("97","100"),trades=("110","100"))
        b=leg("beta",leverage=50,margin="4",marks=("97","100"),trades=("110","100"))
        result=audit(a,b)
        self.assertEqual(result.aggregate_state,"unknown_due_to_liquidation")
        self.assertFalse(result.new_position_research_allowed)
        for c in result.checkpoints:
            self.assertEqual(c.state,"unknown_due_to_liquidation")
            self.assertFalse(c.new_position_research_allowed)
            self.assertIn("unresolved_liquidation",c.violation_codes)
        self.assertEqual(result,audit(b,a))

    def test_decimal_precision_determinism_and_no_network(self):
        a=leg("alpha")
        baseline=audit(a)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            self.assertEqual(baseline,audit(a))
        for precision in (2,4,28):
            with localcontext() as ctx:
                ctx.prec=precision
                self.assertEqual(baseline,audit(a))

    def test_invalid_limits_fail_closed(self):
        bad=[D("NaN"),D("Infinity"),D("-1"),D("0"),1.5,True,"10",D("1e40")]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(DataValidationError):
                    limits(max_allocated_margin_quote=value)
        for value in (D("0"),D("1.01"),D("-0.1"),D("NaN"),D("1e-19"),1.0,True):
            with self.subTest(concentration=value),self.assertRaises(DataValidationError):
                limits(max_open_concentration_fraction=value)
        for value in (0,201,True,D("50"),1.5):
            with self.subTest(leverage=value),self.assertRaises(DataValidationError):
                limits(max_leverage_at_entry=value)
        with self.assertRaises(DataValidationError):
            audit_synthetic_portfolio_risk(
                (leg("alpha"),),limits=None,as_of_ms=T+4000,
                max_tick_gap_ms=60000)


if __name__=="__main__":
    unittest.main()
