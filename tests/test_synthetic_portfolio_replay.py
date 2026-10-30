"""J3 #373: synthetic multi-leg reconciliation, not fills, orders or PnL."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_portfolio_replay import (
    SyntheticPortfolioLeg,replay_synthetic_portfolio,
)
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from test_synthetic_mark_replay import T, plan, tick
from test_synthetic_funding_calendar import calendar,paid
from test_synthetic_risk_tiers import snapshot,tier


def leg(name,side=ResearchDirection.LONG,marks=("100","101","99","102"),
        trades=None,leverage=10,margin="20", funding=(),funding_calendar=None,
        risk_snapshots=None,times=None):
    if trades is None:
        trades=("100",)*len(marks)
    if times is None:
        times=tuple(T+1000*(i+1) for i in range(len(marks)))
    p=replace(plan(side,leverage=leverage,margin=margin),
              instrument_id="fixture_instrument_"+name)
    ticks=tuple(tick(mark,trade,at) for mark,trade,at in zip(marks,trades,times))
    if risk_snapshots is not None:
        risk_snapshots=tuple(replace(s,instrument_id=p.instrument_id)
                             for s in risk_snapshots)
    if funding_calendar is not None:
        funding_calendar=replace(funding_calendar,instrument_id=p.instrument_id)
    return SyntheticPortfolioLeg("fixture_pos_"+name,p,ticks,tuple(funding),
                                funding_calendar,risk_snapshots)


def audit(*legs,max_gap=60000,max_age=None):
    return replay_synthetic_portfolio(tuple(legs),as_of_ms=legs[0].ticks[-1].at_ms,
                                     max_tick_gap_ms=max_gap,
                                     max_risk_snapshot_age_ms=max_age)


class SyntheticPortfolioTests(unittest.TestCase):
    def test_multiple_open_legs_margin_exposure_and_order_determinism(self):
        a=leg("alpha")
        b=leg("beta",ResearchDirection.SHORT,
              marks=("100","99","101","98"))
        result=audit(a,b)
        self.assertEqual(result,audit(b,a))
        self.assertEqual(result.checkpoints[0].hypothetical_equity_quote,D("39.2"))
        self.assertEqual(result.checkpoints[0].gross_open_notional_quote,D("400"))
        self.assertEqual(result.checkpoints[0].signed_open_notional_quote,D("0"))
        self.assertEqual(result.checkpoints[0].max_open_concentration,D("0.5"))
        self.assertEqual(result.checkpoints[0].open_count,2)
        self.assertEqual(result.checkpoints[-1].open_count,2)
        self.assertTrue(result.complete_equity_path)
        self.assertLessEqual(result.known_prefix_drawdown_quote,D("0"))
        self.assertIsNotNone(result.pairwise_mark_return_correlation_min)
        self.assertLess(result.pairwise_mark_return_correlation_min,D("0"))
        report=result.sanitized_report()
        self.assertNotIn("fixture_pos",str(report))
        self.assertNotIn("fixture_instrument",str(report))
        self.assertFalse(report["financial_backtest_approved"])
        self.assertFalse(report["net_pnl_verified"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(report["network_requests"],0)

    def test_terminal_condition_carried_once_without_double_count(self):
        a=leg("alpha",trades=("100","110","100","100"))
        b=leg("beta",ResearchDirection.SHORT,trades=("100","100","90","100"))
        result=audit(a,b)
        self.assertEqual(result.checkpoints[0].open_count,2)
        self.assertEqual(result.checkpoints[1].closed_conditional_count,1)
        self.assertEqual(result.checkpoints[1].open_count,1)
        self.assertEqual(result.checkpoints[2].closed_conditional_count,2)
        self.assertEqual(result.checkpoints[2].gross_open_notional_quote,D("0"))
        self.assertIsNone(result.checkpoints[2].max_open_concentration)
        self.assertEqual(result.checkpoints[2].hypothetical_equity_quote,
                         result.checkpoints[3].hypothetical_equity_quote)
        self.assertEqual(result.checkpoints[2].conditional_net_from_entry_quote,
                         result.checkpoints[3].conditional_net_from_entry_quote)

    def test_liquidation_and_simultaneous_target_cannot_be_summed_as_pnl(self):
        a=leg("alpha",marks=("97","100"),trades=("110","100"),
              leverage=50,margin="4")
        b=leg("beta",ResearchDirection.SHORT,marks=("100","100"),
              trades=("100","100"))
        result=audit(a,b)
        self.assertFalse(result.complete_equity_path)
        for row in result.checkpoints:
            self.assertIsNone(row.hypothetical_equity_quote)
            self.assertIsNone(row.conditional_net_from_entry_quote)
            self.assertIsNone(row.gross_open_notional_quote)
            self.assertGreaterEqual(row.unresolved_liquidation_count,1)
        self.assertEqual(result.known_prefix_drawdown_quote,D("0"))
        self.assertFalse(result.sanitized_report()["liquidation_formula_verified"])

    def test_funding_events_and_pit_tiers_can_coexist(self):
        times=(T+40_000,T+119_000)
        mark=("100","100")
        a=leg("alpha",marks=mark,trades=mark,times=times,
              funding=(paid(),),funding_calendar=calendar(),
              risk_snapshots=(snapshot(tiers=(tier("0",None,"50"),)),))
        b=leg("beta",ResearchDirection.SHORT,marks=mark,trades=mark,times=times,
              funding=(paid(),),funding_calendar=calendar(),
              risk_snapshots=(snapshot(tiers=(tier("0",None,"50"),)),))
        result=audit(a,b,max_gap=80000,max_age=200000)
        self.assertEqual(result.checkpoints[0].signed_funding_paid_quote,D("0"))
        self.assertEqual(result.checkpoints[1].signed_funding_paid_quote,D("0"))
        self.assertTrue(result.complete_equity_path)
        self.assertEqual(result.checkpoints[-1].gross_open_notional_quote,D("400"))

    def test_degenerate_single_leg_correlation_and_precision(self):
        a=leg("alpha",marks=("100","100","100","100"))
        expected=audit(a)
        self.assertIsNone(expected.pairwise_mark_return_correlation_min)
        self.assertIsNone(expected.pairwise_mark_return_correlation_max)
        for precision in (2,4,28):
            with localcontext() as context:
                context.prec=precision
                self.assertEqual(expected,audit(a))
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            self.assertEqual(expected,audit(a))

    def test_invalid_identity_clock_and_budget_fail_closed(self):
        a=leg("alpha")
        b=leg("beta")
        for bad in (
            (a,a),
            (a,replace(b,plan=replace(b.plan,instrument_id=a.plan.instrument_id))),
            (a,replace(b,ticks=b.ticks[:-1])),
            (a,replace(b,plan=replace(b.plan,entry_at_ms=T-1000))),
            tuple([a]*17),
        ):
            with self.subTest(bad=len(bad)),self.assertRaises(DataValidationError):
                audit(*bad)
        with self.assertRaises(DataValidationError):
            audit(a,max_gap=0)
        with self.assertRaises(DataValidationError):
            replay_synthetic_portfolio((a,),as_of_ms=T+4000,
                                       max_tick_gap_ms=True)
        with self.assertRaises(DataValidationError):
            SyntheticPortfolioLeg("BTCUSDT",a.plan,a.ticks)
        with self.assertRaises(DataValidationError):
            audit(replace(a,plan=replace(a.plan,instrument_id="BTCUSDT")))
        with self.assertRaises(DataValidationError):
            audit(leg("alpha",marks=("100","100"),times=(T+1000,T+90000)),
                  max_gap=30000)


if __name__=="__main__":
    unittest.main()
