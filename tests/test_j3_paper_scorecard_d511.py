"""D511 aggregates priced CLOSED PAPER fills, never unrealized/open PnL."""
import unittest

from crypto_intelligence_agent.j3_paper_scorecard_d511 import paper_closed_scorecard
from crypto_intelligence_agent.market_data import DataValidationError


def position(status, pnl=None, at=1000, opened=500, margin="1", symbol="BTCUSDT"):
    return {
        "symbol": symbol, "side": "LONG", "status": status,
        "opened_at_ms": opened, "as_of_ms": at,
        "requested_margin_quote": margin, "leverage_at_intent": 50,
        "conditional_result_before_funding_quote": pnl,
        "funding_not_verified": True, "native_stop_verified": False,
        "real_orders_sent": False,
    }


class PaperScorecardD511Tests(unittest.TestCase):
    def test_closed_priced_only_and_max_drawdown(self):
        rows = [position("CLOSED", "-3", 3000, symbol="ARB"),
                position("PARTIAL", "5000", 2500, symbol="XRP"),
                position("CLOSED", "1", 2000, symbol="ETH")]
        score = paper_closed_scorecard(rows, total_positions=3, total_closed_positions=2)
        self.assertEqual(score["conditional_closed_net_before_funding_quote"], "-2")
        self.assertEqual(score["max_drawdown_closed_trade_sequence_quote"], "3")
        self.assertEqual(score["priced_closed_win_rate_percent"], "50.00")
        self.assertEqual(score["sample_active_positions"], 1)
        self.assertEqual(score["sample_closed_priced"], 2)
        self.assertTrue(score["window_covers_every_closed_position"])
        self.assertFalse(score["exchange_execution_verified"])
        self.assertFalse(score["funding_settlement_verified"])
        self.assertFalse(score["real_account_pnl_available"])

    def test_missing_older_and_unpriced_are_not_zeroed(self):
        score = paper_closed_scorecard(
            [position("CLOSED"), position("OPEN", "999", 2000)],
            total_positions=4, total_closed_positions=3)
        self.assertIsNone(score["conditional_closed_net_before_funding_quote"])
        self.assertEqual(score["sample_closed_unpriced"], 1)
        self.assertFalse(score["window_covers_every_closed_position"])
        self.assertFalse(score["priced_covers_every_closed_position"])
        self.assertIsNone(score["priced_closed_win_rate_percent"])

    def test_empty_sample_is_unknown_not_zero_profit(self):
        score = paper_closed_scorecard([], total_positions=0, total_closed_positions=0)
        self.assertEqual(score["status"], "no_priced_closed_positions")
        self.assertIsNone(score["conditional_closed_net_before_funding_quote"])
        self.assertFalse(score["priced_covers_every_closed_position"])

    def test_invalid_or_untrusted_financial_snapshot_fails_closed(self):
        base = position("CLOSED", "2")
        for edits in (
            {"conditional_result_before_funding_quote": "NaN"},
            {"conditional_result_before_funding_quote": "Infinity"},
            {"conditional_result_before_funding_quote": 1.2},
            {"requested_margin_quote": "0"},
            {"leverage_at_intent": True},
            {"real_orders_sent": True},
            {"funding_not_verified": False},
            {"native_stop_verified": True},
            {"status": "UNKNOWN"},
            {"as_of_ms": True},
            {"as_of_ms": 400},
        ):
            with self.subTest(edits=edits), self.assertRaises(DataValidationError):
                paper_closed_scorecard([{**base, **edits}],
                                       total_positions=1, total_closed_positions=1)
        with self.assertRaises(DataValidationError):
            paper_closed_scorecard([base], total_positions=1, total_closed_positions=0)
        with self.assertRaises(DataValidationError):
            paper_closed_scorecard([base], total_positions=True, total_closed_positions=1)


if __name__ == "__main__":
    unittest.main()
