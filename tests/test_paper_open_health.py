"""J4/AUTO8: local PAPER filled-OPEN health is deliberately fail-closed."""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_open_health import (
    PaperProtectionState, audit_paper_open_health,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

D = Decimal
T = 1_700_000_000_000


def opening():
    return PaperOrderIntent(
        "fixture_health_open", "fixture_health_signal", PaperVenue.BINANCE_USDM,
        "BTCUSDT", SyntheticSide.LONG, PaperOrderSide.BUY, PaperOrderEffect.OPEN,
        D(2), T,
    )


def fill():
    return PaperOrderEvent("fixture_health_fill", PaperOrderEventKind.FILL, T + 1, D(2))


def plan():
    return SyntheticExitPlan(D(2), (SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(100)),), D(0))


class PaperOpenHealthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.orders_path = Path(temp.name) / "orders.sqlite"
        self.positions_path = Path(temp.name) / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.orders_path)
        self.positions = SQLitePaperPositionJournal(self.positions_path)

    def test_empty_independent_journals_allow_next_paper_open(self):
        health = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertTrue(health.new_open_allowed)
        self.assertEqual(health.fills, ())
        self.assertFalse(health.cross_database_atomic_snapshot_available)

    def test_filled_open_without_position_is_unprotected_and_blocks(self):
        self.orders.reserve(opening())
        self.orders.append_events(opening().intent_id, (fill(),), as_of_ms=T + 1)
        health = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(health.new_open_allowed)
        self.assertEqual(health.reason, "paper_open_unprotected")
        self.assertEqual(health.fills[0].protection_state, PaperProtectionState.UNPROTECTED)

    def test_matching_position_is_hypothetical_only_and_still_blocks(self):
        self.orders.reserve(opening())
        self.orders.append_events(opening().intent_id, (fill(),), as_of_ms=T + 1)
        self.positions.create_position(
            position_id="fixture_health_position", opening_intent=opening(),
            opening_events=(fill(),), exit_plan=plan(), plan_version="fixture-v1",
            synthetic_lot_step_units=D(1), as_of_ms=T + 1,
        )
        health = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(health.new_open_allowed)
        self.assertEqual(health.reason, "paper_open_unverified_protection")
        self.assertTrue(health.unverified_protection)
        self.assertEqual(health.fills[0].protection_state,
                         PaperProtectionState.PROTECTED_HYPOTHETICAL_ONLY)
        self.assertFalse(health.native_stop_verified)

    def test_position_or_tampering_mismatch_is_unknown_and_blocks(self):
        self.positions.create_position(
            position_id="fixture_health_position", opening_intent=opening(),
            opening_events=(fill(),), exit_plan=plan(), plan_version="fixture-v1",
            synthetic_lot_step_units=D(1), as_of_ms=T + 1,
        )
        health = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(health.new_open_allowed)
        self.assertEqual(health.reason, "paper_open_health_unknown")
        with self.assertRaises(DataValidationError):
            audit_paper_open_health(self.orders_path, self.orders_path)

    def test_partial_fill_without_position_and_pending_only_are_distinct(self):
        self.orders.reserve(opening())
        pending = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertTrue(pending.new_open_allowed)  # AUTO6 separately gates pending.
        self.orders.append_events(
            opening().intent_id,
            (PaperOrderEvent("fixture_partial", PaperOrderEventKind.FILL,
                             T + 1, D(1)),),
            as_of_ms=T + 1,
        )
        partial = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(partial.new_open_allowed)
        self.assertEqual(partial.reason, "paper_open_unprotected")

    def test_matching_open_identity_with_different_fill_event_is_unknown(self):
        self.orders.reserve(opening())
        self.orders.append_events(opening().intent_id, (fill(),), as_of_ms=T + 1)
        other = PaperOrderEvent(
            "fixture_different_fill", PaperOrderEventKind.FILL, T + 1, D(2),
        )
        self.positions.create_position(
            position_id="fixture_health_position", opening_intent=opening(),
            opening_events=(other,), exit_plan=plan(), plan_version="fixture-v1",
            synthetic_lot_step_units=D(1), as_of_ms=T + 1,
        )
        result = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(result.new_open_allowed)
        self.assertEqual(result.reason, "paper_open_health_unknown")
        self.assertEqual(result.fills[0].reason, "opening_intent_or_fill_events_mismatch")

    def test_orphaned_position_order_index_fails_closed(self):
        with closing(sqlite3.connect(self.positions_path)) as conn, conn:
            conn.execute(
                "INSERT INTO paper_position_order_ids VALUES (?, ?)",
                ("fixture_orphaned_exit", "fixture_missing_position"),
            )
        with self.assertRaisesRegex(DataValidationError, "orphaned order index"):
            audit_paper_open_health(self.orders_path, self.positions_path)

    def _position_with_exit(self, *, units=D(2), filled=D(2),
                            floor=D(0)):
        """Construct only declared hypothetical OPEN/REDUCE_ONLY events."""
        self.orders.reserve(opening())
        self.orders.append_events(opening().intent_id, (fill(),), as_of_ms=T + 1)
        exit_plan = SyntheticExitPlan(
            D(2), (
                SyntheticExitTranche(
                    ExitBasis.INITIAL_POSITION, D(50) if floor else D(100),
                ),
            ), D(50) if floor else D(0),
        )
        self.positions.create_position(
            position_id="fixture_health_position", opening_intent=opening(),
            opening_events=(fill(),), exit_plan=exit_plan,
            plan_version="fixture-flat-v1", synthetic_lot_step_units=D(1),
            as_of_ms=T + 1,
        )
        intent = PaperOrderIntent(
            "fixture_exit_flat", "fixture_exit_signal_flat", PaperVenue.BINANCE_USDM,
            "BTCUSDT", SyntheticSide.LONG, PaperOrderSide.SELL,
            PaperOrderEffect.REDUCE_ONLY, units, T + 2, D(2),
        )
        self.positions.reserve_exit("fixture_health_position", 1, intent, as_of_ms=T + 2)
        if filled is not None:
            self.positions.append_exit_events(
                "fixture_health_position", intent.intent_id,
                (PaperOrderEvent("fixture_exit_fill", PaperOrderEventKind.FILL, T + 3, filled),),
                as_of_ms=T + 3,
            )
        return intent

    def test_complete_exit_qualifies_as_flat_paper_only(self):
        self._position_with_exit()
        h = audit_paper_open_health(
            self.orders_path, self.positions_path, decision_at_ms=T + 4,
        )
        self.assertTrue(h.new_open_allowed)
        self.assertTrue(h.closed_flat_paper_only)
        self.assertEqual(h.reason, "all_paper_positions_fully_flat_hypothetical_only")
        self.assertEqual(h.fills[0].protection_state,
                         PaperProtectionState.CLOSED_FLAT_HYPOTHETICAL_ONLY)
        self.assertFalse(h.native_stop_verified)
        self.assertFalse(h.approved_for_live_use)
        self.assertFalse(h.cross_database_atomic_snapshot_available)
        self.assertEqual(
            SQLitePaperPositionJournal(self.positions_path).load("fixture_health_position")
            .confirmed_remaining_units, D(0),
        )

    def test_residual_units_and_runner_floor_stay_blocked(self):
        self._position_with_exit(units=D(1), filled=D(1))
        h = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(h.new_open_allowed)
        self.assertEqual(h.reason, "paper_open_unverified_protection")
        self.assertFalse(h.closed_flat_paper_only)

    def test_fully_filled_runner_with_nonzero_original_floor_is_flat_only(self):
        self._position_with_exit(units=D(1), filled=D(1), floor=D(50))
        before = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(before.new_open_allowed)
        self.assertFalse(before.closed_flat_paper_only)
        runner = PaperOrderIntent(
            "fixture_health_runner_exit", "fixture_health_runner_signal",
            PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.SELL, PaperOrderEffect.REDUCE_ONLY, D(1),
            T + 4, D(1),
        )
        view = self.positions.reserve_exit(
            "fixture_health_position", 0, runner, as_of_ms=T + 4)
        self.assertEqual(view.runner_reserved_unfilled_units, D(1))
        pending = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(pending.new_open_allowed)
        self.positions.append_exit_events(
            "fixture_health_position", runner.intent_id,
            (PaperOrderEvent("fixture_health_runner_fill", PaperOrderEventKind.FILL,
                             T + 5, D(1)),),
            as_of_ms=T + 5)
        completed = self.positions.load("fixture_health_position")
        self.assertEqual(completed.runner_floor_units, D(1))
        self.assertEqual(completed.runner_filled_units, D(1))
        self.assertEqual(completed.runner_unallocated_units, D(0))
        self.assertEqual(completed.confirmed_remaining_units, D(0))
        final = audit_paper_open_health(
            self.orders_path, self.positions_path, decision_at_ms=T + 6)
        self.assertTrue(final.new_open_allowed)
        self.assertTrue(final.closed_flat_paper_only)
        self.assertEqual(final.reason,
                         "all_paper_positions_fully_flat_hypothetical_only")
        self.assertFalse(final.native_stop_verified)
        self.assertFalse(final.approved_for_live_use)

    def test_runner_floor_cannot_be_fully_consumed(self):
        self._position_with_exit(units=D(1), filled=D(1), floor=D(50))
        h = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(h.new_open_allowed)
        self.assertEqual(h.fills[0].protection_state,
                         PaperProtectionState.PROTECTED_HYPOTHETICAL_ONLY)

    def test_pending_unknown_and_partial_exit_do_not_count_as_flat(self):
        self._position_with_exit(filled=None)
        pending = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertEqual(pending.reason, "paper_open_health_unknown")
        self.assertEqual(pending.fills[0].reason, "unresolved_paper_reduce_only_exit")
        self.positions.append_exit_events(
            "fixture_health_position", "fixture_exit_flat",
            (PaperOrderEvent("fixture_exit_unknown", PaperOrderEventKind.UNKNOWN, T + 3),),
            as_of_ms=T + 3,
        )
        unresolved = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(unresolved.new_open_allowed)
        self.assertEqual(unresolved.fills[0].protection_state, PaperProtectionState.UNKNOWN)

    def test_partial_exit_fill_is_unresolved_not_flat(self):
        self._position_with_exit(filled=D(1))
        h = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(h.new_open_allowed)
        self.assertEqual(h.fills[0].protection_state, PaperProtectionState.UNKNOWN)
        self.assertEqual(h.fills[0].reason, "unresolved_paper_reduce_only_exit")

    def test_future_exit_checkpoint_and_order_checkpoint_fail_closed(self):
        self._position_with_exit()
        with self.assertRaisesRegex(DataValidationError, "future PAPER position checkpoint"):
            audit_paper_open_health(
                self.orders_path, self.positions_path, decision_at_ms=T + 2,
            )
        # Use a separate, empty but valid AUTO4 file to test order-cutoff
        # rejection without relying on which of two future files is read first.
        empty_positions = self.positions_path.parent / "empty_future_case.sqlite"
        SQLitePaperPositionJournal(empty_positions)
        with self.assertRaisesRegex(DataValidationError, "future PAPER order checkpoint"):
            audit_paper_open_health(
                self.orders_path, empty_positions, decision_at_ms=T,
            )
        with self.assertRaises(DataValidationError):
            audit_paper_open_health(
                self.orders_path, self.positions_path, decision_at_ms=True,
            )

    def test_multiple_positions_flat_plus_active_are_blocked_after_restart(self):
        self._position_with_exit()
        second = replace(
            opening(), intent_id="fixture_health_open_b",
            fixture_signal_id="fixture_health_signal_b", created_at_ms=T + 4,
        )
        other_fill = PaperOrderEvent(
            "fixture_health_fill_b", PaperOrderEventKind.FILL, T + 5, D(2),
        )
        self.orders.reserve(second)
        self.orders.append_events(second.intent_id, (other_fill,), as_of_ms=T + 5)
        self.positions.create_position(
            position_id="fixture_health_position_b", opening_intent=second,
            opening_events=(other_fill,), exit_plan=plan(),
            plan_version="fixture-v1", synthetic_lot_step_units=D(1),
            as_of_ms=T + 5,
        )
        h = audit_paper_open_health(
            self.orders_path, self.positions_path, decision_at_ms=T + 6,
        )
        self.assertFalse(h.new_open_allowed)
        self.assertFalse(h.closed_flat_paper_only)
        self.assertEqual(h.reason, "paper_open_unverified_protection")
        self.assertEqual(len(h.fills), 2)
        self.assertEqual(h, audit_paper_open_health(
            self.orders_path, self.positions_path, decision_at_ms=T + 6,
        ))

    def test_standalone_unresolved_reduce_only_blocks_even_after_flat(self):
        self._position_with_exit()
        extra = PaperOrderIntent(
            "fixture_other_reduce", "fixture_other_reduce_signal",
            PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.SELL, PaperOrderEffect.REDUCE_ONLY, D(1), T + 3, D(2),
        )
        self.orders.reserve(extra)
        h = audit_paper_open_health(
            self.orders_path, self.positions_path, decision_at_ms=T + 4,
        )
        self.assertFalse(h.new_open_allowed)
        self.assertEqual(h.reason, "paper_open_health_unknown")

    def test_no_network_or_orders(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                health = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(health.orders_sent)
        self.assertFalse(health.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
