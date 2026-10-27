"""J3/#208: adversarial LONG/SHORT liquidation ordering remains UNVERIFIED.

OHLC can prove threshold contact only, never execution priority, liquidation
formula, a fill, realized PnL or suitability of 50x. Fixtures ONLY.
"""
from __future__ import annotations

from decimal import Decimal as D
import unittest

from crypto_intelligence_agent.synthetic_intrabar_barriers import (
    ObservationKind, ResearchDirection, SyntheticBarrier,
)
from test_synthetic_intrabar_barriers import assess, candle, plan


class IntrabarLiquidationOrderingRegressions(unittest.TestCase):
    def test_long_high_first_vs_low_first_cannot_be_inferred(self):
        # Exactly the same OHLC is consistent with both intrabar paths.
        p = plan(liquidation=D("97"))
        for closing in ("98", "102", "108"):
            with self.subTest(close=closing):
                result = assess((candle(opening="100", high="112",
                                        low="94", close=closing),), p=p)
                self.assertEqual(result.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
                self.assertEqual(result.levels_reached, (
                    SyntheticBarrier.STOP, SyntheticBarrier.TARGET,
                    SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,
                ))
                self.assertFalse(result.intrabar_path_verified)
                self.assertFalse(result.fill_price_verified)
                self.assertFalse(result.liquidation_formula_verified)
                self.assertFalse(result.profitable_trade_verified)
                self.assertFalse(result.financial_backtest_approved)

    def test_short_high_first_vs_low_first_cannot_be_inferred(self):
        p = plan(side=ResearchDirection.SHORT, stop=D("105"),
                 target=D("90"), liquidation=D("103"))
        for closing in ("92", "101", "108"):
            with self.subTest(close=closing):
                result = assess((candle(opening="100", high="108",
                                        low="88", close=closing),), p=p)
                self.assertEqual(result.kind, ObservationKind.MULTIPLE_LEVELS_UNORDERED)
                self.assertEqual(result.levels_reached, (
                    SyntheticBarrier.STOP, SyntheticBarrier.TARGET,
                    SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,
                ))
                self.assertFalse(result.intrabar_path_verified)
                self.assertFalse(result.liquidation_formula_verified)
                self.assertFalse(result.financial_backtest_approved)

    def test_long_gap_past_liquidation_and_stop_cannot_claim_priority(self):
        p = plan(liquidation=D("97"))
        result = assess((candle(opening="93", high="113",
                                low="91", close="110"),), p=p)
        self.assertEqual(result.kind, ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
        self.assertEqual(result.levels_reached, (
            SyntheticBarrier.STOP, SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,
        ))
        self.assertFalse(result.fill_price_verified)
        self.assertFalse(result.liquidation_formula_verified)
        self.assertFalse(result.financial_backtest_approved)

    def test_short_gap_past_liquidation_and_stop_cannot_claim_priority(self):
        p = plan(side=ResearchDirection.SHORT, stop=D("105"),
                 target=D("90"), liquidation=D("103"))
        result = assess((candle(opening="107", high="115",
                                low="88", close="92"),), p=p)
        self.assertEqual(result.kind, ObservationKind.OPEN_AT_OR_BEYOND_LEVEL)
        self.assertEqual(result.levels_reached, (
            SyntheticBarrier.STOP, SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,
        ))
        self.assertFalse(result.intrabar_path_verified)
        self.assertFalse(result.liquidation_formula_verified)
        self.assertFalse(result.approved_for_live_use)

    def test_exact_liquidation_threshold_still_only_observation(self):
        for p, row in (
            (plan(liquidation=D("97")),
             candle(opening="100", high="109", low="97", close="100")),
            (plan(side=ResearchDirection.SHORT, stop=D("105"),
                  target=D("90"), liquidation=D("103")),
             candle(opening="100", high="103", low="91", close="99")),
        ):
            with self.subTest(side=p.side):
                result = assess((row,), p=p)
                self.assertEqual(result.kind, ObservationKind.SINGLE_LEVEL_RANGE)
                self.assertEqual(result.levels_reached,
                                 (SyntheticBarrier.HYPOTHETICAL_LIQUIDATION,))
                self.assertFalse(result.liquidation_formula_verified)
                self.assertFalse(result.fill_price_verified)
                self.assertFalse(result.orders_sent)


if __name__ == "__main__":
    unittest.main()
