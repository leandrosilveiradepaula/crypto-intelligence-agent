"""J4: offline synthetic partial exit cost/funding mark conservation."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, getcontext, localcontext
import json
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_partial_costed_replay import (
    SyntheticPartialCostRates, SyntheticPartialMarkFill,
    evaluate_synthetic_partial_costed_replay,
)
from crypto_intelligence_agent.synthetic_manual_exit_replay import SyntheticManualExitEvent
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import (
    SyntheticLeverageSettings, SyntheticPositionExitFill, SyntheticSide,
    open_synthetic_position,
)


D = Decimal


def rates(**kw) -> SyntheticPartialCostRates:
    return SyntheticPartialCostRates(
        entry_fee_bps=kw.get("entry_fee_bps", D(10)),
        exit_fee_bps=kw.get("exit_fee_bps", D(10)),
        entry_adverse_slippage_bps=kw.get("entry_adverse_slippage_bps", D(5)),
        exit_adverse_slippage_bps=kw.get("exit_adverse_slippage_bps", D(5)),
    )


def position(*, side=SyntheticSide.LONG, settings=None, identity="fixture_j4_costed"):
    plan = SyntheticExitPlan(
        initial_units=D(100),
        tranches=tuple(SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(x))
                       for x in (50, 60, 70)),
        residual_floor_percent=D(6),
    )
    return open_synthetic_position(
        fixture_position_id=identity,
        side=side,
        opened_at_ms=1_000,
        exit_plan=plan,
        synthetic_margin_units=D(2),
        settings=settings or SyntheticLeverageSettings(50),
    )


def fill(p, name: str, step: int, quantity: str, at: int, price: str):
    return SyntheticPartialMarkFill(
        SyntheticPositionExitFill(
            p.fixture_position_id,
            SyntheticManualExitEvent(
                event_id=name, tranche_step=step,
                filled_units=D(quantity), event_at_ms=at,
            ),
        ),
        reference_exit_price_quote=D(price),
    )


def funding(name="fixture_funding_first", at=2_500,
            amount="5000", bps="2") -> SyntheticFundingEvent:
    return SyntheticFundingEvent(name, at, D(amount), D(bps))


class SyntheticPartialCostedReplayTests(unittest.TestCase):
    def setUp(self):
        self.p = position()
        self.fills = (
            fill(self.p, "close50", 1, "50", 2_000, "110"),
            fill(self.p, "close30", 2, "30", 3_000, "120"),
            fill(self.p, "close14", 3, "14", 4_000, "90"),
        )

    def evaluate(self, **overrides):
        args = dict(
            position=self.p,
            marked_fills=self.fills,
            entry_reference_price_quote=D(100),
            last_reference_mark_quote=D(130),
            mark_observed_at_ms=5_000,
            max_mark_age_ms=1_000,
            as_of_ms=5_001,
            cost_rates=rates(),
            funding_events=(funding(),),
        )
        args.update(overrides)
        return evaluate_synthetic_partial_costed_replay(**args)

    def test_50_60_70_runner_costs_and_funding_are_conserved(self):
        x = self.evaluate()
        self.assertEqual(x.filled_units, D(94))
        self.assertEqual(x.residual_units, D(6))
        self.assertEqual(x.runner_floor_units, D(6))
        self.assertEqual(x.realized_gross_reference_quote, D(960))
        self.assertEqual(x.residual_mark_gross_reference_quote, D(180))
        self.assertEqual(x.entry_fee_slippage_quote, D(15))
        self.assertEqual(x.exit_fee_slippage_quote, D("15.54"))
        self.assertEqual(x.signed_funding_cost_quote, D(1))
        self.assertEqual(x.hypothetical_net_mark_reference_quote, D("1108.46"))
        self.assertEqual(x.leverage_at_open, 50)
        self.assertEqual(x.unique_fill_count, 3)
        for flag in (
            "financial_backtest_approved", "realized_pnl_verified",
            "venue_fees_verified", "funding_settlement_verified",
            "liquidation_risk_verified", "actual_margin_return_available",
            "orders_sent", "approved_for_live_use",
        ):
            self.assertFalse(getattr(x, flag), flag)
        evidence = x.sanitized_report()
        self.assertEqual(evidence["status"], "synthetic_partial_exit_mark_reference_only")
        self.assertNotIn("fixture_j4_costed", json.dumps(evidence))
        self.assertNotIn("reference_exit_price_quote", evidence)
        self.assertNotIn("fixture_position_id", evidence)

    def test_short_direction_reverses_gross_and_funding(self):
        p = position(side=SyntheticSide.SHORT)
        f = tuple(fill(p, z.bound_fill.event.event_id,
                       z.bound_fill.event.tranche_step,
                       str(z.bound_fill.event.filled_units),
                       z.bound_fill.event.event_at_ms,
                       str(z.reference_exit_price_quote)) for z in self.fills)
        x = self.evaluate(position=p, marked_fills=f)
        self.assertEqual(x.realized_gross_reference_quote, D(-960))
        self.assertEqual(x.residual_mark_gross_reference_quote, D(-180))
        self.assertEqual(x.signed_funding_cost_quote, D(-1))
        self.assertEqual(x.hypothetical_net_mark_reference_quote, D("-1169.54"))

    def test_duplicate_fill_and_funding_not_double_counted(self):
        dup_fills=(self.fills[0], self.fills[0], *self.fills[1:])
        dup_funding=(funding(), funding())
        x=self.evaluate(marked_fills=dup_fills, funding_events=dup_funding)
        self.assertEqual(x.exact_duplicate_fill_count,1)
        self.assertEqual(x.exact_duplicate_funding_count,1)
        self.assertEqual(x.unique_fill_count,3)
        self.assertEqual(x.hypothetical_net_mark_reference_quote,D("1108.46"))

    def test_fill_id_same_economics_different_price_rejected(self):
        x=self.fills[0]
        fake=SyntheticPartialMarkFill(x.bound_fill,D("111"))
        with self.assertRaises(DataValidationError):
            self.evaluate(marked_fills=(x,fake,*self.fills[1:]))

    def test_fill_duplicate_id_numeric_equal_but_changed_decimal_payload_rejected(self):
        x=self.fills[0]
        changed=fill(self.p,"close50",1,"50.0",2_000,"110")
        with self.assertRaises(DataValidationError):
            self.evaluate(marked_fills=(x,changed,*self.fills[1:]))

    def test_partial_first_step_preserves_residual_and_entry_cost(self):
        x=self.evaluate(
            marked_fills=(fill(self.p,"partial1",1,"20",2_000,"110"),),
            funding_events=(),
        )
        self.assertEqual(x.filled_units,D(20))
        self.assertEqual(x.residual_units,D(80))
        self.assertEqual(x.residual_mark_gross_reference_quote,D(2400))
        self.assertEqual(x.realized_gross_reference_quote,D(200))
        self.assertEqual(x.entry_fee_slippage_quote,D(15))
        self.assertEqual(x.exit_fee_slippage_quote,D("3.30"))
        self.assertEqual(x.hypothetical_net_mark_reference_quote,D("2581.70"))

    def test_no_exit_still_pays_full_entry_cost_but_not_exit_cost(self):
        x=self.evaluate(marked_fills=(),funding_events=())
        self.assertEqual(x.residual_units,D(100))
        self.assertEqual(x.entry_fee_slippage_quote,D(15))
        self.assertEqual(x.exit_fee_slippage_quote,D(0))
        self.assertEqual(x.hypothetical_net_mark_reference_quote,D(2985))

    def test_position_leverage_is_immutable_despite_settings_change(self):
        base=SyntheticLeverageSettings(50)
        later=base.with_new_position_leverage(20)
        p=position(settings=base)
        self.assertEqual(later.for_new_positions,20)
        x=self.evaluate(position=p)
        self.assertEqual(x.leverage_at_open,50)
        self.assertFalse(x.actual_margin_return_available)

    def test_funding_id_collision_and_notional_mismatch_rejected(self):
        bad=funding(name="fixture_funding_first",amount="4999")
        with self.assertRaises(DataValidationError):
            self.evaluate(funding_events=(funding(),bad))
        with self.assertRaises(DataValidationError):
            self.evaluate(funding_events=(bad,))

    def test_funding_must_match_balance_after_sold_units(self):
        # At 3500, only 20 units remain: 2000 quote at the synthetic
        # entry-price reference; using initial notional would fake exposure.
        good=funding("fixture_funding_second",3_500,"2000","-1")
        x=self.evaluate(funding_events=(good,))
        self.assertEqual(x.signed_funding_cost_quote,D("-0.2"))
        self.assertEqual(x.hypothetical_net_mark_reference_quote,D("1109.66"))

    def test_future_stale_and_ambiguous_marks_are_denied(self):
        for options in (
            dict(mark_observed_at_ms=5_002),
            dict(mark_observed_at_ms=3_500),
            dict(mark_observed_at_ms=5_000,as_of_ms=7_000),
            dict(max_mark_age_ms=True),
            dict(max_mark_age_ms=-1),
            dict(last_reference_mark_quote=D("NaN")),
            dict(entry_reference_price_quote=100.0),
        ):
            with self.subTest(options=options),self.assertRaises(DataValidationError):
                self.evaluate(**options)

    def test_funding_time_collision_with_exit_or_future_denied(self):
        for value in (
            funding("fixture_funding_eq",2_000,"10000","1"),
            funding("fixture_funding_future",5_001,"600","1"),
            funding("fixture_funding_before",1_000,"10000","1"),
        ):
            with self.subTest(event_at=value.event_at_ms):
                with self.assertRaises(DataValidationError):
                    self.evaluate(funding_events=(value,))

    def test_out_of_order_cross_position_and_overfill_denied(self):
        x=fill(self.p,"first",1,"51",2_000,"110")
        for marked in (
            (x,self.fills[1:][0]),
            (self.fills[1],self.fills[0]),
            (fill(position(identity="fixture_other"),"other",1,"50",2_000,"110"),),
        ):
            with self.assertRaises(DataValidationError):
                self.evaluate(marked_fills=marked)

    def test_precision_independent_of_global_decimal_context(self):
        with localcontext() as ctx:
            ctx.prec=6
            result=self.evaluate()
        self.assertEqual(result.hypothetical_net_mark_reference_quote,D("1108.46"))


if __name__=="__main__":
    unittest.main()
