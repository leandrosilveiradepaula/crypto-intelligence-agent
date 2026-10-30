"""J5 #393: mobile statuses for durable PAPER runner closure (no real stop)."""
from decimal import Decimal as D
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderEventKind, PaperOrderSide,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.inspect_paper_positions import TEMPLATE, multi_paper_snapshot, render_paper_positions
from test_paper_position_reservations import T, e, opened_order, plan, entire_plan, exit_order
from test_paper_runner_journal import DurablePaperRunnerTests


class RunnerMobileExitTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DurablePaperRunnerTests(
            methodName="test_restart_replay_preserves_ratchet_and_terminal_trigger")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.position
        self.id = self.fixture.id

    def view(self):
        selected = (inspect_paper_position(self.fixture.position_path, self.id),)
        return multi_paper_snapshot(selected), render_paper_positions(
            selected, TEMPLATE.read_text(encoding="utf-8"))

    def assert_state(self, expected, filled, reserved, available):
        snap, html = self.view()
        p = snap["positions"][0]
        self.assertEqual(p["runner_readiness"], expected)
        self.assertEqual(p["runner_filled_units"], str(filled))
        self.assertEqual(p["runner_reserved_unfilled_units"], str(reserved))
        self.assertEqual(p["runner_unallocated_units"], str(available))
        self.assertFalse(p["trailing_stop_active"])
        self.assertFalse(p["native_stop_verified"])
        self.assertFalse(snap["orders_sent"])
        self.assertFalse(snap["live_trading_authorized"])
        self.assertFalse(snap["financial_pnl_available"])
        self.assertIn('data-field="runner-exit-quantities"', html)
        self.assertIn('data-field="runner-readiness"', html)
        self.assertIn("stop nativo não verificado", html)
        self.assertIn("unidades do próprio instrumento", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("https://", html)
        return snap, html

    def test_runner_pending_unknown_cancel_partial_and_closed(self):
        current = self.store.load(self.id)
        self.assert_state("RUNNER_CONFIRMED_NOT_PROTECTED", 0, 0, 6)
        intent = exit_order("runner_mobile", "6", current.as_of_ms - T, cap="6")
        self.store.reserve_exit(self.id, 0, intent, as_of_ms=current.as_of_ms)
        self.assert_state("RUNNER_EXIT_PENDING_RECONCILIATION", 0, 6, 0)
        self.store.append_exit_events(
            self.id, intent.intent_id,
            (e("mobile_runner_unknown", PaperOrderEventKind.UNKNOWN, 5),),
            as_of_ms=T+5)
        _, html = self.assert_state("RUNNER_EXIT_PENDING_RECONCILIATION", 0, 6, 0)
        self.assertIn("reconciliar", html)
        self.store.append_exit_events(
            self.id, intent.intent_id,
            (e("mobile_runner_cancel", PaperOrderEventKind.CANCELLED, 6),),
            as_of_ms=T+6)
        self.assert_state("RUNNER_EXIT_CANCELLED_REMAINDER", 0, 0, 6)
        nxt = exit_order("runner_mobile_replace", "6", 6, cap="6")
        self.store.reserve_exit(self.id, 0, nxt, as_of_ms=T+6)
        self.store.append_exit_events(
            self.id, nxt.intent_id,
            (e("mobile_runner_fill2", PaperOrderEventKind.FILL, 7, "2"),),
            as_of_ms=T+7)
        self.assert_state("RUNNER_EXIT_PENDING_RECONCILIATION", 2, 4, 0)
        self.store.append_exit_events(
            self.id, nxt.intent_id,
            (e("mobile_runner_cancel2", PaperOrderEventKind.CANCELLED, 8),),
            as_of_ms=T+8)
        self.assert_state("RUNNER_EXIT_PARTIALLY_FILLED", 2, 0, 4)
        last = exit_order("runner_mobile_last", "4", 8, cap="4")
        self.store.reserve_exit(self.id, 0, last, as_of_ms=T+8)
        self.store.append_exit_events(
            self.id, last.intent_id,
            (e("mobile_runner_fill4", PaperOrderEventKind.FILL, 9, "4"),),
            as_of_ms=T+9)
        snap, html = self.assert_state("RUNNER_CLOSED_PAPER_ONLY", 6, 0, 0)
        self.assertEqual(snap["positions"][0]["confirmed_remaining_units"], "0")
        self.assertIn("Runner encerrado no diário PAPER", html)
        self.assertIsNone(snap["positions"][0]["recovered_runner"])
        self.assertEqual(snap["positions"][0]["pending_or_unknown_orders"], 0)

    def test_after_runner_reservation_old_trailing_report_is_rejected(self):
        self.fixture.start()
        self.fixture.append("102", 1)
        self.fixture.append("103", 2)
        report = self.fixture.append("102", 3)
        current = self.store.load(self.id)
        intent = exit_order("runner_mobile_observe", "6", current.as_of_ms-T, cap="6")
        self.store.reserve_exit(self.id, 0, intent, as_of_ms=current.as_of_ms)
        selected = (inspect_paper_position(self.fixture.position_path, self.id),)
        with self.assertRaises(DataValidationError):
            multi_paper_snapshot(selected, runner_observation=(self.id, report))
        self.assert_state("RUNNER_EXIT_PENDING_RECONCILIATION", 0, 6, 0)

    def test_no_runner_configuration_is_not_mislabeled(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "no_runner.sqlite"
            journal = SQLitePaperPositionJournal(path)
            journal.create_position(
                position_id="fixture_no_runner_mobile16",
                opening_intent=opened_order(),
                opening_events=(e("mobile16_open", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=entire_plan(), plan_version="fixture_no_runner_mobile16",
                synthetic_lot_step_units=D(1), as_of_ms=T+1)
            snap = multi_paper_snapshot((
                inspect_paper_position(path, "fixture_no_runner_mobile16"),))
            p = snap["positions"][0]
            self.assertEqual(p["runner_readiness"], "NO_RESIDUAL_RUNNER_CONFIGURED")
            self.assertEqual(p["runner_unallocated_units"], "0")

    def test_snapshot_read_only_no_network_or_mutation(self):
        current = self.store.load(self.id)
        intent = exit_order("mobile_ro", "6", current.as_of_ms-T, cap="6")
        self.store.reserve_exit(self.id, 0, intent, as_of_ms=current.as_of_ms)
        before = self.fixture.position_path.read_bytes()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                snapshot, html = self.assert_state(
                    "RUNNER_EXIT_PENDING_RECONCILIATION", 0, 6, 0)
        self.assertEqual(before, self.fixture.position_path.read_bytes())
        self.assertTrue(json.loads(json.dumps(snapshot))["positions"][0]["runner_filled_units"] == "0")


class ShortRunnerMobileExitTests(unittest.TestCase):
    def test_short_runner_receipt_remains_paper_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "short.sqlite"
            store = SQLitePaperPositionJournal(path)
            opening = opened_order(
                intent_id="fixture_short_mobile_open",
                fixture_signal_id="fixture_short_mobile_signal",
                position_side=SyntheticSide.SHORT, side=PaperOrderSide.SELL)
            current = store.create_position(
                position_id="fixture_short_mobile16", opening_intent=opening,
                opening_events=(e("mobile16_short_fill", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=plan(), plan_version="fixture_short_mobile16_plan",
                synthetic_lot_step_units=D(1), as_of_ms=T+1)
            for idx, qty in enumerate((50, 30, 14), 1):
                intent = PaperOrderIntent(
                    intent_id=f"fixture_mobile16_short_exit_{idx}",
                    fixture_signal_id=f"fixture_mobile16_short_sig_{idx}",
                    venue=opening.venue, symbol=opening.symbol,
                    position_side=SyntheticSide.SHORT, side=PaperOrderSide.BUY,
                    effect=PaperOrderEffect.REDUCE_ONLY,
                    requested_units=D(qty), max_reducible_units=current.confirmed_remaining_units,
                    created_at_ms=current.as_of_ms)
                current = store.reserve_exit(current.position_id, idx, intent, as_of_ms=current.as_of_ms)
                current = store.append_exit_events(
                    current.position_id, intent.intent_id,
                    (e(f"mobile16_short_part{idx}", PaperOrderEventKind.FILL,
                       current.as_of_ms-T+1, str(qty)),),
                    as_of_ms=current.as_of_ms+1)
            last = PaperOrderIntent(
                intent_id="fixture_mobile16_short_runner",
                fixture_signal_id="fixture_mobile16_short_runner_sig",
                venue=opening.venue, symbol=opening.symbol,
                position_side=SyntheticSide.SHORT, side=PaperOrderSide.BUY,
                effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(6),
                max_reducible_units=D(6), created_at_ms=current.as_of_ms)
            store.reserve_exit(current.position_id, 0, last, as_of_ms=current.as_of_ms)
            snapshot = multi_paper_snapshot((inspect_paper_position(path, current.position_id),))
            self.assertEqual(snapshot["positions"][0]["runner_readiness"],
                             "RUNNER_EXIT_PENDING_RECONCILIATION")
            self.assertFalse(snapshot["positions"][0]["native_stop_verified"])


if __name__ == "__main__":
    unittest.main()
