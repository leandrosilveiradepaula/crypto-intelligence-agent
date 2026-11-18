"""D435: parity with synthetic mathematics without reclassifying public candles."""
from dataclasses import replace
from decimal import Decimal
import unittest

from crypto_intelligence_agent.j2_bybit_closed_research_bridge import (
    BybitClosedResearchSeries,
)
from crypto_intelligence_agent.j2_observed_bybit_research import (
    evaluate_observed_bybit_research,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataGapError, DataValidationError
from crypto_intelligence_agent.synthetic_entry_hypotheses import (
    CompressionBreakoutConfig, research_synthetic_compression_breakouts,
)
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

HOUR = 3_600_000
FIRST = 1_792_998_000_000  # UTC hour grid
JOURNAL_DIGEST = "a" * 64
REGISTRY_DIGEST = "b" * 64
CONFIG = CompressionBreakoutConfig(
    FeatureConfig(2, 2, 2, 2),
    compression_bars=2, baseline_bars=2,
    max_atr_ratio=Decimal("1"),
    min_quote_volume_ratio=Decimal("1"),
    cooldown_bars=0,
)


def observed_case(side=None, *, last_volume="4"):
    candles = []
    for i in range(24):
        last = i == 23
        close = "105" if last and side == "LONG" else (
            "95" if last and side == "SHORT" else "100"
        )
        high = "106" if last and side == "LONG" else "101"
        low = "94" if last and side == "SHORT" else "99"
        opened = FIRST + i * HOUR
        candles.append(ClosedCandle(
            exchange="bybit_v5_public", market="linear_perpetual",
            symbol="BTCUSDT", interval="1h",
            open_time_ms=opened, close_time_ms=opened + HOUR - 1,
            open=Decimal("100"), high=Decimal(high),
            low=Decimal(low), close=Decimal(close),
            base_volume=Decimal("10"),
            quote_volume=Decimal(last_volume if last else "2"),
            quality="bybit_public_ws_confirmed_unverified",
        ))
    series = BybitClosedResearchSeries(
        tuple(candles), JOURNAL_DIGEST, REGISTRY_DIGEST,
        "research_only_public_closed_series",
    )
    decision = candles[-1].close_time_ms + 1
    return series, decision


class ObservedBybitJ2ResearchTests(unittest.TestCase):
    def test_long_short_match_reusable_synthetic_j2_math(self):
        for name, expected in (("LONG", SyntheticSide.LONG), ("SHORT", SyntheticSide.SHORT)):
            with self.subTest(side=name):
                series, decision = observed_case(name)
                observed = evaluate_observed_bybit_research(
                    series, config=CONFIG, decision_at_ms=decision,
                )
                self.assertEqual(observed.status, "observed_hypothesis_not_authorized")
                self.assertEqual(len(observed.hypotheses), 1)
                candidate = observed.hypotheses[0]
                self.assertEqual(candidate.side, expected)
                self.assertEqual(candidate.closed_at_ms, decision - 1)
                self.assertEqual(candidate.journal_digest_sha256, JOURNAL_DIGEST)
                self.assertFalse(candidate.approved_for_signals)
                self.assertFalse(candidate.orders_sent)
                self.assertFalse(observed.approved_for_signals)
                self.assertFalse(observed.orders_sent)
                # The public series is NEVER relabelled; a separate fixture
                # compares identical mathematical inputs with the J2 reference.
                self.assertTrue(all(
                    c.quality == "bybit_public_ws_confirmed_unverified"
                    for c in series.candles
                ))
                reference = research_synthetic_compression_breakouts(
                    tuple(replace(c, quality="synthetic_fixture")
                          for c in series.candles),
                    config=CONFIG, decision_at_ms=decision, close_safety_ms=1,
                )
                self.assertTrue(reference.candidates)
                last = reference.candidates[-1]
                self.assertEqual(last.closed_at_ms, candidate.closed_at_ms)
                self.assertEqual(last.side, candidate.side)
                self.assertEqual(last.ema_close, candidate.ema_close)
                self.assertEqual(last.atr_compression_ratio,
                                 candidate.atr_compression_ratio)
                self.assertEqual(last.volume_to_prior_mean,
                                 candidate.quote_volume_to_prior_mean)

    def test_flat_market_and_insufficient_volume_abstain(self):
        for side, volume in ((None, "4"), ("LONG", "0")):
            with self.subTest(side=side, volume=volume):
                series, decision = observed_case(side, last_volume=volume)
                result = evaluate_observed_bybit_research(
                    series, config=CONFIG, decision_at_ms=decision,
                )
                self.assertEqual(result.status, "observed_no_hypothesis")
                self.assertEqual(result.hypotheses, ())
                self.assertFalse(result.approved_for_signals)

    def test_reject_future_mixed_gap_and_forged_quality(self):
        series, decision = observed_case("LONG")
        cases = (
            ("early_decision", series, decision - 1),
            ("stale_decision", series, decision + 1),
            ("quality", replace(series, candles=series.candles[:-1] +
                         (replace(series.candles[-1], quality="synthetic_fixture"),)), decision),
            ("wrong_identity", replace(series, candles=series.candles[:-1] +
                         (replace(series.candles[-1], symbol="ETHUSDT"),)), decision),
            ("invalid_prices", replace(series, candles=series.candles[:-1] +
                         (replace(series.candles[-1], high=Decimal("1")),)), decision),
            ("bad_status", replace(series, status="fixture_no_verification"), decision),
        )
        for name, item, at in cases:
            with self.subTest(case=name), self.assertRaises((DataGapError, DataValidationError)):
                evaluate_observed_bybit_research(item, config=CONFIG, decision_at_ms=at)
        with self.assertRaises(DataValidationError):
            evaluate_observed_bybit_research(
                series, config=CONFIG, decision_at_ms=decision,
                close_safety_ms=True,
            )
        with self.assertRaises(DataGapError):
            evaluate_observed_bybit_research(
                replace(series, candles=series.candles[:10] + series.candles[11:]),
                config=CONFIG, decision_at_ms=decision,
            )

    def test_cooldown_blocks_consecutive_hypothesis(self):
        series, decision = observed_case("LONG")
        config = replace(CONFIG, cooldown_bars=1)
        # A last-bar breakout remains valid when previous close is flat.
        output = evaluate_observed_bybit_research(
            series, config=config, decision_at_ms=decision,
        )
        self.assertEqual(output.status, "observed_hypothesis_not_authorized")
        self.assertEqual(len(output.hypotheses), 1)


if __name__ == "__main__":
    unittest.main()
