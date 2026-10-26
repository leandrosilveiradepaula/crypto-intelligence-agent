"""J4/AUTO4: concurrent aggregate paper exit reservations and recovery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import (
    SQLitePaperPositionJournal,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
    plan_synthetic_partial_exits,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide


D = Decimal
T = 1792985000000


def opened_order(**changes):
    base = dict(
        intent_id="fixture_open_A", fixture_signal_id="fixture_signal_A",
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
        effect=PaperOrderEffect.OPEN, requested_units=D(100),
        created_at_ms=T,
    )
    base.update(changes)
    return PaperOrderIntent(**base)


def e(name, kind, at, qty="0"):
    return PaperOrderEvent(
        "fixture_event_" + name, kind, T + at, D(qty),
    )


def plan(*, floor="6"):
    return SyntheticExitPlan(
        initial_units=D(100),
        tranches=tuple(
            SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(pct))
            for pct in ("50", "60", "70")
        ),
        residual_floor_percent=D(floor),
    )


def entire_plan():
    return SyntheticExitPlan(
        initial_units=D(100),
        tranches=(SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(100)),),
    )


def exit_order(number, amount, created, *, cap="100", step=None):
    return PaperOrderIntent(
        intent_id=f"fixture_exit_{number}",
        fixture_signal_id=f"fixture_exit_signal_{number}",
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.SELL,
        effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(amount),
        max_reducible_units=D(cap), created_at_ms=T + created,
    )


class PaperPositionReservationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "position-paper.sqlite"
        self.store = SQLitePaperPositionJournal(self.path)

    def open(self, *, position_id="fixture_position_A", exit_plan=None):
        return self.store.create_position(
            position_id=position_id,
            opening_intent=opened_order(),
            opening_events=(e("open", PaperOrderEventKind.FILL, 1, "100"),),
            exit_plan=plan() if exit_plan is None else exit_plan,
            plan_version="paper-plan-v1", as_of_ms=T + 1,
        )

    def test_opening_is_derived_from_fills_not_ack_or_unknown(self):
        valid = self.open()
        self.assertEqual(valid.initial_confirmed_units, D(100))
        self.assertEqual(valid.opened_at_ms, T + 1)
        self.assertEqual(valid.filled_exit_units, D(0))
        self.assertEqual(valid.confirmed_remaining_units, D(100))
        self.assertEqual(valid.runner_floor_units, D(6))
        self.assertEqual([t.target_units for t in valid.tranches],
                         [D(50), D(30), D(14)])
        self.assertFalse(valid.orders_sent)
        self.assertFalse(valid.approved_for_live_use)
        self.assertFalse(valid.live_trading_authorized)
        self.assertFalse(valid.persistent_idempotency_verified)
        self.assertEqual(valid.quality, "synthetic_position_reservations_only")
        with self.assertRaises(FrozenInstanceError):
            valid.confirmed_remaining_units = D(0)
        with self.assertRaises(DataValidationError):
            self.store.create_position(
                position_id="fixture_no_fill",
                opening_intent=opened_order(intent_id="fixture_open_2"),
                opening_events=(e("ack", PaperOrderEventKind.ACKNOWLEDGED, 1),),
                exit_plan=plan(), plan_version="paper-plan-v1", as_of_ms=T + 1,
            )
        with self.assertRaises(DataValidationError):
            self.store.create_position(
                position_id="fixture_misreported_fill",
                opening_intent=opened_order(intent_id="fixture_open_3"),
                opening_events=(e("small", PaperOrderEventKind.FILL, 1, "10"),),
                exit_plan=plan(), plan_version="paper-plan-v1", as_of_ms=T + 1,
            )

    def test_realized_tranches_leave_six_percent_runner(self):
        current = self.open()
        amounts = ("50", "30", "14")
        for step, amount in enumerate(amounts, start=1):
            order = exit_order(str(step), amount, current.as_of_ms - T, cap=str(current.confirmed_remaining_units))
            current = self.store.reserve_exit(
                current.position_id, step, order, as_of_ms=current.as_of_ms,
            )
            self.assertEqual(current.reserved_unfilled_units, D(amount))
            current = self.store.append_exit_events(
                current.position_id, order.intent_id,
                (e("fill_" + str(step), PaperOrderEventKind.FILL,
                   current.as_of_ms - T + 1, amount),),
                as_of_ms=current.as_of_ms + 1,
            )
            self.assertEqual(current.reserved_unfilled_units, D(0))
        self.assertEqual(current.initial_confirmed_units, D(100))
        self.assertEqual(current.filled_exit_units, D(94))
        self.assertEqual(current.confirmed_remaining_units, D(6))
        self.assertEqual(current.unreserved_units, D(6))
        self.assertEqual([t.filled_units for t in current.tranches],
                         [D(50), D(30), D(14)])
        self.assertEqual(SQLitePaperPositionJournal(self.path).load(
            "fixture_position_A"), current)
        self.assertEqual(current.runner_floor_units, D(6))

    def test_second_exit_cannot_reserve_same_position_twice(self):
        self.open(exit_plan=entire_plan())
        first = exit_order("A", "60", 1)
        accepted = self.store.reserve_exit("fixture_position_A", 1, first, as_of_ms=T + 1)
        self.assertEqual(accepted.reserved_unfilled_units, D(60))
        with self.assertRaises(DataValidationError):
            SQLitePaperPositionJournal(self.path).reserve_exit(
                "fixture_position_A", 1, exit_order("B", "60", 1), as_of_ms=T + 1,
            )
        self.assertEqual(self.store.load("fixture_position_A"), accepted)

    def test_unknown_keeps_capacity_reserved_until_terminal_cancel(self):
        self.open()
        first = exit_order("A", "50", 1)
        self.store.reserve_exit("fixture_position_A", 1, first, as_of_ms=T + 1)
        uncertain = self.store.append_exit_events(
            "fixture_position_A", first.intent_id,
            (e("unknown", PaperOrderEventKind.UNKNOWN, 2),), as_of_ms=T + 2,
        )
        self.assertEqual(uncertain.reserved_unfilled_units, D(50))
        self.assertEqual(uncertain.exit_orders[0].snapshot.status, PaperOrderStatus.UNKNOWN)
        with self.assertRaises(DataValidationError):
            self.store.reserve_exit("fixture_position_A", 1,
                                    exit_order("B", "50", 2), as_of_ms=T + 2)
        canceled = self.store.append_exit_events(
            "fixture_position_A", first.intent_id,
            (e("cancel", PaperOrderEventKind.CANCELLED, 3),), as_of_ms=T + 3,
        )
        self.assertEqual(canceled.reserved_unfilled_units, D(0))
        replacement = exit_order("replace", "50", 3)
        after = self.store.reserve_exit(
            "fixture_position_A", 1, replacement, as_of_ms=T + 3,
        )
        self.assertEqual(after.reserved_unfilled_units, D(50))
        self.assertEqual(after.confirmed_remaining_units, D(100))

    def test_partial_fill_cancel_and_replace_uses_only_unrefilled_balance(self):
        self.open()
        first = exit_order("partial_A", "50", 1)
        self.store.reserve_exit("fixture_position_A", 1, first, as_of_ms=T + 1)
        partial = self.store.append_exit_events(
            "fixture_position_A", first.intent_id,
            (e("partial_fill", PaperOrderEventKind.FILL, 2, "20"),),
            as_of_ms=T + 2,
        )
        self.assertEqual(partial.filled_exit_units, D(20))
        self.assertEqual(partial.reserved_unfilled_units, D(30))
        self.assertEqual(partial.confirmed_remaining_units, D(80))
        self.assertEqual(partial.unreserved_units, D(50))
        canceled = self.store.append_exit_events(
            "fixture_position_A", first.intent_id,
            (e("cancel_partial", PaperOrderEventKind.CANCELLED, 3),),
            as_of_ms=T + 3,
        )
        self.assertEqual(canceled.reserved_unfilled_units, D(0))
        self.assertEqual(canceled.tranches[0].unallocated_units, D(30))
        with self.assertRaises(DataValidationError):
            self.store.reserve_exit("fixture_position_A", 1,
                exit_order("bad_replace", "40", 3, cap="80"), as_of_ms=T + 3)
        second = exit_order("remaining", "30", 3, cap="80")
        self.store.reserve_exit("fixture_position_A", 1, second, as_of_ms=T + 3)
        final = self.store.append_exit_events(
            "fixture_position_A", second.intent_id,
            (e("replaced_fill", PaperOrderEventKind.FILL, 4, "30"),),
            as_of_ms=T + 4,
        )
        self.assertEqual(final.filled_exit_units, D(50))
        self.assertEqual(final.confirmed_remaining_units, D(50))
        self.assertEqual(final.tranches[0].filled_units, D(50))
        self.assertEqual(final.tranches[0].unallocated_units, D(0))

    def test_idempotent_reserve_and_events_after_restart(self):
        first = self.open()
        self.assertEqual(self.open(), first)
        with self.assertRaises(DataValidationError):
            self.store.create_position(
                position_id=first.position_id,
                opening_intent=opened_order(),
                opening_events=(e("open", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=plan(floor="5"), plan_version="paper-plan-v1",
                as_of_ms=T + 1,
            )
        order = exit_order("idempotent", "50", 1)
        a = self.store.reserve_exit(first.position_id, 1, order, as_of_ms=T + 1)
        reopened = SQLitePaperPositionJournal(self.path)
        self.assertEqual(reopened.reserve_exit(first.position_id, 1, order,
                                              as_of_ms=T + 1), a)
        fill = e("idempotent_fill", PaperOrderEventKind.FILL, 2, "10")
        b = self.store.append_exit_events(first.position_id, order.intent_id,
                                          (fill,), as_of_ms=T + 2)
        self.assertEqual(reopened.append_exit_events(first.position_id, order.intent_id,
                                                     (fill,), as_of_ms=T + 2), b)
        self.assertEqual(b.exit_orders[0].snapshot.unique_event_count, 1)
        self.assertEqual(b.filled_exit_units, D(10))
        self.assertEqual(b.reserved_unfilled_units, D(40))

    def test_batch_with_invalid_second_event_has_no_partial_commit(self):
        self.open()
        order = exit_order("batch", "50", 1)
        self.store.reserve_exit("fixture_position_A", 1, order, as_of_ms=T + 1)
        before = self.store.load("fixture_position_A")
        with self.assertRaises(DataValidationError):
            self.store.append_exit_events(
                "fixture_position_A", order.intent_id,
                (e("valid", PaperOrderEventKind.ACKNOWLEDGED, 2),
                 e("overfill", PaperOrderEventKind.FILL, 3, "51")),
                as_of_ms=T + 3,
            )
        self.assertEqual(SQLitePaperPositionJournal(self.path).load(
            "fixture_position_A"), before)

    def test_crash_after_insert_order_id_rolls_back_full_position(self):
        self.open()
        before = self.store.load("fixture_position_A")
        order = exit_order("crash", "20", 1)
        with patch.object(SQLitePaperPositionJournal, "_update",
                          side_effect=RuntimeError("simulated disk exception")):
            with self.assertRaises(RuntimeError):
                self.store.reserve_exit("fixture_position_A", 1, order,
                                        as_of_ms=T + 1)
        reopened = SQLitePaperPositionJournal(self.path)
        self.assertEqual(reopened.load("fixture_position_A"), before)
        successful = reopened.reserve_exit("fixture_position_A", 1, order,
                                           as_of_ms=T + 1)
        self.assertEqual(successful.reserved_unfilled_units, D(20))
