"""Offline tests for paper-only SQLite journal persistence and recovery."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
from contextlib import closing
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
        with closing(sqlite3.connect(self.db)) as conn, conn:
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


    def test_duplicate_conflict_and_causal_checkpoint_fail_closed(self):
        i = make_intent()
        self.store.reserve(i)
        ack = make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1)
        self.store.append_events(i.intent_id, (ack,), as_of_ms=T + 1)
        initial = self.store.load(i.intent_id)
        with self.assertRaises(DataValidationError):
            self.store.append_events(i.intent_id, (
                make_event("first", PaperOrderEventKind.FILL, 2, "2"),
                replace(ack, kind=PaperOrderEventKind.UNKNOWN),
            ), as_of_ms=T + 2)
        with self.assertRaises(DataValidationError):
            self.store.append_events(i.intent_id, (
                make_event("backdated", PaperOrderEventKind.FILL, 0, "1"),
            ), as_of_ms=T + 2)
        with self.assertRaises(DataValidationError):
            self.store.append_events(i.intent_id, (
                make_event("future", PaperOrderEventKind.FILL, 4, "2"),
            ), as_of_ms=T + 3)
        with self.assertRaises(DataValidationError):
            self.store.append_events(i.intent_id, (), as_of_ms=T)
        self.assertEqual(SQLitePaperOrderJournal(self.db).load(i.intent_id), initial)

    def test_invalid_input_does_not_change_database(self):
        with self.assertRaises(DataValidationError):
            self.store.reserve(object())
        with self.assertRaises(DataValidationError):
            self.store.load("not_a_fixture")
        with self.assertRaises(DataValidationError):
            self.store.load("fixture_unknown")
        i = make_intent()
        self.store.reserve(i)
        original = self.store.load(i.intent_id)
        for batch in (
            [make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1)],
            (object(),),
        ):
            with self.subTest(batch=batch), self.assertRaises(DataValidationError):
                self.store.append_events(i.intent_id, batch, as_of_ms=T + 1)
        self.assertEqual(self.store.load(i.intent_id), original)

    def test_reduce_only_enforces_stated_fixture_limit(self):
        with self.assertRaises(DataValidationError):
            make_intent(
                intent_id="fixture_exit_A", fixture_signal_id="fixture_close_A",
                effect=PaperOrderEffect.REDUCE_ONLY, side=PaperOrderSide.SELL,
                max_reducible_units=D("9"),
            )
        close = make_intent(
            intent_id="fixture_exit_B", fixture_signal_id="fixture_close_B",
            effect=PaperOrderEffect.REDUCE_ONLY, side=PaperOrderSide.SELL,
            max_reducible_units=D("10"),
        )
        self.store.reserve(close)
        result = self.store.append_events(
            close.intent_id,
            (make_event("close", PaperOrderEventKind.FILL, 1, "10"),),
            as_of_ms=T + 1,
        )
        self.assertEqual(result.snapshot.status, PaperOrderStatus.FILLED)
        self.assertEqual(result.snapshot.filled_total_units, D(10))
        self.assertEqual(SQLitePaperOrderJournal(self.db).load(close.intent_id), result)
        self.assertFalse(result.orders_sent)

    def test_corrupt_event_or_checkpoint_fails_closed_after_restart(self):
        i = make_intent()
        self.store.reserve(i)
        ack = make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1)
        self.store.append_events(i.intent_id, (ack,), as_of_ms=T + 1)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE paper_order_events SET payload='{}'")
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.db).load(i.intent_id)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("DELETE FROM paper_order_events")
            conn.execute("UPDATE paper_order_intents SET event_count=0")
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.db).load(i.intent_id)

    def test_foreign_schema_and_unknown_version_refused(self):
        for path in (":memory:", "file::memory:?cache=shared", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                SQLitePaperOrderJournal(path)
        foreign_path = self.db.parent / "market.sqlite"
        with closing(sqlite3.connect(foreign_path)) as conn, conn:
            conn.execute("CREATE TABLE candles (source TEXT)")
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(foreign_path)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE paper_order_meta SET value='unknown-v2'")
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.db)

    def test_concurrent_open_reservations_use_sqlite_unique_gate(self):
        from concurrent.futures import ThreadPoolExecutor

        a = make_intent(
            intent_id="fixture_race_A", fixture_signal_id="fixture_race",
        )
        b = make_intent(
            intent_id="fixture_race_B", fixture_signal_id="fixture_race",
        )
        def reserve(i):
            try:
                SQLitePaperOrderJournal(self.db).reserve(i)
                return "stored"
            except DataValidationError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve, (a, b)))
        self.assertEqual(sorted(results), ["blocked", "stored"])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM paper_order_intents "
                "WHERE fixture_signal_id='fixture_race'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_paper_journal_does_not_use_network(self):
        with patch("urllib.request.urlopen",
                   side_effect=AssertionError("unexpected network")):
            i = make_intent()
            self.store.reserve(i)
            self.store.append_events(
                i.intent_id,
                (make_event("ack", PaperOrderEventKind.ACKNOWLEDGED, 1),),
                as_of_ms=T + 1,
            )
            item = SQLitePaperOrderJournal(self.db).load(i.intent_id)
        self.assertFalse(item.orders_sent)
        self.assertFalse(item.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
