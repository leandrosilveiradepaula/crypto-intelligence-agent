"""J3/PRE2: bounded exact hypothetical costs, not venue fees or PnL."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_cost_scenarios import (
    MAX_FUNDING_EVENTS, SyntheticFundingEvent, SyntheticCostScenario,
    SyntheticCostBreakdown, evaluate_synthetic_costs,
)

D = Decimal
START = 1_800_000_000_000
END = START + 10_000
L, S = ResearchDirection.LONG, ResearchDirection.SHORT


def funding(id="fixture_funding_1", rate="5", notional="1000", at=START+1000):
    return SyntheticFundingEvent(
        event_id=id, event_at_ms=at,
        hypothetical_notional_quote_units=D(str(notional)) if type(notional) is str
        else notional,
        signed_funding_rate_bps=D(str(rate)) if type(rate) is str else rate,
    )


def scenario(*, side=L, start=START, end=END, entry="1000", exit="800",
             entry_fee="10", exit_fee="20", entry_slip="5", exit_slip="15",
             events=()):
    return SyntheticCostScenario(
        direction=side, entry_at_ms=start, exit_at_ms=end,
        entry_hypothetical_notional_quote_units=D(str(entry)) if type(entry) is str else entry,
        exit_hypothetical_notional_quote_units=D(str(exit)) if type(exit) is str else exit,
        entry_fee_bps=D(str(entry_fee)) if type(entry_fee) is str else entry_fee,
        exit_fee_bps=D(str(exit_fee)) if type(exit_fee) is str else exit_fee,
        entry_adverse_slippage_bps=D(str(entry_slip)) if type(entry_slip) is str else entry_slip,
        exit_adverse_slippage_bps=D(str(exit_slip)) if type(exit_slip) is str else exit_slip,
        funding_events=events,
    )


def evaluate(**kw):
    return evaluate_synthetic_costs(scenario(**kw))


class SyntheticCostTests(unittest.TestCase):
    def test_manual_reference_fee_slippage_on_each_leg_no_funding(self):
        out = evaluate()
        self.assertIsInstance(out, SyntheticCostBreakdown)
        self.assertEqual(out.entry_fee_units, D("1"))
        self.assertEqual(out.exit_fee_units, D("1.6"))
        self.assertEqual(out.entry_slippage_cost_units, D("0.5"))
        self.assertEqual(out.exit_slippage_cost_units, D("1.2"))
        self.assertEqual(out.fees_and_slippage_units, D("4.3"))
        self.assertEqual(out.signed_funding_cost_units, D(0))
        self.assertEqual(out.total_signed_cost_units, D("4.3"))
        self.assertFalse(out.net_pnl_verified)

    def test_long_positive_funding_is_a_synthetic_cost(self):
        out = evaluate(events=(funding(rate="5"),))
        self.assertEqual(out.signed_funding_cost_units, D("0.5"))
        self.assertEqual(out.total_signed_cost_units, D("4.8"))
        self.assertEqual(out.unique_funding_count, 1)

    def test_short_positive_funding_is_hypothetical_credit(self):
        out = evaluate(side=S, events=(funding(rate="5"),))
        self.assertEqual(out.signed_funding_cost_units, D("-0.5"))
        self.assertEqual(out.total_signed_cost_units, D("3.8"))

    def test_long_negative_funding_is_credit_short_negative_pays(self):
        for direction, amount in ((L, D("-2")), (S, D("2"))):
            with self.subTest(direction=direction):
                out = evaluate(side=direction, events=(funding(rate="-20"),))
                self.assertEqual(out.signed_funding_cost_units, amount)
                self.assertEqual(out.total_signed_cost_units, D("4.3")+amount)

    def test_signed_funding_inflows_do_not_create_profit_certification(self):
        out = evaluate(
            entry_fee="0", exit_fee="0", entry_slip="0", exit_slip="0",
            events=(funding(rate="-100", notional="1000"),),
        )
        self.assertEqual(out.total_signed_cost_units, D("-10"))
        self.assertFalse(out.financial_backtest_approved)
        self.assertFalse(out.net_pnl_verified)
        self.assertFalse(hasattr(out, "gross_pnl"))
        self.assertFalse(hasattr(out, "profit"))

    def test_funding_notional_can_differ_from_entry_exit_synthetic_notionals(self):
        out = evaluate(events=(funding(rate="10", notional="2000"),))
        self.assertEqual(out.signed_funding_cost_units, D("2"))
        self.assertEqual(out.fees_and_slippage_units, D("4.3"))
        self.assertEqual(out.total_signed_cost_units, D("6.3"))

    def test_entry_exit_fees_are_not_equal_when_notionals_differ(self):
        out = evaluate(entry_fee="10", exit_fee="10", entry_slip="0", exit_slip="0")
        self.assertEqual(out.entry_fee_units, D(1))
        self.assertEqual(out.exit_fee_units, D("0.8"))
        self.assertEqual(out.total_signed_cost_units, D("1.8"))

    def test_zero_rates_mean_zero_costs_not_guaranteed_zero_real_costs(self):
        out = evaluate(entry_fee="0", exit_fee="0", entry_slip="0",
                       exit_slip="0", events=(funding(rate="0"),))
        self.assertEqual(out.total_signed_cost_units, D(0))
        self.assertFalse(out.venue_fee_schedule_verified)
        self.assertFalse(out.funding_schedule_verified)
        self.assertFalse(out.fill_price_verified)

    def test_multiple_funding_observations_have_signed_sum(self):
        rows = (
            funding("fixture_funding_a", rate="10", at=START+1000),
            funding("fixture_funding_b", rate="-20", at=START+2000),
            funding("fixture_funding_c", rate="5", at=START+3000),
        )
        out = evaluate(events=rows)
        self.assertEqual(out.signed_funding_cost_units, D("-0.5"))
        self.assertEqual(out.total_signed_cost_units, D("3.8"))
        self.assertEqual(out.unique_funding_count, 3)
        self.assertEqual(out.last_unique_funding_at_ms, START+3000)

    def test_identical_duplicate_is_counted_once(self):
        row = funding()
        out = evaluate(events=(row, row, row))
        self.assertEqual(out.unique_funding_count, 1)
        self.assertEqual(out.exact_duplicate_count, 2)
        self.assertEqual(out.signed_funding_cost_units, D("0.5"))

    def test_identical_duplicate_later_than_other_unique_is_ignored(self):
        a = funding("fixture_funding_a", at=START+1000)
        b = funding("fixture_funding_b", at=START+2000)
        out = evaluate(events=(a, b, a))
        self.assertEqual(out.unique_funding_count, 2)
        self.assertEqual(out.exact_duplicate_count, 1)
        self.assertEqual(out.signed_funding_cost_units, D(1))
        self.assertEqual(out.last_unique_funding_at_ms, START+2000)

    def test_same_id_different_rate_notional_timestamp_conflicts(self):
        original = funding(rate="5", at=START+1000, notional="1000")
        variants = (
            funding(rate="6", at=START+1000, notional="1000"),
            funding(rate="5", at=START+1001, notional="1000"),
            funding(rate="5", at=START+1000, notional="1001"),
            funding(rate="5.0", at=START+1000, notional="1000"),
            funding(rate="5", at=START+1000, notional="1000.0"),
        )
        for row in variants:
            with self.subTest(row=row), self.assertRaisesRegex(
                DataValidationError, "conflicting"
            ):
                evaluate(events=(original, row))

    def test_different_ids_same_timestamp_rejected_to_avoid_double_count(self):
        with self.assertRaisesRegex(DataValidationError, "chronological"):
            evaluate(events=(funding("fixture_funding_a", at=START+1000),
                             funding("fixture_funding_b", at=START+1000)))

    def test_backwards_time_unique_events_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "chronological"):
            evaluate(events=(funding("fixture_funding_a", at=START+2000),
                             funding("fixture_funding_b", at=START+1000)))

    def test_funding_strictly_inside_holding_window(self):
        for when in (START-1, START, END, END+1):
            with self.subTest(when=when), self.assertRaisesRegex(
                DataValidationError, "outside open holding"
            ):
                evaluate(events=(funding(at=when),))
        self.assertEqual(evaluate(events=(funding(at=START+1),)).unique_funding_count, 1)
        self.assertEqual(evaluate(events=(funding(at=END-1),)).unique_funding_count, 1)

    def test_funding_count_limit_is_not_position_target(self):
        rows = tuple(funding(f"fixture_funding_{i}", at=START+1+i)
                     for i in range(MAX_FUNDING_EVENTS))
        out = evaluate(events=rows)
        self.assertEqual(out.unique_funding_count, MAX_FUNDING_EVENTS)
        with self.assertRaises(DataValidationError):
            evaluate(events=rows + (funding("fixture_funding_extra", at=START+200),))

    def test_missing_and_malformed_utc_timestamps_rejected(self):
        for bad in (0, -1, True, 1.5, "1800000000000", None, 253_402_300_800_000):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                scenario(start=bad)
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                scenario(end=bad)
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                funding(at=bad)
        with self.assertRaisesRegex(DataValidationError, "after entry"):
            scenario(start=END, end=END)
        with self.assertRaises(DataValidationError):
            scenario(start=END+1, end=END)

    def test_scenario_direction_is_explicit_enum_not_string_or_bool(self):
        for wrong in ("LONG", "SHORT", None, True, 0):
            with self.subTest(wrong=wrong), self.assertRaises(DataValidationError):
                scenario(side=wrong)
        self.assertEqual(scenario(side=S).direction, ResearchDirection.SHORT)

    def test_notional_must_be_bounded_positive_decimal_never_float(self):
        for invalid in (D(0), D(-1), D("NaN"), D("Infinity"), D("1e-19"),
                        D("1e25"), D("1"*41), 1000.0, 1000, True, None):
            with self.subTest(invalid=str(invalid)[:30]), self.assertRaises(DataValidationError):
                scenario(entry=invalid)
            with self.subTest(invalid=str(invalid)[:30]), self.assertRaises(DataValidationError):
                scenario(exit=invalid)
            with self.subTest(invalid=str(invalid)[:30]), self.assertRaises(DataValidationError):
                funding(notional=invalid)

    def test_fee_and_slippage_rates_require_nonnegative_exact_decimal(self):
        for value in (D("-1"), D("NaN"), D("Infinity"), D("10001"), D("1e-7"),
                      1, 1.0, True, None):
            for name in ("entry_fee", "exit_fee", "entry_slip", "exit_slip"):
                with self.subTest(name=name, value=str(value)), self.assertRaises(DataValidationError):
                    scenario(**{name: value})
        with self.assertRaises(DataValidationError):
            replace(scenario(), entry_fee_bps="1")
        self.assertEqual(evaluate(entry_fee="0.000001").entry_fee_units, D("0.0000001"))

    def test_funding_bps_are_signed_and_bounded(self):
        for value in (D("10001"), D("-10001"), D("NaN"), D("Infinity"),
                      D("-Infinity"), D("1e-7"), 1, 1.0, True, None):
            with self.subTest(value=str(value)), self.assertRaises(DataValidationError):
                funding(rate=value)
        with self.assertRaises(DataValidationError):
            SyntheticFundingEvent("fixture_funding_a", START+1000, D(1000), "1")
        self.assertEqual(funding(rate="-10000").signed_funding_rate_bps, D(-10000))
        self.assertEqual(funding(rate="10000").signed_funding_rate_bps, D(10000))

    def test_funding_id_synthetic_ascii_only(self):
        for bad in ("", "funding_real", "fixture_funding_", "fixture_funding_" + "a"*41,
                    "fixture_funding_a/b", "fixture_funding_é", "fixture_funding_a\n",
                    "fixture_funding_a@b", True, None):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                SyntheticFundingEvent(bad, START+1000, D(1000), D(5))
        self.assertEqual(funding(id="fixture_funding_a_b").event_id, "fixture_funding_a_b")

    def test_immutable_tuple_of_events_required(self):
        for bad in ([funding()], (funding() for _ in range(1)),
                    ("event",), ({"event_id": "fixture_funding_1"},)):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(DataValidationError):
                scenario(events=bad)

    def test_decimal_exact_under_global_precision_and_long_list(self):
        rows = tuple(
            funding(f"fixture_funding_{i}", rate="0.000001",
                    notional="123456789012345678.123456789012345678",
                    at=START+1+i)
            for i in range(MAX_FUNDING_EVENTS)
        )
        config = dict(entry="123456789012345678.123456789012345678",
                      exit="123456789012345678.123456789012345678",
                      entry_fee="0.000001", exit_fee="0.000001",
                      entry_slip="0.000001", exit_slip="0.000001", events=rows)
        with localcontext() as c:
            c.prec = 3
            low = evaluate(**config)
        with localcontext() as c:
            c.prec = 400
            high = evaluate(**config)
        self.assertEqual(low, high)
        with localcontext() as c:
            c.prec = 512
            self.assertEqual(low.total_signed_cost_units,
                             low.fees_and_slippage_units + low.signed_funding_cost_units)

    def test_repeated_evaluation_is_deterministic_without_io(self):
        config = scenario(events=(funding(),))
        self.assertEqual(evaluate_synthetic_costs(config), evaluate_synthetic_costs(config))
        self.assertEqual(config.entry_hypothetical_notional_quote_units, D(1000))

    def test_input_record_is_immutable(self):
        config = scenario()
        event = funding()
        with self.assertRaises(FrozenInstanceError):
            config.entry_fee_bps = D(100)
        with self.assertRaises(FrozenInstanceError):
            event.signed_funding_rate_bps = D(999)

    def test_output_security_flags_are_constant_false(self):
        res = evaluate(events=(funding(),))
        self.assertEqual(res.quality, "synthetic_cost_scenario_only")
        for name in (
            "venue_fee_schedule_verified", "funding_schedule_verified",
            "real_quote_currency_verified", "fill_price_verified",
            "persistent_idempotency_verified", "financial_backtest_approved",
            "net_pnl_verified", "approved_for_live_use", "orders_sent",
        ):
            self.assertIs(getattr(res, name), False)
            with self.subTest(name=name), self.assertRaises(TypeError):
                replace(res, **{name: True})
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(res, name, True)
        with self.assertRaises(TypeError):
            replace(res, quality="live")
        with self.assertRaises(FrozenInstanceError):
            res.total_signed_cost_units = D(0)

    def test_no_price_or_fx_conversion_or_margin_and_leverage_in_outputs(self):
        res = evaluate()
        for name in ("price", "margin", "leverage", "contract_multiplier", "real_quote_currency",
                     "exchange", "quote_usd", "fx_rate", "pnl", "roi",
                     "liquidation_price", "filled_at", "order_id", "profit"):
            self.assertFalse(hasattr(res, name))

    def test_no_network_storage_or_live_trading_api(self):
        src = (Path(__file__).resolve().parent.parent
               / "crypto_intelligence_agent/synthetic_cost_scenarios.py").read_text()
        for forbidden in ("urllib.request", "requests.", "socket", "sqlite3", "open(",
                          "create_order(", "send_order(", "futures.kraken.com",
                          "api.hyperliquid.xyz", "subprocess"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
