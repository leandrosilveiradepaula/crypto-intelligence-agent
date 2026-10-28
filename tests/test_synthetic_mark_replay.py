"""J3/PRE16 mark-vs-trade synthetic liquidation and funding regressions."""
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
from crypto_intelligence_agent.synthetic_mark_replay import (
    SyntheticMarkReplayPlan, SyntheticMarkTick, SyntheticReplayState,
    replay_synthetic_mark_path,
)
D = Decimal
T = 1_792_900_000_000


def plan(side=ResearchDirection.LONG, leverage=50, margin="4"):
    return SyntheticMarkReplayPlan(
        side, T, D("100"), D("2"),
        D("95") if side is ResearchDirection.LONG else D("105"),
        D("105") if side is ResearchDirection.LONG else D("95"),
        SyntheticMarginBasis(D(margin), leverage, D("200"), "SYNTHETIC_USDT"),
        D("50"), D("0"), D("10"), D("10"), D("10"), D("10"),
    )


def tick(mark, trade, at=T + 1_000):
    return SyntheticMarkTick(at, D(mark), D(trade))


class SyntheticMarkReplayTests(unittest.TestCase):
    def test_liquidation_overrides_simultaneous_trade_target_long_and_short(self):
        for side, mark, trade in ((ResearchDirection.LONG, "97", "110"),
                                  (ResearchDirection.SHORT, "103", "90")):
            with self.subTest(side=side):
                result = replay_synthetic_mark_path(plan(side), (tick(mark, trade),),
                                                    as_of_ms=T + 2_000)
                self.assertEqual(result.state, SyntheticReplayState.LIQUIDATION_CONDITION)
                self.assertIsNone(result.conditional_net_quote)
                self.assertIsNone(result.assumed_exit_trade_price)
                self.assertFalse(result.liquidation_formula_verified)
                self.assertEqual(result.first_trigger_at_ms, T + 1_000)

    def test_healthy_target_trade_price_is_not_threshold(self):
        for side, target_price in ((ResearchDirection.LONG, "110"),
                                   (ResearchDirection.SHORT, "90")):
            result = replay_synthetic_mark_path(
                plan(side, leverage=10, margin="20"),
                (tick("100", target_price),), as_of_ms=T + 2_000,
            )
            self.assertEqual(result.state, SyntheticReplayState.CONDITIONAL_TARGET)
            self.assertEqual(result.assumed_exit_trade_price, D(target_price))
            self.assertEqual(result.conditional_net_quote, D("19.16"))
            self.assertFalse(result.fill_price_verified)
            self.assertFalse(result.net_pnl_verified)

    def test_stop_gap_uses_actual_declared_trade_tick(self):
        result = replay_synthetic_mark_path(
            plan(leverage=10, margin="20"), (tick("100", "90"),),
            as_of_ms=T + 2_000,
        )
        self.assertEqual(result.state, SyntheticReplayState.CONDITIONAL_STOP)
        self.assertEqual(result.assumed_exit_trade_price, D("90"))
        self.assertEqual(result.conditional_net_quote, D("-20.76"))

    def test_no_trigger_never_reports_realized_pnl(self):
        path = (tick("101", "101"), tick("100", "100", T + 2_000))
        result = replay_synthetic_mark_path(
            plan(leverage=10, margin="20"), path, as_of_ms=T + 2_000,
        )
        self.assertEqual(result.state, SyntheticReplayState.OPEN_UNRESOLVED)
        self.assertEqual(len(result.observations), 2)
        self.assertIsNone(result.conditional_net_quote)
        self.assertEqual(result.worst_mark_equity_quote, D("19.6"))
        self.assertFalse(result.orders_sent)

    def test_funding_paid_or_credited_changes_mark_equity(self):
        for side, rate in ((ResearchDirection.LONG, "100"),
                           (ResearchDirection.SHORT, "-100")):
            funding = SyntheticFundingEvent(
                "fixture_funding_once", T + 500, D("200"), D(rate),
            )
            result = replay_synthetic_mark_path(
                plan(side, leverage=10, margin="20"),
                (tick("100", "100"),), (funding,), as_of_ms=T + 1_000,
            )
            self.assertEqual(result.observations[0].signed_funding_paid_quote, D("2"))
            self.assertEqual(result.observations[0].equity_at_mark_quote, D("17.6"))
            self.assertEqual(result.state, SyntheticReplayState.OPEN_UNRESOLVED)

    def test_fifty_x_can_liquidate_where_ten_x_survives(self):
        path = (tick("97", "100"),)
        vulnerable = replay_synthetic_mark_path(plan(), path, as_of_ms=T + 1_000)
        safer = replay_synthetic_mark_path(
            plan(leverage=10, margin="20"), path, as_of_ms=T + 1_000,
        )
        self.assertEqual(vulnerable.state, SyntheticReplayState.LIQUIDATION_CONDITION)
        self.assertEqual(safer.state, SyntheticReplayState.OPEN_UNRESOLVED)

    def test_replay_precision_is_context_independent_and_no_network(self):
        path = (tick("100", "106"),)
        expected = replay_synthetic_mark_path(
            plan(leverage=10, margin="20"), path, as_of_ms=T + 1_000,
        )
        for precision in (2, 4, 8, 28):
            with localcontext() as context:
                context.prec = precision
                # Build outside context so fixture validates independently.
                observed = replay_synthetic_mark_path(
                    plan(leverage=10, margin="20"), path, as_of_ms=T + 1_000,
                )
            self.assertEqual(expected, observed)
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            self.assertEqual(expected, replay_synthetic_mark_path(
                plan(leverage=10, margin="20"), path, as_of_ms=T + 1_000,
            ))

    def test_timestamps_invalid_prices_and_funding_boundaries_refused(self):
        valid = plan(leverage=10, margin="20")
        for path, at in (
            ((tick("100", "100"), tick("100", "100")), T + 2_000),
            ((tick("100", "100", T),), T + 1_000),
            ((tick("100", "100", T + 2_000),), T + 1_000),
            ((tick("100", "100", T + 2_000), tick("100", "100")), T + 3_000),
        ):
            with self.subTest(path=path), self.assertRaises(DataValidationError):
                replay_synthetic_mark_path(valid, path, as_of_ms=at)
        with self.assertRaises(DataValidationError):
            SyntheticMarkTick(T + 1_000, D("NaN"), D("100"))
        with self.assertRaises(DataValidationError):
            replace(valid, quantity_base=D("NaN"))
        event = SyntheticFundingEvent("fixture_funding_a", T + 1_000, D("200"), D("5"))
        with self.assertRaises(DataValidationError):
            replay_synthetic_mark_path(valid, (tick("100", "100"),),
                                       (event,), as_of_ms=T + 1_000)
        with self.assertRaises(DataValidationError):
            replay_synthetic_mark_path(valid, (tick("100", "100"),),
                                       (event, event), as_of_ms=T + 1_000)

    def test_funding_only_after_terminal_trigger_is_refused(self):
        event = SyntheticFundingEvent("fixture_funding_late", T + 2_000, D("200"), D("5"))
        with self.assertRaises(DataValidationError):
            replay_synthetic_mark_path(
                plan(leverage=10, margin="20"),
                (tick("100", "110"), tick("100", "100", T + 3_000)),
                (event,), as_of_ms=T + 3_000,
            )


if __name__ == "__main__":
    unittest.main()
