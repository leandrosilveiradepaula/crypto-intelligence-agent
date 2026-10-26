"""J6/PRE1: incremental synthetic paper decisions, NEVER market/real orders."""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError,
)
from crypto_intelligence_agent.offline_paper_forward_session import (
    OfflinePaperForwardSession, OfflineForwardPaperTick,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import PaperRiskReason
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import (
    H, SHORT_ROWS, candles, config,
)

D = Decimal


class OfflineForwardSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "order.sqlite"
        self.positions_path = Path(tmp.name) / "positions.sqlite"
        self.journal = SQLitePaperOrderJournal(self.db)
        self.positions = SQLitePaperPositionJournal(self.positions_path)
        self.rows = candles(n=10)
        self.session = self.make_session()

    def make_session(self, **changes):
        args = dict(
            strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D(2), limits=limits(),
            journal=self.journal, position_journal_path=self.positions_path,
            close_safety_ms=1_000,
        )
        args.update(changes)
        return OfflinePaperForwardSession(**args)

    def count_intents(self):
        with closing(sqlite3.connect(self.db)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM paper_order_intents",
            ).fetchone()[0]

    def send(self, upto, *, session=None, rows=None, snap=None,
             now=None, safety=1_000):
        cs = (self.rows if rows is None else rows)[:upto]
        instant = cs[-1].close_time_ms + safety if now is None else now
        return (self.session if session is None else session).step(
            cs, observation=(observation(instant) if snap is None else snap),
            decision_at_ms=instant,
        )

    def test_neutral_to_long_fresh_signal_only_reserves_one_pending(self):
        neutral = self.send(5)
        self.assertIsInstance(neutral, OfflineForwardPaperTick)
        self.assertEqual(neutral.opening.reason, "no_fresh_synthetic_hypothesis")
        self.assertFalse(neutral.paper_intent_reserved)
        self.assertEqual(self.count_intents(), 0)
        entry = self.send(6)
        self.assertEqual(entry.sequence_number, 2)
        self.assertEqual(entry.accepted_candle_count, 6)
        self.assertTrue(entry.paper_intent_reserved)
        self.assertEqual(entry.opening.candidate.side, SyntheticSide.LONG)
        self.assertEqual(entry.opening.reservation.entry.snapshot.status,
                         PaperOrderStatus.PENDING)
        self.assertEqual(entry.opening.reservation.entry.events, ())
        self.assertEqual(self.count_intents(), 1)
        self.assertEqual(self.session.accepted_ticks, 2)
        self.assertEqual(self.session.reserved_paper_intents, 1)
        self.assertEqual(self.session.last_accepted_candle_open_ms,
                         self.rows[5].open_time_ms)
        self.assertEqual(entry.source_quality, "offline_fixture_forward_replay_only")
        for flag in (
            "orders_sent", "live_feed_connected", "market_data_verified",
            "stop_native_verified", "real_pnl_available", "approved_for_live_use",
            "durable_session_checkpoint_available", "prospectively_homologated",
            "cross_database_atomic_snapshot_available",
        ):
            self.assertFalse(getattr(entry, flag), flag)
        self.assertFalse(self.session.order_submission_enabled)

    def test_short_fresh_breakout_only_sell_paper(self):
        short = candles(n=6, source=SHORT_ROWS)
        a = self.send(5, rows=short)
        b = self.send(6, rows=short)
        self.assertEqual(a.opening.reason, "no_fresh_synthetic_hypothesis")
        self.assertTrue(b.paper_intent_reserved)
        self.assertEqual(b.opening.candidate.side, SyntheticSide.SHORT)
        self.assertIs(b.opening.intent.side, PaperOrderSide.SELL)
        self.assertEqual(b.opening.reservation.entry.events, ())

    def test_latest_bar_only_then_new_neutral_bar_does_not_double_open(self):
        self.send(6)
        later = self.send(7)
        self.assertEqual(later.sequence_number, 2)
        self.assertFalse(later.paper_intent_reserved)
        self.assertEqual(self.count_intents(), 1)
        self.assertEqual(self.session.reserved_paper_intents, 1)

    def test_same_candle_and_skipped_prefix_refused_without_state_mutation(self):
        self.send(5)
        before = self.session.last_accepted_candle_open_ms
        with self.assertRaisesRegex(DataValidationError, "one and only one"):
            self.send(5)
        with self.assertRaisesRegex(DataValidationError, "one and only one"):
            self.send(7)
        self.assertEqual(self.session.last_accepted_candle_open_ms, before)
        self.assertEqual(self.session.accepted_ticks, 1)
        self.assertEqual(self.count_intents(), 0)
        self.assertTrue(self.send(6).paper_intent_reserved)

    def test_rewritten_historical_close_even_if_number_valid_refused(self):
        self.send(5)
        edited = list(self.rows[:6])
        edited[2] = replace(edited[2], close=D(100), open=D(100))
        # This row remains a structurally valid OHLC, but the prior prefix
        # may not be re-written after a checkpoint.
        with self.assertRaisesRegex(DataValidationError, "modified or reordered"):
            self.send(6, rows=edited)
        self.assertEqual(self.session.accepted_ticks, 1)
        self.assertEqual(self.count_intents(), 0)
        self.assertTrue(self.send(6).paper_intent_reserved)

    def test_decimal_precision_rewrite_refused_even_when_numerically_equal(self):
        self.send(5)
        edited = list(self.rows[:6])
        edited[0] = replace(edited[0], open=D("100.0"))
        with self.assertRaisesRegex(DataValidationError, "modified or reordered"):
            self.send(6, rows=edited)
        self.assertEqual(self.session.accepted_ticks, 1)

    def test_future_or_late_clock_refused_no_checkpoint_mutation(self):
        self.send(5)
        last = self.rows[5]
        correct = last.close_time_ms + 1_000
        for time in (correct-1, correct+1):
            with self.subTest(time=time), self.assertRaises(DataValidationError):
                self.send(6, now=time, snap=observation(correct))
        with self.assertRaises(DataValidationError):
            self.send(6, now=True)
        self.assertEqual(self.session.accepted_ticks, 1)
        self.assertEqual(self.count_intents(), 0)

    def test_discontinuity_and_market_quality_refused(self):
        self.send(5)
        discontinuous = list(self.rows[:6])
        discontinuous[-1] = replace(
            discontinuous[-1],
            open_time_ms=discontinuous[-1].open_time_ms + H,
            close_time_ms=discontinuous[-1].close_time_ms + H,
        )
        with self.assertRaises(DataGapError):
            self.send(6, rows=discontinuous)
        corrupt = list(self.rows[:6])
        corrupt[1] = replace(corrupt[1], quality="live_provider")
        with self.assertRaises(DataValidationError):
            self.send(6, rows=corrupt)
        corrupt = list(self.rows[:6])
        corrupt[5] = replace(corrupt[5], quote_volume=D("NaN"))
        with self.assertRaises(DataValidationError):
            self.send(6, rows=corrupt)
        self.assertEqual(self.session.accepted_ticks, 1)
        self.assertEqual(self.count_intents(), 0)

    def test_no_historical_signal_retroactive_on_late_bootstrap(self):
        out = self.send(8)
        self.assertFalse(out.paper_intent_reserved)
        self.assertEqual(out.opening.reason, "no_fresh_synthetic_hypothesis")
        self.assertFalse(out.prospectively_homologated)
        self.assertEqual(self.count_intents(), 0)

    def test_kill_switch_denies_but_valid_tick_advances_without_reserve(self):
        self.send(5)
        now = self.rows[5].close_time_ms + 1_000
        denied = self.send(6, snap=observation(now, kill_switch_active=True))
        self.assertFalse(denied.paper_intent_reserved)
        self.assertEqual(denied.opening.reservation.decision.reason,
                         PaperRiskReason.KILL_SWITCH)
        self.assertEqual(self.count_intents(), 0)
        self.assertEqual(self.session.accepted_ticks, 2)
        later = self.send(7)
        self.assertEqual(later.sequence_number, 3)
        self.assertEqual(self.count_intents(), 0)

    def test_mismatched_risk_venue_fails_without_checkpoint(self):
        self.send(5)
        now = self.rows[5].close_time_ms + 1_000
        with self.assertRaises(DataValidationError):
            self.send(6, snap=observation(now, venue=PaperVenue.BYBIT_V5))
        self.assertEqual(self.session.accepted_ticks, 1)
        self.assertEqual(self.count_intents(), 0)
        self.assertTrue(self.send(6).paper_intent_reserved)

    def test_restarted_session_same_signal_is_refused_by_sqlite_dedup(self):
        first = self.send(6)
        self.assertTrue(first.paper_intent_reserved)
        restarted = self.make_session(journal=SQLitePaperOrderJournal(self.db))
        with self.assertRaises(DataValidationError):
            self.send(6, session=restarted)
        self.assertEqual(restarted.accepted_ticks, 0)
        self.assertEqual(self.count_intents(), 1)
        self.assertFalse(restarted.durable_session_checkpoint_available)

    def test_resource_limit_prevents_unbounded_in_memory_history(self):
        small = self.make_session(max_candles=6)
        self.send(5, session=small)
        self.send(6, session=small)
        with self.assertRaisesRegex(DataValidationError, "bounded"):
            self.send(7, session=small)
        self.assertEqual(small.accepted_ticks, 2)
        self.assertEqual(self.count_intents(), 1)

    def test_invalid_constructor_and_concurrent_steps_fail_closed(self):
        bad = (
            {"venue": "Binance"}, {"requested_units": 1},
            {"requested_units": D("NaN")}, {"requested_units": D(-1)},
            {"max_candles": True}, {"max_candles": 10001},
            {"close_safety_ms": -1}, {"position_journal_path": None},
            {"journal": {}},
        )
        for option in bad:
            with self.subTest(option=option), self.assertRaises(DataValidationError):
                self.make_session(**option)
        self.session._step_lock.acquire()
        try:
            with self.assertRaisesRegex(DataValidationError, "concurrent"):
                self.send(6)
        finally:
            self.session._step_lock.release()
        self.assertEqual(self.session.accepted_ticks, 0)
        self.assertEqual(self.count_intents(), 0)

    def test_zero_safety_and_no_network(self):
        session = self.make_session(close_safety_ms=0)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                output = self.send(
                    6, session=session,
                    now=self.rows[5].close_time_ms,
                    snap=observation(self.rows[5].close_time_ms),
                )
        self.assertTrue(output.paper_intent_reserved)
        self.assertFalse(output.orders_sent)
        self.assertEqual(self.count_intents(), 1)


if __name__ == "__main__":
    unittest.main()
