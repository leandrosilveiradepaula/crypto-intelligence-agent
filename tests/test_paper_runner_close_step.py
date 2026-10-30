"""J6 #395: restart-safe PAPER-only runner-close step with zero broker actions."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_runner_close_step import (
    PaperRunnerCloseStepState, step_durable_paper_runner_close,
)
from crypto_intelligence_agent.paper_runner_journal import (
    start_paper_runner_journal, append_paper_runner_mark,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide, PaperOrderEventKind,
    PaperOrderStatus,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_paper_position_reservations import T, e, opened_order, plan, exit_order
from test_paper_runner_journal import DurablePaperRunnerTests, policy, tick


class DurablePaperRunnerCloseStepTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DurablePaperRunnerTests(
            methodName="test_restart_replay_preserves_ratchet_and_terminal_trigger")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.position

    def trigger(self):
        self.fixture.start()
        self.fixture.append("102", 1)
        self.fixture.append("103", 2)
        self.fixture.append("102", 3)

    def step(self, at=T+3100):
        return step_durable_paper_runner_close(
            self.fixture.path, self.fixture.position_path, self.fixture.id,
            policy=policy(), as_of_ms=at)

    def test_first_step_and_restart_are_idempotent_without_fake_fills(self):
        self.trigger()
        runner_before = self.fixture.path.read_bytes()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            first = self.step()
            self.assertEqual(first.state, PaperRunnerCloseStepState.RESERVED_PAPER_ONLY)
            self.assertEqual(first.runner_reserved_unfilled_units, D(6))
            self.assertEqual(first.runner_filled_units, D(0))
            self.assertEqual(first.runner_order_count, 1)
            self.assertFalse(first.orders_sent)
            self.assertFalse(first.native_stop_verified)
            view = self.store.load(self.fixture.id)
            self.assertEqual(view.runner_reserved_unfilled_units, D(6))
            self.assertEqual(view.confirmed_remaining_units, D(6))
            self.assertEqual(len([x for x in view.exit_orders if x.tranche_step == 0]), 1)
            order = view.exit_orders[-1]
            self.assertEqual(order.intent.intent_id, first.created_intent_id)
            self.assertEqual(order.snapshot.status, PaperOrderStatus.PENDING)
            self.assertEqual(order.events, ())
            self.assertEqual(order.intent.effect, PaperOrderEffect.REDUCE_ONLY)
            content_before_restart = self.fixture.position_path.read_bytes()
            restarted = self.step(T+3200)
        self.assertEqual(restarted.state, PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY)
        self.assertIsNone(restarted.created_intent_id)
        self.assertEqual(restarted.runner_order_count, 1)
        self.assertEqual(self.fixture.path.read_bytes(), runner_before)
        self.assertEqual(self.fixture.position_path.read_bytes(), content_before_restart)
        self.assertFalse(restarted.sanitized_report()["orders_sent"])

    def test_missing_or_nontriggering_runner_fails_without_new_writer(self):
        original = self.fixture.position_path.read_bytes()
        with self.assertRaises(DataValidationError):
            self.step()
        self.assertEqual(original, self.fixture.position_path.read_bytes())
        self.fixture.start()
        self.fixture.append("102", 1)
        with self.assertRaises(DataValidationError):
            self.step(T+1100)
        self.assertEqual(original, self.fixture.position_path.read_bytes())

    def test_unknown_cancel_partial_and_manual_restart_are_never_retried(self):
        self.trigger()
        first = self.step()
        intent_id = first.created_intent_id
        self.store.append_exit_events(self.fixture.id, intent_id,
            (e("j6_runner_unknown", PaperOrderEventKind.UNKNOWN, 3101),),
            as_of_ms=T+3101)
        self.assertEqual(self.step(T+3102).state,
                         PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY)
        self.store.append_exit_events(self.fixture.id, intent_id,
            (e("j6_runner_cancel", PaperOrderEventKind.CANCELLED, 3103),),
            as_of_ms=T+3103)
        self.assertEqual(self.step(T+3104).state,
                         PaperRunnerCloseStepState.TERMINAL_MANUAL_REVIEW_REQUIRED)
        self.assertEqual(len([x for x in self.store.load(self.fixture.id).exit_orders
                              if x.tranche_step == 0]), 1)
        replacement = exit_order("j6_manual_runner", "6", 3103, cap="6")
        self.store.reserve_exit(self.fixture.id, 0, replacement, as_of_ms=T+3103)
        self.store.append_exit_events(self.fixture.id, replacement.intent_id,
            (e("j6_runner_partial", PaperOrderEventKind.FILL, 3104, "2"),),
            as_of_ms=T+3104)
        self.assertEqual(self.step(T+3105).state,
                         PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY)
        self.store.append_exit_events(self.fixture.id, replacement.intent_id,
            (e("j6_runner_partial_cancel", PaperOrderEventKind.CANCELLED, 3105),),
            as_of_ms=T+3105)
        self.assertEqual(self.step(T+3106).state,
                         PaperRunnerCloseStepState.TERMINAL_MANUAL_REVIEW_REQUIRED)
        last = exit_order("j6_manual_last", "4", 3105, cap="4")
        self.store.reserve_exit(self.fixture.id, 0, last, as_of_ms=T+3105)
        self.store.append_exit_events(self.fixture.id, last.intent_id,
            (e("j6_runner_last", PaperOrderEventKind.FILL, 3106, "4"),),
            as_of_ms=T+3106)
        result = self.step(T+3107)
        self.assertEqual(result.state, PaperRunnerCloseStepState.CLOSED_PAPER_ONLY)
        self.assertEqual(result.runner_filled_units, D(6))
        self.assertEqual(result.runner_reserved_unfilled_units, D(0))
        self.assertEqual(self.store.load(self.fixture.id).confirmed_remaining_units, D(0))

    def test_concurrent_steps_never_allocate_two_residuals(self):
        self.trigger()
        def attempt(_):
            try:
                return self.step()
            except DataValidationError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, (0,1)))
        self.assertTrue(any(x is not None for x in outcomes))
        saved = SQLitePaperPositionJournal(self.fixture.position_path).load(self.fixture.id)
        self.assertEqual(saved.runner_reserved_unfilled_units, D(6))
        self.assertEqual(len([x for x in saved.exit_orders if x.tranche_step == 0]), 1)
        self.assertEqual(saved.confirmed_remaining_units, D(6))
        self.assertFalse(any(x.snapshot.status is PaperOrderStatus.FILLED
                             for x in saved.exit_orders if x.tranche_step == 0))

    def test_corruption_and_staleness_block_first_reservation(self):
        self.trigger()
        with self.assertRaises(DataValidationError):
            self.step(T+10000)
        before = self.fixture.position_path.read_bytes()
        with sqlite3.connect(self.fixture.path) as con:
            con.execute("UPDATE paper_runner_state SET digest='invalid'")
        with self.assertRaises(DataValidationError):
            self.step()
        self.assertEqual(before, self.fixture.position_path.read_bytes())


class ShortDurableRunnerCloseStepTests(unittest.TestCase):
    def test_short_direction_and_exact_residual_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            position_path, runner_path = root/"short.sqlite", root/"trail.sqlite"
            store = SQLitePaperPositionJournal(position_path)
            opening = opened_order(
                intent_id="fixture_j6_short_open", fixture_signal_id="fixture_j6_short_sig",
                position_side=SyntheticSide.SHORT, side=PaperOrderSide.SELL)
            current = store.create_position(
                position_id="fixture_j6_short_pos",
                opening_intent=opening,
                opening_events=(e("j6_short_open", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=plan(), plan_version="fixture_j6_short_plan",
                synthetic_lot_step_units=D(1), as_of_ms=T+1)
            for idx, units in enumerate((50,30,14),1):
                intent = PaperOrderIntent(
                    intent_id=f"fixture_j6_short_exit_{idx}",
                    fixture_signal_id=f"fixture_j6_short_signal_{idx}",
                    venue=opening.venue, symbol=opening.symbol,
                    position_side=SyntheticSide.SHORT, side=PaperOrderSide.BUY,
                    effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(units),
                    max_reducible_units=current.confirmed_remaining_units,
                    created_at_ms=current.as_of_ms)
                current = store.reserve_exit(current.position_id, idx, intent,
                                             as_of_ms=current.as_of_ms)
                current = store.append_exit_events(
                    current.position_id, intent.intent_id,
                    (e(f"j6_short_fill_{idx}",PaperOrderEventKind.FILL,
                       current.as_of_ms-T+1,str(units)),),
                    as_of_ms=current.as_of_ms+1)
            start_paper_runner_journal(
                runner_path, position_path, current.position_id,
                policy=policy(), first_mark=tick("100",0), as_of_ms=T+100)
            for index, price in enumerate(("98","97","98"),1):
                append_paper_runner_mark(
                    runner_path, position_path, current.position_id,
                    tick(price,index), policy=policy(), as_of_ms=T+100+index*1000)
            first = step_durable_paper_runner_close(
                runner_path,position_path,current.position_id,
                policy=policy(),as_of_ms=T+3100)
            self.assertEqual(first.state,PaperRunnerCloseStepState.RESERVED_PAPER_ONLY)
            saved = store.load(current.position_id)
            self.assertEqual(saved.exit_orders[-1].intent.side,PaperOrderSide.BUY)
            self.assertEqual(saved.exit_orders[-1].intent.requested_units,D(6))
            self.assertFalse(first.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
