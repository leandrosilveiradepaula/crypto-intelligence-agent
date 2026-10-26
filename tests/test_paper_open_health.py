"""J4/AUTO8: local PAPER filled-OPEN health is deliberately fail-closed."""
from __future__ import annotations

from contextlib import closing
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

    def test_no_network_or_orders(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                health = audit_paper_open_health(self.orders_path, self.positions_path)
        self.assertFalse(health.orders_sent)
        self.assertFalse(health.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
