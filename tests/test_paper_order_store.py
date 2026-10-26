"""Offline tests for paper-only SQLite journal persistence and recovery."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

T = 1792985000000
D = Decimal


def make_intent(**updates):
    args = dict(
        intent_id="fixture_intent_A", fixture_signal_id="fixture_signal_A",
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
        effect=PaperOrderEffect.OPEN, requested_units=D("10"),
        created_at_ms=T,
    )
    args.update(updates)
    return PaperOrderIntent(**args)


def make_event(name, kind, at, filled="0"):
    return PaperOrderEvent(
        event_id="fixture_event_" + name, kind=kind,
        event_at_ms=T + at, filled_units=D(filled),
    )


class PaperOrderStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "paper.sqlite"
        self.store = SQLitePaperOrderJournal(self.db)

    def test_idempotent_reserve_and_restart(self):
        i = make_intent()
        first = self.store.reserve(i)
        self.assertEqual(first.snapshot.status, PaperOrderStatus.PENDING)
        self.assertEqual(first.events, ())
        self.assertFalse(first.orders_sent)
        self.assertFalse(first.approved_for_live_use)
        self.assertFalse(first.persistent_idempotency_verified)
        self.assertEqual(SQLitePaperOrderJournal(self.db).load(i.intent_id), first)
        self.assertEqual(SQLitePaperOrderJournal(self.db).reserve(i), first)
        with self.assertRaises(DataValidationError):
            self.store.reserve(replace(i, requested_units=D("10.00")))
        self.assertEqual(self.store.load(i.intent_id), first)

    def test_same_signal_cannot_open_twice_even_on_other_venue(self):
        i = make_intent()
        self.store.reserve(i)
        other = SQLitePaperOrderJournal(self.db)
        for changes in (
            dict(intent_id="fixture_intent_B"),
            dict(intent_id="fixture_intent_C", venue=PaperVenue.BYBIT_V5),
            dict(intent_id="fixture_intent_D", symbol="ETHUSDT"),
        ):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                other.reserve(replace(i, **changes))
        independent = replace(
            i, intent_id="fixture_intent_E",
            fixture_signal_id="fixture_signal_E",
        )
        self.assertEqual(other.reserve(independent).intent, independent)

    def test_unknown_blocks_new_open_until_explicit_reconciliation(self):
        i = make_intent()
        self.store.reserve(i)
        timeout = make_event("timeout", PaperOrderEventKind.UNKNOWN, 1)
        a = self.store.append_events(i.intent_id, (timeout,), as_of_ms=T + 1)
        self.assertEqual(a.snapshot.status, PaperOrderStatus.UNKNOWN)
        self.assertTrue(a.snapshot.requires_reconciliation)
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.db).reserve(
                replace(i, intent_id="fixture_intent_RETRY")
            )
        fill = make_event("confirmed", PaperOrderEventKind.FILL, 2, "10")
        b = SQLitePaperOrderJournal(self.db).append_events(
            i.intent_id, (fill,), as_of_ms=T + 2,
        )
        self.assertEqual(b.snapshot.status, PaperOrderStatus.FILLED)
        self.assertEqual(b.snapshot.filled_total_units, D(10))
        self.assertFalse(b.snapshot.requires_reconciliation)
        self.assertFalse(b.orders_sent)

    def test_ack_not_fill_and_partial_cancel(self):
        i = make_intent()
        self.store.reserve(i)
        ack = make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1)
        first = self.store.append_events(i.intent_id, (ack,), as_of_ms=T + 1)
        self.assertEqual(first.snapshot.filled_total_units, D(0))
        self.assertEqual(first.snapshot.status, PaperOrderStatus.ACKNOWLEDGED)
        fill = make_event("partial", PaperOrderEventKind.FILL, 2, "4")
        cancel = make_event("cancel", PaperOrderEventKind.CANCELLED, 3)
        completed = self.store.append_events(i.intent_id, (fill, cancel), as_of_ms=T + 3)
        self.assertEqual(completed.snapshot.status, PaperOrderStatus.CANCELLED)
        self.assertEqual(completed.snapshot.filled_total_units, D(4))
        self.assertEqual(completed.snapshot.unfilled_units, D(6))
        self.assertEqual(SQLitePaperOrderJournal(self.db).load(i.intent_id), completed)

    def test_replaying_same_batch_does_not_duplicate_fill(self):
        i = make_intent()
        self.store.reserve(i)
        events = (
            make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1),
            make_event("part", PaperOrderEventKind.FILL, 2, "5"),
        )
        first = self.store.append_events(i.intent_id, events, as_of_ms=T + 2)
        after = SQLitePaperOrderJournal(self.db).append_events(
            i.intent_id, events, as_of_ms=T + 2,
        )
        self.assertEqual(after, first)
        self.assertEqual(after.snapshot.filled_total_units, D(5))
        self.assertEqual(after.snapshot.unique_event_count, 2)
        self.assertEqual(after.snapshot.exact_duplicate_count, 0)
        with sqlite3.connect(self.db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM paper_order_events").fetchone()[0]
        self.assertEqual(count, 2)

    def test_second_invalid_event_does_not_commit_first(self):
        i = make_intent()
        first = self.store.reserve(i)
        a = make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1)
        b = make_event("overfill", PaperOrderEventKind.FILL, 2, "11")
        with self.assertRaises(DataValidationError):
            self.store.append_events(i.intent_id, (a, b), as_of_ms=T + 2)
        self.assertEqual(SQLitePaperOrderJournal(self.db).load(i.intent_id), first)

    def test_crash_while_inserting_second_event_rolls_back(self):
        i = make_intent()
        self.store.reserve(i)
        a = make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1)
        b = make_event("part", PaperOrderEventKind.FILL, 2, "5")
        original = SQLitePaperOrderJournal._insert_event
        count = 0

        def crashing_insert(conn, identity, seq, value):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("synthetic interrupted write")
            return original(conn, identity, seq, value)

        with patch.object(SQLitePaperOrderJournal, "_insert_event",
                          side_effect=crashing_insert):
            with self.assertRaises(RuntimeError):
                self.store.append_events(i.intent_id, (a, b), as_of_ms=T + 2)
        loaded = SQLitePaperOrderJournal(self.db).load(i.intent_id)
        self.assertEqual(loaded.events, ())
        self.assertEqual(loaded.snapshot.as_of_ms, T)
        self.assertEqual(loaded.snapshot.filled_total_units, D(0))
        resolved = self.store.append_events(i.intent_id, (a, b), as_of_ms=T + 2)
        self.assertEqual(resolved.snapshot.filled_total_units, D(5))


if __name__ == "__main__":
    unittest.main()
