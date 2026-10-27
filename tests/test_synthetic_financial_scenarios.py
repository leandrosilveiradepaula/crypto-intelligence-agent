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
    ObservationKind, ResearchDirection, SyntheticBarrier, SyntheticBarrierPlan,
    SyntheticBarrierObservation,
)

D = Decimal
LONG, SHORT = ResearchDirection.LONG, ResearchDirection.SHORT


def observation(kind=ObservationKind.SINGLE_LEVEL_RANGE, levels=None):
    if levels is None:
        if kind is ObservationKind.MULTIPLE_LEVELS_UNORDERED:
            levels = (SyntheticBarrier.TARGET, SyntheticBarrier.STOP)
        elif kind is ObservationKind.NO_LEVEL_REACHED:
            levels = ()
        else:
            levels = (SyntheticBarrier.TARGET,)
    no_hit = kind is ObservationKind.NO_LEVEL_REACHED
    return SyntheticBarrierObservation(
        exchange="synthetic_venue", symbol="BTCUSDT", interval="1h", plan_created_at_ms=1_000,
        as_of_ms=5_000, available_closed_candles=1, examined_closed_candles=1, kind=kind,
        levels_reached=levels, first_candidate_index=None if no_hit else 0,
        first_candidate_open_time_ms=None if no_hit else 2_000,
        first_candidate_close_time_ms=None if no_hit else 4_999,
    )


def barrier_plan(side=LONG, liquidation=False):
    return SyntheticBarrierPlan(
        side=side, hypothetical_entry_price=D("100"),
        stop_level=D("95") if side is LONG else D("110"),
        target_level=D("110") if side is LONG else D("90"),
        plan_created_at_ms=1_000,
        hypothetical_liquidation_level=(D("80") if side is LONG else D("120")) if liquidation else None,
    )


def evaluate(ob, rows, *, side=LONG, liquidation=False):
    return evaluate_conditional_financial_scenarios(
        ob, rows, barrier_plan=barrier_plan(side=side, liquidation=liquidation),
    )


def funding(rate="5"):
    return SyntheticFundingEvent("fixture_funding_a", 2_500, D("1000"), D(rate))


def scenario(*, identity="fixture_financial_a", side=LONG, resolution=ScenarioResolution.EXPLICIT_EXIT,
             entry="100", exit="110", loss=None, events=(), provenance=(), barrier=None):
    if barrier is None:
        barrier = (SyntheticBarrier.HYPOTHETICAL_LIQUIDATION
                   if resolution is ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS else SyntheticBarrier.TARGET)
    return ConditionalFinancialScenario(
        scenario_id=identity, exchange="synthetic_venue", symbol="BTCUSDT", interval="1h", direction=side,
        assumed_barrier=barrier, entry_price=D(entry), quantity_base_units=D("2"), resolution=resolution,
        exit_price=D(exit) if exit is not None else None,
        hypothetical_liquidation_loss_quote_units=D(loss) if loss is not None else None,
        quote_currency="SYNTHETIC_QUOTE",
        costs=SyntheticCostScenario(side, 2_000, 3_000, D(entry)*D("2"),
                                    D(exit)*D("2") if exit is not None else D("220"),
                                    D("10"), D("10"), D("0"), D("0"), events),
        funding_provenance=provenance,
    )


class ConditionalFinancialScenarioTests(unittest.TestCase):
    def test_long_and_short_explicit_prices_use_decimal_and_declared_costs(self):
        long = scenario()
        short = scenario(identity="fixture_financial_b", side=SHORT, entry="100", exit="90")
        long_result = evaluate(observation(), (long,))[0]
        short_result = evaluate(observation(), (short,), side=SHORT)[0]
        self.assertEqual(long_result.gross_price_movement_quote_units, D("20"))
        self.assertEqual(long_result.conditional_net_quote_units, D("19.58"))
        self.assertEqual(short_result.gross_price_movement_quote_units, D("20"))
        self.assertEqual(short_result.conditional_net_quote_units, D("19.62"))

    def test_multiple_intrabar_levels_require_alternative_explicit_branches(self):
        ambiguous = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        with self.assertRaisesRegex(DataValidationError, "alternative"):
            evaluate(ambiguous, (scenario(),))
        exits = (scenario(), scenario(identity="fixture_financial_stop", exit="95",
                                      barrier=SyntheticBarrier.STOP))
        result = evaluate(ambiguous, exits)
        self.assertEqual([item.gross_price_movement_quote_units for item in result], [D("20"), D("-10")])
        self.assertEqual(result[0].ambiguity_branch_count, 2)

    def test_explicit_liquidation_is_a_loss_assumption_not_venue_formula(self):
        row = scenario(resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS, exit=None, loss="75")
        result = evaluate(observation(levels=(SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,)),
                          (row,), liquidation=True)[0]
        self.assertEqual(result.gross_price_movement_quote_units, D("-75"))
        self.assertEqual(result.conditional_net_quote_units, D("-75.42"))
        self.assertFalse(result.liquidation_formula_verified)

    def test_positive_and_negative_funding_have_declared_source_sign_and_currency(self):
        paid = funding("5")
        credit = funding("-5")
        paid_provenance = (FundingProvenance(paid, "fixture_source_rates", "SYNTHETIC_QUOTE"),)
        credit_provenance = (FundingProvenance(credit, "fixture_source_rates", "SYNTHETIC_QUOTE"),)
        pay_result = evaluate(observation(), (scenario(events=(paid,), provenance=paid_provenance),))[0]
        credit_result = evaluate(observation(), (scenario(events=(credit,), provenance=credit_provenance),))[0]
        self.assertEqual(pay_result.costs.signed_funding_cost_units, D("0.5"))
        self.assertEqual(credit_result.costs.signed_funding_cost_units, D("-0.5"))

    def test_missing_funding_provenance_and_no_barrier_fail_closed(self):
        with self.assertRaisesRegex(DataValidationError, "matching source"):
            scenario(events=(funding(),))
        with self.assertRaisesRegex(DataValidationError, "no observed barrier"):
            evaluate(observation(ObservationKind.NO_LEVEL_REACHED), (scenario(),))

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
        first = evaluate(observation(), (row,))
        with localcontext() as context:
            context.prec = 3
            second = evaluate(observation(), (row,))
        self.assertEqual(first, second)
        result = first[0]
        for name in ("intrabar_path_verified", "fill_price_verified", "liquidation_formula_verified", "financial_backtest_approved", "approved_for_live_use", "orders_sent"):
            self.assertIs(getattr(result, name), False)

    def test_fee_notional_and_quantity_must_match_declared_fills(self):
        row = scenario()
        with self.assertRaisesRegex(DataValidationError, "entry cost notional"):
            replace(row, costs=replace(row.costs, entry_hypothetical_notional_quote_units=D("199")))
        with self.assertRaisesRegex(DataValidationError, "exit cost notional"):
            replace(row, costs=replace(row.costs, exit_hypothetical_notional_quote_units=D("219")))
        with self.assertRaises(DataValidationError):
            replace(row, quantity_base_units=D("1e100"))
        with self.assertRaises(DataValidationError):
            replace(row, quantity_base_units=D("0.0000000000000000001"))
        with self.assertRaises(DataValidationError):
            replace(row, quote_currency="SYNTHETIC_")

    def test_ambiguous_branches_must_cover_actual_distinct_levels(self):
        both = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        same_target = (scenario(), scenario(identity="fixture_financial_copy", exit="111"))
        with self.assertRaisesRegex(DataValidationError, "cover"):
            evaluate(both, same_target)
        with self.assertRaisesRegex(DataValidationError, "cover"):
            evaluate(observation(), (scenario(barrier=SyntheticBarrier.STOP),))
        with self.assertRaisesRegex(DataValidationError, "multiple"):
            evaluate(observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED,
                                 levels=(SyntheticBarrier.TARGET,)), (scenario(),))
        with self.assertRaisesRegex(DataValidationError, "sixteen"):
            evaluate(observation(), [scenario(identity=f"fixture_financial_{i}") for i in range(17)])

    def test_binding_to_plan_side_entry_and_timestamps(self):
        row = scenario()
        with self.assertRaisesRegex(DataValidationError, "side/entry"):
            evaluate(observation(), (row,), side=SHORT)
        shifted = replace(row, entry_price=D("101"),
                          costs=replace(row.costs, entry_hypothetical_notional_quote_units=D("202")))
        with self.assertRaisesRegex(DataValidationError, "side/entry"):
            evaluate(observation(), (shifted,))
        with self.assertRaisesRegex(DataValidationError, "outside observed"):
            evaluate(observation(), (replace(row, costs=replace(row.costs, exit_at_ms=9_000)),))
        with self.assertRaisesRegex(DataValidationError, "does not match"):
            evaluate_conditional_financial_scenarios(
                observation(), (row,), barrier_plan=replace(barrier_plan(), plan_created_at_ms=999))
        with self.assertRaisesRegex(DataValidationError, "event timestamp"):
            evaluate(replace(observation(), first_candidate_close_time_ms=1_000), (row,))

    def test_liquidation_requires_matching_reached_level_and_plan(self):
        liq = scenario(resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS,
                       exit=None, loss="75")
        with self.assertRaisesRegex(DataValidationError, "liquidation barrier not declared"):
            evaluate(observation(levels=(SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,)), (liq,))
        with self.assertRaisesRegex(DataValidationError, "cover"):
            evaluate(observation(), (liq,), liquidation=True)
        with self.assertRaisesRegex(DataValidationError, "liquidation loss requires"):
            replace(liq, assumed_barrier=SyntheticBarrier.STOP)
        with self.assertRaisesRegex(DataValidationError, "liquidation barrier needs"):
            replace(scenario(), assumed_barrier=SyntheticBarrier.HYPOTHETICAL_LIQUIDATION)
        with self.assertRaises(DataValidationError):
            replace(liq, hypothetical_liquidation_loss_quote_units=D("1e1000000"))
        with self.assertRaises(DataValidationError):
            replace(liq, hypothetical_liquidation_loss_quote_units=D("0.0000000000000000001"))

    def test_result_records_hypothetical_assumed_barrier(self):
        results = evaluate(observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED),
                           (scenario(), scenario(identity="fixture_financial_stop", exit="95",
                                                 barrier=SyntheticBarrier.STOP)))
        self.assertEqual(tuple(r.assumed_barrier for r in results),
                         (SyntheticBarrier.TARGET, SyntheticBarrier.STOP))
        self.assertTrue(all(not r.financial_backtest_approved for r in results))
        self.assertTrue(all(not r.net_pnl_verified and not r.out_of_sample_results_validated
                            for r in results))

    def test_alternative_exits_must_share_one_economic_entry_basis(self):
        """Changing exposure or entry fees by outcome is not a valid comparison."""
        target = scenario()
        stop = scenario(identity="fixture_financial_stop", exit="95",
                        barrier=SyntheticBarrier.STOP)
        alternate = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        changed_quantity = replace(
            stop, quantity_base_units=D("3"),
            costs=replace(stop.costs,
                          entry_hypothetical_notional_quote_units=D("300"),
                          exit_hypothetical_notional_quote_units=D("285")))
        mutations = (
            ("quote_unit", replace(stop, quote_currency="SYNTHETIC_OTHER")),
            ("quantity", changed_quantity),
            ("entry_time", replace(
                stop, costs=replace(stop.costs, entry_at_ms=2_100))),
            ("entry_fee", replace(
                stop, costs=replace(stop.costs, entry_fee_bps=D("12")))),
            ("entry_slippage", replace(
                stop, costs=replace(stop.costs,
                                    entry_adverse_slippage_bps=D("3")))),
        )
        for name, changed in mutations:
            with self.subTest(name=name), self.assertRaisesRegex(
                DataValidationError, "same position quantity"
            ):
                evaluate(alternate, (target, changed))
        # Reordering alternatives cannot defeat the comparison gate.
        with self.assertRaisesRegex(DataValidationError, "same position quantity"):
            evaluate(alternate, (changed_quantity, target))

    def test_alternative_exits_can_have_different_exit_costs_and_times(self):
        """Exit-specific assumptions remain explicit and branch-dependent."""
        target = scenario()
        stop = scenario(identity="fixture_financial_stop", exit="95",
                        barrier=SyntheticBarrier.STOP)
        changed_exit = replace(
            stop, costs=replace(
                stop.costs, exit_at_ms=3_250, exit_fee_bps=D("15"),
                exit_adverse_slippage_bps=D("7")))
        results = evaluate(observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED),
                           (target, changed_exit))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].assumed_barrier, SyntheticBarrier.TARGET)
        self.assertEqual(results[1].assumed_barrier, SyntheticBarrier.STOP)
        self.assertNotEqual(results[0].conditional_net_quote_units,
                            results[1].conditional_net_quote_units)
        for row in results:
            self.assertEqual(row.ambiguity_branch_count, 2)
            self.assertFalse(row.net_pnl_verified)
            self.assertFalse(row.liquidation_formula_verified)
            self.assertFalse(row.financial_backtest_approved)

    def test_three_way_short_target_stop_liquidation_share_position(self):
        levels = (SyntheticBarrier.TARGET, SyntheticBarrier.STOP,
                  SyntheticBarrier.HYPOTHETICAL_LIQUIDATION)
        alternate = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED,
                                levels=levels)
        target = scenario(identity="fixture_financial_short_target",
                          side=SHORT, exit="90")
        stop = scenario(identity="fixture_financial_short_stop", side=SHORT,
                        exit="110", barrier=SyntheticBarrier.STOP)
        liquidation = scenario(
            identity="fixture_financial_short_liquidation", side=SHORT,
            resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS,
            exit=None, loss="75")
        valid = evaluate(alternate, (target, stop, liquidation),
                         side=SHORT, liquidation=True)
        self.assertEqual(len(valid), 3)
        self.assertTrue(all(r.ambiguity_branch_count == 3 for r in valid))
        self.assertTrue(all(not r.liquidation_formula_verified and
                            not r.financial_backtest_approved for r in valid))
        invalid_liquidation = replace(
            liquidation, quantity_base_units=D("3"),
            costs=replace(liquidation.costs,
                          entry_hypothetical_notional_quote_units=D("300")))
        with self.assertRaisesRegex(DataValidationError, "same position quantity"):
            evaluate(alternate, (target, stop, invalid_liquidation),
                     side=SHORT, liquidation=True)

    def test_shared_pre_exit_funding_schedule_long_short(self):
        """One open position cannot silently drop a prior settlement."""
        event = funding("5")
        provenance = (FundingProvenance(
            event, "fixture_source_rates", "SYNTHETIC_QUOTE"),)
        for side, target_exit, stop_exit in (
            (LONG, "110", "95"), (SHORT, "90", "110"),
        ):
            target = scenario(
                identity="fixture_financial_target", side=side, exit=target_exit,
                events=(event,), provenance=provenance)
            stop = scenario(
                identity="fixture_financial_stop", side=side, exit=stop_exit,
                barrier=SyntheticBarrier.STOP, events=(event,),
                provenance=provenance)
            with self.subTest(side=side):
                observed = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)
                results = evaluate(observed, (target, stop), side=side)
                self.assertEqual(len(results), 2)
                self.assertEqual(
                    results[0].costs.signed_funding_cost_units,
                    results[1].costs.signed_funding_cost_units)
                with self.assertRaisesRegex(DataValidationError,
                                            "share funding event"):
                    evaluate(observed, (target, replace(
                        stop, costs=replace(stop.costs, funding_events=()),
                        funding_provenance=())), side=side)

    def test_pre_exit_funding_identity_rate_time_and_source_are_shared(self):
        event = funding("5")
        common_provenance = (FundingProvenance(
            event, "fixture_source_rates", "SYNTHETIC_QUOTE"),)
        target = scenario(events=(event,), provenance=common_provenance)
        stop = scenario(
            identity="fixture_financial_stop", exit="95",
            barrier=SyntheticBarrier.STOP, events=(event,),
            provenance=common_provenance)
        observed = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        changes = (
            SyntheticFundingEvent(
                "fixture_funding_different", 2_500, D("1000"), D("5")),
            SyntheticFundingEvent(
                "fixture_funding_a", 2_600, D("1000"), D("5")),
            SyntheticFundingEvent(
                "fixture_funding_a", 2_500, D("1000"), D("6")),
        )
        for mutated in changes:
            with self.subTest(event=mutated):
                alternative = replace(
                    stop, costs=replace(stop.costs, funding_events=(mutated,)),
                    funding_provenance=(FundingProvenance(
                        mutated, "fixture_source_rates", "SYNTHETIC_QUOTE"),))
                with self.assertRaisesRegex(DataValidationError,
                                            "share funding event"):
                    evaluate(observed, (target, alternative))
        other_source = replace(
            stop, funding_provenance=(FundingProvenance(
                event, "fixture_source_other", "SYNTHETIC_QUOTE"),))
        with self.assertRaisesRegex(DataValidationError, "share funding event"):
            evaluate(observed, (target, other_source))

    def test_funding_notional_may_vary_by_path_and_later_exit(self):
        original = funding("5")
        changed_notional = SyntheticFundingEvent(
            "fixture_funding_a", 2_500, D("2000"), D("5"))
        target = scenario(
            events=(original,), provenance=(FundingProvenance(
                original, "fixture_source_rates", "SYNTHETIC_QUOTE"),))
        stop = scenario(
            identity="fixture_financial_stop", exit="95",
            barrier=SyntheticBarrier.STOP, events=(changed_notional,),
            provenance=(FundingProvenance(
                changed_notional, "fixture_source_rates", "SYNTHETIC_QUOTE"),))
        observed = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)
        results = evaluate(observed, (target, stop))
        self.assertEqual(results[0].costs.signed_funding_cost_units, D("0.5"))
        self.assertEqual(results[1].costs.signed_funding_cost_units, D("1"))
        self.assertTrue(all(not row.net_pnl_verified for row in results))

        after_earliest_exit = SyntheticFundingEvent(
            "fixture_funding_later", 3_250, D("1000"), D("5"))
        later_stop = replace(
            scenario(identity="fixture_financial_stop", exit="95",
                     barrier=SyntheticBarrier.STOP),
            costs=replace(
                stop.costs, exit_at_ms=3_500,
                funding_events=(after_earliest_exit,)),
            funding_provenance=(FundingProvenance(
                after_earliest_exit, "fixture_source_rates",
                "SYNTHETIC_QUOTE"),))
        # The first branch exits at 3_000; an event at 3_250 only
        # belongs to the branch still holding the hypothetical position.
        self.assertEqual(len(evaluate(observed, (scenario(), later_stop))), 2)

    def test_liquidation_branch_must_retain_prior_funding(self):
        event = funding("5")
        provenance = (FundingProvenance(
            event, "fixture_source_rates", "SYNTHETIC_QUOTE"),)
        target = scenario(
            identity="fixture_financial_short_target", side=SHORT,
            exit="90", events=(event,), provenance=provenance)
        liquidation = scenario(
            identity="fixture_financial_short_liquidation",
            side=SHORT, resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS,
            exit=None, loss="75")
        observed = observation(
            ObservationKind.MULTIPLE_LEVELS_UNORDERED,
            levels=(SyntheticBarrier.TARGET,
                    SyntheticBarrier.HYPOTHETICAL_LIQUIDATION))
        with self.assertRaisesRegex(DataValidationError, "share funding event"):
            evaluate(observed, (target, liquidation),
                     side=SHORT, liquidation=True)
        same_history = replace(
            liquidation, costs=replace(liquidation.costs,
                                       funding_events=(event,)),
            funding_provenance=provenance)
        results = evaluate(
            observed, (target, same_history), side=SHORT, liquidation=True)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(not row.liquidation_formula_verified
                            for row in results))

    def test_funding_at_earliest_exit_instant_remains_conditional(self):
        at_boundary = SyntheticFundingEvent(
            "fixture_funding_boundary", 3_000, D("1000"), D("5"))
        late = scenario(
            identity="fixture_financial_stop", exit="95",
            barrier=SyntheticBarrier.STOP, events=(at_boundary,),
            provenance=(FundingProvenance(
                at_boundary, "fixture_source_rates", "SYNTHETIC_QUOTE"),))
        late = replace(late, costs=replace(late.costs, exit_at_ms=3_500))
        result = evaluate(
            observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED),
            (scenario(), late))
        self.assertEqual(len(result), 2)
        self.assertFalse(result[1].funding_schedule_verified
                         if hasattr(result[1], "funding_schedule_verified")
                         else result[1].costs.funding_schedule_verified)

    def test_one_branch_per_observed_barrier_prevents_duplicate_outcome_weight(self):
        """Extra branches for a reached level must not create fictitious odds."""
        target = scenario(identity="fixture_financial_target")
        extra_target = scenario(identity="fixture_financial_target_copy")
        stop = scenario(identity="fixture_financial_stop", exit="95",
                        barrier=SyntheticBarrier.STOP)
        one = observation()
        both = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED)

        for rows, observed in (
            ((target, extra_target), one),
            ((target, stop, extra_target), both),
            ((extra_target, stop, target), both),
            ((stop, target, replace(
                stop, scenario_id="fixture_financial_stop_copy")), both),
        ):
            with self.subTest(identities=[r.scenario_id for r in rows]):
                with self.assertRaisesRegex(DataValidationError,
                                            "exactly once"):
                    evaluate(observed, rows)

        valid = evaluate(both, (stop, target))
        self.assertEqual(len(valid), 2)
        self.assertEqual({r.assumed_barrier for r in valid},
                         {SyntheticBarrier.STOP, SyntheticBarrier.TARGET})
        self.assertTrue(all(not r.net_pnl_verified for r in valid))

    def test_three_way_liquidation_cannot_duplicate_winning_branch(self):
        target = scenario(identity="fixture_financial_short_target",
                          side=SHORT, exit="90")
        stop = scenario(identity="fixture_financial_short_stop", side=SHORT,
                        exit="110", barrier=SyntheticBarrier.STOP)
        liquid = scenario(
            identity="fixture_financial_short_liquid",
            side=SHORT, resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS,
            exit=None, loss="75")
        duplicate = scenario(identity="fixture_financial_short_target_copy",
                             side=SHORT, exit="90")
        levels = (SyntheticBarrier.TARGET, SyntheticBarrier.STOP,
                  SyntheticBarrier.HYPOTHETICAL_LIQUIDATION)
        observed = observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED,
                               levels=levels)
        with self.assertRaisesRegex(DataValidationError, "exactly once"):
            evaluate(observed, (target, stop, liquid, duplicate),
                     side=SHORT, liquidation=True)
        good = evaluate(observed, (target, stop, liquid),
                        side=SHORT, liquidation=True)
        self.assertEqual(len(good), 3)
        self.assertTrue(all(not r.financial_backtest_approved for r in good))

    def test_entry_must_precede_first_hit_candle_open_for_long_short_and_liquidation(self):
        """No branch may consume a candle range that began before its entry."""
        for side, exit_price in ((LONG, "110"), (SHORT, "90")):
            row = scenario(side=side, exit=exit_price)
            late = replace(row, costs=replace(row.costs, entry_at_ms=2_500))
            with self.subTest(side=side), self.assertRaisesRegex(
                    DataValidationError, "at or before first-hit candle open"):
                evaluate(observation(), (late,), side=side)
            # Both the exact open boundary and an already-open position are valid.
            for entry_time in (1_999, 2_000):
                existing = replace(row, costs=replace(row.costs, entry_at_ms=entry_time))
                self.assertEqual(len(evaluate(observation(), (existing,), side=side)), 1)

        liquid = scenario(resolution=ScenarioResolution.EXPLICIT_LIQUIDATION_LOSS,
                          exit=None, loss="75")
        late_liquid = replace(liquid, costs=replace(liquid.costs, entry_at_ms=2_500))
        with self.assertRaisesRegex(DataValidationError, "at or before first-hit candle open"):
            evaluate(observation(levels=(SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,)),
                     (late_liquid,), liquidation=True)

        target = scenario()
        stop = scenario(identity="fixture_financial_stop", exit="95",
                        barrier=SyntheticBarrier.STOP)
        late_both = tuple(replace(row, costs=replace(row.costs, entry_at_ms=2_500))
                          for row in (target, stop))
        with self.assertRaisesRegex(DataValidationError, "at or before first-hit candle open"):
            evaluate(observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED), late_both)

    def test_same_funding_calendar_is_order_invariant_across_branches(self):
        """Equivalent event ledgers must not fail because of input ordering."""
        earlier = SyntheticFundingEvent(
            "fixture_funding_earlier", 2_200, D("1000"), D("5"))
        later = SyntheticFundingEvent(
            "fixture_funding_later", 2_500, D("1000"), D("-3"))
        provenance = lambda events: tuple(
            FundingProvenance(event, "fixture_source_rates", "SYNTHETIC_QUOTE")
            for event in events)
        for side, target_exit, stop_exit in (
            (LONG, "110", "95"), (SHORT, "90", "110")
        ):
            target_events = (earlier, later)
            stop_events = (later, earlier)
            target = scenario(
                identity="fixture_financial_target", side=side,
                exit=target_exit, events=target_events,
                provenance=provenance(target_events))
            stop = scenario(
                identity="fixture_financial_stop", side=side,
                exit=stop_exit, barrier=SyntheticBarrier.STOP,
                events=stop_events, provenance=provenance(stop_events))
            with self.subTest(side=side):
                result = evaluate(
                    observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED),
                    (target, stop), side=side)
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0].costs.signed_funding_cost_units,
                                 result[1].costs.signed_funding_cost_units)
                changed = SyntheticFundingEvent(
                    "fixture_funding_later", 2_500, D("1000"), D("-4"))
                bad = replace(
                    stop, costs=replace(stop.costs,
                                        funding_events=(changed, earlier)),
                    funding_provenance=provenance((changed, earlier)))
                with self.assertRaisesRegex(DataValidationError,
                                            "share funding event"):
                    evaluate(
                        observation(ObservationKind.MULTIPLE_LEVELS_UNORDERED),
                        (target, bad), side=side)

    def test_module_has_no_network_storage_or_order_surface(self):
        source = (Path(__file__).resolve().parent.parent / "crypto_intelligence_agent" / "synthetic_financial_scenarios.py").read_text()
        for forbidden in ("urllib.request", "requests.", "sqlite3", "create_order(", "send_order(", "socket", "open("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
