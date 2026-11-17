"""D398: only a recorded prior PAPER partial can reduce mark liquidation proxy."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D
import json
import socket
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_mark_risk_cost_gate_d397 import (
    audit_paper_costs_with_prior_mark_risk,
)
from crypto_intelligence_agent.paper_partial_derisk_risk_gate_d398 import (
    audit_paper_partial_derisk_mark_risk,
)
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_mark_replay import SyntheticMarkTick
from test_paper_mark_risk_cost_gate_d397 import (
    J3PaperMarkRiskGateD397Tests, POSITION, RATES, T,
)


class J3PartialDeriskD398Tests(unittest.TestCase):
    def make(self, *, leverage=50, short=False, with_margin=True, close=True):
        self.fixture=J3PaperMarkRiskGateD397Tests(
            "test_no_network_and_unchanged_durable_journals"
        )
        self.fixture.build(leverage=leverage, short=short, with_margin=with_margin)
        self.addCleanup(self.fixture.doCleanups)
        if close:
            self.fixture.close()
        return self.fixture

    def risk(self, *, ticks=None, refs=None, order_path=None,
             risks=None, funding=(), gap=1500):
        f=self.fixture
        return audit_paper_partial_derisk_mark_risk(
            f.position_path, POSITION,
            opening_order_path=(
                f.order_path if order_path is None else order_path
            ),
            entry_reference_price_quote=D(100),
            fill_references=f.refs if refs is None else refs,
            cost_rates=RATES, mark_plan=f.plan(),
            mark_ticks=f.ticks(bad_mark=True) if ticks is None else ticks,
            max_tick_gap_ms=gap,
            risk_snapshots=f.tiers() if risks is None else risks,
            max_risk_snapshot_age_ms=10_000,
            funding_events=funding,
        )

    def test_50x_after_partial_97_mark_remains_conditional_not_full_proxy_veto(self):
        f=self.make()
        old=f.evaluate(ticks=f.ticks(bad_mark=True))
        self.assertEqual(old.status,"abstain_prior_mark_liquidation_proxy")
        self.assertIsNone(old.conditional_net_after_risk_veto_quote)
        new=self.risk()
        self.assertEqual(new.status,"conditional_closed_after_observed_partial_derisk_proxy")
        self.assertEqual(new.leverage_at_open_intent,50)
        self.assertEqual(new.mark_ticks_checked,4)
        self.assertEqual(new.confirmed_paper_fills_applied,2)
        self.assertTrue(new.full_notional_proxy_vetoed)
        self.assertEqual(new.conditional_net_after_partial_risk_quote,D("3.394"))
        report=new.sanitized_report()
        self.assertFalse(report["venue_liquidation_verified"])
        self.assertFalse(report["net_pnl_verified"])
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["margin_added_from_fills"])
        self.assertNotIn("BTCUSDT",json.dumps(report))
        self.assertNotIn("fixture_d397",json.dumps(report))

    def test_same_97_mark_before_partial_is_liquidation_even_if_later_fill_profitable(self):
        f=self.make()
        ticks=f.ticks()
        premature=(
            ticks[0], SyntheticMarkTick(T+800,D(97),D(100)),
            ticks[1],ticks[2],ticks[3],
        )
        outcome=self.risk(ticks=premature)
        self.assertEqual(outcome.status,"abstain_partial_risk_liquidation_proxy")
        self.assertEqual(outcome.first_discrete_terminal_at_ms,T+800)
        self.assertEqual(outcome.confirmed_paper_fills_applied,0)
        self.assertIsNone(outcome.conditional_net_after_partial_risk_quote)

    def test_liquidation_at_same_tick_as_first_fill_precedes_derisk(self):
        f=self.make()
        ticks=f.ticks()
        same=(
            ticks[0],replace(ticks[1],mark_price=D(97)),
            ticks[2],ticks[3],
        )
        outcome=self.risk(ticks=same)
        self.assertEqual(outcome.status,"abstain_partial_risk_liquidation_proxy")
        self.assertEqual(outcome.first_discrete_terminal_at_ms,T+1100)
        self.assertEqual(outcome.confirmed_paper_fills_applied,0)

    def test_even_after_partial_worse_mark_95_vetoes_fictive_profit(self):
        f=self.make()
        ticks=f.ticks()
        worse=(
            ticks[0],ticks[1],replace(ticks[2],mark_price=D(95)),ticks[3],
        )
        result=self.risk(ticks=worse)
        self.assertEqual(result.status,"abstain_partial_risk_liquidation_proxy")
        self.assertEqual(result.confirmed_paper_fills_applied,1)
        self.assertIsNone(result.conditional_net_after_partial_risk_quote)

    def test_10x_survives_97_but_result_still_not_real_pnl(self):
        self.make(leverage=10)
        r=self.risk()
        self.assertFalse(r.full_notional_proxy_vetoed)
        self.assertEqual(r.conditional_net_after_partial_risk_quote,D("3.394"))
        self.assertFalse(r.sanitized_report()["venue_leverage_verified"])

    def test_short_after_partial_reduces_exposure_symmetrically(self):
        f=self.make(short=True)
        old=f.evaluate(ticks=f.ticks(bad_mark=True))
        self.assertEqual(old.status,"abstain_prior_mark_liquidation_proxy")
        result=self.risk()
        self.assertTrue(result.full_notional_proxy_vetoed)
        self.assertEqual(result.conditional_net_after_partial_risk_quote,D("3.406"))
        self.assertEqual(result.confirmed_paper_fills_applied,2)

    def test_signed_funding_between_fills_uses_original_cash_and_remaining_notional(self):
        self.make()
        positive=SyntheticFundingEvent(
            "fixture_funding_d398_positive",T+1500,D(100),D(20),
        )
        negative=SyntheticFundingEvent(
            "fixture_funding_d398_negative",T+1500,D(100),D(-20),
        )
        paid=self.risk(funding=(positive,))
        received=self.risk(funding=(negative,))
        self.assertEqual(paid.conditional_net_after_partial_risk_quote,D("3.194"))
        self.assertEqual(received.conditional_net_after_partial_risk_quote,D("3.594"))
        self.assertEqual(paid.confirmed_paper_fills_applied,2)
        self.assertFalse(paid.sanitized_report()["funding_calendar_complete"])

    def test_stop_or_target_first_blocks_partial_derisk_narrative(self):
        f=self.make()
        seq=f.ticks()
        for trade in (D(94),D(111)):
            with self.subTest(trade=trade):
                ticks=(seq[0],SyntheticMarkTick(T+900,D(100),trade),
                       seq[1],seq[2],seq[3])
                r=self.risk(ticks=ticks)
                self.assertTrue(r.status.startswith("abstain_prior_conditional"))
                self.assertIsNone(r.conditional_net_after_partial_risk_quote)

    def test_missing_receipt_tiers_and_crosscheck_abstain(self):
        self.make(with_margin=False)
        no_margin=self.risk()
        self.assertEqual(no_margin.status,"abstain_immutable_open_margin_receipt_missing")
        self.assertIsNone(no_margin.conditional_net_after_partial_risk_quote)
        self.make()
        no_tiers=self.risk(risks=())
        self.assertEqual(no_tiers.status,"abstain_pit_maintenance_tiers_missing")
        self.assertIsNone(no_tiers.conditional_net_after_partial_risk_quote)
        no_crosscheck=audit_paper_partial_derisk_mark_risk(
            self.fixture.position_path,POSITION,
            opening_order_path=None,entry_reference_price_quote=D(100),
            fill_references=self.fixture.refs,cost_rates=RATES,
            mark_plan=self.fixture.plan(),mark_ticks=self.fixture.ticks(),
            max_tick_gap_ms=1500,risk_snapshots=self.fixture.tiers(),
            max_risk_snapshot_age_ms=10_000,
        )
        self.assertEqual(no_crosscheck.status,
                         "abstain_open_journal_crosscheck_required")

    def test_unclosed_and_unknown_order_cannot_expose_net(self):
        f=self.make(close=False)
        x=self.risk()
        self.assertEqual(x.status,"abstain_position_open_or_pending_reconciliation")
        self.assertIsNone(x.conditional_net_after_partial_risk_quote)

    def test_invalid_fill_price_gap_funding_notional_and_scope_rejected(self):
        f=self.make()
        all_ticks=f.ticks()
        wrong=[
            dict(ticks=(all_ticks[0],replace(all_ticks[1],trade_price=D(102)),
                        all_ticks[2],all_ticks[3])),
            dict(gap=100),
            dict(refs=f.refs[:1]),
            dict(funding=(SyntheticFundingEvent(
                "fixture_funding_d398_bad",T+1500,D(200),D(20)),)),
            dict(risks=(replace(f.tiers()[0],instrument_id="fixture_other"),)),
        ]
        for kw in wrong:
            with self.subTest(inputs=tuple(kw)), self.assertRaises(DataValidationError):
                self.risk(**kw)

    def test_no_writes_network_or_cross_file_side_effects(self):
        f=self.make()
        before_orders=f.order_path.read_bytes()
        before_positions=f.position_path.read_bytes()
        with patch.object(socket,"create_connection",
                          side_effect=AssertionError("network prohibited")):
            x=self.risk()
        self.assertEqual(x.conditional_net_after_partial_risk_quote,D("3.394"))
        self.assertEqual(before_orders,f.order_path.read_bytes())
        self.assertEqual(before_positions,f.position_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
