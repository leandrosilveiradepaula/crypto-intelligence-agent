"""J6/PRE3 #234: end-to-end bounded PAPER batch, recovery and safety."""
from __future__ import annotations

from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.offline_paper_batch import (
    MAX_NEW_STEPS, OfflinePaperBatchReport, run_durable_offline_paper_batch,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import candles, config

D = Decimal


class OfflinePaperBatchTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "orders.sqlite"
        self.positions = self.root / "positions.sqlite"
        self.journal = SQLitePaperOrderJournal(self.db)
        SQLitePaperPositionJournal(self.positions)
        self.cs = candles(n=10)
        self.obs = tuple(observation(c.close_time_ms + 1_000) for c in self.cs)

    def run_batch(self, **changes):
        args = dict(
            candles=self.cs, observations=self.obs,
            strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D(2), limits=limits(),
            journal=self.journal, position_journal_path=self.positions,
            bootstrap_candles=5, max_new_steps=MAX_NEW_STEPS,
            max_candles=20,
        )
        args.update(changes)
        candle_input = args.pop("candles")
        return run_durable_offline_paper_batch(candle_input, **args)

    def inventory(self):
        with closing(sqlite3.connect(self.db)) as c:
            count = c.execute("SELECT COUNT(*) FROM paper_order_intents").fetchone()[0]
            keys = dict(c.execute("SELECT key,value FROM paper_order_meta").fetchall())
        return count, keys

    def test_multi_call_auto_progress_restart_and_complete_noop(self):
        initial = self.run_batch(max_new_steps=1)
        self.assertIsInstance(initial, OfflinePaperBatchReport)
        self.assertFalse(initial.recovered_prior_checkpoint)
        self.assertEqual((initial.processed_steps, initial.final_checkpoint_count), (1, 5))
        self.assertEqual(initial.reserved_open_intents, 0)
        self.assertEqual(initial.no_fresh_hypothesis_steps, 1)
        self.assertFalse(initial.all_supplied_candles_processed)
        self.assertEqual(self.inventory()[0], 0)

        self.journal = SQLitePaperOrderJournal(self.db)
        middle = self.run_batch(max_new_steps=1)
        self.assertTrue(middle.recovered_prior_checkpoint)
        self.assertEqual((middle.starting_checkpoint_count, middle.final_checkpoint_count), (5, 6))
        self.assertEqual(middle.candidate_steps, 1)
        self.assertEqual(middle.reserved_open_intents, 1)
        self.assertEqual(self.inventory()[0], 1)
        self.assertFalse(middle.orders_sent)
        self.assertFalse(middle.live_trading_authorized)
        self.assertFalse(middle.exchange_feed_connected)
        self.assertFalse(middle.financial_backtest_approved)

        completion = self.run_batch()
        self.assertTrue(completion.recovered_prior_checkpoint)
        self.assertEqual((completion.starting_checkpoint_count,
                          completion.final_checkpoint_count), (6, 10))
        self.assertTrue(completion.all_supplied_candles_processed)
        before = self.inventory()
        duplicate = self.run_batch()
        self.assertEqual((duplicate.processed_steps, duplicate.reserved_open_intents), (0, 0))
        self.assertEqual(duplicate.final_checkpoint_count, 10)
        self.assertTrue(duplicate.all_supplied_candles_processed)
        self.assertEqual(self.inventory(), before)
        with self.assertRaises(FrozenInstanceError):
            duplicate.orders_sent = True

    def test_initial_one_call_runs_all_remaining_steps(self):
        result = self.run_batch()
        self.assertEqual(result.input_candle_count, 10)
        self.assertEqual(result.processed_steps, 6)
        self.assertEqual(result.reserved_open_intents, 1)
        self.assertTrue(result.all_supplied_candles_processed)
        self.assertEqual(self.inventory()[0], 1)

    def test_pause_between_steps_blocks_fresh_entry_without_replay(self):
        self.run_batch(max_new_steps=1)
        paused = self.journal.set_local_kill_switch(
            pause=True, expected_sequence=0,
            changed_at_ms=self.cs[4].close_time_ms + 1_001,
        )
        self.assertTrue(paused.active)
        step6 = self.run_batch(max_new_steps=1)
        self.assertEqual(step6.candidate_steps, 1)
        self.assertEqual(step6.reserved_open_intents, 0)
        self.assertEqual(step6.risk_or_health_denials, 1)
        self.assertIn(("paper_risk_denied_kill_switch_active", 1), step6.reasons)
        self.assertEqual(self.inventory()[0], 0)
        self.journal.set_local_kill_switch(
            pause=False, expected_sequence=1,
            changed_at_ms=self.cs[5].close_time_ms + 1_001,
            acknowledge_resume=True,
        )
        last = self.run_batch()
        self.assertTrue(last.all_supplied_candles_processed)
        self.assertEqual(last.reserved_open_intents, 0)
        self.assertEqual(self.inventory()[0], 0)

    def test_preflight_rejects_all_bad_inputs_without_writing_cursor(self):
        cases = (
            dict(observations=self.obs[:-1]),
            dict(observations=list(self.obs) + [self.obs[0]]),
            dict(observations=tuple(replace(x, venue=PaperVenue.BYBIT_V5)
                                    if i == 6 else x
                                    for i, x in enumerate(self.obs))),
            dict(observations=tuple(replace(x, observed_at_ms=x.observed_at_ms + 1)
                                    if i == 7 else x
                                    for i, x in enumerate(self.obs))),
            dict(observations=tuple(replace(x, observed_at_ms=1)
                                    if i == 6 else x
                                    for i, x in enumerate(self.obs))),
            dict(candles=self.cs[:5] + (self.cs[4],) + self.cs[6:]),
            dict(candles=self.cs[:-1] + (replace(self.cs[-1], quality="real"),)),
            dict(max_new_steps=0),
            dict(max_new_steps=65),
            dict(max_new_steps=True),
            dict(bootstrap_candles=11),
            dict(bootstrap_candles=0),
            dict(requested_units=D("NaN")),
        )
        for changes in cases:
            with self.subTest(changes=str(changes)[:65]), self.assertRaises(
                (DataValidationError, ValueError)
            ):
                self.run_batch(**changes)
            self.assertEqual(self.inventory()[0], 0)
            self.assertNotIn("offline_paper_forward_cursor_v1", self.inventory()[1])

    def test_changed_historical_precision_or_context_cannot_resume(self):
        self.run_batch(max_new_steps=1)
        before = self.inventory()
        altered = self.cs[:1] + (replace(self.cs[1], close=D("101.00")),) + self.cs[2:]
        for kw in (
            dict(candles=altered),
            dict(venue=PaperVenue.BYBIT_V5),
            dict(limits=limits(max_market_age_ms=1001)),
            dict(requested_units=D("2.0")),
            dict(candles=self.cs[:4]),
            dict(bootstrap_candles=6),
        ):
            with self.subTest(kw=str(kw)[:80]), self.assertRaises(DataValidationError):
                self.run_batch(**kw)
            self.assertEqual(self.inventory(), before)
        next_tick = self.run_batch(max_new_steps=1)
        self.assertEqual(next_tick.final_checkpoint_count, 6)

    def test_second_tick_crash_keeps_first_commit_and_resume_without_duplicate(self):
        import crypto_intelligence_agent.offline_paper_batch as source
        original = source.step_durable_offline_paper
        count = 0

        def interrupted(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("synthetic fault between independent steps")
            return original(*args, **kwargs)

        with patch.object(source, "step_durable_offline_paper", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                self.run_batch(max_new_steps=3)
        self.assertEqual(self.inventory()[0], 0)
        resumed = self.run_batch()
        self.assertEqual(resumed.starting_checkpoint_count, 5)
        self.assertEqual(resumed.reserved_open_intents, 1)
        self.assertEqual(self.inventory()[0], 1)
        self.assertTrue(resumed.all_supplied_candles_processed)

    def test_no_http_or_provider_calls_even_during_signal_and_recovery(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("internet")):
            with patch("socket.create_connection", side_effect=AssertionError("internet")):
                a = self.run_batch(max_new_steps=2)
                b = self.run_batch()
                c = self.run_batch()
        self.assertEqual(a.reserved_open_intents, 1)
        self.assertEqual(b.reserved_open_intents, 0)
        self.assertEqual(c.processed_steps, 0)
        self.assertFalse(c.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
