"""J2/CONFLUENCE1: causal multi-strategy arbitration, no orders or signals."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D, localcontext
import json
import socket
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_btc_breakout_screen import (
    ScreenDisposition,
)
from crypto_intelligence_agent.synthetic_entry_confluence import (
    ConfluenceDisposition, SyntheticConfluenceConfig,
    arbitrate_synthetic_entry_confluence,
    research_synthetic_entry_confluence,
)
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from crypto_intelligence_agent.synthetic_trend_pullback import (
    STRATEGY_ID as PULLBACK_STRATEGY,
    TrendPullbackCandidate, TrendPullbackConfig, TrendPullbackResearch,
)
from test_synthetic_btc_breakout_screen import (
    btc, long, short, candles, config as btc_config, run as btc_screen,
)


def config() -> SyntheticConfluenceConfig:
    screen = btc_config()
    return SyntheticConfluenceConfig(
        screen=screen,
        pullback=TrendPullbackConfig(
            features=screen.breakout.features,
            min_ema_slope_atr=D("0.01"),
            min_volume_ratio=D("0.5"),
            max_trigger_extension_atr=D("10"),
        ),
    )


def research(b=None, assets=None, decision=None):
    btc_bars = btc() if b is None else b
    items = [long()] if assets is None else assets
    at = btc_bars[-1].close_time_ms + 1000 if decision is None else decision
    return research_synthetic_entry_confluence(
        btc_bars, items, config=config(), decision_at_ms=at,
    )


def synthetic_trend(screen, symbol="ETHUSDT", *, side=SyntheticSide.LONG,
                    at=None, earlier=()):
    """Explicit synthetic fixture vote to exercise pure arbitration; no fills."""
    closed = screen.last_closed_at_ms if at is None else at
    votes = tuple(earlier) + (
        TrendPullbackCandidate(
            strategy_id=PULLBACK_STRATEGY,
            exchange=screen.exchange, symbol=symbol, interval=screen.interval,
            side=side, trigger_closed_at_ms=closed,
            earliest_research_at_ms=closed + 1000,
            trigger_close=D(105), trigger_level=D(102),
            ema_at_trigger=D(103), ema_slope_atr=D("0.5"),
            volume_ratio=D(5),
        ),
    )
    return TrendPullbackResearch(
        strategy_id=PULLBACK_STRATEGY, exchange=screen.exchange,
        symbol=symbol, interval=screen.interval,
        evaluated_candle_count=max(6, len(votes)),
        candidates=votes,
    )


def empty_trend(screen, symbol):
    return TrendPullbackResearch(
        PULLBACK_STRATEGY, screen.exchange, symbol, screen.interval, 6, (),
    )


class SyntheticConfluenceTests(unittest.TestCase):
    def test_integrated_pipeline_abstains_without_current_pullback(self):
        out = research()
        self.assertEqual(out.evaluated_asset_count, 1)
        self.assertEqual(out.confluence_symbols, ())
        self.assertEqual(
            out.items[0].disposition,
            ConfluenceDisposition.NO_PULLBACK_CONFIRMATION,
        )
        self.assertEqual(out.items[0].btc_breakout_disposition,
                         ScreenDisposition.RANKED_HYPOTHESIS)
        self.assertIsNone(out.items[0].confluence_research_rank)
        report = out.sanitized_report()
        self.assertEqual(report["confluence_count"], 0)
        self.assertEqual(report["evaluated_asset_count"], 1)
        self.assertFalse(report["approved_for_signals"])
        self.assertFalse(report["approved_for_live_use"])
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["returns_backtested"])
        self.assertFalse(report["probabilities_calibrated"])
        self.assertEqual(report["network_requests"], 0)
        for secret in ("BTCUSDT", "ETHUSDT", "fixture_", "bybit", "100.00"):
            self.assertNotIn(secret, json.dumps(report))

    def test_end_to_end_long_confluence_uses_closed_prior_pullback(self):
        # Concrete causal bar pattern simultaneously triggers PRE2 breakout
        # and the earlier-trend/pullback PRE1; no forged candidate needed.
        series = candles("ETHUSDT", (
            (100, 110, 90, 10),
            (101, 111, 91, 10),
            (103, 104, 102, 10),
            (104, 105, 103, 10),
            (102, 103, 101, 10),
            (107, 108, 106, 50),
        ))
        result = research(assets=[series])
        self.assertEqual(result.confluence_symbols, ("ETHUSDT",))
        self.assertEqual(result.items[0].disposition,
                         ConfluenceDisposition.CONFLUENT_RESEARCH_ONLY)
        self.assertEqual(result.items[0].breakout_side, SyntheticSide.LONG)
        self.assertEqual(result.items[0].pullback_side, SyntheticSide.LONG)
        self.assertEqual(result.items[0].confluence_research_rank, 1)
        self.assertFalse(result.approved_for_signals)

    def test_end_to_end_short_confluence_only_in_btc_downtrend(self):
        series = candles("ETHUSDT", (
            (100, 110, 90, 10),
            (99, 109, 89, 10),
            (97, 98, 96, 10),
            (96, 97, 95, 10),
            (98, 99, 97, 10),
            (93, 94, 92, 50),
        ))
        yes = research(b=btc(98), assets=[series])
        self.assertEqual(yes.confluence_symbols, ("ETHUSDT",))
        self.assertEqual(yes.items[0].breakout_side, SyntheticSide.SHORT)
        self.assertEqual(yes.items[0].pullback_side, SyntheticSide.SHORT)
        veto = research(b=btc(102), assets=[series])
        self.assertEqual(veto.confluence_symbols, ())
        self.assertEqual(veto.items[0].disposition,
                         ConfluenceDisposition.BTC_OR_BREAKOUT_VETO)

    def test_two_agreeing_current_votes_keep_btc_rank_order_and_no_fixed_target(self):
        a = long("ETHUSDT", 105, 50)
        z = long("SOLUSDT", 108, 50)
        screen = btc_screen(assets=[a, z])
        self.assertEqual(screen.ranked_symbols, ("SOLUSDT", "ETHUSDT"))
        agreed = arbitrate_synthetic_entry_confluence(
            screen, (
                synthetic_trend(screen, "ETHUSDT"),
                synthetic_trend(screen, "SOLUSDT"),
            ),
        )
        self.assertEqual(agreed.confluence_symbols, ("SOLUSDT", "ETHUSDT"))
        self.assertEqual(
            [i.confluence_research_rank for i in agreed.items], [2, 1])
        self.assertEqual(
            [i.disposition for i in agreed.items],
            [ConfluenceDisposition.CONFLUENT_RESEARCH_ONLY] * 2,
        )
        self.assertFalse(agreed.approved_for_signals)
        self.assertFalse(agreed.order_capable)
        self.assertFalse(agreed.orders_sent)
        self.assertEqual(
            agreed, arbitrate_synthetic_entry_confluence(
                screen, (
                    synthetic_trend(screen, "SOLUSDT"),
                    synthetic_trend(screen, "ETHUSDT"),
                ),
            ),
        )

    def test_conflicting_or_missing_pullback_cannot_inherit_breakout_rank(self):
        screen = btc_screen(assets=[long("ETHUSDT"), long("SOLUSDT", 108)])
        result = arbitrate_synthetic_entry_confluence(
            screen,
            (
                synthetic_trend(screen, "ETHUSDT", side=SyntheticSide.SHORT),
                empty_trend(screen, "SOLUSDT"),
            ),
        )
        self.assertEqual(result.confluence_symbols, ())
        self.assertEqual(result.items[0].disposition,
                         ConfluenceDisposition.DIRECTION_CONFLICT_ABSTAIN)
        self.assertEqual(result.items[1].disposition,
                         ConfluenceDisposition.NO_PULLBACK_CONFIRMATION)
        self.assertTrue(all(x.confluence_research_rank is None for x in result.items))

    def test_existing_btc_stress_sideways_or_against_regime_veto_even_trend(self):
        cases = (
            btc_screen(b=btc(100)),
            btc_screen(b=btc(98)),
            btc_screen(cfg=btc_config(
                context=btc_config().context.__class__(
                    FeatureConfig(2, 2, 2, 2), 2, D("0.01"), D("0.01")
                )
            )),
        )
        for screen in cases:
            with self.subTest(btc=screen.items[0].disposition):
                result = arbitrate_synthetic_entry_confluence(
                    screen, (synthetic_trend(screen),),
                )
                self.assertEqual(result.confluence_symbols, ())
                self.assertEqual(result.items[0].disposition,
                                 ConfluenceDisposition.BTC_OR_BREAKOUT_VETO)
                self.assertIsNone(result.items[0].confluence_research_rank)

    def test_no_current_breakout_cannot_be_promoted_by_trend_vote(self):
        from dataclasses import replace as dataclass_replace
        a = long()
        last = dataclass_replace(a[-1], open=D(101), high=D(102), close=D(101))
        screen = btc_screen(assets=[a[:-1]+(last,)])
        self.assertIsNone(screen.items[0].candidate)
        result = arbitrate_synthetic_entry_confluence(
            screen, (synthetic_trend(screen),),
        )
        self.assertEqual(result.items[0].disposition,
                         ConfluenceDisposition.BTC_OR_BREAKOUT_VETO)

    def test_old_pullback_candidate_never_becomes_a_latest_vote(self):
        screen = btc_screen()
        old = synthetic_trend(
            screen, at=screen.last_closed_at_ms-3_600_000,
        )
        self.assertEqual(
            arbitrate_synthetic_entry_confluence(
                screen, (old,),
            ).items[0].disposition,
            ConfluenceDisposition.NO_PULLBACK_CONFIRMATION,
        )

    def test_screener_and_pullback_inputs_must_cover_identical_assets(self):
        screen = btc_screen(assets=[long("ETHUSDT"),long("SOLUSDT",108)])
        a = synthetic_trend(screen, "ETHUSDT")
        b = synthetic_trend(screen, "SOLUSDT")
        for trends in (
            (a,), (a, a), (a, replace(b, symbol="OTHERUSDT")),
            [a, b], (a, "not a trend"),
        ):
            with self.subTest(case=str(trends)[:55]):
                with self.assertRaises(DataValidationError):
                    arbitrate_synthetic_entry_confluence(screen, trends)

    def test_reject_forged_screen_rank_current_bar_and_btc_context(self):
        screen = btc_screen()
        trend = synthetic_trend(screen)
        item = screen.items[0]
        cases = (
            replace(screen, ranked_symbols=("OTHERSYMBOL",)),
            replace(screen, items=(replace(item, rank=2),)),
            replace(screen, items=(item,item)),
            replace(screen, decision_at_ms=screen.last_closed_at_ms),
            replace(screen, items=(replace(
                item, context=replace(item.context, btc_symbol="ETHUSDT")
            ),)),
            replace(screen, items=(replace(
                item, context=replace(
                    item.context, decision_at_ms=screen.decision_at_ms+1,
                )
            ),)),
            replace(screen, items=(replace(
                item, candidate=replace(item.candidate, closed_at_ms=screen.last_closed_at_ms-1)
            ),)),
        )
        for source in cases:
            with self.subTest(item=str(source)[:80]):
                with self.assertRaises(DataValidationError):
                    arbitrate_synthetic_entry_confluence(source, (trend,))

    def test_reject_future_duplicate_and_cross_venue_trend_votes(self):
        screen = btc_screen()
        original = synthetic_trend(screen)
        candidate = original.candidates[0]
        for trend in (
            replace(original, exchange="another_venue"),
            replace(original, strategy_id="different_strategy"),
            replace(original, interval="4h"),
            replace(original, candidates=(
                replace(candidate, trigger_closed_at_ms=screen.last_closed_at_ms+1,
                        earliest_research_at_ms=screen.decision_at_ms+2000),
            )),
            replace(original, candidates=(candidate, candidate)),
            replace(original, candidates=(
                replace(candidate, side="LONG"),
            )),
        ):
            with self.subTest(trend=str(trend)[:75]):
                with self.assertRaises(DataValidationError):
                    arbitrate_synthetic_entry_confluence(screen, (trend,))

    def test_incompatible_feature_config_rejected_without_recomputing(self):
        bad = TrendPullbackConfig(
            features=FeatureConfig(3, 2, 2, 2),
            min_ema_slope_atr=D("0.01"),
            min_volume_ratio=D("0.5"),
            max_trigger_extension_atr=D("10"),
        )
        with self.assertRaises(DataValidationError):
            SyntheticConfluenceConfig(btc_config(), bad)
        with self.assertRaises(DataValidationError):
            research_synthetic_entry_confluence(
                btc(), [long()], config="fake",
                decision_at_ms=btc()[-1].close_time_ms+1000,
            )

    def test_live_quality_future_candles_and_mismatched_venue_abstain(self):
        a = long()
        latest = a[-1].close_time_ms
        for bars in (
            a[:-1]+(replace(a[-1], quality="venue_verified"),),
            a[:-1]+(replace(a[-1], exchange="different_venue"),),
            a[:-1]+(replace(a[-1], open_time_ms=a[-1].open_time_ms+3600000,
                             close_time_ms=a[-1].close_time_ms+3600000),),
        ):
            with self.subTest(bars=bars[-1]):
                with self.assertRaises(DataValidationError):
                    research(assets=[bars])
        with self.assertRaises(DataValidationError):
            research(decision=latest+999)

    def test_context_independence_and_explicit_network_prohibition(self):
        expected = research(assets=[long("ETHUSDT"), long("SOLUSDT",108)])
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")), patch(
            "urllib.request.urlopen", side_effect=AssertionError("http")
        ):
            for precision in (3, 6, 16, 28):
                with localcontext() as context:
                    context.prec = precision
                    observed = research(assets=[long("SOLUSDT",108),long("ETHUSDT")])
                self.assertEqual(expected, observed)
        self.assertEqual(expected.sanitized_report()["network_requests"], 0)


if __name__ == "__main__":
    unittest.main()
