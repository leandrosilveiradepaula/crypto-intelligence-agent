"""J2/PRE4: offline numeric, temporal, batch and no-trade regressions."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import MARKET, ClosedCandle, DataGapError, DataValidationError
from crypto_intelligence_agent.synthetic_btc_relative_regime import BtcRelativeConfig
from crypto_intelligence_agent.synthetic_btc_breakout_screen import (
    ScreenDisposition, SyntheticScreenConfig, screen_synthetic_btc_breakouts,
)
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig

D = Decimal
HOUR = 3_600_000
START = 10 * HOUR

def candles(symbol, prices, *, venue="fixture", first=0):
    out = []
    for i, (price, high, low, quote) in enumerate(prices):
        out.append(ClosedCandle(
            exchange=venue, market=MARKET, symbol=symbol, interval="1h",
            open_time_ms=START+(i+first)*HOUR,
            close_time_ms=START+(i+first+1)*HOUR-1,
            open=D(price), high=D(high), low=D(low), close=D(price),
            base_volume=D(1), quote_volume=D(quote), quality="synthetic_fixture",
        ))
    return tuple(out)

def btc(last=102):
    return candles("BTCUSDT", [(100,101,99,10)]*5+[(last, max(101,last+1),min(99,last-1),10)])

def long(symbol="ETHUSDT", last=105, volume=50):
    return candles(symbol, [
        (100,110,90,10),(101,111,91,10),(101,102,100,10),
        (101,102,100,10),(101,102,100,10),
        (last,max(103,last+1),101,volume),
    ])

def short(symbol="ETHUSDT", last=95, volume=50):
    return candles(symbol,[
        (100,110,90,10),(99,109,89,10),(99,100,98,10),
        (99,100,98,10),(99,100,98,10),
        (last,99,min(94,last-1),volume),
    ])

def config(**kwargs):
    features=FeatureConfig(2,2,2,2)
    args=dict(
        breakout=CompressionBreakoutConfig(features,2,2,D("0.6"),D("2"),0),
        context=BtcRelativeConfig(features,2,D("0.01"),D("0.5")),
        min_absolute_relative_strength=D("0.001"),
    )
    args.update(kwargs)
    return SyntheticScreenConfig(**args)

def run(b=None, assets=None, cfg=None, decision=None):
    b=btc() if b is None else b
    assets=[long()] if assets is None else assets
    t=b[-1].close_time_ms+1000 if decision is None else decision
    return screen_synthetic_btc_breakouts(
        b, assets, config=config() if cfg is None else cfg, decision_at_ms=t
    )

class BtcBreakoutScreenTests(unittest.TestCase):
    def test_two_long_assets_order_invariance_and_exact_ranks(self):
        a=long("ETHUSDT",105,50)
        z=long("SOLUSDT",108,50)
        r=run(assets=[a,z])
        self.assertEqual(r.ranked_symbols,("SOLUSDT","ETHUSDT"))
        self.assertEqual([x.symbol for x in r.items],["ETHUSDT","SOLUSDT"])
        self.assertEqual([x.rank for x in r.items],[2,1])
        self.assertTrue(all(x.disposition==ScreenDisposition.RANKED_HYPOTHESIS for x in r.items))
        self.assertEqual(run(assets=[z,a]),r)
        self.assertFalse(r.approved_for_live_use)
        self.assertFalse(r.approved_for_signals)
        self.assertFalse(r.order_capable)
        self.assertFalse(r.orders_sent)
        self.assertFalse(hasattr(r,"submit_order"))
        with self.assertRaises(FrozenInstanceError):
            r.items[0].rank=99
        with localcontext() as ctx:
            ctx.prec=50
            # SOL outperforms ETH at same UTC endpoints, relative to same BTC baseline.
            self.assertGreater(r.items[1].context.relative_strength,
                               r.items[0].context.relative_strength)

    def test_short_undershoots_btc_with_rank(self):
        r=run(b=btc(98),assets=[short("ETHUSDT",95),short("SOLUSDT",94)])
        self.assertEqual(r.ranked_symbols,("SOLUSDT","ETHUSDT"))
        self.assertTrue(all(x.rank is not None for x in r.items))

    def test_explicit_abstentions_and_never_promote_old_breakout(self):
        sideways=run(b=btc(100))
        self.assertEqual(sideways.items[0].disposition,ScreenDisposition.BTC_SIDEWAYS)
        stress=run(cfg=config(context=BtcRelativeConfig(FeatureConfig(2,2,2,2),2,D("0.01"),D("0.01"))))
        self.assertEqual(stress.items[0].disposition,ScreenDisposition.BTC_VOLATILITY_STRESS)
        against=run(b=btc(98))
        self.assertEqual(against.items[0].disposition,ScreenDisposition.AGAINST_BTC_REGIME)
        weak=run(cfg=config(min_absolute_relative_strength=D("0.2")))
        self.assertEqual(weak.items[0].disposition,ScreenDisposition.WEAK_RELATIVE_STRENGTH)
        insufficient=run(cfg=config(context=BtcRelativeConfig(FeatureConfig(2,2,2,2),6,D("0.01"),D("0.5"))))
        self.assertEqual(insufficient.items[0].disposition,ScreenDisposition.INSUFFICIENT_CONTEXT)
        no_break=long()
        no_break=no_break[:-1]+(replace(no_break[-1],open=D(101),high=D(102),close=D(101)),)
        self.assertEqual(run(assets=[no_break]).items[0].disposition,ScreenDisposition.NO_CURRENT_BREAKOUT)
        self.assertFalse(any(x.rank for x in (sideways.items[0], stress.items[0], against.items[0],weak.items[0],insufficient.items[0])))

    def test_previously_emitted_breakout_never_promoted(self):
        # PRE2 could emit i5, but latest i6 lacks a new breakout.
        old=long()
        newer=replace(old[-1],open=D(105),high=D(106),low=D(104),close=D(105),
                      open_time_ms=old[-1].open_time_ms+HOUR,
                      close_time_ms=old[-1].close_time_ms+HOUR)
        asset=old+(newer,)
        benchmark=btc()+(replace(btc()[-1],
                            open_time_ms=btc()[-1].open_time_ms+HOUR,
                            close_time_ms=btc()[-1].close_time_ms+HOUR),)
        result=run(b=benchmark,assets=[asset])
        self.assertEqual(result.items[0].disposition,ScreenDisposition.NO_CURRENT_BREAKOUT)

    def test_reject_duplicate_bad_venue_stale_btc_and_future(self):
        b=btc();a=long()
        with self.assertRaisesRegex(DataValidationError,"duplicate"):
            run(assets=[a,a])
        with self.assertRaises(DataValidationError):
            run(assets=[a,tuple(replace(c,exchange="other") for c in a)])
        with self.assertRaises(DataValidationError):
            run(b=b[:-1],assets=[a],decision=a[-1].close_time_ms+1000)
        with self.assertRaises(DataValidationError):
            run(assets=[a],decision=a[-1].close_time_ms+999)
        with self.assertRaises(DataGapError):
            run(assets=[a[:2]+a[3:]])
        with self.assertRaises(DataValidationError):
            run(assets=[a[:-1]+(replace(a[-1],close=D("NaN")),)])
        with self.assertRaises(DataValidationError):
            run(assets=[a[:-1]+(replace(a[-1],close=0.5),)])
        with self.assertRaises(DataValidationError):
            run(assets=[a[:-1]+(replace(a[-1],quality="verified_live"),)])
        with self.assertRaises(DataValidationError):
            run(assets=[a[:-1]+(replace(a[-1],symbol="BTCUSDT"),)])

    def test_config_bounded_and_no_fixed_number_of_positions(self):
        for bad in [
            dict(breakout=None),dict(context=None),
            dict(min_absolute_relative_strength=D(-1)),
            dict(min_absolute_relative_strength=D("NaN")),
            dict(min_absolute_relative_strength=0.02),
            dict(min_absolute_relative_strength=D("1.1")),
            dict(context=BtcRelativeConfig(FeatureConfig(3,2,2,2),2,D("0.01"),D("0.5"))),
        ]:
            with self.subTest(bad=bad),self.assertRaises(DataValidationError):
                config(**bad)
        with self.assertRaises(DataValidationError):
            run(assets=[])
        with self.assertRaises(DataValidationError):
            run(assets=[long()]*1001)
        r=run(assets=[long("ETHUSDT"),long("SOLUSDT")])
        self.assertEqual(len(r.ranked_symbols),2)

    def test_prefix_and_network_independence(self):
        r=run()
        b=btc();a=long()
        with patch("urllib.request.urlopen",side_effect=AssertionError("network")):
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                with localcontext() as ctx:
                    ctx.prec=6
                    self.assertEqual(run(),r)
        future=replace(b[-1],open_time_ms=b[-1].open_time_ms+HOUR,
                       close_time_ms=b[-1].close_time_ms+HOUR,close=D(1000),
                       open=D(1000),high=D(1001),low=D(999))
        with self.assertRaises(DataValidationError):
            run(b=b+(future,),assets=[a],decision=r.decision_at_ms)
        self.assertEqual(run(b=b,assets=[a],decision=r.decision_at_ms),r)

if __name__=="__main__":
    unittest.main()
