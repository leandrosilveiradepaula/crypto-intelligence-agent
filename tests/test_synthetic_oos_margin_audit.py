"""PRE15: bind synthetic OOS alternatives to requested margin without fills."""
from dataclasses import replace
from decimal import Decimal
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_margin_envelope import (
    SyntheticMarginBasis, SyntheticAdverseCostStress,
)
from crypto_intelligence_agent.synthetic_research_cycle import (
    audit_synthetic_oos_margin,
)
from test_synthetic_research_cycle import candles, cycle, plan_for, branch

D = Decimal


def stress():
    return SyntheticAdverseCostStress(D("10"), D("10"), D("10"), D("10"))


def margin():
    # PRE7 fixture entry is 105 * 2 = 210; 50x margin = 4.2 synthetic units.
    return SyntheticMarginBasis(D("4.2"), 50, D("210"), "SYNTHETIC_QUOTE")


class OOSMarginAuditTests(unittest.TestCase):
    def prepared(self):
        rows = candles()
        e = cycle(rows).events[0]
        plan = plan_for(e)
        financial = (branch(e, rows),)
        report = cycle(rows, plans={5: plan}, scenarios={5: financial})
        return report, {5: plan}, {5: financial}

    def test_exact_oos_event_and_adverse_costs(self):
        c, plans, scenarios = self.prepared()
        result = audit_synthetic_oos_margin(
            c, margin_by_candidate={5: margin()}, stress_by_candidate={5: stress()},
            barrier_plans=plans, financial_scenarios=scenarios,
        )
        self.assertEqual(result.event_indices, (5,))
        self.assertEqual(result.refused_events, 0)
        self.assertEqual(len(result.stressed), 1)
        self.assertLess(result.stressed[0].worst_conditional_net_quote,
                        result.baseline[0].worst_conditional_net_quote)
        self.assertFalse(result.financial_backtest_approved)
        self.assertFalse(result.orders_sent)

    def test_abstentions_cannot_be_claimed_as_profitable(self):
        c = cycle(candles())
        result = audit_synthetic_oos_margin(
            c, margin_by_candidate={}, stress_by_candidate={},
            barrier_plans={}, financial_scenarios={},
        )
        self.assertEqual(result.event_indices, ())
        self.assertEqual(result.baseline, ())
        self.assertEqual(result.refused_events, 1)
        self.assertFalse(result.net_pnl_verified)

    def test_missing_margin_and_altered_financial_terms_fail_closed(self):
        c, plans, scenarios = self.prepared()
        args = dict(cycle=c, margin_by_candidate={5: margin()},
                    stress_by_candidate={5: stress()},
                    barrier_plans=plans, financial_scenarios=scenarios)
        with self.assertRaises(DataValidationError):
            audit_synthetic_oos_margin(**{**args, "margin_by_candidate": {}})
        with self.assertRaises(DataValidationError):
            audit_synthetic_oos_margin(**{**args, "stress_by_candidate": {}})
        changed = replace(scenarios[5][0], scenario_id="fixture_financial_changed")
        with self.assertRaisesRegex(DataValidationError, "changed since PRE7"):
            audit_synthetic_oos_margin(**{**args, "financial_scenarios": {5: (changed,)}})
        with self.assertRaises(DataValidationError):
            audit_synthetic_oos_margin(**{**args, "margin_by_candidate": {5: replace(
                margin(), quote_currency="SYNTHETIC_USDC")}})

    def test_cannot_claim_results_for_non_candidate_or_wrong_type(self):
        c, plans, scenarios = self.prepared()
        for margins, stresses in (
            ({5: margin(), 6: margin()}, {5: stress()}),
            ({"5": margin()}, {5: stress()}),
            ({5: margin()}, {5: None}),
        ):
            with self.subTest(margins=margins), self.assertRaises(DataValidationError):
                audit_synthetic_oos_margin(
                    c, margin_by_candidate=margins, stress_by_candidate=stresses,
                    barrier_plans=plans, financial_scenarios=scenarios,
                )


if __name__ == "__main__":
    unittest.main()
