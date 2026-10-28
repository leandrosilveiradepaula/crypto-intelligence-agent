"""J6/PRE7 #266: durable-replay to REDUCE_ONLY recovery E2E, fail-closed.

All artifacts are local synthetic journals. No network, exchange account,
real positions, real orders, deployment or provider credentials.
"""
from __future__ import annotations

from contextlib import closing, redirect_stdout
from dataclasses import FrozenInstanceError
from decimal import Decimal
from io import StringIO
import json
from pathlib import Path
import socket
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import crypto_intelligence_agent.paper_recovery_status as recovery_module
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.offline_paper_batch import (
    run_durable_offline_paper_batch,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import (
    SQLitePaperPositionJournal,
)
from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, inspect_local_paper_recovery_status,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.inspect_paper_recovery import main as recovery_cli
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import candles, config


D = Decimal


class PaperRecoveryEndToEndTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.order_path = self.root / "orders.sqlite"
        self.position_path = self.root / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.order_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        self.cs = candles(n=10)
        self.observations = tuple(
            observation(c.close_time_ms + 1_000) for c in self.cs
        )

    def batch(self, steps=2):
        return run_durable_offline_paper_batch(
            self.cs, observations=self.observations,
            strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D(2), limits=limits(), journal=self.orders,
            position_journal_path=self.position_path,
            bootstrap_candles=5, max_new_steps=steps, max_candles=20,
        )

    def inspect(self, *, decision_at_ms=None):
        return inspect_local_paper_recovery_status(
            self.order_path, self.position_path,
            decision_at_ms=decision_at_ms,
        )

    def existing_open(self):
        with closing(sqlite3.connect(self.order_path)) as conn:
            row = conn.execute(
                "SELECT intent_id FROM paper_order_intents WHERE effect='OPEN'"
            ).fetchone()
        self.assertIsNotNone(row)
        return self.orders.load(row[0])

    def filled_open(self, *, with_position=True, runner=False):
        report = self.batch(2)
        self.assertEqual(report.reserved_open_intents, 1)
        entry = self.existing_open()
        event = PaperOrderEvent(
            "fixture_recovery_open_fill", PaperOrderEventKind.FILL,
            entry.snapshot.as_of_ms + 1, D(2),
        )
        self.orders.append_events(
            entry.intent.intent_id, (event,), as_of_ms=event.event_at_ms,
        )
        if with_position:
            share = D(50) if runner else D(100)
            plan = SyntheticExitPlan(
                D(2), (
                    SyntheticExitTranche(ExitBasis.INITIAL_POSITION, share),
                ), D(50) if runner else D(0),
            )
            self.positions.create_position(
                position_id="fixture_recovery_position",
                opening_intent=entry.intent,
                opening_events=(event,), exit_plan=plan,
                plan_version="fixture-recovery-v1",
                synthetic_lot_step_units=D(1),
                as_of_ms=event.event_at_ms,
            )
        return entry.intent, event

    def reserve_and_fill_exit(self, opening, open_fill, *, units=D(2), filled=D(2)):
        moment = open_fill.event_at_ms + 1
        exit_side = (
            PaperOrderSide.SELL if opening.position_side is SyntheticSide.LONG
            else PaperOrderSide.BUY
        )
        intent = PaperOrderIntent(
            "fixture_recovery_exit", "fixture_recovery_exit_signal",
            opening.venue, opening.symbol, opening.position_side,
            exit_side, PaperOrderEffect.REDUCE_ONLY, units, moment, D(2),
        )
        self.positions.reserve_exit(
            "fixture_recovery_position", 1, intent, as_of_ms=moment,
        )
        if filled is not None:
            self.positions.append_exit_events(
                "fixture_recovery_position", intent.intent_id,
                (PaperOrderEvent(
                    "fixture_recovery_exit_fill", PaperOrderEventKind.FILL,
                    moment + 1, filled,
                ),), as_of_ms=moment + 1,
            )

    def assert_no_authorization(self, status):
        self.assertFalse(status.cross_database_atomic_snapshot_available)
        self.assertFalse(status.native_stop_verified)
        self.assertFalse(status.new_open_authorized)
        self.assertFalse(status.orders_sent)
        self.assertFalse(status.live_trading_authorized)
        with self.assertRaises(FrozenInstanceError):
            status.new_open_authorized = True

    def test_new_journals_without_cursor_are_unverified(self):
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.UNVERIFIED)
        self.assertEqual(status.reason, "paper_replay_not_initialized")
        self.assert_no_authorization(status)

    def test_cursor_with_no_open_only_proves_hypothetical_flat(self):
        first = self.batch(1)
        self.assertEqual(first.reserved_open_intents, 0)
        self.orders = SQLitePaperOrderJournal(self.order_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        before = (self.order_path.read_bytes(), self.position_path.read_bytes())
        status = self.inspect()
        self.assertEqual(
            status.state, PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY,
        )
        self.assertEqual(status.reason, "paper_flat_not_live_verified")
        self.assertTrue(status.operator.durable_cursor_present)
        self.assert_no_authorization(status)
        self.assertEqual(
            (self.order_path.read_bytes(), self.position_path.read_bytes()),
            before,
        )

    def test_pending_open_with_cursor_is_blocked(self):
        self.batch(2)
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(status.reason, "paper_order_reconciliation_required")
        self.assertEqual(status.operator.pending_or_unresolved_open_count, 1)
        self.assert_no_authorization(status)

    def test_unknown_open_after_cursor_is_blocked(self):
        self.batch(2)
        entry = self.existing_open()
        event = PaperOrderEvent(
            "fixture_recovery_unknown", PaperOrderEventKind.UNKNOWN,
            entry.snapshot.as_of_ms + 1, D(0),
        )
        self.orders.append_events(
            entry.intent.intent_id, (event,), as_of_ms=event.event_at_ms,
        )
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(status.reason, "paper_order_reconciliation_required")
        self.assertTrue(status.operator.unknown_open_requires_reconciliation)

    def test_filled_open_without_auto4_position_is_blocked(self):
        self.filled_open(with_position=False)
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(status.reason, "paper_open_unprotected")
        self.assert_no_authorization(status)

    def test_matching_position_without_native_stop_is_blocked(self):
        self.filled_open()
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(status.reason, "paper_open_unverified_protection")
        self.assert_no_authorization(status)

    def test_partial_reduce_only_fill_does_not_certify_flat(self):
        opening, open_fill = self.filled_open()
        self.reserve_and_fill_exit(
            opening, open_fill, units=D(2), filled=D(1),
        )
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(status.reason, "paper_open_health_unknown")
        self.assert_no_authorization(status)

    def test_fully_filled_reduce_only_is_only_hypothetical_flat(self):
        opening, open_fill = self.filled_open()
        self.reserve_and_fill_exit(opening, open_fill)
        self.orders = SQLitePaperOrderJournal(self.order_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        status = self.inspect()
        self.assertEqual(
            status.state, PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY,
        )
        self.assert_no_authorization(status)
        self.assertEqual(
            self.positions.load("fixture_recovery_position")
            .confirmed_remaining_units, D(0),
        )

    def test_runner_floor_still_blocks_after_partial_exit(self):
        opening, open_fill = self.filled_open(runner=True)
        self.reserve_and_fill_exit(
            opening, open_fill, units=D(1), filled=D(1),
        )
        status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(status.reason, "paper_open_unverified_protection")

    def test_persisted_pause_then_resume_changes_diagnostic(self):
        self.batch(1)
        at = self.cs[4].close_time_ms + 1_001
        self.orders.set_local_kill_switch(
            pause=True, expected_sequence=0, changed_at_ms=at,
        )
        self.orders = SQLitePaperOrderJournal(self.order_path)
        paused = self.inspect()
        self.assertEqual(paused.state, PaperRecoveryState.BLOCKED)
        self.assertEqual(paused.reason, "paper_operator_paused")
        self.orders.set_local_kill_switch(
            pause=False, expected_sequence=1,
            changed_at_ms=at + 1, acknowledge_resume=True,
        )
        resumed = self.inspect()
        self.assertEqual(
            resumed.state, PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY,
        )
        self.assert_no_authorization(resumed)

    def test_corrupt_position_and_cursor_both_fail_closed(self):
        self.filled_open()
        with closing(sqlite3.connect(self.position_path)) as con, con:
            con.execute("UPDATE paper_positions SET payload='{}'")
        corrupted = self.inspect()
        self.assertEqual(corrupted.state, PaperRecoveryState.UNVERIFIED)
        self.assertEqual(corrupted.reason, "paper_journal_unverified")
        self.assert_no_authorization(corrupted)

    def test_change_to_order_pause_between_readers_is_unverified(self):
        self.batch(1)
        source = recovery_module.inspect_local_paper_operator_status
        count = 0

        def mutate_after_first_read(path):
            nonlocal count
            result = source(path)
            count += 1
            if count == 1:
                self.orders.set_local_kill_switch(
                    pause=True, expected_sequence=0,
                    changed_at_ms=self.cs[4].close_time_ms + 1_001,
                )
            return result

        with patch.object(
            recovery_module, "inspect_local_paper_operator_status",
            side_effect=mutate_after_first_read,
        ):
            status = self.inspect()
        self.assertEqual(count, 2)
        self.assertEqual(status.state, PaperRecoveryState.UNVERIFIED)
        self.assertEqual(
            status.reason, "paper_snapshot_changed_during_inspection",
        )
        self.assertIsNone(status.operator)
        self.assert_no_authorization(status)

    def test_change_to_exit_between_health_reads_is_unverified(self):
        opening, open_fill = self.filled_open()
        source = recovery_module.audit_paper_open_health
        count = 0

        def mutate_after_first_health(*args, **kwargs):
            nonlocal count
            result = source(*args, **kwargs)
            count += 1
            if count == 1:
                self.reserve_and_fill_exit(opening, open_fill)
            return result

        with patch.object(
            recovery_module, "audit_paper_open_health",
            side_effect=mutate_after_first_health,
        ):
            status = self.inspect()
        self.assertEqual(count, 2)
        self.assertEqual(status.state, PaperRecoveryState.UNVERIFIED)
        self.assertEqual(
            status.reason, "paper_snapshot_changed_during_inspection",
        )
        self.assert_no_authorization(status)

    def test_invalid_second_health_snapshot_fails_closed(self):
        self.batch(1)
        source = recovery_module.audit_paper_open_health
        count = 0

        def invalid_second_read(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise DataValidationError("injected read failure")
            return source(*args, **kwargs)

        with patch.object(
            recovery_module, "audit_paper_open_health",
            side_effect=invalid_second_read,
        ):
            status = self.inspect()
        self.assertEqual(status.state, PaperRecoveryState.UNVERIFIED)
        self.assertEqual(status.reason, "paper_journal_unverified")

    def test_cli_sanitized_and_no_network_for_recovered_flat(self):
        self.batch(1)
        before = (self.order_path.read_bytes(), self.position_path.read_bytes())
        out = StringIO()
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                with redirect_stdout(out):
                    result = recovery_cli([
                        "--orders", str(self.order_path),
                        "--positions", str(self.position_path),
                    ])
        self.assertEqual(result, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["state"], "PAPER_FLAT_HYPOTHETICAL_ONLY")
        for key in (
            "cross_database_atomic_snapshot_available", "native_stop_verified",
            "new_open_authorized", "orders_sent", "live_trading_authorized",
        ):
            self.assertFalse(data[key])
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertNotIn("BTCUSDT", out.getvalue())
        self.assertEqual(
            (self.order_path.read_bytes(), self.position_path.read_bytes()),
            before,
        )

    def test_real_durable_replay_states_render_without_promoting_live(self):
        from scripts.inspect_paper_recovery import render_recovery_html
        self.batch(2)
        pending = render_recovery_html(self.inspect())
        self.assertIn('data-state="BLOCKED"', pending)
        self.assertIn("Novas OPEN autorizadas por esta página", pending)
        self.assertIn("<dd>NÃO</dd>", pending)
        # The operator journal has a durable cursor; the pending OPEN still
        # blocks recovery and the UI cannot turn a local plan into a stop.
        self.assertNotIn(str(self.root), pending)

    def test_real_flat_replay_html_cli_is_static_and_read_only(self):
        from scripts.inspect_paper_recovery import render_recovery_html
        self.batch(1)
        status = self.inspect()
        before = (self.order_path.read_bytes(), self.position_path.read_bytes())
        html = render_recovery_html(status)
        self.assertIn('data-state="PAPER_FLAT_HYPOTHETICAL_ONLY"', html)
        self.assertIn("SIMULAÇÃO OFFLINE", html)
        self.assertIn("<dd>NÃO</dd>", html)
        self.assertEqual(
            before, (self.order_path.read_bytes(), self.position_path.read_bytes()),
        )

    def test_invalid_decision_clock_does_not_claim_recovery(self):
        self.batch(1)
        self.assertEqual(
            self.inspect(decision_at_ms=True).state,
            PaperRecoveryState.UNVERIFIED,
        )


if __name__ == "__main__":
    unittest.main()
