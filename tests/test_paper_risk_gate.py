"""Offline paper-only preflight gate tests with fictitious mark and exposure."""
from dataclasses import FrozenInstanceError
from decimal import Decimal
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_risk_gate import (
    PaperRiskLimits, PaperRiskObservation, PaperRiskReason, evaluate_paper_risk,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

T = 1792985000000
D = Decimal


def intent(**updates):
    fields = dict(
        intent_id="fixture_intent_X", fixture_signal_id="fixture_signal_X",
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
        effect=PaperOrderEffect.OPEN, requested_units=D(10),
        created_at_ms=T,
    )
    fields.update(updates)
    return PaperOrderIntent(**fields)


def limits(**updates):
    fields = dict(
        max_order_notional_quote=D(100),
        max_symbol_exposure_quote=D(200),
        max_portfolio_exposure_quote=D(500),
        max_realized_loss_today_quote=D(10),
        max_pending_open_orders=2,
        max_market_age_ms=1000,
    )
    fields.update(updates)
    return PaperRiskLimits(**fields)


def obs(**updates):
    fields = dict(
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT", quote_currency="USDT",
        observed_at_ms=T, mark_price_quote=D(2),
        symbol_exposure_quote=D(100), portfolio_exposure_quote=D(200),
        realized_loss_today_quote=D(0), pending_open_orders=0,
        unresolved_open_exists=False, kill_switch_active=False,
    )
    fields.update(updates)
    return PaperRiskObservation(**fields)


class PaperRiskGateTests(unittest.TestCase):
    def test_paper_allowed_never_means_real_order(self):
        d = evaluate_paper_risk(intent(), limits(), obs(), decision_at_ms=T + 1000)
        self.assertTrue(d.allowed_for_paper_only)
        self.assertEqual(d.reason, PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY)
        self.assertEqual(d.hypothetical_notional_quote, D(20))
        self.assertEqual(d.observed_age_ms, 1000)
        self.assertFalse(d.order_submission_enabled)
        self.assertFalse(d.orders_sent)
        self.assertFalse(d.approved_for_live_use)
        with self.assertRaises(FrozenInstanceError):
            d.allowed_for_paper_only = False

    def test_kill_switch_and_unknown_block_open(self):
        killed = evaluate_paper_risk(
            intent(), limits(), obs(kill_switch_active=True), decision_at_ms=T,
        )
        self.assertFalse(killed.allowed_for_paper_only)
        self.assertEqual(killed.reason, PaperRiskReason.KILL_SWITCH)
        uncertain = evaluate_paper_risk(
            intent(), limits(), obs(unresolved_open_exists=True), decision_at_ms=T,
        )
        self.assertFalse(uncertain.allowed_for_paper_only)
        self.assertEqual(uncertain.reason, PaperRiskReason.UNRESOLVED_OPEN)

    def test_pending_count_and_loss_cap_boundaries(self):
        self.assertEqual(evaluate_paper_risk(
            intent(), limits(), obs(pending_open_orders=2), decision_at_ms=T,
        ).reason, PaperRiskReason.PENDING_LIMIT)
        self.assertTrue(evaluate_paper_risk(
            intent(), limits(), obs(pending_open_orders=1), decision_at_ms=T,
        ).allowed_for_paper_only)
        self.assertEqual(evaluate_paper_risk(
            intent(), limits(), obs(realized_loss_today_quote=D(10)), decision_at_ms=T,
        ).reason, PaperRiskReason.LOSS_LIMIT)
        self.assertTrue(evaluate_paper_risk(
            intent(), limits(), obs(realized_loss_today_quote=D("9.999")),
            decision_at_ms=T,
        ).allowed_for_paper_only)

    def test_stale_feed_and_no_future_information(self):
        self.assertTrue(evaluate_paper_risk(
            intent(), limits(), obs(), decision_at_ms=T + 1000,
        ).allowed_for_paper_only)
        self.assertEqual(evaluate_paper_risk(
            intent(), limits(), obs(), decision_at_ms=T + 1001,
        ).reason, PaperRiskReason.STALE_FEED)
        with self.assertRaises(DataValidationError):
            evaluate_paper_risk(intent(), limits(), obs(observed_at_ms=T + 1),
                                decision_at_ms=T)
        with self.assertRaises(DataValidationError):
            evaluate_paper_risk(intent(), limits(), obs(), decision_at_ms=T - 1)

    def test_order_symbol_and_portfolio_caps(self):
        items = [
            (intent(requested_units=D(51)), obs(), PaperRiskReason.ORDER_NOTIONAL),
            (intent(), obs(symbol_exposure_quote=D(181)),
             PaperRiskReason.SYMBOL_EXPOSURE),
            (intent(), obs(portfolio_exposure_quote=D(481)),
             PaperRiskReason.PORTFOLIO_EXPOSURE),
        ]
        for order, observation, reason in items:
            with self.subTest(reason=reason):
                d = evaluate_paper_risk(order, limits(), observation, decision_at_ms=T)
                self.assertEqual(d.reason, reason)
                self.assertFalse(d.allowed_for_paper_only)
        self.assertTrue(evaluate_paper_risk(
            intent(), limits(),
            obs(symbol_exposure_quote=D(180), portfolio_exposure_quote=D(480)),
            decision_at_ms=T,
        ).allowed_for_paper_only)


if __name__ == "__main__":
    unittest.main()
