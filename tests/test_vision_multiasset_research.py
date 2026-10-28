"""J1/PIT1: bounded synthetic multiasset volume ordering with no lookahead."""
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_multiasset_research import (
    ObservedVisionResearchWindow, rank_observed_vision_quote_volume,
)
from test_offline_vision_series import month

D = Decimal
HOUR = 3_600_000


def group(symbol):
    return (month(2026, 8, symbol), month(2026, 9, symbol))


def set_quote(month_obj, index, amount):
    bars = list(month_obj.candles)
    bars[index] = replace(bars[index], documented_quote_volume=D(amount))
    return replace(month_obj, candles=tuple(bars))


def set_first_24(month_obj, amount):
    bars = list(month_obj.candles)
    for i in range(24):
        bars[i] = replace(bars[i], documented_quote_volume=D(amount))
    return replace(month_obj, candles=tuple(bars))


def query(*groups, decision=None, max_candidates=50):
    cutoff = group("BTCUSDT")[-1].end_open_exclusive_ms + 1000
    return rank_observed_vision_quote_volume(
        tuple(groups), as_of_ms=cutoff,
        decision_at_ms=(groups[0][0].first_open_ms + 24*HOUR
                        if decision is None else decision),
        max_candidates=max_candidates,
    )


class VisionMultiassetResearchTests(unittest.TestCase):
    def test_exact_prior_closed_24_hours_and_ties(self):
        btc, eth = group("BTCUSDT"), group("ETHUSDT")
        changed_btc = (set_first_24(btc[0], "2000"), btc[1])
        changed_eth = (set_first_24(eth[0], "1000"), eth[1])
        x = query(changed_eth, changed_btc)
        self.assertIsInstance(x, ObservedVisionResearchWindow)
        self.assertEqual(x.observed_symbol_count, 2)
        self.assertEqual(x.observed_closed_bars_per_symbol, 24)
        self.assertEqual([i.symbol for i in x.ranked], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual([i.observed_quote_volume_24h_usdt for i in x.ranked],
                         [D("48000"), D("24000")])
        self.assertEqual(x.window_end_open_exclusive_ms, x.decision_at_ms)
        self.assertEqual(x.window_first_open_ms, btc[0].first_open_ms)
        self.assertEqual(query(changed_btc, changed_eth), x)
        ties = query(btc, eth)
        self.assertEqual([i.symbol for i in ties.ranked], ["BTCUSDT", "ETHUSDT"])
        self.assertFalse(ties.sample_is_full_eligible_market)
        for flag in ("historical_top50_verified", "historical_listing_eligibility_verified",
                     "usd_comparable_volume_verified", "source_authenticated",
                     "dataset_rights_authorized_for_live", "canonical_ohlcv_approved",
                     "financial_backtest_approved", "ready_for_trading", "orders_sent"):
            self.assertFalse(getattr(x, flag))

    def test_future_candle_mutation_cannot_change_past_ordering(self):
        btc, eth = group("BTCUSDT"), group("ETHUSDT")
        strong_btc = (set_first_24(btc[0], "200"), btc[1])
        weak_eth = (set_first_24(eth[0], "100"), eth[1])
        first = query(strong_btc, weak_eth)
        mutated_eth = (set_quote(weak_eth[0], 30, "999999999"), weak_eth[1])
        self.assertEqual(first, query(strong_btc, mutated_eth))
        after = query(strong_btc, mutated_eth,
                      decision=btc[0].first_open_ms + 31*HOUR)
        self.assertEqual(after.ranked[0].symbol, "ETHUSDT")
        # Do not include the candle that opens at the decision timestamp.
        immediate = query(strong_btc, mutated_eth,
                          decision=btc[0].first_open_ms + 30*HOUR)
        self.assertEqual(immediate.ranked[0].symbol, "BTCUSDT")

    def test_calendar_boundaries_and_deterministic_precision(self):
        btc, eth = group("BTCUSDT"), group("ETHUSDT")
        at_sep_start = btc[1].first_open_ms
        x = query(btc, eth, decision=at_sep_start)
        self.assertEqual(x.window_first_open_ms, at_sep_start - 24*HOUR)
        self.assertEqual(x.observed_closed_bars_per_symbol, 24)
        for context_precision in (2, 4, 28):
            with localcontext() as ctx:
                ctx.prec = context_precision
                self.assertEqual(query(btc, eth, decision=at_sep_start), x)
        one = query(btc, eth, max_candidates=1)
        self.assertEqual(len(one.ranked), 1)
        self.assertEqual(one.observed_symbol_count, 2)
        self.assertFalse(one.historical_top50_verified)

    def test_refuse_unaligned_duplicate_and_partial_months(self):
        btc, eth = group("BTCUSDT"), group("ETHUSDT")
        invalid = (
            (btc, btc),
            (btc, (month(2026, 7, "ETHUSDT"), month(2026, 8, "ETHUSDT"))),
            (btc, (eth[0],)),
            (btc, (eth[1], eth[0])),
            (btc, (eth[0], eth[0])),
            (btc, (replace(eth[0], candles=eth[0].candles[:-1]), eth[1])),
            (btc, (replace(eth[0], symbol="BTCUSDT"), eth[1])),
        )
        for sample in invalid:
            with self.subTest(sample=str([x[0].archive_name for x in sample])):
                with self.assertRaises(DataValidationError):
                    query(*sample)

    def test_invalid_decisions_inputs_and_tainted_volume(self):
        btc, eth = group("BTCUSDT"), group("ETHUSDT")
        beginning, end = btc[0].first_open_ms, btc[-1].end_open_exclusive_ms
        for t in (beginning, beginning+23*HOUR,
                  beginning+24*HOUR+1, end+HOUR, True, 2.5):
            with self.subTest(t=t), self.assertRaises(DataValidationError):
                query(btc, eth, decision=t)
        for bound in (0, True, 51, 1.2):
            with self.subTest(bound=bound), self.assertRaises(DataValidationError):
                query(btc, eth, max_candidates=bound)
        for value in ("NaN", "Infinity", "-1", "9"*42):
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                query(btc, (set_quote(eth[0], 2, value), eth[1]))
        with self.assertRaises(DataValidationError):
            rank_observed_vision_quote_volume(
                [btc, eth], as_of_ms=end+1000, decision_at_ms=beginning+24*HOUR)
        with self.assertRaises(DataValidationError):
            rank_observed_vision_quote_volume(
                (btc, eth), as_of_ms=end-1, decision_at_ms=beginning+24*HOUR)
        with self.assertRaises(DataValidationError):
            query(btc, eth, group("BNBUSDT"))

    def test_no_network_persistence_or_decision_authority(self):
        btc, eth = group("BTCUSDT"), group("ETHUSDT")
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                a = query(btc, eth)
                self.assertEqual(a, query(btc, eth))
        self.assertEqual(a.ranking_basis,
                         "last_24_fully_closed_1h_quote_volumes_usdt_in_supplied_sample")
        self.assertTrue(a.research_only)


if __name__ == "__main__":
    unittest.main()
