"""J3/PRE6 offline regressions: explicit branches, never inferred fills."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticCostScenario, SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_financial_scenarios import (
    ConditionalFinancialScenario, FundingProvenance, ScenarioResolution,
    evaluate_conditional_financial_scenarios,
)
from crypto_intelligence_agent.synthetic_intrabar_barriers import (
    ObservationKind, ResearchDirection, SyntheticBarrier, SyntheticBarrierObservation,
)

D = Decimal
LONG, SHORT = ResearchDirection.LONG, ResearchDirection.SHORT


def observation(kind=ObservationKind.SINGLE_LEVEL_RANGE):
    return SyntheticBarrierObservation(
        exchange="synthetic_venue", symbol="BTCUSDT", interval="1h", plan_created_at_ms=1_000,
        as_of_ms=5_000, available_closed_candles=1, examined_closed_candles=1, kind=kind,
        levels_reached=(SyntheticBarrier.TARGET,), first_candidate_index=0,
        first_candidate_open_time_ms=2_000, first_candidate_close_time_ms=4_999,
    )


def funding(rate="5"):
    return SyntheticFundingEvent("fixture_funding_a", 2_500, D("1000"), D(rate))


def scenario(*, identity="fixture_financial_a", side=LONG, resolution=ScenarioResolution.EXPLICIT_EXIT,
             entry="100", exit="110", loss=None, events=(), provenance=()):
    return ConditionalFinancialScenario(
        scenario_id=identity, exchange="synthetic_venue", symbol="BTCUSDT", interval="1h", direction=side,
        entry_price=D(entry), quantity_base_units=D("2"), resolution=resolution,
        exit_price=D(exit) if exit is not None else None,
        hypothetical_liquidation_loss_quote_units=D(loss) if loss is not None else None,
        quote_currency="SYNTHETIC_QUOTE",
        costs=SyntheticCostScenario(side, 2_000, 3_000, D("200"), D("220"), D("10"), D("10"), D("0"), D("0"), events),
        funding_provenance=provenance,
    )


class ConditionalFinancialScenarioTests(unittest.TestCase):
    def test_long_and_short_explicit_prices_use_decimal_and_declared_costs(self):
        long = scenario()
        short = scenario(identity="fixture_financial_b", side=SHORT, entry="100", exit="90")
        results = evaluate_conditional_financial_scenarios(observation(), (long, short))
        self.assertEqual(results[0].gross_price_movement_quote_units, D("20"))
        self.assertEqual(results[0].conditional_net_quote_units, D("19.58"))
        self.assertEqual(results[1].gross_price_movement_quote_units, D("20"))
        self.assertEqual(results[1].conditional_net_quote_units, D("19.58"))

    def test_multiple_intrabar_levels_require_alternative_explicit_branches(self):
        ambiguous = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        with self.assertRaisesRegex(DataValidationError, "alternative"):
            evaluate_conditional_financial_scenarios(ambiguous, (scenario(),))
        exits = (scenario(), scenario(identity="fixture_financial_stop", exit="95"))
        result = evaluate_conditional_financial_scenarios(ambiguous, exits)
        self.assertEqual([item.gross_price_movement_quote_units for item in result], [D("20"), D("-10")])
        self.assertEqual(result[0].ambiguity_branch_count, 2)

    def test_explicit_liquidation_is_a_loss_assumption_not_venue_formula(self):
        row = scenario(resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS, exit=None, loss="75")
        result = evaluate_conditional_financial_scenarios(observation(), (row,))[0]
        self.assertEqual(result.gross_price_movement_quote_units, D("-75"))
        self.assertEqual(result.conditional_net_quote_units, D("-75.42"))
        self.assertFalse(result.liquidation_formula_verified)

    def test_positive_and_negative_funding_have_declared_source_sign_and_currency(self):
        paid = funding("5")
        credit = funding("-5")
        paid_provenance = (FundingProvenance(paid, "fixture_source_rates", "SYNTHETIC_QUOTE"),)
        credit_provenance = (FundingProvenance(credit, "fixture_source_rates", "SYNTHETIC_QUOTE"),)
        pay_result = evaluate_conditional_financial_scenarios(observation(), (scenario(events=(paid,), provenance=paid_provenance),))[0]
        credit_result = evaluate_conditional_financial_scenarios(observation(), (scenario(events=(credit,), provenance=credit_provenance),))[0]
        self.assertEqual(pay_result.costs.signed_funding_cost_units, D("0.5"))
        self.assertEqual(credit_result.costs.signed_funding_cost_units, D("-0.5"))

    def test_missing_funding_provenance_and_no_barrier_fail_closed(self):
        with self.assertRaisesRegex(DataValidationError, "matching source"):
            scenario(events=(funding(),))
        with self.assertRaisesRegex(DataValidationError, "no observed barrier"):
            evaluate_conditional_financial_scenarios(observation(ObservationKind.NO_LEVEL_REACHED), (scenario(),))

    def test_invalid_or_inferred_assumptions_are_rejected(self):
        with self.assertRaises(DataValidationError):
            scenario(exit=None)
        with self.assertRaises(DataValidationError):
            scenario(resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS, exit="80", loss="10")
        with self.assertRaises(DataValidationError):
            scenario(resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS, exit=None, loss="0")
        with self.assertRaises(DataValidationError):
            replace(scenario(), quantity_base_units=2.0)
        with self.assertRaises(DataValidationError):
            replace(scenario(), quote_currency="USDT")

    def test_replay_is_deterministic_and_safety_flags_stay_false(self):
        row = scenario()
        first = evaluate_conditional_financial_scenarios(observation(), (row,))
        with localcontext() as context:
            context.prec = 3
            second = evaluate_conditional_financial_scenarios(observation(), (row,))
        self.assertEqual(first, second)
        result = first[0]
        for name in ("intrabar_path_verified", "fill_price_verified", "liquidation_formula_verified", "financial_backtest_approved", "approved_for_live_use", "orders_sent"):
            self.assertIs(getattr(result, name), False)

    def test_module_has_no_network_storage_or_order_surface(self):
        source = (Path(__file__).resolve().parent.parent / "crypto_intelligence_agent" / "synthetic_financial_scenarios.py").read_text()
        for forbidden in ("urllib.request", "requests.", "sqlite3", "create_order(", "send_order(", "socket", "open("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
