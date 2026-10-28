"""J4/PRE11 #278: exact hypothetical $1/$5 margin and 50x PAPER risk checks.

No venue rules, quote collateral, mark price, trading rights or live orders
are inferred. Only local Decimal fixtures and the existing PAPER RiskGate.
"""
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_margin_preflight import (
    PaperLinearContractFixture, PaperMarginReason, assess_paper_margin_open,
)
from crypto_intelligence_agent.paper_risk_gate import (
    PaperRiskLimits, PaperRiskObservation, PaperRiskReason,
    evaluate_paper_risk,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_position_state import (
    SyntheticLeverageSettings, SyntheticSide,
)

D = Decimal
T = 1_792_985_000_000


def order(**changes):
    data = dict(
        intent_id="fixture_margin_open", fixture_signal_id="fixture_margin_signal",
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
        effect=PaperOrderEffect.OPEN, requested_units=D("0.5"),
        created_at_ms=T,
    )
    data.update(changes)
    return PaperOrderIntent(**data)


def contract(**changes):
    data = dict(
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        quote_currency="USDT", observed_at_ms=T,
        fixture_version="fixture_binance_assumed_v1",
        max_leverage_assumed=75, price_tick_quote=D("0.01"),
        quantity_step_base=D("0.01"),
        min_quantity_base=D("0.01"),
        min_notional_quote=D("100"), max_notional_quote=D("1000"),
    )
    data.update(changes)
    return PaperLinearContractFixture(**data)


def limits(**changes):
    data = dict(
        max_order_notional_quote=D("1000"),
        max_symbol_exposure_quote=D("2000"),
        max_portfolio_exposure_quote=D("5000"),
        max_realized_loss_today_quote=D("50"),
        max_pending_open_orders=2, max_market_age_ms=2000,
    )
    data.update(changes)
    return PaperRiskLimits(**data)


def mark(**changes):
    data = dict(
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        quote_currency="USDT", observed_at_ms=T,
        mark_price_quote=D("100"),
        symbol_exposure_quote=D(0), portfolio_exposure_quote=D(0),
        realized_loss_today_quote=D(0), pending_open_orders=0,
        unresolved_open_exists=False, kill_switch_active=False,
    )
    data.update(changes)
    return PaperRiskObservation(**data)


def assess(*, intent=None, settings=None, margin=D(1),
           instrument=None, risk=None, observation=None,
           decision=T, freshness=2000):
    return assess_paper_margin_open(
        order() if intent is None else intent,
        SyntheticLeverageSettings() if settings is None else settings,
        margin, contract() if instrument is None else instrument,
        limits() if risk is None else risk,
        mark() if observation is None else observation,
        decision_at_ms=decision, max_contract_age_ms=freshness,
    )


class PaperMarginPreflightTests(unittest.TestCase):
    def test_global_initial_50x_captured_on_new_paper_intent(self):
        snapshot = assess(margin=D("5"), intent=order(requested_units=D("2.5")))
        self.assertEqual(snapshot.leverage_captured_for_new_intent, 50)
        self.assertEqual(snapshot.assumed_notional_quote, D("250"))
        self.assertEqual(snapshot.actual_intent_notional_quote, D("250"))
        self.assertEqual(snapshot.requested_units_base, D("2.5"))
        self.assertEqual(snapshot.quote_currency, "USDT")
        self.assertTrue(snapshot.allowed_for_paper_research_only)
        self.assertEqual(snapshot.reason, PaperMarginReason.FEASIBLE_PAPER_ONLY)
        self.assertEqual(snapshot.risk_reason, PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY)
        for flag in (
            "orders_sent", "order_submission_enabled", "approved_for_live_use",
            "venue_contract_verified", "real_margin_currency_verified",
            "mark_price_authenticated", "liquidation_model_verified",
            "financial_backtest_approved", "leverage_persisted_to_position_ledger",
        ):
            self.assertFalse(getattr(snapshot, flag), flag)
        with self.assertRaises(FrozenInstanceError):
            snapshot.leverage_captured_for_new_intent = 5

    def test_one_dollar_at_50x_fails_assumed_min_notional(self):
        check = assess(margin=D("1"), intent=order(requested_units=D("0.5")))
        self.assertEqual(check.reason, PaperMarginReason.MIN_NOTIONAL)
        self.assertFalse(check.allowed_for_paper_research_only)
        self.assertEqual(check.assumed_notional_quote, D(50))
        self.assertEqual(check.risk_reason, PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY)
        self.assertFalse(check.order_submission_enabled)

    def test_five_dollars_at_50x_can_fit_synthetic_minimum_not_a_real_order(self):
        good = assess(margin=D("5"), intent=order(requested_units=D("2.5")))
        self.assertTrue(good.allowed_for_paper_research_only)
        self.assertFalse(good.venue_contract_verified)
        self.assertFalse(good.order_submission_enabled)

    def test_lower_cap_rejects_50x_without_silent_adjustment(self):
        bad = assess(
            margin=D("5"), intent=order(requested_units=D("2.5")),
            instrument=contract(max_leverage_assumed=20),
        )
        self.assertEqual(bad.reason, PaperMarginReason.LEVERAGE_CAP_EXCEEDED)
        self.assertEqual(bad.leverage_captured_for_new_intent, 50)
        self.assertFalse(bad.allowed_for_paper_research_only)

    def test_settings_change_is_not_retroactive_and_new_positions_use_new_cap(self):
        initial = SyntheticLeverageSettings()
        first = assess(
            margin=D(5), intent=order(requested_units=D("2.5")),
            settings=initial,
        )
        changed = initial.with_new_position_leverage(20)
        second = assess(
            margin=D(5), intent=order(requested_units=D("1")),
            settings=changed, instrument=contract(max_leverage_assumed=20),
        )
        self.assertTrue(second.allowed_for_paper_research_only)
        self.assertEqual(first.leverage_captured_for_new_intent, 50)
        self.assertEqual(second.leverage_captured_for_new_intent, 20)
        self.assertEqual(initial.for_new_positions, 50)

    def test_no_implicit_rounding_when_margin_fails_exact_notional(self):
        result = assess(
            margin=D("5"), intent=order(requested_units=D("83.33")),
            observation=mark(mark_price_quote=D("3")),
            instrument=contract(quantity_step_base=D("0.01"), min_notional_quote=D("1")),
        )
        self.assertEqual(result.assumed_notional_quote, D(250))
        self.assertEqual(result.actual_intent_notional_quote, D("249.99"))
        self.assertEqual(result.reason, PaperMarginReason.MARGIN_NOTIONAL_MISMATCH)
        self.assertFalse(result.allowed_for_paper_research_only)
        self.assertEqual(result.requested_units_base, D("83.33"))

    def test_exact_notional_but_non_multiple_base_step_is_rejected(self):
        result = assess(
            margin=D("1.1"), intent=order(requested_units=D("0.55")),
            instrument=contract(quantity_step_base=D("0.1"),
                                min_quantity_base=D("0.1"),
                                min_notional_quote=D(1)),
        )
        self.assertEqual(result.reason, PaperMarginReason.QUANTITY_STEP_MISMATCH)

    def test_nonzero_minimum_quantity_and_maximum_notional(self):
        small = assess(
            margin=D(1), intent=order(requested_units=D("0.5")),
            instrument=contract(min_quantity_base=D(1), min_notional_quote=D(1)),
        )
        self.assertEqual(small.reason, PaperMarginReason.MIN_QUANTITY)
        large = assess(
            margin=D(5), intent=order(requested_units=D("2.5")),
            instrument=contract(max_notional_quote=D(200)),
        )
        self.assertEqual(large.reason, PaperMarginReason.MAX_NOTIONAL)

    def test_kill_switch_and_unresolved_open_override_convenience_failures(self):
        for variant, expected in (
            (mark(kill_switch_active=True), PaperRiskReason.KILL_SWITCH),
            (mark(unresolved_open_exists=True), PaperRiskReason.UNRESOLVED_OPEN),
            (mark(pending_open_orders=2), PaperRiskReason.PENDING_LIMIT),
            (mark(realized_loss_today_quote=D(50)), PaperRiskReason.LOSS_LIMIT),
        ):
            with self.subTest(reason=expected):
                check = assess(
                    margin=D(1), intent=order(requested_units=D("0.5")),
                    observation=variant,
                )
                self.assertEqual(check.reason, PaperMarginReason.RISK_GATE_BLOCKED)
                self.assertEqual(check.risk_reason, expected)
                self.assertFalse(check.allowed_for_paper_research_only)

    def test_risk_notional_exposure_and_market_staleness_remain_authoritative(self):
        tests = (
            (limits(max_order_notional_quote=D(100), max_symbol_exposure_quote=D(150)),
             mark(), PaperRiskReason.ORDER_NOTIONAL),
            (limits(), mark(symbol_exposure_quote=D(1900), portfolio_exposure_quote=D(1900)),
             PaperRiskReason.SYMBOL_EXPOSURE),
            (limits(), mark(portfolio_exposure_quote=D(4900)),
             PaperRiskReason.PORTFOLIO_EXPOSURE),
            (limits(), mark(observed_at_ms=T - 3000),
             PaperRiskReason.STALE_FEED),
        )
        for rule, observation, expected in tests:
            with self.subTest(reason=expected):
                outcome = assess(
                    intent=order(requested_units=D("2.5")), margin=D(5),
                    risk=rule, observation=observation,
                )
                self.assertEqual(outcome.reason, PaperMarginReason.RISK_GATE_BLOCKED)
                self.assertEqual(outcome.risk_reason, expected)

    def test_fixture_stale_and_future_metadata_fail_closed(self):
        original = contract(observed_at_ms=T - 1001)
        stale = assess(
            margin=D(5), intent=order(requested_units=D("2.5")),
            instrument=original, freshness=1000,
        )
        self.assertEqual(stale.reason, PaperMarginReason.CONTRACT_FIXTURE_STALE)
        exact = assess(
            margin=D(5), intent=order(requested_units=D("2.5")),
            instrument=original, freshness=1001,
        )
        self.assertTrue(exact.allowed_for_paper_research_only)
        with self.assertRaises(DataValidationError):
            assess(instrument=contract(observed_at_ms=T+1))
        for bad in (True, -1, 604800001, D(1), "100"):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                assess(freshness=bad)

    def test_bybit_usdc_is_distinct_from_usdt_and_usd(self):
        bybit = order(venue=PaperVenue.BYBIT_V5, symbol="BTCUSDC",
                      requested_units=D("2.5"))
        contract_usdc = contract(
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDC",
            quote_currency="USDC",
        )
        result = assess(
            intent=bybit, instrument=contract_usdc, margin=D(5),
            observation=mark(venue=PaperVenue.BYBIT_V5, symbol="BTCUSDC",
                             quote_currency="USDC"),
        )
        self.assertEqual(result.quote_currency, "USDC")
        self.assertTrue(result.allowed_for_paper_research_only)
        with self.assertRaises(DataValidationError):
            assess(intent=bybit, instrument=contract_usdc, margin=D(5),
                   observation=mark())
        with self.assertRaises(DataValidationError):
            contract(quote_currency="USD")
        with self.assertRaises(DataValidationError):
            contract(quote_currency="USDC")
        with self.assertRaises(DataValidationError):
            contract(venue=PaperVenue.BINANCE_USDM,
                     symbol="BTCUSDC", quote_currency="USDC")

    def test_reject_reduce_only_without_impact_on_existing_protective_exit(self):
        exit_intent = order(
            intent_id="fixture_close_exit", fixture_signal_id="fixture_exit_signal",
            effect=PaperOrderEffect.REDUCE_ONLY,
            side=PaperOrderSide.SELL,
            max_reducible_units=D("0.5"),
        )
        with self.assertRaises(DataValidationError):
            assess(intent=exit_intent)
        self.assertTrue(evaluate_paper_risk(
            exit_intent, limits(), mark(kill_switch_active=True),
            decision_at_ms=T,
        ).allowed_for_paper_only)

    def test_validation_rejects_float_nan_bool_and_fake_provenance(self):
        for bad in (D("NaN"), D("Infinity"), D("-1"), 1.0, True, D("1e-30")):
            with self.subTest(bad=str(bad)), self.assertRaises(DataValidationError):
                assess(margin=bad)
        for value in (20.0, True, "50", 0, 201):
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                contract(max_leverage_assumed=value)
        for field, value in (
            ("price_tick_quote", D("0")),
            ("price_tick_quote", D("NaN")),
            ("quantity_step_base", D("NaN")),
            ("quantity_step_base", D("0")),
            ("min_quantity_base", D("0")),
            ("min_quantity_base", D("0.005")),
            ("min_notional_quote", D("NaN")),
            ("max_notional_quote", D("0")),
            ("fixture_version", "approved-live-v1"),
            ("fixture_version", "https://api.bybit.com"),
            ("symbol", "BTCUSD"),
            ("symbol", "BTCUSDT/../orders"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(DataValidationError):
                contract(**{field: value})

    def test_no_socket_credentials_or_provider_data_needed(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                result = assess(
                    margin=D(5), intent=order(requested_units=D("2.5")),
                )
        self.assertTrue(result.allowed_for_paper_research_only)
        self.assertFalse(result.orders_sent)
        self.assertFalse(result.approved_for_live_use)


if __name__ == "__main__":
    unittest.main()
