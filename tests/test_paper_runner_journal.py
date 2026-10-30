"""J4 #387: durable PAPER runner recovery, no venue/exchange writes."""
from contextlib import closing
from decimal import Decimal as D
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_runner_journal import (
    start_paper_runner_journal, load_paper_runner_journal, append_paper_runner_mark,
)
from crypto_intelligence_agent.paper_runner_trailing import (
    PaperRunnerMark, PaperRunnerTrailPolicy, PaperRunnerTrailState,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEventKind, PaperOrderSide, PaperOrderIntent,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_paper_position_reservations import T, e, opened_order, plan, exit_order


def policy():
    return PaperRunnerTrailPolicy(D(100),D(50),5000,5000)


def tick(p,n):
    return PaperRunnerMark("BTCUSDT",T+100+1000*n,D(p))


class DurablePaperRunnerTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.position_path=self.root/"positions.sqlite"
        self.path=self.root/"trailing.sqlite"
        self.position=SQLitePaperPositionJournal(self.position_path)
        current=self.position.create_position(
            position_id="fixture_durable_runner",opening_intent=opened_order(),
            opening_events=(e("durable_open",PaperOrderEventKind.FILL,1,"100"),),
            exit_plan=plan(),plan_version="fixture_durable_v1",
            synthetic_lot_step_units=D(1),as_of_ms=T+1)
        for index,amount in enumerate(("50","30","14"),start=1):
            order=exit_order(f"durable{index}",amount,current.as_of_ms-T,
                             cap=str(current.confirmed_remaining_units))
            current=self.position.reserve_exit(current.position_id,index,order,
                                                as_of_ms=current.as_of_ms)
            current=self.position.append_exit_events(
                current.position_id,order.intent_id,
                (e(f"durable_fill{index}",PaperOrderEventKind.FILL,
                   current.as_of_ms-T+1,amount),),
                as_of_ms=current.as_of_ms+1)
        self.assertEqual(current.confirmed_remaining_units,D(6))
        self.id=current.position_id

    def start(self):
        return start_paper_runner_journal(
            self.path,self.position_path,self.id,
            policy=policy(),first_mark=tick("100",0),as_of_ms=T+100)

    def append(self,price,index,*,as_of_ms=None,policy_override=None):
        return append_paper_runner_mark(
            self.path,self.position_path,self.id,tick(price,index),
            policy=policy() if policy_override is None else policy_override,
            as_of_ms=T+100+index*1000 if as_of_ms is None else as_of_ms)

    def load(self,at):
        return load_paper_runner_journal(
            self.path,self.position_path,self.id,policy=policy(),
            as_of_ms=T+100+at*1000)

    def test_restart_replay_preserves_ratchet_and_terminal_trigger(self):
        self.assertEqual(self.start().state,PaperRunnerTrailState.NOT_ACTIVATED)
        self.assertEqual(self.append("102",1).state,PaperRunnerTrailState.TRACKING)
        self.assertEqual(self.append("103",2).last_stop_mark_quote,D("102.485"))
        checkpoint=self.load(2)
        self.assertEqual(checkpoint.last_stop_mark_quote,D("102.485"))
        self.assertEqual(checkpoint.observed_tick_count,3)
        triggered=self.append("102",3)
        self.assertEqual(triggered.state,PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY)
        self.assertEqual(triggered.triggered_tick_number,4)
        self.assertEqual(self.load(3),triggered)
        for field in ("orders_sent","approved_for_live_use","native_stop_verified",
                      "live_trading_authorized"):
            self.assertFalse(triggered.sanitized_report()[field])
        with self.assertRaises(DataValidationError):
            self.append("104",4)
        self.assertEqual(self.load(3),triggered)

    def test_duplicate_exact_last_tick_is_idempotent_and_conflict_is_rejected(self):
        self.start()
        r=self.append("102",1)
        self.assertEqual(self.append("102",1),r)
        with self.assertRaises(DataValidationError):
            self.append("103",1)
        self.assertEqual(self.load(1),r)
        with self.assertRaises(DataValidationError):
            self.start()

    def test_gap_staleness_bad_symbol_and_policy_fail_without_writes(self):
        self.start()
        before=self.load(0)
        with self.assertRaises(DataValidationError):
            self.append("101",10)
        with self.assertRaises(DataValidationError):
            self.append("101",-1)
        with self.assertRaises(DataValidationError):
            self.append("102",1,policy_override=PaperRunnerTrailPolicy(
                D(100),D(75),5000,5000))
        with self.assertRaises(DataValidationError):
            append_paper_runner_mark(
                self.path,self.position_path,self.id,
                PaperRunnerMark("ETHUSDT",T+1100,D(102)),
                policy=policy(),as_of_ms=T+1100)
        with self.assertRaises(DataValidationError):
            self.append("102",1,as_of_ms=T+100000)
        self.assertEqual(self.load(0),before)

    def test_position_checkpoint_is_pinned_even_if_journal_changes(self):
        self.start()
        with self.assertRaises(DataValidationError):
            load_paper_runner_journal(
                self.path,self.position_path,"fixture_nonexistent",
                policy=policy(),as_of_ms=T+100)
        with self.assertRaises(DataValidationError):
            load_paper_runner_journal(
                self.path,self.position_path,self.id,
                policy=PaperRunnerTrailPolicy(D(90),D(50),5000,5000),
                as_of_ms=T+100)
        self.assertEqual(self.load(0).observed_tick_count,1)

    def test_corrupt_digest_schema_and_missing_file_fail_closed(self):
        with self.assertRaises(DataValidationError):
            self.load(0)
        self.start()
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE paper_runner_state SET digest='bad'")
        with self.assertRaises(DataValidationError):
            self.load(0)
        with self.assertRaises(DataValidationError):
            self.append("102",1)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE foreign_table(x TEXT)")
        with self.assertRaises(DataValidationError):
            self.load(0)

    def test_no_exchange_or_new_position_writes(self):
        before=self.position.load(self.id)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            self.start()
            self.append("102",1)
            self.load(1)
        self.assertEqual(before,self.position.load(self.id))
        if os.name == "posix":
            self.assertEqual(self.path.stat().st_mode & 0o777,0o600)

    def test_unconfirmed_runner_never_creates_db(self):
        with tempfile.TemporaryDirectory() as folder:
            position_path=Path(folder)/"pending.sqlite"
            journal=SQLitePaperPositionJournal(position_path)
            journal.create_position(
                position_id="fixture_unconfirmed",opening_intent=opened_order(),
                opening_events=(e("pending_open",PaperOrderEventKind.FILL,1,"100"),),
                exit_plan=plan(),plan_version="fixture_pending_v1",
                synthetic_lot_step_units=D(1),as_of_ms=T+1)
            missing=Path(folder)/"runner.sqlite"
            with self.assertRaises(DataValidationError):
                start_paper_runner_journal(
                    missing,position_path,"fixture_unconfirmed",policy=policy(),
                    first_mark=tick("100",0),as_of_ms=T+100)
            self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
