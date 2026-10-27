"""J4/J5 #232: persisted PAPER pause protects all local OPEN reservation paths."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.offline_paper_durable_cursor import (
    recover_durable_offline_paper, step_durable_offline_paper,
)
from crypto_intelligence_agent.paper_open_health import audit_paper_open_health
from crypto_intelligence_agent.paper_operator_kill_switch import KEY, PaperLocalKillSwitchState
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import PaperRiskReason
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from scripts.control_paper_kill_switch import run
from test_causal_paper_open import limits as causal_limits, observation as causal_obs
from test_paper_risk_gate import T, intent, limits, obs
from test_synthetic_research_cycle import candles, config


D = Decimal


class PaperOperatorKillSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "orders.sqlite"
        self.position_path = self.root / "positions.sqlite"
        self.journal = SQLitePaperOrderJournal(self.db)
        SQLitePaperPositionJournal(self.position_path)

    def pause(self):
        return self.journal.set_local_kill_switch(
            pause=True, expected_sequence=0, changed_at_ms=T + 1,
        )

    def test_defaults_and_pause_durable_across_restart(self):
        first = self.journal.read_local_kill_switch()
        self.assertIsInstance(first, PaperLocalKillSwitchState)
        self.assertFalse(first.active)
        self.assertEqual((first.sequence, first.changed_at_ms), (0, 0))
        paused = self.pause()
        self.assertTrue(paused.active)
        self.assertEqual(paused.sequence, 1)
        self.assertEqual(paused.last_action, "pause")
        self.assertFalse(paused.live_trading_authorized)
        self.assertFalse(paused.orders_sent)
        self.assertFalse(paused.order_submission_enabled)
        with self.assertRaises(FrozenInstanceError):
            paused.active = False
        self.assertEqual(SQLitePaperOrderJournal(self.db).read_local_kill_switch(), paused)

    def test_stale_caller_unpaused_fixture_cannot_open(self):
        self.pause()
        another = SQLitePaperOrderJournal(self.db)
        out = another.reserve_open_if_paper_risk(
            intent(), limits(), obs(kill_switch_active=False), decision_at_ms=T + 2,
        )
        self.assertFalse(out.decision.allowed_for_paper_only)
        self.assertEqual(out.decision.reason, PaperRiskReason.KILL_SWITCH)
        self.assertIsNone(out.entry)
        with self.assertRaisesRegex(DataValidationError, "kill switch"):
            another.reserve(intent())
        self.assertFalse(out.orders_sent)
        self.assertFalse(out.approved_for_live_use)

    def test_resume_is_explicit_sequenced_and_never_overrides_input_kill(self):
        self.pause()
        for updates in (
            dict(pause=True, expected_sequence=1, changed_at_ms=T + 2),
            dict(pause=False, expected_sequence=0, changed_at_ms=T + 2,
                 acknowledge_resume=True),
            dict(pause=False, expected_sequence=1, changed_at_ms=T + 2),
            dict(pause=False, expected_sequence=1, changed_at_ms=T,
                 acknowledge_resume=True),
        ):
            with self.subTest(updates=updates), self.assertRaises(DataValidationError):
                self.journal.set_local_kill_switch(**updates)
            self.assertTrue(self.journal.read_local_kill_switch().active)
        restored = SQLitePaperOrderJournal(self.db).set_local_kill_switch(
            pause=False, expected_sequence=1,
            changed_at_ms=T + 2, acknowledge_resume=True,
        )
        self.assertEqual(restored.sequence, 2)
        self.assertFalse(restored.active)
        self.assertEqual(restored.last_action, "resume")
        blocked = self.journal.reserve_open_if_paper_risk(
            intent(), limits(), obs(kill_switch_active=True), decision_at_ms=T + 2,
        )
        self.assertEqual(blocked.decision.reason, PaperRiskReason.KILL_SWITCH)
        self.assertIsNone(blocked.entry)
        accepted = self.journal.reserve_open_if_paper_risk(
            intent(), limits(), obs(), decision_at_ms=T + 2,
        )
        self.assertIsNotNone(accepted.entry)
        self.assertEqual(accepted.entry.snapshot.status, PaperOrderStatus.PENDING)
        self.assertFalse(accepted.orders_sent)
        self.assertFalse(self.journal.read_local_kill_switch().active)

    def test_paper_reduce_only_is_not_blocked_by_local_pause(self):
        self.pause()
        reducer = replace(
            intent(), intent_id="fixture_reduce_only", fixture_signal_id="fixture_reduce_signal",
            effect=PaperOrderEffect.REDUCE_ONLY, side=PaperOrderSide.SELL,
            max_reducible_units=D(10),
        )
        item = self.journal.reserve(reducer)
        self.assertEqual(item.snapshot.status, PaperOrderStatus.PENDING)
        self.assertFalse(item.orders_sent)
        self.assertTrue(self.journal.read_local_kill_switch().active)

    def test_corruption_and_unknown_meta_key_fail_closed(self):
        self.pause()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE paper_order_meta SET value='forged_false' WHERE key=?", (KEY,))
        with self.assertRaises(DataValidationError):
            self.journal.read_local_kill_switch()
        with self.assertRaises(DataValidationError):
            SQLitePaperOrderJournal(self.db)
        with self.assertRaises(DataValidationError):
            self.journal.reserve_open_if_paper_risk(
                intent(), limits(), obs(), decision_at_ms=T + 2,
            )
        with self.assertRaises(DataValidationError):
            audit_paper_open_health(self.db, self.position_path)

    def test_unknown_metadata_fails_even_without_pause_key(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                "INSERT INTO paper_order_meta(key,value) VALUES('unrecognized_flag','false')"
            )
        with self.assertRaises(DataValidationError):
            self.journal.set_local_kill_switch(
                pause=True, expected_sequence=0, changed_at_ms=T + 1,
            )
        with self.assertRaises(DataValidationError):
            self.journal.reserve(intent())

    def test_two_concurrent_pauses_cannot_both_win(self):
        def update(_):
            return SQLitePaperOrderJournal(self.db).set_local_kill_switch(
                pause=True, expected_sequence=0, changed_at_ms=T + 1,
            )
        successes, failures = [], []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in (pool.submit(update, 1), pool.submit(update, 2)):
                try:
                    successes.append(future.result())
                except DataValidationError as exc:
                    failures.append(exc)
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(self.journal.read_local_kill_switch().sequence, 1)

    def test_durable_paper_cursor_uses_same_pause_without_skipping_checkpoint(self):
        rows = candles(n=10)
        def inputs(n):
            segment = rows[:n]
            now = segment[-1].close_time_ms + 1000
            return dict(
                strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
                requested_units=D(2), limits=causal_limits(),
                observation=causal_obs(now), journal=self.journal,
                position_journal_path=self.position_path,
                decision_at_ms=now, max_candles=20,
            )
        initial = step_durable_offline_paper(rows[:5], **inputs(5))
        self.assertEqual(initial.sequence_number, 1)
        self.assertFalse(initial.opening.paper_intent_reserved)
        self.pause()
        next_tick = step_durable_offline_paper(rows[:6], **inputs(6))
        self.assertEqual(next_tick.sequence_number, 2)
        self.assertFalse(next_tick.opening.paper_intent_reserved)
        self.assertFalse(next_tick.orders_sent)
        recovered = recover_durable_offline_paper(
            rows[:6], strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D(2), limits=causal_limits(), journal=self.journal,
            max_candles=20,
        )
        self.assertEqual(recovered, next_tick.seal)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM paper_order_intents").fetchone()[0], 0
            )

    def test_invalid_transition_fields_leave_state_unchanged(self):
        for bad in (
            dict(pause=1, expected_sequence=0, changed_at_ms=T),
            dict(pause=True, expected_sequence=True, changed_at_ms=T),
            dict(pause=True, expected_sequence=0, changed_at_ms=False),
            dict(pause=True, expected_sequence=0, changed_at_ms=T,
                 acknowledge_resume="yes"),
        ):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                self.journal.set_local_kill_switch(**bad)
        self.assertEqual(self.journal.read_local_kill_switch().sequence, 0)

    @unittest.skipUnless(os.name == "posix", "private local operator CLI is POSIX-only")
    def test_cli_pause_status_resume_requires_private_file_and_confirmation(self):
        self.root.chmod(0o700)
        self.db.chmod(0o600)
        args = ["--journal", str(self.db)]
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(run(args + ["--action", "status"]), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "open_reservations_not_paused")
        with patch("scripts.control_paper_kill_switch.time.time", return_value=(T + 1)/1000):
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(run(args + ["--action", "pause",
                                             "--expected-sequence", "0"]), 0)
        self.assertEqual(json.loads(out.getvalue())["sequence"], 1)
        with redirect_stdout(StringIO()) as out:
            self.assertEqual(run(args + ["--action", "resume",
                                         "--expected-sequence", "1"]), 1)
        self.assertEqual(json.loads(out.getvalue())["status"], "operator_switch_refused")
        self.assertTrue(self.journal.read_local_kill_switch().active)
        with patch("scripts.control_paper_kill_switch.time.time", return_value=(T + 2)/1000):
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(run(args + [
                    "--action", "resume", "--expected-sequence", "1",
                    "--confirm-paper-resume",
                ]), 0)
        self.assertEqual(json.loads(out.getvalue())["sequence"], 2)
        for sensitive in (str(self.root), "BTCUSDT", "api_key"):
            self.assertNotIn(sensitive, out.getvalue())


if __name__ == "__main__":
    unittest.main()
