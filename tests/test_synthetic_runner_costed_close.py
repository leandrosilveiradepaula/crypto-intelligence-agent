"""J4/#607: terminal runner is a declared fixture fill, not a trailing mark."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
import json
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import (
    SyntheticSide, SyntheticLeverageSettings, open_synthetic_position,
)
from crypto_intelligence_agent.synthetic_runner_costed_close import (
    SyntheticRunnerCloseMarkFill, evaluate_synthetic_runner_costed_closure,
)
from test_synthetic_partial_costed_replay import position, rates, fill, funding

D = Decimal


def partials(p):
    return (
        fill(p, "close50", 1, "50", 2_000, "110"),
        fill(p, "close30", 2, "30", 3_000, "120"),
        fill(p, "close14", 3, "14", 4_000, "90"),
    )


def runner(p, *, receipt="receiptXYZ171", qty="6", price="130", at=5_000):
    return SyntheticRunnerCloseMarkFill(
        fixture_position_id=p.fixture_position_id, event_id=receipt,
        filled_units=D(qty), reference_exit_price_quote=D(price),
        event_at_ms=at,
    )


class SyntheticRunnerCostedCloseTests(unittest.TestCase):
    def setUp(self):
        self.p = position()
        self.partials = partials(self.p)
        self.runner = runner(self.p)

    def evaluate(self, **kwargs):
        args = dict(
            position=self.p,
            partial_fills=self.partials,
            runner_receipts=(self.runner,),
            entry_reference_price_quote=D(100),
            cost_rates=rates(),
            as_of_ms=7_000,
            funding_events=(funding(),),
        )
        args.update(kwargs)
        return evaluate_synthetic_runner_costed_closure(**args)

    def test_long_50_60_70_then_runner_close_conserves_costs_exactly(self):
        closed = self.evaluate()
        self.assertEqual((closed.initial_units, closed.partial_filled_units,
                          closed.runner_closed_units, closed.final_remaining_units),
                         (D(100), D(94), D(6), D(0)))
        self.assertEqual(closed.partial_realized_gross_reference_quote, D(960))
        self.assertEqual(closed.runner_gross_reference_quote, D(180))
        self.assertEqual(closed.total_gross_reference_quote, D(1140))
        self.assertEqual(closed.entry_fee_slippage_quote, D(15))
        self.assertEqual(closed.partial_exit_fee_slippage_quote, D("15.54"))
        self.assertEqual(closed.runner_exit_fee_slippage_quote, D("1.17"))
        self.assertEqual(closed.signed_funding_cost_quote, D(1))
        self.assertEqual(closed.hypothetical_net_closed_reference_quote, D("1107.29"))
        self.assertEqual(closed.leverage_at_open, 50)
        report = closed.sanitized_report()
        self.assertEqual(report["status"], "synthetic_runner_terminal_close_reference_only")
        self.assertEqual(report["hypothetical_net_closed_reference_quote"], "1107.29")
        for secret in ("fixture_j4_costed", "receiptXYZ171", "close50", "BTCUSDT"):
            self.assertNotIn(secret, json.dumps(report))
        for key in (
            "realized_pnl_verified", "liquidation_risk_verified",
            "venue_fees_verified", "funding_settlement_verified",
            "venue_fill_verified", "persistent_idempotency_verified",
            "financial_backtest_approved", "approved_for_live_use",
            "orders_sent",
        ):
            self.assertFalse(getattr(closed, key), key)
            self.assertIs(report[key], False)

    def test_short_reverses_gross_and_funding_not_fees(self):
        p = position(side=SyntheticSide.SHORT)
        closed = self.evaluate(position=p, partial_fills=partials(p),
                               runner_receipts=(runner(p),))
        self.assertEqual(closed.total_gross_reference_quote, D(-1140))
        self.assertEqual(closed.signed_funding_cost_quote, D(-1))
        self.assertEqual(closed.entry_fee_slippage_quote, D(15))
        self.assertEqual(closed.runner_exit_fee_slippage_quote, D("1.17"))
        self.assertEqual(closed.hypothetical_net_closed_reference_quote, D("-1170.71"))

    def test_later_funding_uses_20_remaining_not_100(self):
        second = funding("fixture_funding_second", 3_500, "2000", "-1")
        closed = self.evaluate(funding_events=(second,))
        self.assertEqual(closed.signed_funding_cost_quote, D("-0.2"))
        self.assertEqual(closed.hypothetical_net_closed_reference_quote, D("1108.49"))
        with self.assertRaises(DataValidationError):
            self.evaluate(funding_events=(funding("fixture_funding_bad",
                                                  3_500, "10000", "-1"),))

    def test_duplicate_receipt_is_idempotent_but_no_persistent_guarantee(self):
        closed = self.evaluate(
            partial_fills=(self.partials[0], self.partials[0],
                           self.partials[1], self.partials[2]),
            runner_receipts=(self.runner, self.runner),
            funding_events=(funding(), funding()),
        )
        self.assertEqual(closed.exact_duplicate_runner_receipt_count, 1)
        self.assertEqual(closed.exact_duplicate_partial_fill_count, 1)
        self.assertEqual(closed.exact_duplicate_funding_count, 1)
        self.assertEqual(closed.hypothetical_net_closed_reference_quote, D("1107.29"))
        self.assertFalse(closed.persistent_idempotency_verified)

    def test_conflict_and_second_receipt_id_never_close_twice(self):
        forged = (
            replace(self.runner, event_id="runner_second"),
            replace(self.runner, filled_units=D("6.0")),
            replace(self.runner, reference_exit_price_quote=D("130.0")),
            replace(self.runner, reference_exit_price_quote=D(131)),
            replace(self.runner, event_at_ms=5_001),
        )
        for case in forged:
            with self.subTest(case=case.event_id, price=str(case.reference_exit_price_quote)):
                with self.assertRaises(DataValidationError):
                    self.evaluate(runner_receipts=(self.runner, case))
        with self.assertRaises(DataValidationError):
            self.evaluate(runner_receipts=(self.runner,) * 513)

    def test_partial_tranche_or_wrong_runner_quantity_never_promotes_close(self):
        cases = (
            dict(partial_fills=self.partials[:2]),
            dict(partial_fills=()),
            dict(runner_receipts=(runner(self.p, qty="5"),)),
            dict(runner_receipts=(runner(self.p, qty="7"),)),
            dict(runner_receipts=(runner(self.p, qty="100"),)),
        )
        for change in cases:
            with self.subTest(change=str(change)[:80]), self.assertRaises(DataValidationError):
                self.evaluate(**change)

    def test_zero_floor_position_has_no_runner_to_close(self):
        plan = SyntheticExitPlan(
            initial_units=D(100),
            tranches=(SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(100)),),
            residual_floor_percent=D(0),
        )
        p = open_synthetic_position(
            fixture_position_id="fixture_zero_runner",
            side=SyntheticSide.LONG, opened_at_ms=1_000,
            exit_plan=plan, synthetic_margin_units=D(2),
            settings=SyntheticLeverageSettings(50),
        )
        complete = (fill(p, "full100", 1, "100", 2_000, "110"),)
        with self.assertRaises(DataValidationError):
            self.evaluate(position=p, partial_fills=complete,
                          runner_receipts=(runner(p, qty="1"),),
                          funding_events=())

    def test_clock_and_identity_fail_closed(self):
        p2 = position(identity="fixture_other_runner")
        bad_cases = (
            dict(runner_receipts=(runner(p2),)),
            dict(runner_receipts=(runner(self.p, receipt="close50"),)),
            dict(runner_receipts=(runner(self.p, at=4_000),)),
            dict(runner_receipts=(runner(self.p, at=3_500),)),
            dict(runner_receipts=(runner(self.p, at=1_000),)),
            dict(runner_receipts=(runner(self.p, at=9_000),)),
            dict(as_of_ms=4_999),
            dict(as_of_ms=True),
        )
        for changed in bad_cases:
            with self.subTest(changed=str(changed)[:90]), self.assertRaises(DataValidationError):
                self.evaluate(**changed)

    def test_funding_on_close_or_after_close_cannot_charge_closed_position(self):
        for at in (5_000, 5_001, 6_000):
            with self.subTest(at=at), self.assertRaises(DataValidationError):
                self.evaluate(funding_events=(funding(
                    "fixture_funding_after", at, "600", "2"),))
        with self.assertRaises(DataValidationError):
            self.evaluate(funding_events=(funding(
                "fixture_funding_same_partial", 4_000, "2000", "2"),))

    def test_invalid_numeric_types_and_receipt_contracts(self):
        for value in (D("NaN"), D("-1"), D("0"), 6.0, "6"):
            with self.subTest(value=str(value)), self.assertRaises(DataValidationError):
                SyntheticRunnerCloseMarkFill(
                    fixture_position_id=self.p.fixture_position_id,
                    event_id="runner_valid",
                    filled_units=value,
                    reference_exit_price_quote=D(130),
                    event_at_ms=5_000,
                )
        for price in (D("NaN"), D("Infinity"), D(0), D(-1), 130.0):
            with self.subTest(price=str(price)), self.assertRaises(DataValidationError):
                SyntheticRunnerCloseMarkFill(
                    self.p.fixture_position_id, "runner_valid", D(6), price, 5_000,
                )
        for id_ in ("", "BTC.USDT", "secret/path", "a" * 100):
            with self.subTest(id=id_), self.assertRaises(DataValidationError):
                SyntheticRunnerCloseMarkFill(
                    self.p.fixture_position_id, id_, D(6), D(130), 5_000,
                )
        for changed in (
            dict(position="not-a-position"),
            dict(runner_receipts=[]),
            dict(runner_receipts=()),
            dict(runner_receipts=(self.runner, "invalid")),
            dict(entry_reference_price_quote=D(0)),
            dict(cost_rates="fake"),
        ):
            with self.subTest(changed=str(changed)[:60]), self.assertRaises(DataValidationError):
                self.evaluate(**changed)

    def test_immutable_open_leverage_decimal_context_and_late_audit(self):
        p = position(settings=SyntheticLeverageSettings(50))
        revised = SyntheticLeverageSettings(50).with_new_position_leverage(20)
        self.assertEqual(revised.for_new_positions, 20)
        with localcontext() as ctx:
            ctx.prec = 6
            a = self.evaluate(position=p, partial_fills=partials(p),
                              runner_receipts=(runner(p),), as_of_ms=8_000_000)
        self.assertEqual(a.leverage_at_open, 50)
        self.assertEqual(a.hypothetical_net_closed_reference_quote, D("1107.29"))
        self.assertEqual(a.as_of_ms, 8_000_000)
        self.assertEqual(a.runner_closed_at_ms, 5_000)


if __name__ == "__main__":
    unittest.main()
