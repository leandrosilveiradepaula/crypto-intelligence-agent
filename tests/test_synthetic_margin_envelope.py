"""J3/PRE15 exact margin stress envelope over PRE6 alternative results."""
from dataclasses import replace
from decimal import Decimal, localcontext
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_margin_envelope import (
    SyntheticMarginBasis, evaluate_conditional_margin_envelope,
)
from test_synthetic_financial_scenarios import (
    LONG, SHORT, SyntheticBarrier, ObservationKind, observation,
    scenario, evaluate, ScenarioResolution,
)

D = Decimal


def basis(currency="SYNTHETIC_USDT"):
    return SyntheticMarginBasis(D("4"), 50, D("200"), currency)


class ConditionalMarginEnvelopeTests(unittest.TestCase):
    def test_50x_target_and_stop_do_not_select_target_as_sure_win(self):
        target = scenario()
        stop = scenario(identity="fixture_financial_stop", exit="95",
                        barrier=SyntheticBarrier.STOP)
        results = evaluate(observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED),
                           (target, stop))
        # PRE6 uses synthetic QUOTE; adapt only the allowed synthetic currency.
        margin = SyntheticMarginBasis(D("4"), 50, D("200"), "SYNTHETIC_QUOTE")
        # Currency is purposely *not* in the allowlist: must fail instead.
        with self.assertRaises(DataValidationError):
            evaluate_conditional_margin_envelope(results, margin=margin)

    def test_exact_scenarios_favorable_branch_and_downside(self):
        from crypto_intelligence_agent.synthetic_financial_scenarios import ConditionalFinancialResult
        from crypto_intelligence_agent.synthetic_cost_scenarios import evaluate_synthetic_costs
        from test_synthetic_financial_scenarios import scenario
        target = evaluate(observation(), (scenario(),))[0]
        stop = replace(target, scenario_id="fixture_financial_stop",
                       assumed_barrier=SyntheticBarrier.STOP,
                       conditional_net_quote_units=D("-6"),
                       ambiguity_branch_count=2,
                       quote_currency="SYNTHETIC_USDT")
        target = replace(target, ambiguity_branch_count=2,
                         quote_currency="SYNTHETIC_USDT")
        result = evaluate_conditional_margin_envelope((target, stop), margin=basis())
        self.assertEqual(result.worst_barrier, SyntheticBarrier.STOP)
        self.assertEqual(result.hypothetical_max_downside_over_margin, D("1.5"))
        self.assertTrue(result.conditional_margin_exhaustion_possible)
        self.assertTrue(result.favorable_branch_not_sufficient_for_safety)
        self.assertFalse(result.net_pnl_verified)
        self.assertEqual(result, evaluate_conditional_margin_envelope((stop, target), margin=basis()))
        for precision in (2, 4, 28):
            with localcontext() as c:
                c.prec = precision
                self.assertEqual(result, evaluate_conditional_margin_envelope((target, stop), margin=basis()))

    def test_negative_net_can_be_worse_than_margin_without_liquidation_proof(self):
        target = evaluate(observation(), (scenario(),))[0]
        expensive = replace(target, conditional_net_quote_units=D("-4.0001"),
                            quote_currency="SYNTHETIC_USDT")
        result = evaluate_conditional_margin_envelope((expensive,), margin=basis())
        self.assertTrue(result.conditional_margin_exhaustion_possible)
        self.assertFalse(result.hypothetical_liquidation_branch_present)
        self.assertFalse(result.liquidation_formula_verified)

    def test_margin_guards_and_heterogeneous_quotes(self):
        for kwargs in (
            {"requested_margin_quote": D("0")},
            {"requested_margin_quote": 4.0},
            {"requested_margin_quote": D("NaN")},
            {"leverage_at_intent": True},
            {"leverage_at_intent": 201},
            {"entry_notional_quote": D("199")},
            {"quote_currency": "USDT"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(DataValidationError):
                replace(basis(), **kwargs)
        one = evaluate(observation(), (scenario(),))[0]
        with self.assertRaises(DataValidationError):
            evaluate_conditional_margin_envelope((one,), margin=basis())
        bad = replace(one, quote_currency="SYNTHETIC_USDT",
                      ambiguity_branch_count=2)
        with self.assertRaises(DataValidationError):
            evaluate_conditional_margin_envelope((bad,), margin=basis())
        with self.assertRaises(DataValidationError):
            evaluate_conditional_margin_envelope((), margin=basis())


if __name__ == "__main__":
    unittest.main()
