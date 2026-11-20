"""D452: risk measured from replayed AUTO2/AUTO4, no invented PnL or market."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.j2_observed_paper_entry_d447 import reserve_observed_paper_entry
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import (
    arm_observed_paper_entry, materialize_observed_paper_entry,
)
from crypto_intelligence_agent.j4_durable_paper_risk_d452 import DurablePaperRiskSource
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from test_j2_observed_paper_entry_d447 import inputs
from test_j4_automatic_entry_materializer_d448 import POLICY


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "D452 owner-only POSIX PAPER store")
class DurablePaperRiskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cia-d452-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home.chmod(0o700)
        self.order_file = self.home / "paper-orders.sqlite"
        self.position_file = self.home / "paper-positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.order_file)
        self.positions = SQLitePaperPositionJournal(self.position_file)
        self.order_file.chmod(0o600)
        self.position_file.chmod(0o600)
        self.source = DurablePaperRiskSource(
            private_paper_directory=self.home,
        )
        self.args = inputs()
        self.q = self.args["quote"]

    def open_pending(self):
        report = reserve_observed_paper_entry(
            **self.args, journal=self.orders,
            position_journal_path=self.position_file,
        )
        self.assertEqual(report.status, "paper_open_intent_reserved_only")
        return report.intent_id

    def simulate_fill(self, intent_id):
        arm_observed_paper_entry(
            private_paper_directory=self.home,
            intent_id=intent_id, policy=POLICY,
            allow_paper_entry_strategy=True,
        )
        q = replace(self.q,
                    exchange_at_ms=self.q.exchange_at_ms + 500,
                    received_at_ms=self.q.received_at_ms + 500,
                    cross_sequence=self.q.cross_sequence + 1,
                    bid_size=Decimal(20), ask_size=Decimal(20))
        r = materialize_observed_paper_entry(
            private_paper_directory=self.home, intent_id=intent_id,
            quote=q, as_of_ms=q.received_at_ms,
            enable_hypothetical_open_fill=True,
        )
        self.assertEqual(r["status"],
                         "paper_position_routed_for_continuous_held_monitor")
        return q

    def test_virgin_durable_ledger_is_only_provable_zero_pnl_case(self):
        self.source.observe_public_quote(self.q)
        state = self.source.inspect(self.q)
        self.assertEqual(state.symbol_exposure_quote, 0)
        self.assertEqual(state.portfolio_exposure_quote, 0)
        self.assertEqual(state.pending_open_orders, 0)
        self.assertTrue(state.realized_loss_known_zero)
        self.assertTrue(state.mark_coverage_complete)
        risk = self.source(self.q)
        self.assertEqual(risk.realized_loss_today_quote, Decimal(0))
        self.assertEqual(risk.mark_price_quote, self.q.mark_price)
        self.assertFalse(risk.kill_switch_active)
        self.assertFalse(state.sanitized_report()["venue_account_authenticated"])
        self.assertFalse(state.sanitized_report()["orders_sent"])

    def test_one_open_pending_is_read_from_auto2_not_fake_default(self):
        self.open_pending()
        self.source.observe_public_quote(self.q)
        state = self.source.inspect(self.q)
        self.assertEqual(state.pending_open_orders, 1)
        self.assertTrue(state.realized_loss_known_zero)
        self.assertEqual(self.source(self.q).pending_open_orders, 1)

    def test_filled_open_replays_actual_exposure_and_blocks_unavailable_loss(self):
        intent_id = self.open_pending()
        q = self.simulate_fill(intent_id)
        self.source.observe_public_quote(q)
        state = self.source.inspect(q)
        self.assertEqual(state.symbol_exposure_quote, Decimal("250.0"))
        self.assertEqual(state.portfolio_exposure_quote, Decimal("250.0"))
        self.assertEqual(state.filled_open_count, 1)
        self.assertEqual(state.filled_exit_count, 0)
        self.assertFalse(state.realized_loss_known_zero)
        with self.assertRaises(DataGapError):
            self.source(q)
        # No prices are restored magically from SQLite after restart.
        restarted = DurablePaperRiskSource(
            private_paper_directory=self.home,
        )
        with self.assertRaises(DataGapError):
            restarted.inspect(q)
        restarted.observe_public_quote(q)
        self.assertEqual(
            restarted.inspect(q).portfolio_exposure_quote, Decimal("250.0"),
        )

    def test_kill_switch_is_existing_journal_state_not_input_zero(self):
        self.source.observe_public_quote(self.q)
        self.orders.set_local_kill_switch(
            pause=True, expected_sequence=0,
            changed_at_ms=self.q.received_at_ms - 10,
        )
        actual = self.source(self.q)
        self.assertTrue(actual.kill_switch_active)
        self.assertTrue(self.source.inspect(self.q).kill_switch_active)

    def test_without_ticker_or_after_session_reset_risk_fails_closed(self):
        with self.assertRaises(DataGapError):
            self.source(self.q)
        self.source.observe_public_quote(self.q)
        self.source.reset_market_session()
        with self.assertRaises(DataGapError):
            self.source(self.q)


if __name__ == "__main__":
    unittest.main()
