"""J3/PRE29: a profitable fictitious runner never overrides prior mark risk."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D, localcontext
import json
import socket
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
from crypto_intelligence_agent.synthetic_mark_replay import (
    SyntheticMarkReplayPlan, SyntheticMarkTick,
)
from crypto_intelligence_agent.synthetic_partial_costed_replay import (
    SyntheticPartialCostRates,
)
from crypto_intelligence_agent.synthetic_position_state import (
    SyntheticSide, SyntheticLeverageSettings, open_synthetic_position,
)
from crypto_intelligence_agent.synthetic_runner_liquidation_gate import (
    evaluate_synthetic_runner_risk_gate,
)
from test_synthetic_partial_costed_replay import (
    fill, funding, position, rates,
)
from test_synthetic_runner_costed_close import runner


def make_position(side=SyntheticSide.LONG, leverage=50):
    # 100 * 100 / 50 = 200 quote; unlike J4 abstract margin=2, these
    # explicit financial scenario fixtures must be collateral-consistent.
    p = position(side=side, settings=SyntheticLeverageSettings(leverage))
    return replace(p, synthetic_margin_units=D(10000) / D(leverage))


def make_partials(p):
    prices = ("101", "102", "99") if p.side is SyntheticSide.LONG else (
        "99", "98", "101",
    )
    return (
        fill(p, "partial_first", 1, "50", 2_000, prices[0]),
        fill(p, "partial_second", 2, "30", 3_000, prices[1]),
        fill(p, "partial_third", 3, "14", 4_000, prices[2]),
    )


def make_receipt(p):
    return (runner(p, receipt="last_runner_receipt",
                   price="103" if p.side is SyntheticSide.LONG else "97"),)


def make_plan(p, *, maintenance="50"):
    side = (ResearchDirection.LONG if p.side is SyntheticSide.LONG
            else ResearchDirection.SHORT)
    return SyntheticMarkReplayPlan(
        direction=side,
        entry_at_ms=p.opened_at_ms,
        entry_price=D(100),
        quantity_base=D(100),
        stop_price=D(95) if side is ResearchDirection.LONG else D(105),
        target_price=D(110) if side is ResearchDirection.LONG else D(90),
        margin=SyntheticMarginBasis(
            p.synthetic_margin_units, p.leverage_at_open,
            D(10000), "SYNTHETIC_USDT",
        ),
        maintenance_rate_bps=D(maintenance),
        reserve_for_close_quote=D(0),
        entry_fee_bps=D(10),
        exit_fee_bps=D(10),
        entry_slippage_bps=D(5),
        exit_slippage_bps=D(5),
    )


def marks(p):
    vals = ("101", "102", "99", "103") if p.side is SyntheticSide.LONG else (
        "99", "98", "101", "97",
    )
    return tuple(
        SyntheticMarkTick(at, D(v), D(v))
        for at, v in zip((2_000, 3_000, 4_000, 5_000), vals)
    )


class J3RunnerRiskGateTests(unittest.TestCase):
    def setUp(self):
        self.p = make_position()
        self.fills = make_partials(self.p)
        self.receipts = make_receipt(self.p)
        self.ticks = marks(self.p)
        self.plan = make_plan(self.p)

    def run_gate(self, **updates):
        args = dict(
            position=self.p,
            partial_fills=self.fills,
            runner_receipts=self.receipts,
            entry_reference_price_quote=D(100),
            cost_rates=rates(),
            mark_plan=self.plan,
            mark_ticks=self.ticks,
            as_of_ms=5_000,
            max_tick_gap_ms=2_000,
            funding_events=(funding(),),
        )
        args.update(updates)
        return evaluate_synthetic_runner_risk_gate(**args)

    def test_long_no_discrete_terminal_exposes_only_conditional_reference(self):
        result = self.run_gate()
        self.assertEqual(result.status, "conditional_reference_no_discrete_terminal_observed")
        self.assertIsNone(result.first_terminal_at_ms)
        self.assertEqual(result.checked_mark_ticks, 4)
        self.assertEqual(result.initial_leverage, 50)
        self.assertEqual(result.runner_closed_units, D(6))
        # 50*(101-100)+30*(102-100)+14*(99-100)+6*(103-100) = 114.
        # Entry=15, partial exit=14.244, runner exit=0.927, funding=1.
        self.assertEqual(result.hypothetical_net_if_no_unobserved_events_quote,
                         D("82.829"))
        report = result.sanitized_report()
        self.assertEqual(report["hypothetical_net_if_no_unobserved_events_quote"],
                         "82.829")
        self.assertIs(report["full_initial_notional_proxy_only"], True)
        self.assertIs(report["partial_derisking_in_mark_path_modeled"], False)
        for field in (
            "real_pnl_verified", "liquidation_risk_verified",
            "intrabar_trajectory_verified", "venue_fills_verified",
            "live_trading_authorized", "orders_sent",
        ):
            self.assertIs(report[field], False)
        self.assertEqual(report["network_requests"], 0)
        for token in ("fixture_", "partial_first", "last_runner_receipt", "BTCUSDT"):
            self.assertNotIn(token, json.dumps(report))

    def test_50x_liquidation_precedes_apparent_profitable_runner_and_hides_net(self):
        adverse = SyntheticMarkTick(1_500, D(97), D(100))
        result = self.run_gate(
            mark_ticks=(adverse,) + self.ticks,
            funding_events=(),
        )
        self.assertEqual(result.status, "abstain_full_notional_mark_liquidation_proxy")
        self.assertEqual(result.first_terminal_at_ms, 1_500)
        self.assertIsNone(result.hypothetical_net_if_no_unobserved_events_quote)
        self.assertIsNone(result.sanitized_report()["hypothetical_net_if_no_unobserved_events_quote"])
        self.assertFalse(result.liquidation_risk_verified)
        self.assertFalse(result.real_pnl_verified)

    def test_same_mark_dip_survives_10x_but_not_50x_in_full_notional_proxy(self):
        adverse = SyntheticMarkTick(1_500, D(97), D(100))
        p = make_position(leverage=10)
        result = self.run_gate(
            position=p,
            partial_fills=make_partials(p),
            runner_receipts=make_receipt(p),
            mark_plan=make_plan(p),
            mark_ticks=(adverse,) + marks(p),
        )
        self.assertEqual(result.status, "conditional_reference_no_discrete_terminal_observed")
        self.assertEqual(result.initial_leverage, 10)
        self.assertEqual(result.hypothetical_net_if_no_unobserved_events_quote,
                         D("82.829"))
        self.assertFalse(result.liquidation_risk_verified)

    def test_stop_and_target_prior_to_runner_both_veto_conditional_net(self):
        for price, expected in (("94", "abstain_prior_conditional_stop"),
                                ("111", "abstain_prior_conditional_target")):
            with self.subTest(trade=price):
                before = SyntheticMarkTick(1_500, D(100), D(price))
                result = self.run_gate(
                    mark_ticks=(before,) + self.ticks,
                    funding_events=(),
                )
                self.assertEqual(result.status, expected)
                self.assertIsNone(result.hypothetical_net_if_no_unobserved_events_quote)

    def test_short_scenario_is_not_converted_into_long(self):
        p = make_position(side=SyntheticSide.SHORT)
        result = self.run_gate(
            position=p, partial_fills=make_partials(p),
            runner_receipts=make_receipt(p),
            mark_plan=make_plan(p), mark_ticks=marks(p),
        )
        self.assertEqual(result.status, "conditional_reference_no_discrete_terminal_observed")
        # SHORT exit notionals are lower: 4_950+2_940+1_414+582.
        # Exit costs 13.956+0.873, entry 15; -1 signed funding is a credit.
        self.assertEqual(result.hypothetical_net_if_no_unobserved_events_quote,
                         D("85.171"))
        self.assertEqual(result.initial_leverage, 50)

    def test_funding_is_causal_consistent_and_no_late_coverage_is_borrowed(self):
        result = self.run_gate(funding_events=())
        self.assertEqual(result.funding_event_count, 0)
        self.assertEqual(result.hypothetical_net_if_no_unobserved_events_quote,
                         D("83.829"))
        with self.assertRaises(DataValidationError):
            self.run_gate(funding_events=(funding(), funding()))
        with self.assertRaises(DataValidationError):
            self.run_gate(funding_events=(funding("fixture_funding_late", 5_001),))
        with self.assertRaises(DataValidationError):
            self.run_gate(funding_events=(funding("fixture_funding_same_tick", 3_000),))

    def test_mismatched_financial_contracts_rejected_instead_of_optimistic_net(self):
        p10 = make_position(leverage=10)
        for args in (
            dict(mark_plan=replace(self.plan, direction=ResearchDirection.SHORT,
                                   stop_price=D(105), target_price=D(90))),
            dict(mark_plan=replace(self.plan, entry_at_ms=900)),
            dict(mark_plan=replace(self.plan, entry_price=D(101),
                                   margin=SyntheticMarginBasis(
                                       D(202), 50, D(10100), "SYNTHETIC_USDT"))),
            dict(mark_plan=replace(self.plan, exit_fee_bps=D(11))),
            dict(mark_plan=replace(self.plan, maintenance_rate_bps=D(0)),
                 position=p10, partial_fills=make_partials(p10),
                 runner_receipts=make_receipt(p10)),
            dict(entry_reference_price_quote=D(101)),
            dict(cost_rates=rates(entry_fee_bps=D(11))),
            dict(position=p10, partial_fills=make_partials(p10),
                 runner_receipts=make_receipt(p10)),
        ):
            with self.subTest(change=tuple(args)), self.assertRaises(DataValidationError):
                self.run_gate(**args)

    def test_partial_receipt_price_time_and_mark_coverage_are_binding(self):
        for changed in (
            dict(mark_ticks=self.ticks[:-1]),
            dict(mark_ticks=self.ticks[:-2]+self.ticks[-1:]),
            dict(mark_ticks=(replace(self.ticks[0], trade_price=D(100)),)
                            + self.ticks[1:]),
            dict(mark_ticks=self.ticks[:-1]
                            + (replace(self.ticks[-1], trade_price=D(104)),)),
            dict(mark_ticks=self.ticks + (self.ticks[-1],)),
            dict(as_of_ms=5_001),
            dict(as_of_ms=True),
            dict(max_tick_gap_ms=999),
            dict(max_tick_gap_ms=0),
            dict(max_tick_gap_ms=True),
        ):
            with self.subTest(change=tuple(changed)), self.assertRaises(DataValidationError):
                self.run_gate(**changed)

    def test_incomplete_runner_and_wrong_typed_evidence_are_never_upgraded(self):
        for bad in (
            dict(partial_fills=self.fills[:2]),
            dict(runner_receipts=(replace(self.receipts[0], filled_units=D(5)),)),
            dict(runner_receipts=[]),
            dict(partial_fills=list(self.fills)),
            dict(mark_ticks=list(self.ticks)),
            dict(mark_plan="not-a-plan"),
        ):
            with self.subTest(case=tuple(bad)), self.assertRaises(DataValidationError):
                self.run_gate(**bad)

    def test_precision_and_network_isolation(self):
        expected = self.run_gate()
        for precision in (3, 6, 16, 28):
            with localcontext() as context:
                context.prec = precision
                other = self.run_gate()
            self.assertEqual(expected, other)
        with patch.object(socket, "create_connection",
                          side_effect=AssertionError("network forbidden")):
            self.assertEqual(expected, self.run_gate())


if __name__ == "__main__":
    unittest.main()
