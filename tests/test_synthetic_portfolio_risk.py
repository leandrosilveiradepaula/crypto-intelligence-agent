"""J3/PRE17 synchronized descriptive risk without cross-margin/netting."""
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from crypto_intelligence_agent.synthetic_mark_replay import SyntheticMarkTick, SyntheticReplayState
from crypto_intelligence_agent.synthetic_portfolio_risk import (
    SyntheticPortfolioTrack, replay_synthetic_portfolio_risk,
)
from test_synthetic_mark_replay import T, plan, tick

D = Decimal


def track(pid, side=ResearchDirection.LONG, *, symbol="BTCUSDT", leverage=50,
          marks=("100", "100"), trades=("100", "100")):
    ticks = tuple(tick(mark, trade, T + (i+1)*1000)
                  for i, (mark, trade) in enumerate(zip(marks, trades)))
    return SyntheticPortfolioTrack(
        pid, symbol, plan(side, leverage=leverage,
                          margin="4" if leverage == 50 else "20"),
        ticks,
    )


def audit(a, b):
    return replay_synthetic_portfolio_risk((a, b), as_of_ms=T+2000)


class PortfolioRiskTests(unittest.TestCase):
    def test_concentration_and_signed_exposure_do_not_net_away_gross_risk(self):
        a = track("fixture_long", ResearchDirection.LONG)
        b = track("fixture_short", ResearchDirection.SHORT)
        result = audit(a, b)
        self.assertEqual(result.position_count, 2)
        self.assertEqual(result.symbol_count, 1)
        self.assertEqual(result.max_symbol_entry_concentration_fraction, D(1))
        self.assertEqual(result.snapshots[0].gross_entry_notional_quote, D(400))
        self.assertEqual(result.snapshots[0].signed_mark_notional_quote, D(0))
        self.assertEqual(result.snapshots[0].gross_mark_notional_quote, D(400))
        self.assertEqual(result.snapshots[0].requested_margin_quote, D(8))
        self.assertIsNone(result.first_terminal_at_ms)
        self.assertFalse(result.portfolio_liquidation_verified)
        self.assertFalse(result.net_pnl_verified)
        self.assertFalse(result.orders_sent)
        self.assertEqual(result, audit(b, a))

    def test_one_insolvent_bucket_is_not_rescued_by_winning_hedge(self):
        a = track("fixture_long", ResearchDirection.LONG,
                  marks=("100", "97"), trades=("100", "110"))
        b = track("fixture_short", ResearchDirection.SHORT,
                  marks=("100", "97"), trades=("100", "90"))
        result = audit(a, b)
        last = result.snapshots[-1]
        self.assertEqual(result.first_terminal_at_ms, T + 2000)
        self.assertEqual(result.first_terminal_states, (
            ("fixture_long", SyntheticReplayState.LIQUIDATION_CONDITION),
            ("fixture_short", SyntheticReplayState.CONDITIONAL_TARGET),
        ))
        self.assertTrue(result.first_terminal_includes_liquidation_condition)
        self.assertEqual(last.insolvent_bucket_ids, ("fixture_long",))
        self.assertEqual(last.simultaneous_terminal_ids,
                         ("fixture_long", "fixture_short"))
        self.assertGreater(last.sum_isolated_mark_equity_quote, D(0))
        self.assertEqual(last.adverse_mark_bucket_ids, ("fixture_long",))
        self.assertEqual(last.affected_symbols, ("BTCUSDT",))

    def test_distinct_symbols_reduce_concentration_but_no_correlation_claim(self):
        a = track("fixture_a", symbol="BTCUSDT", marks=("100", "99"))
        b = track("fixture_b", symbol="ETHUSDT", marks=("100", "99"))
        r = audit(a, b)
        self.assertEqual(r.symbol_count, 2)
        self.assertEqual(r.max_symbol_entry_concentration_fraction, D("0.5"))
        self.assertEqual(r.snapshots[-1].adverse_mark_bucket_ids,
                         ("fixture_a", "fixture_b"))
        self.assertEqual(r.snapshots[-1].affected_symbols, ("BTCUSDT", "ETHUSDT"))
        self.assertFalse(r.correlation_estimated)

    def test_10x_survives_mark_shock_that_triggers_50x(self):
        a = track("fixture_fifty", leverage=50, marks=("100", "97"))
        b = track("fixture_ten", leverage=10, marks=("100", "97"))
        r = audit(a, b)
        self.assertEqual(r.snapshots[-1].insolvent_bucket_ids, ("fixture_fifty",))
        self.assertEqual(r.snapshots[-1].requested_margin_quote, D(24))

    def test_invalid_identifiers_clocks_and_quote_fail_closed(self):
        a = track("fixture_a")
        b = track("fixture_b")
        for rows in ((a,), (a, a), (a, replace(b, position_id="fixture_a")),
                     (a, replace(b, ticks=(tick("100", "100", T+1000),
                                           tick("100", "100", T+3000))))):
            with self.subTest(rows=rows), self.assertRaises(DataValidationError):
                replay_synthetic_portfolio_risk(rows, as_of_ms=T+3000)
        with self.assertRaises(DataValidationError):
            SyntheticPortfolioTrack("not_fixture", "BTCUSDT", a.plan, a.ticks)
        with self.assertRaises(DataValidationError):
            replay_synthetic_portfolio_risk((a, replace(b, plan=replace(
                b.plan, entry_at_ms=T+1))), as_of_ms=T+2000)
        with self.assertRaises(DataValidationError):
            replay_synthetic_portfolio_risk((a, replace(b, plan=replace(
                b.plan, margin=replace(b.plan.margin,
                                       quote_currency="SYNTHETIC_USDC")))),
                                       as_of_ms=T+2000)

    def test_context_precision_and_network_independence(self):
        a, b = track("fixture_a"), track("fixture_b", symbol="ETHUSDT")
        original = audit(a, b)
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            for prec in (2, 4, 28):
                with localcontext() as ctx:
                    ctx.prec = prec
                    self.assertEqual(original, audit(a, b))


if __name__ == "__main__":
    unittest.main()
