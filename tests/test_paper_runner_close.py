"""J4 #391: runner residual is now a bounded PAPER-only tranche zero."""
from dataclasses import replace
from decimal import Decimal as D
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_runner_close_preview import preview_paper_runner_close
from crypto_intelligence_agent.paper_runner_journal import (
    start_paper_runner_journal, append_paper_runner_mark,
)
from crypto_intelligence_agent.paper_runner_trailing import PaperRunnerMark
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderEventKind, PaperOrderSide,
    PaperOrderStatus,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_paper_position_reservations import T, e, opened_order, plan, exit_order
from test_paper_runner_journal import DurablePaperRunnerTests, policy, tick


class RunnerClosePaperTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DurablePaperRunnerTests(
            methodName="test_restart_replay_preserves_ratchet_and_terminal_trigger")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def trigger(self):
        self.fixture.start()
        self.fixture.append("102", 1)
        self.fixture.append("103", 2)
        self.fixture.append("102", 3)

    def preview(self, cutoff=T+3100):
        return preview_paper_runner_close(
            self.fixture.path, self.fixture.position_path, self.fixture.id,
            policy=policy(), as_of_ms=cutoff)

    def test_trigger_preview_is_deterministic_no_write_or_order(self):
        self.trigger()
        before = (self.fixture.path.read_bytes(), self.fixture.position_path.read_bytes())
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            a = self.preview()
            b = self.preview()
        self.assertEqual(a, b)
        self.assertEqual(a.intent.requested_units, D(6))
        self.assertEqual(a.intent.max_reducible_units, D(6))
        self.assertEqual(a.intent.effect, PaperOrderEffect.REDUCE_ONLY)
        self.assertEqual(a.intent.side, PaperOrderSide.SELL)
        self.assertFalse(a.orders_sent)
        self.assertFalse(a.native_stop_verified)
        self.assertFalse(a.order_submission_enabled)
        self.assertEqual(
            before, (self.fixture.path.read_bytes(), self.fixture.position_path.read_bytes()))

    def test_atomic_runner_reservation_idempotent_and_no_double_spend(self):
        self.trigger()
        intent = self.preview().intent
        store = SQLitePaperPositionJournal(self.fixture.position_path)
        current = store.reserve_exit(self.fixture.id, 0, intent, as_of_ms=T+3100)
        self.assertEqual(current.runner_reserved_unfilled_units, D(6))
        self.assertEqual(current.runner_unallocated_units, D(0))
        self.assertEqual(current.confirmed_remaining_units, D(6))
        self.assertEqual(current.unreserved_units, D(0))
        self.assertEqual(current.exit_orders[-1].tranche_step, 0)
        self.assertEqual(current.exit_orders[-1].snapshot.status, PaperOrderStatus.PENDING)
        self.assertEqual(SQLitePaperPositionJournal(self.fixture.position_path).load(self.fixture.id), current)
        self.assertEqual(store.reserve_exit(self.fixture.id, 0, intent, as_of_ms=T+3100), current)
        with self.assertRaises(DataValidationError):
            store.reserve_exit(self.fixture.id, 0,
                               replace(intent, intent_id="fixture_runner_second"),
                               as_of_ms=T+3100)
        with self.assertRaises(DataValidationError):
            self.preview()
        self.assertEqual(store.load(self.fixture.id), current)

    def test_unknown_cancel_and_replacement_then_fill(self):
        self.trigger()
        intent = self.preview().intent
        store = SQLitePaperPositionJournal(self.fixture.position_path)
        store.reserve_exit(self.fixture.id, 0, intent, as_of_ms=T+3100)
        uncertain = store.append_exit_events(self.fixture.id, intent.intent_id,
            (e("runner_unknown", PaperOrderEventKind.UNKNOWN, 3101),),
            as_of_ms=T+3101)
        self.assertEqual(uncertain.runner_reserved_unfilled_units, D(6))
        self.assertEqual(uncertain.exit_orders[-1].snapshot.status, PaperOrderStatus.UNKNOWN)
        with self.assertRaises(DataValidationError):
            store.reserve_exit(self.fixture.id, 0,
                replace(intent, intent_id="fixture_runner_second", created_at_ms=T+3101),
                as_of_ms=T+3101)
        cancelled = store.append_exit_events(self.fixture.id, intent.intent_id,
            (e("runner_cancelled", PaperOrderEventKind.CANCELLED, 3102),),
            as_of_ms=T+3102)
        self.assertEqual(cancelled.runner_unallocated_units, D(6))
        replacement = replace(
            intent, intent_id="fixture_runner_replacement",
            fixture_signal_id="fixture_runner_replace_signal",
            created_at_ms=T+3102)
        store.reserve_exit(self.fixture.id, 0, replacement, as_of_ms=T+3102)
        complete = store.append_exit_events(self.fixture.id, replacement.intent_id,
            (e("runner_fill_complete", PaperOrderEventKind.FILL, 3103, "6"),),
            as_of_ms=T+3103)
        self.assertEqual(complete.confirmed_remaining_units, D(0))
        self.assertEqual(complete.runner_filled_units, D(6))
        self.assertEqual(complete.runner_reserved_unfilled_units, D(0))
        self.assertEqual(complete.runner_unallocated_units, D(0))
        self.assertEqual(complete.filled_exit_units, D(100))
        self.assertEqual(SQLitePaperPositionJournal(self.fixture.position_path).load(self.fixture.id), complete)

    def test_partial_fill_cannot_overfill_and_cancel_releases_only_unfilled(self):
        self.trigger()
        intent = self.preview().intent
        store = SQLitePaperPositionJournal(self.fixture.position_path)
        store.reserve_exit(self.fixture.id, 0, intent, as_of_ms=T+3100)
        part = store.append_exit_events(self.fixture.id, intent.intent_id,
            (e("runner_partial", PaperOrderEventKind.FILL, 3101, "2"),),
            as_of_ms=T+3101)
        self.assertEqual(part.runner_filled_units, D(2))
        self.assertEqual(part.runner_reserved_unfilled_units, D(4))
        self.assertEqual(part.confirmed_remaining_units, D(4))
        with self.assertRaises(DataValidationError):
            store.append_exit_events(self.fixture.id, intent.intent_id,
                (e("runner_overfill", PaperOrderEventKind.FILL, 3102, "5"),),
                as_of_ms=T+3102)
        self.assertEqual(store.load(self.fixture.id), part)
        cancelled = store.append_exit_events(self.fixture.id, intent.intent_id,
            (e("runner_partial_cancel", PaperOrderEventKind.CANCELLED, 3102),),
            as_of_ms=T+3102)
        self.assertEqual(cancelled.runner_unallocated_units, D(4))
        replacement = replace(
            intent, intent_id="fixture_runner_partial_replacement",
            fixture_signal_id="fixture_runner_partial_signal",
            requested_units=D(4), max_reducible_units=D(4), created_at_ms=T+3102)
        store.reserve_exit(self.fixture.id, 0, replacement, as_of_ms=T+3102)
        final = store.append_exit_events(self.fixture.id, replacement.intent_id,
            (e("runner_remaining_fill", PaperOrderEventKind.FILL, 3103, "4"),),
            as_of_ms=T+3103)
        self.assertEqual(final.confirmed_remaining_units, D(0))
        self.assertEqual(final.runner_filled_units, D(6))

    def test_runner_unavailable_until_all_tranches_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            position_path = Path(folder) / "unfinished.sqlite"
            store = SQLitePaperPositionJournal(position_path)
            store.create_position(
                position_id="fixture_unfinished_runner",
                opening_intent=opened_order(),
                opening_events=(e("unfinished_open", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=plan(), plan_version="fixture_unfinished_plan",
                synthetic_lot_step_units=D(1), as_of_ms=T+1)
            early = exit_order("early_runner", "6", 1, cap="100")
            before = position_path.read_bytes()
            with self.assertRaises(DataValidationError):
                store.reserve_exit("fixture_unfinished_runner", 0, early, as_of_ms=T+1)
            self.assertEqual(before, position_path.read_bytes())
            with self.assertRaises(DataValidationError):
                store.reserve_exit("fixture_unfinished_runner", -1, early, as_of_ms=T+1)

    def test_no_preview_without_genuine_local_trigger_or_with_stale_cutoff(self):
        with self.assertRaises(DataValidationError):
            self.preview()
        self.fixture.start()
        self.fixture.append("102", 1)
        with self.assertRaises(DataValidationError):
            self.preview(T+1100)
        self.fixture.append("103", 2)
        self.fixture.append("102", 3)
        with self.assertRaises(DataValidationError):
            self.preview(T+10000)
        with self.assertRaises(DataValidationError):
            preview_paper_runner_close(
                self.fixture.path, self.fixture.position_path, self.fixture.id,
                policy=type(policy())(D(200), D(50), 5000, 5000),
                as_of_ms=T+3100)
        with sqlite3.connect(self.fixture.path) as conn:
            conn.execute("UPDATE paper_runner_state SET digest='corrupt'")
        with self.assertRaises(DataValidationError):
            self.preview()

    def test_legacy_tranche_plan_never_implicitly_closes_runner(self):
        before = inspect_paper_position(self.fixture.position_path, self.fixture.id)
        self.assertEqual(before.balance.runner_filled_units, D(0))
        self.assertEqual(before.balance.runner_reserved_unfilled_units, D(0))
        self.assertEqual(before.balance.runner_unallocated_units, D(6))


class ShortRunnerCloseTests(unittest.TestCase):
    def test_short_closes_with_buy_and_no_provider_traffic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            positions, runner = root/"positions.sqlite", root/"runner.sqlite"
            store = SQLitePaperPositionJournal(positions)
            opening = opened_order(
                intent_id="fixture_open_short", fixture_signal_id="fixture_signal_short",
                position_side=SyntheticSide.SHORT, side=PaperOrderSide.SELL)
            cur = store.create_position(
                position_id="fixture_short_runner", opening_intent=opening,
                opening_events=(e("short_open", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=plan(), plan_version="fixture_short_plan",
                synthetic_lot_step_units=D(1), as_of_ms=T+1)
            for step, qty in enumerate((50, 30, 14), 1):
                intent = PaperOrderIntent(
                    intent_id=f"fixture_short_exit_{step}",
                    fixture_signal_id=f"fixture_short_signal_{step}",
                    venue=opening.venue, symbol=opening.symbol,
                    position_side=SyntheticSide.SHORT, side=PaperOrderSide.BUY,
                    effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(qty),
                    max_reducible_units=cur.confirmed_remaining_units,
                    created_at_ms=cur.as_of_ms)
                cur = store.reserve_exit("fixture_short_runner", step, intent, as_of_ms=cur.as_of_ms)
                cur = store.append_exit_events(
                    "fixture_short_runner", intent.intent_id,
                    (e(f"short_fill_{step}", PaperOrderEventKind.FILL,
                       cur.as_of_ms-T+1, str(qty)),), as_of_ms=cur.as_of_ms+1)
            self.assertEqual(cur.runner_floor_units, D(6))
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                start_paper_runner_journal(
                    runner, positions, "fixture_short_runner",
                    policy=policy(), first_mark=tick("100", 0), as_of_ms=T+100)
                for n, px in enumerate(("98", "97", "98"), 1):
                    append_paper_runner_mark(
                        runner, positions, "fixture_short_runner",
                        tick(px, n), policy=policy(), as_of_ms=T+100+n*1000)
                preview = preview_paper_runner_close(
                    runner, positions, "fixture_short_runner",
                    policy=policy(), as_of_ms=T+3100)
            self.assertEqual(preview.intent.side, PaperOrderSide.BUY)
            self.assertEqual(preview.intent.requested_units, D(6))
            self.assertFalse(preview.orders_sent)


if __name__ == "__main__":
    unittest.main()
