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


    def test_kill_switch_does_not_prevent_planning_paper_exit(self):
        close = intent(
            intent_id="fixture_close_X", fixture_signal_id="fixture_close_signal_X",
            effect=PaperOrderEffect.REDUCE_ONLY, side=PaperOrderSide.SELL,
            max_reducible_units=D(10),
        )
        d = evaluate_paper_risk(
            close, limits(),
            obs(kill_switch_active=True, unresolved_open_exists=True),
            decision_at_ms=T + 5000,
        )
        self.assertTrue(d.allowed_for_paper_only)
        self.assertEqual(d.reason, PaperRiskReason.PROTECTIVE_EXIT_PAPER_ONLY)
        self.assertFalse(d.order_submission_enabled)
        self.assertFalse(d.orders_sent)

    def test_venue_and_quote_incompatible_snapshots_fail(self):
        with self.assertRaises(DataValidationError):
            evaluate_paper_risk(intent(), limits(),
                                obs(venue=PaperVenue.BYBIT_V5), decision_at_ms=T)
        with self.assertRaises(DataValidationError):
            evaluate_paper_risk(intent(), limits(),
                                obs(symbol="ETHUSDT"), decision_at_ms=T)
        for name in ("USDC", "USD", "BTC"):
            with self.subTest(name=name), self.assertRaises(DataValidationError):
                obs(quote_currency=name)
        bybit_order = intent(venue=PaperVenue.BYBIT_V5, symbol="BTCUSDC")
        bybit_obs = obs(
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDC", quote_currency="USDC",
        )
        self.assertTrue(evaluate_paper_risk(
            bybit_order, limits(), bybit_obs, decision_at_ms=T,
        ).allowed_for_paper_only)

    def test_no_float_boolean_nan_or_implicit_limits(self):
        for value in (0.5, True, D("NaN"), D("Infinity"), D(-1),
                      D("1e100"), D("1e-28")):
            with self.subTest(value=str(value)):
                with self.assertRaises(DataValidationError):
                    limits(max_order_notional_quote=value)
                with self.assertRaises(DataValidationError):
                    obs(mark_price_quote=value)
        for values in (
            dict(max_pending_open_orders=True),
            dict(max_pending_open_orders=-1),
            dict(max_market_age_ms=True),
            dict(max_market_age_ms=-1),
            dict(max_order_notional_quote=D(201)),
        ):
            with self.subTest(values=values), self.assertRaises(DataValidationError):
                limits(**values)
        for values in (
            dict(portfolio_exposure_quote=D(99)),
            dict(pending_open_orders=1.5),
            dict(unresolved_open_exists=1),
            dict(kill_switch_active="false"),
            dict(observed_at_ms=True),
        ):
            with self.subTest(values=values), self.assertRaises(DataValidationError):
                obs(**values)

    def test_never_accept_live_flag_or_mutable_authority(self):
        for incompatible in ("live", {"mode": "live"}):
            with self.assertRaises(DataValidationError):
                evaluate_paper_risk(incompatible, limits(), obs(), decision_at_ms=T)
        with self.assertRaises(DataValidationError):
            evaluate_paper_risk(intent(), {"mode": "live"}, obs(), decision_at_ms=T)
        first = evaluate_paper_risk(intent(), limits(), obs(), decision_at_ms=T)
        self.assertEqual(
            first, evaluate_paper_risk(intent(), limits(), obs(), decision_at_ms=T)
        )
        self.assertFalse(first.approved_for_live_use)
        self.assertFalse(first.order_submission_enabled)

    def test_paper_risk_never_touches_network(self):
        from unittest.mock import patch
        with patch("urllib.request.urlopen",
                   side_effect=AssertionError("unexpected network")):
            d = evaluate_paper_risk(intent(), limits(), obs(), decision_at_ms=T)
        self.assertTrue(d.allowed_for_paper_only)
        self.assertFalse(d.orders_sent)


if __name__ == "__main__":
    unittest.main()
