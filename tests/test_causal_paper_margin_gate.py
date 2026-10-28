"""J4/PRE12 #280: opt-in margin gate before a durable PAPER OPEN reservation.

Uses real local synthetic journals and causal J2 fixture candles only.
This suite never uses market APIs, credentials, trading or real collateral.
"""
from contextlib import closing
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.causal_paper_open import (
    prepare_causal_paper_open, reserve_causal_paper_open,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_margin_preflight import (
    PaperLinearContractFixture, PaperMarginPreflightRequest, PaperMarginReason,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import (
    PaperRiskLimits, PaperRiskObservation, PaperRiskReason,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticLeverageSettings
from test_synthetic_research_cycle import candles, config

D = Decimal


class CausalMarginPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.order_path = root / "orders.sqlite"
        self.position_path = root / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.order_path)
        SQLitePaperPositionJournal(self.position_path)
        self.rows = candles()[:6]
        self.strategy = config().strategy
        self.now = self.rows[-1].close_time_ms + 1000

    def count_open_intents(self):
        with closing(sqlite3.connect(self.order_path)) as db:
            return db.execute(
                "SELECT COUNT(*) FROM paper_order_intents"
            ).fetchone()[0]

    def rule(self, *, now=None, **change):
        attrs = dict(
            venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
            quote_currency="USDT",
            observed_at_ms=self.now if now is None else now,
            fixture_version="fixture_margin_causal_v1",
            max_leverage_assumed=75,
            price_tick_quote=D("0.01"),
            quantity_step_base=D("0.01"),
            min_quantity_base=D("0.01"),
            min_notional_quote=D("100"),
            max_notional_quote=D("1000"),
        )
        attrs.update(change)
        return PaperLinearContractFixture(**attrs)

    def request(self, *, margin=D(5), leverage=50, max_age=1000, rule=None):
        return PaperMarginPreflightRequest(
            settings=SyntheticLeverageSettings(leverage),
            margin_quote=margin, contract=self.rule() if rule is None else rule,
            max_contract_age_ms=max_age,
        )

    def limits(self):
        return PaperRiskLimits(
            max_order_notional_quote=D(400),
            max_symbol_exposure_quote=D(1000),
            max_portfolio_exposure_quote=D(2000),
            max_realized_loss_today_quote=D(50),
            max_pending_open_orders=1, max_market_age_ms=1000,
        )

    def observation(self, *, at=None, **change):
        values = dict(
            venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
            quote_currency="USDT",
            observed_at_ms=self.now if at is None else at,
            mark_price_quote=D(100),
            symbol_exposure_quote=D(0),
            portfolio_exposure_quote=D(0),
            realized_loss_today_quote=D(0),
            pending_open_orders=0, unresolved_open_exists=False,
            kill_switch_active=False,
        )
        values.update(change)
        return PaperRiskObservation(**values)

    def run(self, *, quantity=D("2.5"), requirement=None,
            observation=None, rows=None, now=None):
        data = self.rows if rows is None else rows
        at = data[-1].close_time_ms + 1000 if now is None else now
        return reserve_causal_paper_open(
            data, strategy=self.strategy,
            venue=PaperVenue.BINANCE_USDM,
            requested_units=quantity,
            limits=self.limits(),
            observation=self.observation(at=at) if observation is None else observation,
            journal=self.orders,
            position_journal_path=self.position_path,
            decision_at_ms=at,
            margin_preflight=requirement,
        )

    def prepare(self, *, quantity=D("2.5"), requirement=None):
        return prepare_causal_paper_open(
            self.rows, strategy=self.strategy,
            venue=PaperVenue.BINANCE_USDM,
            requested_units=quantity,
            limits=self.limits(), observation=self.observation(),
            decision_at_ms=self.now, margin_preflight=requirement,
        )

    def test_five_quote_units_at_50x_reaches_only_paper_pending(self):
        result = self.run(requirement=self.request())
        self.assertTrue(result.paper_intent_reserved)
        self.assertEqual(result.reason, "paper_open_intent_reserved_only")
        self.assertEqual(result.margin_assessment.reason,
                         PaperMarginReason.FEASIBLE_PAPER_ONLY)
        self.assertEqual(result.margin_assessment.leverage_captured_for_new_intent, 50)
        self.assertEqual(result.reservation.entry.snapshot.status,
                         PaperOrderStatus.PENDING)
        self.assertEqual(result.reservation.entry.snapshot.filled_total_units, D(0))
        self.assertEqual(self.count_open_intents(), 1)
        self.assertFalse(result.orders_sent)
        self.assertFalse(result.order_submission_enabled)
        self.assertFalse(result.approved_for_live_use)
        self.assertFalse(result.margin_assessment.leverage_persisted_to_position_ledger)

    def test_one_quote_unit_at_50x_below_assumed_minimum_reserves_nothing(self):
        old = self.count_open_intents()
        result = self.run(
            quantity=D("0.5"), requirement=self.request(margin=D(1)),
        )
        self.assertIsNone(result.intent)
        self.assertIsNone(result.reservation)
        self.assertIsNone(result.health)
        self.assertFalse(result.paper_intent_reserved)
        self.assertEqual(result.margin_assessment.reason,
                         PaperMarginReason.MIN_NOTIONAL)
        self.assertEqual(result.reason,
                         "paper_margin_denied_hypothetical_min_notional_not_met")
        self.assertEqual(self.count_open_intents(), old)

    def test_50x_does_not_auto_downgrade_if_cap_fixture_is_20x(self):
        result = self.run(
            requirement=self.request(rule=self.rule(max_leverage_assumed=20)),
        )
        self.assertEqual(result.margin_assessment.reason,
                         PaperMarginReason.LEVERAGE_CAP_EXCEEDED)
        self.assertEqual(result.margin_assessment.leverage_captured_for_new_intent, 50)
        self.assertFalse(result.paper_intent_reserved)
        self.assertEqual(self.count_open_intents(), 0)

    def test_kill_switch_wins_over_insufficient_notional(self):
        observation = self.observation(kill_switch_active=True)
        result = self.run(
            quantity=D("0.5"), requirement=self.request(margin=D(1)),
            observation=observation,
        )
        self.assertFalse(result.paper_intent_reserved)
        self.assertEqual(result.margin_assessment.reason,
                         PaperMarginReason.RISK_GATE_BLOCKED)
        self.assertEqual(result.margin_assessment.risk_reason,
                         PaperRiskReason.KILL_SWITCH)
        self.assertEqual(self.count_open_intents(), 0)

    def test_unresolved_open_and_portfolio_exposure_block_before_reservation(self):
        for altered, reason in (
            (self.observation(unresolved_open_exists=True),
             PaperRiskReason.UNRESOLVED_OPEN),
            (self.observation(portfolio_exposure_quote=D(1900)),
             PaperRiskReason.PORTFOLIO_EXPOSURE),
        ):
            with self.subTest(reason=reason):
                result = self.run(requirement=self.request(), observation=altered)
                self.assertEqual(result.margin_assessment.reason,
                                 PaperMarginReason.RISK_GATE_BLOCKED)
                self.assertEqual(result.margin_assessment.risk_reason, reason)
                self.assertEqual(self.count_open_intents(), 0)

    def test_stale_fixture_and_mismatched_quote_fail_before_journal(self):
        requirement = self.request(
            rule=self.rule(now=self.now - 1001), max_age=1000,
        )
        stale = self.run(requirement=requirement)
        self.assertEqual(stale.margin_assessment.reason,
                         PaperMarginReason.CONTRACT_FIXTURE_STALE)
        self.assertEqual(self.count_open_intents(), 0)
        bad = self.request(rule=self.rule(
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDC",
            quote_currency="USDC",
        ))
        with self.assertRaises(DataValidationError):
            self.run(requirement=bad)
        self.assertEqual(self.count_open_intents(), 0)

    def test_no_latest_candidate_never_reserves_even_if_request_is_opted_in(self):
        source = candles()[:8]
        result = self.run(rows=source, requirement=self.request())
        self.assertEqual(result.reason, "no_fresh_synthetic_hypothesis")
        self.assertIsNone(result.margin_assessment)
        self.assertEqual(self.count_open_intents(), 0)

    def test_wrong_or_partial_opt_in_rejected_not_silently_bypassed(self):
        with self.assertRaises(DataValidationError):
            self.run(requirement={"margin_quote": "5"})
        with self.assertRaises(DataValidationError):
            self.request(margin="5")
        with self.assertRaises(DataValidationError):
            self.request(max_age=604800001)
        self.assertEqual(self.count_open_intents(), 0)

    def test_legacy_no_opt_in_remains_unchanged_and_no_margin_claimed(self):
        previous = self.run(quantity=D(2), requirement=None)
        self.assertTrue(previous.paper_intent_reserved)
        self.assertIsNone(previous.margin_assessment)
        self.assertEqual(previous.reason, "paper_open_intent_reserved_only")
        self.assertFalse(previous.approved_for_live_use)

    def test_prepare_copies_only_new_leverage_settings_not_old_result(self):
        first = self.prepare(requirement=self.request())
        second = self.prepare(
            quantity=D(1), requirement=self.request(
                margin=D(5), leverage=20,
                rule=self.rule(max_leverage_assumed=20),
            ),
        )
        self.assertEqual(first.margin_assessment.leverage_captured_for_new_intent, 50)
        self.assertEqual(second.margin_assessment.leverage_captured_for_new_intent, 20)
        self.assertEqual(first.margin_assessment.assumed_notional_quote, D(250))
        self.assertEqual(second.margin_assessment.assumed_notional_quote, D(100))
        self.assertFalse(first.paper_intent_reserved)
        self.assertFalse(second.paper_intent_reserved)
        self.assertEqual(self.count_open_intents(), 0)
        with self.assertRaises(FrozenInstanceError):
            first.margin_assessment = None

    def test_journal_health_pause_denies_after_preflight_without_losing_reason(self):
        self.orders.set_local_kill_switch(
            pause=True, expected_sequence=0, changed_at_ms=self.now,
        )
        result = self.run(requirement=self.request())
        self.assertFalse(result.paper_intent_reserved)
        self.assertIsNotNone(result.margin_assessment)
        self.assertTrue(result.margin_assessment.allowed_for_paper_research_only)
        self.assertTrue(result.reason.startswith("paper_open_health_denied_"))
        self.assertEqual(self.count_open_intents(), 0)

    def test_paper_approval_never_bypasses_double_open_reservation(self):
        first = self.run(requirement=self.request())
        self.assertTrue(first.paper_intent_reserved)
        with self.assertRaises(DataValidationError):
            self.run(requirement=self.request())
        self.assertEqual(self.count_open_intents(), 1)

    def test_no_network_when_margin_preflight_blocks_or_allows(self):
        with patch("socket.create_connection",
                   side_effect=AssertionError("network not allowed")):
            with patch("urllib.request.urlopen",
                       side_effect=AssertionError("network not allowed")):
                denied = self.run(
                    quantity=D("0.5"), requirement=self.request(margin=D(1)),
                )
                accepted = self.run(requirement=self.request())
        self.assertFalse(denied.paper_intent_reserved)
        self.assertTrue(accepted.paper_intent_reserved)
        self.assertFalse(accepted.margin_assessment.venue_contract_verified)


if __name__ == "__main__":
    unittest.main()
