"""J4/AUTO7: only the latest causal J2 fixture can reserve an OPEN PAPER."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.causal_paper_open import reserve_causal_paper_open
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import (
    PaperRiskLimits, PaperRiskObservation, PaperRiskReason,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (ExitBasis, SyntheticExitPlan, SyntheticExitTranche)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_synthetic_research_cycle import (
    SHORT_ROWS, candles, config,
)

D = Decimal


def limits(**changes):
    payload = dict(
        max_order_notional_quote=D(400),
        max_symbol_exposure_quote=D(1_000),
        max_portfolio_exposure_quote=D(2_000),
        max_realized_loss_today_quote=D(50),
        max_pending_open_orders=1,
        max_market_age_ms=1_000,
    )
    payload.update(changes)
    return PaperRiskLimits(**payload)


def observation(ts, *, venue=PaperVenue.BINANCE_USDM, **changes):
    payload = dict(
        venue=venue, symbol="BTCUSDT", quote_currency="USDT",
        observed_at_ms=ts, mark_price_quote=D(100),
        symbol_exposure_quote=D(0), portfolio_exposure_quote=D(0),
        realized_loss_today_quote=D(0), pending_open_orders=0,
        unresolved_open_exists=False, kill_switch_active=False,
    )
    payload.update(changes)
    return PaperRiskObservation(**payload)


class CausalPaperOpenTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "paper-open.sqlite"
        self.position_db = Path(temp.name) / "paper-positions.sqlite"
        self.journal = SQLitePaperOrderJournal(self.db)
        self.positions = SQLitePaperPositionJournal(self.position_db)
        self.rows = candles()[:6]
        self.now = self.rows[-1].close_time_ms + 1_000
        self.strategy = config().strategy

    def count_intents(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            return conn.execute("SELECT COUNT(*) FROM paper_order_intents").fetchone()[0]

    def admit(self, *, rows=None, venue=PaperVenue.BINANCE_USDM,
            qty=D(2), safety=1_000, now=None, rules=None,
            snapshot=None, strategy=None, journal=None):
        source = self.rows if rows is None else rows
        at = source[-1].close_time_ms + safety if now is None else now
        return reserve_causal_paper_open(
            source, strategy=self.strategy if strategy is None else strategy,
            venue=venue, requested_units=qty,
            limits=limits() if rules is None else rules,
            observation=observation(at, venue=venue) if snapshot is None else snapshot,
            journal=self.journal if journal is None else journal,
            position_journal_path=self.position_db,
            decision_at_ms=at, close_safety_ms=safety,
        )

    def test_long_latest_signal_reserves_pending_without_fills(self):
        result = self.admit()
        self.assertEqual(result.reason, "paper_open_intent_reserved_only")
        self.assertTrue(result.paper_intent_reserved)
        self.assertEqual(result.paper_intent_count, 1)
        self.assertEqual(result.candidate.close, D(105))
        self.assertEqual(result.candidate.earliest_research_at_ms, self.now)
        self.assertEqual(result.intent.created_at_ms, self.now)
        self.assertEqual(result.intent.effect, PaperOrderEffect.OPEN)
        self.assertEqual(result.intent.side, PaperOrderSide.BUY)
        self.assertEqual(result.reservation.decision.hypothetical_notional_quote, D(200))
        self.assertEqual(result.reservation.entry.snapshot.status, PaperOrderStatus.PENDING)
        self.assertEqual(result.reservation.entry.snapshot.filled_total_units, D(0))
        self.assertEqual(result.reservation.entry.events, ())
        self.assertEqual(self.count_intents(), 1)
        self.assertEqual(self.journal.load(result.intent.intent_id), result.reservation.entry)
        self.assertEqual(result.mode, "offline_paper")
        for key in ("orders_sent", "order_submission_enabled", "approved_for_live_use",
                    "market_data_verified", "real_pnl_available",
                    "financial_backtest_approved"):
            self.assertFalse(getattr(result, key), key)

    def test_short_latest_creates_sell_not_reduce_only(self):
        result = self.admit(rows=candles(source=SHORT_ROWS)[:6])
        self.assertEqual(result.candidate.close, D(95))
        self.assertEqual(result.candidate.side, SyntheticSide.SHORT)
        self.assertEqual(result.intent.position_side, SyntheticSide.SHORT)
        self.assertEqual(result.intent.side, PaperOrderSide.SELL)
        self.assertIsNone(result.intent.max_reducible_units)
        self.assertEqual(result.reservation.entry.snapshot.filled_total_units, D(0))

    def test_only_latest_bar_can_trigger_a_paper_intent(self):
        result = self.admit(rows=candles()[:8])
        self.assertEqual(result.reason, "no_fresh_synthetic_hypothesis")
        self.assertIsNone(result.intent)
        self.assertIsNone(result.candidate)
        self.assertIsNone(result.reservation)
        self.assertEqual(self.count_intents(), 0)
        self.assertEqual(result.paper_intent_count, 0)

    def test_future_candle_must_not_be_included_as_of_old_signal(self):
        with self.assertRaisesRegex(DataValidationError, "exact availability"):
            self.admit(rows=candles()[:8], now=self.now)
        self.assertEqual(self.count_intents(), 0)
        self.assertTrue(self.admit().paper_intent_reserved)

    def test_safety_zero_and_millisecond_boundary(self):
        early = self.rows[-1].close_time_ms
        good = self.admit(safety=0, now=early)
        self.assertEqual(good.intent.created_at_ms, early)
        self.assertEqual(good.candidate.earliest_research_at_ms, early)
        with self.assertRaisesRegex(DataValidationError, "exact availability"):
            self.admit(now=self.now - 1)
        with self.assertRaisesRegex(DataValidationError, "exact availability"):
            self.admit(now=self.now + 1)
        with self.assertRaises(DataValidationError):
            self.admit(safety=True)
        with self.assertRaises(DataValidationError):
            self.admit(safety=86_400_001)

    def test_repeated_signal_and_threshold_change_cannot_double_open(self):
        first = self.admit()
        with self.assertRaisesRegex(DataValidationError, "already reserved"):
            self.admit()
        alt = replace(self.strategy, max_atr_ratio=D("0.7"))
        with self.assertRaises(DataValidationError):
            self.admit(strategy=alt)
        self.assertEqual(self.count_intents(), 1)
        self.assertEqual(self.journal.load(first.intent.intent_id),
                         first.reservation.entry)

    def test_cross_venue_same_causal_signal_cannot_open_twice(self):
        first = self.admit()
        denied = self.admit(venue=PaperVenue.BYBIT_V5)
        self.assertIsNone(denied.reservation.entry)
        self.assertEqual(denied.reservation.decision.reason, PaperRiskReason.PENDING_LIMIT)
        # Even when the pending limit would allow another opening, the
        # journal's unique index forbids a second venue on the SAME signal.
        with self.assertRaisesRegex(DataValidationError, "already has an OPEN"):
            self.admit(venue=PaperVenue.BYBIT_V5,
                       rules=limits(max_pending_open_orders=2))
        self.assertEqual(self.count_intents(), 1)
        self.assertEqual(first.intent.venue, PaperVenue.BINANCE_USDM)

    def test_kill_switch_stale_loss_and_limits_reject_without_reserve(self):
        cases = (
            (observation(self.now, kill_switch_active=True), limits(), PaperRiskReason.KILL_SWITCH),
            (observation(self.now, realized_loss_today_quote=D(50)),
             limits(), PaperRiskReason.LOSS_LIMIT),
            (observation(self.now - 1_001), limits(), PaperRiskReason.STALE_FEED),
            (observation(self.now, mark_price_quote=D(250)),
             limits(), PaperRiskReason.ORDER_NOTIONAL),
            (observation(self.now, symbol_exposure_quote=D(900),
                         portfolio_exposure_quote=D(900)),
             limits(), PaperRiskReason.SYMBOL_EXPOSURE),
        )
        for snap, rule, reason in cases:
            with self.subTest(reason=reason):
                result = self.admit(snapshot=snap, rules=rule)
                self.assertEqual(result.reservation.decision.reason, reason)
                self.assertFalse(result.paper_intent_reserved)
                self.assertIsNone(result.reservation.entry)
                self.assertEqual(self.count_intents(), 0)

    def test_mark_is_explicit_not_copied_from_candidate_close(self):
        result = self.admit(snapshot=observation(self.now, mark_price_quote=D(120)))
        self.assertEqual(result.candidate.close, D(105))
        self.assertEqual(result.reservation.decision.hypothetical_notional_quote, D(240))
        self.assertEqual(result.reservation.entry.intent.requested_units, D(2))

    def test_pending_and_unknown_in_existing_journal_fail_closed(self):
        other = PaperOrderIntent(
            "fixture_unrelated_existing_open", "fixture_unrelated_signal",
            PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.BUY, PaperOrderEffect.OPEN, D(1), self.now - 2,
        )
        old = self.journal.reserve_open_if_paper_risk(
            other, limits(), observation(self.now), decision_at_ms=self.now,
        )
        self.assertIsNotNone(old.entry)
        denied = self.admit()
        self.assertEqual(denied.reservation.decision.reason, PaperRiskReason.PENDING_LIMIT)
        self.assertIsNone(denied.reservation.entry)
        self.journal.append_events(
            other.intent_id,
            (PaperOrderEvent("fixture_existing_timeout", PaperOrderEventKind.UNKNOWN,
                             self.now - 1),),
            as_of_ms=self.now - 1,
        )
        restarted = SQLitePaperOrderJournal(self.db)
        blocked = self.admit(journal=restarted)
        self.assertEqual(blocked.reservation.decision.reason, PaperRiskReason.UNRESOLVED_OPEN)
        self.assertFalse(blocked.paper_intent_reserved)
        self.assertEqual(self.count_intents(), 1)

    def test_filled_open_without_position_health_blocks_even_when_not_pending(self):
        old = PaperOrderIntent(
            "fixture_health_prior_open", "fixture_health_prior_signal",
            PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.BUY, PaperOrderEffect.OPEN, D(1), self.now - 2,
        )
        self.journal.reserve(old)
        self.journal.append_events(
            old.intent_id,
            (PaperOrderEvent("fixture_health_prior_fill", PaperOrderEventKind.FILL,
                             self.now - 1, D(1)),),
            as_of_ms=self.now - 1,
        )
        result = self.admit()
        self.assertEqual(result.reason,
                         "paper_open_health_denied_paper_open_unprotected")
        self.assertIsNone(result.intent)
        self.assertIsNone(result.reservation)
        self.assertFalse(result.health.new_open_allowed)
        self.assertEqual(self.count_intents(), 1)

    def test_concurrent_fill_before_reservation_transaction_cannot_pass_health(self):
        """Regression: detached RO audit followed by a separate TX was unsafe."""
        old = PaperOrderIntent(
            "fixture_race_open", "fixture_race_signal",
            PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.BUY, PaperOrderEffect.OPEN, D(1), self.now - 2,
        )
        other_writer = SQLitePaperOrderJournal(self.db)
        other_writer.reserve(old)
        original_transaction = self.journal._transaction
        injected = [False]

        @contextmanager
        def fill_before_lock():
            if not injected[0]:
                injected[0] = True
                other_writer.append_events(
                    old.intent_id,
                    (PaperOrderEvent(
                        "fixture_race_fill", PaperOrderEventKind.FILL,
                        self.now - 1, D(1),
                    ),),
                    as_of_ms=self.now - 1,
                )
            with original_transaction() as conn:
                yield conn

        # The former path audited BEFORE this injected FILL; its subsequent
        # risk-only transaction could then accept the new OPEN. AUTO8 now
        # checks health after acquiring that exact write lock.
        with patch.object(self.journal, "_transaction", fill_before_lock):
            result = self.admit()
        self.assertTrue(injected[0])
        self.assertEqual(result.reason, "paper_open_health_denied_paper_open_unprotected")
        self.assertIsNone(result.reservation)
        self.assertEqual(self.count_intents(), 1)
        self.assertFalse(result.orders_sent)

    def _previous_flat_position(self, *, exit_at=None):
        """Separate PAPER opening finished via explicit REDUCE_ONLY events."""
        when = self.now - 6 if exit_at is None else exit_at
        old = PaperOrderIntent(
            "fixture_prior_flat_open", "fixture_prior_flat_signal",
            PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.BUY, PaperOrderEffect.OPEN, D(1), self.now - 9,
        )
        entry_fill = PaperOrderEvent(
            "fixture_prior_flat_fill", PaperOrderEventKind.FILL,
            self.now - 8, D(1),
        )
        self.journal.reserve(old)
        self.journal.append_events(old.intent_id, (entry_fill,), as_of_ms=self.now - 8)
        exit_plan = SyntheticExitPlan(
            D(1), (SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(100)),), D(0),
        )
        self.positions.create_position(
            position_id="fixture_prior_flat_position", opening_intent=old,
            opening_events=(entry_fill,), exit_plan=exit_plan,
            plan_version="fixture-flat-v1", synthetic_lot_step_units=D(1),
            as_of_ms=self.now - 8,
        )
        close = PaperOrderIntent(
            "fixture_prior_flat_reduce", "fixture_prior_flat_reduce_signal",
            PaperVenue.BINANCE_USDM, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.SELL, PaperOrderEffect.REDUCE_ONLY, D(1),
            self.now - 7, D(1),
        )
        self.positions.reserve_exit(
            "fixture_prior_flat_position", 1, close, as_of_ms=self.now - 7,
        )
        self.positions.append_exit_events(
            "fixture_prior_flat_position", close.intent_id,
            (PaperOrderEvent(
                "fixture_prior_flat_reduce_fill", PaperOrderEventKind.FILL,
                when, D(1),
            ),),
            as_of_ms=when,
        )

    def test_new_causal_open_after_explicit_flat_and_restart(self):
        self._previous_flat_position()
        result = self.admit()
        self.assertTrue(result.paper_intent_reserved)
        self.assertTrue(result.health.closed_flat_paper_only)
        self.assertFalse(result.health.native_stop_verified)
        self.assertEqual(self.count_intents(), 2)
        with self.assertRaisesRegex(DataValidationError, "already reserved"):
            self.admit(journal=SQLitePaperOrderJournal(self.db))

    def test_new_open_still_respects_kill_switch_after_flat(self):
        self._previous_flat_position()
        result = self.admit(
            snapshot=observation(self.now, kill_switch_active=True),
        )
        self.assertEqual(result.reservation.decision.reason, PaperRiskReason.KILL_SWITCH)
        self.assertFalse(result.paper_intent_reserved)
        self.assertEqual(self.count_intents(), 1)

    def test_future_exit_event_cannot_unlock_new_signal(self):
        self._previous_flat_position(exit_at=self.now + 1)
        with self.assertRaisesRegex(DataValidationError, "future PAPER position checkpoint"):
            self.admit()
        self.assertEqual(self.count_intents(), 1)

    def test_invalid_types_identity_future_snapshot_and_quantity_refuse(self):
        for bad in (None, "2", 2, D("NaN"), D(-1), D("1e99"), D(0)):
            with self.subTest(qty=repr(bad)), self.assertRaises(DataValidationError):
                self.admit(qty=bad)
        for invalid in ("live", "testnet", None, 5, True):
            with self.subTest(venue=invalid), self.assertRaises(DataValidationError):
                self.admit(venue=invalid)
        with self.assertRaises(DataValidationError):
            self.admit(snapshot=observation(self.now + 1))
        with self.assertRaises(DataValidationError):
            self.admit(snapshot=observation(self.now, symbol="ETHUSDT"))
        with self.assertRaises(DataValidationError):
            self.admit(snapshot=observation(self.now, venue=PaperVenue.BYBIT_V5))
        with self.assertRaises(DataValidationError):
            self.admit(journal={})
        self.assertEqual(self.count_intents(), 0)

    def test_no_network_or_broker_and_stable_fixture_source(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                result = self.admit()
        self.assertEqual(result.quality, "synthetic_fixture_only")
        self.assertFalse(result.orders_sent)
        self.assertFalse(hasattr(result, "api_key"))
        self.assertFalse(hasattr(result, "profit_percent"))
        self.assertEqual(self.count_intents(), 1)


if __name__ == "__main__":
    unittest.main()
