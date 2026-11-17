"""D397: exact AUTO2/AUTO4 opening margin -> J3 50x mark risk -> D393 costs."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_mark_risk_cost_gate_d397 import (
    audit_paper_costs_with_prior_mark_risk,
)
from crypto_intelligence_agent.paper_closed_cost_audit_d393 import (
    PaperDeclaredFillReference,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_margin_preflight import PaperMarginReason
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
from crypto_intelligence_agent.synthetic_mark_replay import (
    SyntheticMarkReplayPlan, SyntheticMarkTick,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_costed_replay import SyntheticPartialCostRates
from crypto_intelligence_agent.synthetic_position_state import (
    SyntheticSide, SyntheticLeverageSettings,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    SyntheticExitPlan, SyntheticExitTranche, ExitBasis,
)
from crypto_intelligence_agent.synthetic_risk_tiers import (
    SyntheticRiskSnapshot, SyntheticMaintenanceTier,
)
from test_paper_margin_preflight import (
    T, order as paper_order, assess, contract, mark, limits,
)

POSITION = "fixture_d397_paper_position"
RATES = SyntheticPartialCostRates(D(10), D(10), D(5), D(5))


class J3PaperMarkRiskGateD397Tests(unittest.TestCase):
    def build(self, *, leverage=50, short=False, with_margin=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.order_path = Path(temp.name) / "open_orders.sqlite"
        self.position_path = Path(temp.name) / "paper_positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.order_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        self.side = SyntheticSide.SHORT if short else SyntheticSide.LONG
        self.order_side = PaperOrderSide.SELL if short else PaperOrderSide.BUY
        self.exit_side = PaperOrderSide.BUY if short else PaperOrderSide.SELL
        self.leverage = leverage
        opening = paper_order(
            intent_id="fixture_d397_open",
            fixture_signal_id="fixture_d397_open_signal",
            venue=PaperVenue.BYBIT_V5, requested_units=D(2),
            position_side=self.side, side=self.order_side,
        )
        assumptions = contract(
            venue=PaperVenue.BYBIT_V5,
            fixture_version="fixture_d397_contract",
        )
        observation = mark(venue=PaperVenue.BYBIT_V5)
        if with_margin:
            margin = D(200) / D(leverage)
            assessed = assess(
                intent=opening, margin=margin,
                settings=SyntheticLeverageSettings(leverage),
                instrument=assumptions, observation=observation,
            )
            self.assertIs(assessed.reason, PaperMarginReason.FEASIBLE_PAPER_ONLY)
            health, entry = self.orders.reserve_open_if_paper_risk_with_health(
                opening, limits(), observation,
                decision_at_ms=T,
                position_journal_path=self.position_path,
                margin_assessment=assessed,
            )
            self.assertTrue(health.new_open_allowed)
            self.assertIsNotNone(entry.entry)
        else:
            self.orders.reserve(opening)
        event = PaperOrderEvent(
            "fixture_d397_entry_fill", PaperOrderEventKind.FILL,
            T + 10, D(2),
        )
        self.orders.append_events(opening.intent_id, (event,), as_of_ms=T + 10)
        self.positions.create_position(
            position_id=POSITION,
            opening_intent=opening, opening_events=(event,),
            exit_plan=SyntheticExitPlan(
                initial_units=D(2),
                tranches=(SyntheticExitTranche(
                    ExitBasis.INITIAL_POSITION, D(50),
                ),),
                residual_floor_percent=D(50),
            ),
            plan_version="d397-cost-risk-gate-v1",
            synthetic_lot_step_units=D("0.1"),
            as_of_ms=T + 10,
            opening_order_path=self.order_path,
        )
        self.refs = ()
        return self

    def close(self):
        partial = PaperOrderIntent(
            intent_id="fixture_d397_partial",
            fixture_signal_id="fixture_d397_partial_signal",
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDT",
            position_side=self.side, side=self.exit_side,
            effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(1),
            max_reducible_units=D(2), created_at_ms=T + 1000,
        )
        self.positions.reserve_exit(
            POSITION, 1, partial, as_of_ms=T + 1000,
        )
        part_ev = PaperOrderEvent(
            "fixture_d397_partial_fill", PaperOrderEventKind.FILL,
            T + 1100, D(1),
        )
        self.positions.append_exit_events(
            POSITION, partial.intent_id, (part_ev,), as_of_ms=T + 1100,
        )
        runner = PaperOrderIntent(
            intent_id="fixture_d397_runner",
            fixture_signal_id="fixture_d397_runner_signal",
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDT",
            position_side=self.side, side=self.exit_side,
            effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(1),
            max_reducible_units=D(1), created_at_ms=T + 3000,
        )
        self.positions.reserve_exit(
            POSITION, 0, runner, as_of_ms=T + 3000,
        )
        runner_ev = PaperOrderEvent(
            "fixture_d397_runner_fill", PaperOrderEventKind.FILL,
            T + 3100, D(1),
        )
        self.positions.append_exit_events(
            POSITION, runner.intent_id, (runner_ev,), as_of_ms=T + 3100,
        )
        one = D(99) if self.side is SyntheticSide.SHORT else D(101)
        two = D(97) if self.side is SyntheticSide.SHORT else D(103)
        self.refs = (
            PaperDeclaredFillReference(
                partial.intent_id, part_ev.event_id, part_ev.event_at_ms, one,
            ),
            PaperDeclaredFillReference(
                runner.intent_id, runner_ev.event_id, runner_ev.event_at_ms, two,
            ),
        )
        self.assertEqual(self.positions.load(POSITION).confirmed_remaining_units, D(0))
        return self

    def plan(self):
        direction = (
            ResearchDirection.SHORT if self.side is SyntheticSide.SHORT
            else ResearchDirection.LONG
        )
        return SyntheticMarkReplayPlan(
            direction=direction,
            entry_at_ms=T + 10,
            entry_price=D(100),
            quantity_base=D(2),
            stop_price=D(105) if direction is ResearchDirection.SHORT else D(95),
            target_price=D(90) if direction is ResearchDirection.SHORT else D(110),
            margin=SyntheticMarginBasis(
                D(200) / D(self.leverage), self.leverage,
                D(200), "SYNTHETIC_USDT",
            ),
            maintenance_rate_bps=D(50),
            reserve_for_close_quote=D(0),
            entry_fee_bps=RATES.entry_fee_bps,
            exit_fee_bps=RATES.exit_fee_bps,
            entry_slippage_bps=RATES.entry_adverse_slippage_bps,
            exit_slippage_bps=RATES.exit_adverse_slippage_bps,
            instrument_id="fixture_d397_BTCUSDT",
        )

    def tiers(self):
        return (SyntheticRiskSnapshot(
            "fixture_d397_BTCUSDT", "fixture_d397_PIT_v1",
            T - 100, T - 100,
            (SyntheticMaintenanceTier(D(0), None, D(50), D(0)),),
        ),)

    def ticks(self, *, bad_mark=False):
        is_short = self.side is SyntheticSide.SHORT
        first_exit = D(99) if is_short else D(101)
        final_exit = D(97) if is_short else D(103)
        adverse = (D(103) if is_short else D(97)) if bad_mark else D(100)
        return (
            SyntheticMarkTick(T + 500, D(100), D(100)),
            SyntheticMarkTick(T + 1100, D(100), first_exit),
            SyntheticMarkTick(T + 2500, adverse, D(100)),
            SyntheticMarkTick(T + 3100, D(100), final_exit),
        )

    def evaluate(self, *, ticks=None, plan=None, risks=None, refs=None,
                 order_path=None, max_gap=1500):
        return audit_paper_costs_with_prior_mark_risk(
            self.position_path, POSITION,
            opening_order_path=(
                self.order_path if order_path is None else order_path
            ),
            entry_reference_price_quote=D(100),
            fill_references=self.refs if refs is None else refs,
            cost_rates=RATES,
            mark_plan=self.plan() if plan is None else plan,
            mark_ticks=self.ticks() if ticks is None else ticks,
            max_tick_gap_ms=max_gap,
            risk_snapshots=self.tiers() if risks is None else risks,
            max_risk_snapshot_age_ms=10_000,
        )

    def test_50x_adverse_mark_vetoes_apparently_profitable_runner(self):
        self.build(leverage=50).close()
        result = self.evaluate(ticks=self.ticks(bad_mark=True))
        self.assertEqual(result.status, "abstain_prior_mark_liquidation_proxy")
        self.assertEqual(result.initial_leverage_at_intent, 50)
        self.assertEqual(result.mark_ticks_checked, 3)
        self.assertEqual(result.first_discrete_terminal_at_ms, T + 2500)
        self.assertTrue(result.possible_liquidation_detected)
        self.assertIsNone(result.conditional_net_after_risk_veto_quote)
        report = result.sanitized_report()
        self.assertTrue(report["has_prior_discrete_terminal"])
        self.assertFalse(report["liquidation_formula_verified"])
        self.assertFalse(report["net_pnl_verified"])
        self.assertFalse(report["orders_sent"])
        for token in ("BTCUSDT", "fixture_d397", "101", "103"):
            self.assertNotIn(token, json.dumps(report))

    def test_same_adverse_mark_10x_only_conditional_never_certifies_venue(self):
        self.build(leverage=10).close()
        result = self.evaluate(ticks=self.ticks(bad_mark=True))
        self.assertEqual(
            result.status,
            "conditional_closed_reference_after_discrete_mark_risk_gate",
        )
        self.assertEqual(result.initial_leverage_at_intent, 10)
        self.assertEqual(result.conditional_net_after_risk_veto_quote, D("3.394"))
        self.assertFalse(result.sanitized_report()["margin_collateral_verified"])
        self.assertFalse(result.sanitized_report()["intrabar_trajectory_verified"])

    def test_50x_healthy_marks_only_conditional_return(self):
        self.build(leverage=50).close()
        result = self.evaluate()
        self.assertEqual(
            result.status,
            "conditional_closed_reference_after_discrete_mark_risk_gate",
        )
        self.assertEqual(result.conditional_net_after_risk_veto_quote, D("3.394"))
        self.assertFalse(result.sanitized_report()["venue_leverage_verified"])

    def test_short_adverse_50x_veto_and_10x_conditional(self):
        self.build(short=True, leverage=50).close()
        veto = self.evaluate(ticks=self.ticks(bad_mark=True))
        self.assertTrue(veto.possible_liquidation_detected)
        self.assertIsNone(veto.conditional_net_after_risk_veto_quote)

    def test_prior_stop_or_target_never_becomes_runner_profit(self):
        self.build(leverage=50).close()
        for trade, expected in (
            (D(94), "abstain_prior_conditional_stop"),
            (D(111), "abstain_prior_conditional_target"),
        ):
            with self.subTest(trade=trade):
                tick = SyntheticMarkTick(T + 900, D(100), trade)
                sequence = self.ticks()
                sequence = (sequence[0], tick) + sequence[1:]
                out = self.evaluate(ticks=sequence)
                self.assertEqual(out.status, expected)
                self.assertIsNone(out.conditional_net_after_risk_veto_quote)

    def test_unknown_and_unclosed_position_never_expose_net(self):
        self.build()
        partial = PaperOrderIntent(
            intent_id="fixture_d397_pending",
            fixture_signal_id="fixture_d397_pending_signal",
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDT",
            position_side=self.side, side=self.exit_side,
            effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(1),
            max_reducible_units=D(2), created_at_ms=T + 1000,
        )
        self.positions.reserve_exit(POSITION, 1, partial, as_of_ms=T + 1000)
        self.positions.append_exit_events(
            POSITION, partial.intent_id,
            (PaperOrderEvent(
                "fixture_d397_unknown", PaperOrderEventKind.UNKNOWN,
                T + 1001,
            ),), as_of_ms=T + 1001,
        )
        out = self.evaluate()
        self.assertEqual(out.status, "abstain_position_open_or_pending_reconciliation")
        self.assertIsNone(out.conditional_net_after_risk_veto_quote)
        self.assertEqual(out.confirmed_remaining_units, D(2))

    def test_missing_margin_receipt_or_risk_tiers_always_returns_null(self):
        self.build(with_margin=False).close()
        out = self.evaluate()
        self.assertEqual(out.status, "abstain_immutable_open_margin_receipt_missing")
        self.assertIsNone(out.conditional_net_after_risk_veto_quote)
        # No opening AUTO2 cross-check: even a locally signed margin receipt
        # may not expose a costed result.
        self.build(with_margin=True).close()
        no_crosscheck = audit_paper_costs_with_prior_mark_risk(
            self.position_path, POSITION, opening_order_path=None,
            entry_reference_price_quote=D(100), fill_references=self.refs,
            cost_rates=RATES, mark_plan=self.plan(), mark_ticks=self.ticks(),
            max_tick_gap_ms=1500, risk_snapshots=self.tiers(),
            max_risk_snapshot_age_ms=10_000,
        )
        self.assertEqual(no_crosscheck.status,
                         "abstain_open_journal_crosscheck_required")
        self.assertIsNone(no_crosscheck.conditional_net_after_risk_veto_quote)
        missing_tiers = self.evaluate(risks=())
        self.assertEqual(missing_tiers.status,
                         "abstain_pit_maintenance_tiers_missing")
        self.assertIsNone(missing_tiers.conditional_net_after_risk_veto_quote)

    def test_mismatched_fill_prices_clocks_and_leverage_fail_closed(self):
        self.build().close()
        seq = self.ticks()
        changed = (
            dict(ticks=(seq[0], replace(seq[1], trade_price=D(102)),
                        seq[2], seq[3])),
            dict(ticks=seq[:-1]),
            dict(refs=self.refs[:1]),
            dict(plan=replace(self.plan(), entry_price=D(101),
                              margin=SyntheticMarginBasis(
                                  D(202)/D(50), 50, D(202), "SYNTHETIC_USDT",
                              ))),
            dict(plan=replace(self.plan(), margin=SyntheticMarginBasis(
                D(20), 10, D(200), "SYNTHETIC_USDT",
            ))),
            dict(max_gap=50),
        )
        for updates in changed:
            with self.subTest(update=tuple(updates)), self.assertRaises(
                DataValidationError
            ):
                self.evaluate(**updates)
        self.assertEqual(self.positions.load(POSITION).filled_exit_units, D(2))

    def test_risk_snapshot_late_or_wrong_identity_rejected(self):
        self.build().close()
        invalid = (
            (replace(self.tiers()[0], instrument_id="fixture_wrong_scope"),),
            (replace(self.tiers()[0], effective_at_ms=T+100),),
        )
        for snapshots in invalid:
            with self.subTest(snapshots=snapshots):
                with self.assertRaises(DataValidationError):
                    self.evaluate(risks=snapshots)

    def test_no_network_and_unchanged_durable_journals(self):
        self.build().close()
        before_open = self.order_path.read_bytes()
        before_paper = self.position_path.read_bytes()
        with patch.object(socket, "create_connection",
                          side_effect=AssertionError("network forbidden")):
            result = self.evaluate(ticks=self.ticks(bad_mark=True))
        self.assertIsNone(result.conditional_net_after_risk_veto_quote)
        self.assertEqual(self.order_path.read_bytes(), before_open)
        self.assertEqual(self.position_path.read_bytes(), before_paper)


if __name__ == "__main__":
    unittest.main()
