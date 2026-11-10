"""J2/PRE5 reproducible as-of membership, digest and no-future offline tests."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import (
    MARKET, ClosedCandle, DataGapError, DataValidationError,
)
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_btc_relative_regime import BtcRelativeConfig
from crypto_intelligence_agent.synthetic_btc_breakout_screen import SyntheticScreenConfig
from crypto_intelligence_agent.synthetic_btc_snapshot_replay import (
    MAX_REPLAY_SNAPSHOTS, SyntheticUniverseAtClose,
    replay_synthetic_btc_universe,
)

D = Decimal
H = 3_600_000
START = 10 * H


def candles(symbol, values, *, venue="fixture"):
    output = []
    for i, (close, high, low, volume) in enumerate(values):
        output.append(ClosedCandle(
            exchange=venue, market=MARKET, symbol=symbol, interval="1h",
            open_time_ms=START+i*H, close_time_ms=START+(i+1)*H-1,
            open=D(close), high=D(high), low=D(low), close=D(close),
            base_volume=D(1), quote_volume=D(volume), quality="synthetic_fixture",
        ))
    return tuple(output)


def fixture():
    b = candles("BTCUSDT", [(100, 101, 99, 10)]*5 + [
        (102, 103, 99, 10), (103, 104, 101, 10),
    ])
    eth = candles("ETHUSDT", [
        (100,110,90,10),(101,111,91,10),(101,102,100,10),
        (101,102,100,10),(101,102,100,10),
        (105,106,101,50),(105,106,104,10),
    ])
    sol = candles("SOLUSDT", [
        (100,110,90,10),(101,111,91,10),(101,102,100,10),
        (101,102,100,10),(101,102,100,10),
        (101,102,100,10),(108,109,101,50),
    ])
    return b, {"ETHUSDT": eth, "SOLUSDT": sol}


def config():
    f = FeatureConfig(2,2,2,2)
    return SyntheticScreenConfig(
        breakout=CompressionBreakoutConfig(f,2,2,D("0.6"),D("2"),0),
        context=BtcRelativeConfig(f,2,D("0.01"),D("0.5")),
        min_absolute_relative_strength=D("0.001"),
    )


def snapshots(b):
    return (
        SyntheticUniverseAtClose(b[5].close_time_ms,b[5].close_time_ms+1000,
                                 ("ETHUSDT",)),
        SyntheticUniverseAtClose(b[6].close_time_ms,b[6].close_time_ms+1000,
                                 ("ETHUSDT","SOLUSDT")),
    )


def run(b=None,assets=None,snaps=None,cutoff=None):
    orig_b, orig_assets = fixture()
    b = orig_b if b is None else b
    assets = orig_assets if assets is None else assets
    snaps = snapshots(orig_b) if snaps is None else snaps
    as_of = orig_b[6].close_time_ms+1000 if cutoff is None else cutoff
    return replay_synthetic_btc_universe(
        b,assets,snaps,config=config(),as_of_ms=as_of
    )


class SnapshotReplayTests(unittest.TestCase):
    def test_reference_membership_ranking_and_replay_digest(self):
        out = run()
        self.assertEqual(len(out.rows),2)
        self.assertEqual(out.rows[0].members,("ETHUSDT",))
        self.assertEqual(out.rows[0].ranked_symbols,("ETHUSDT",))
        self.assertEqual(out.rows[1].members,("ETHUSDT","SOLUSDT"))
        self.assertEqual(out.rows[1].ranked_symbols,("SOLUSDT",))
        self.assertEqual(out.rows[1].dispositions,(
            ("ETHUSDT","no_current_breakout"),
            ("SOLUSDT","ranked_hypothesis"),
        ))
        self.assertEqual(out.rows[-1].digest_sha256,out.replay_digest_sha256)
        self.assertEqual(len(out.replay_digest_sha256),64)
        self.assertFalse(out.approved_for_live_use)
        self.assertFalse(out.approved_for_signals)
        self.assertFalse(out.order_capable)
        self.assertFalse(out.orders_sent)
        self.assertFalse(hasattr(out,"pnl"))
        with self.assertRaises(FrozenInstanceError):
            out.rows[0].members=()

    def test_past_decision_invariant_to_future_values_and_order_of_asset_mapping(self):
        b,assets=fixture()
        baseline=run()
        altered_b=b[:-1]+(replace(b[-1],open=D(990),high=D(999),
                                   low=D(980),close=D(998)),)
        altered_sol=assets["SOLUSDT"][:-1]+(
            replace(assets["SOLUSDT"][-1],open=D(90),high=D(90),
                    low=D(89),close=D(90)),)
        alt_assets={"SOLUSDT":altered_sol,"ETHUSDT":assets["ETHUSDT"]}
        alt=run(b=altered_b,assets=alt_assets)
        self.assertEqual(alt.rows[0],baseline.rows[0])
        self.assertNotEqual(alt.replay_digest_sha256,baseline.replay_digest_sha256)
        perm=run(assets={"SOLUSDT":assets["SOLUSDT"],"ETHUSDT":assets["ETHUSDT"]})
        self.assertEqual(perm,baseline)
        first=run(snaps=snapshots(b)[:1],cutoff=b[5].close_time_ms+1000)
        self.assertEqual(first.rows[0],baseline.rows[0])
        self.assertEqual(first.replay_digest_sha256,baseline.rows[0].digest_sha256)

    def test_late_membership_cannot_receive_prelisting_breakout(self):
        b,assets=fixture()
        later = (snapshots(b)[1],)
        result=run(snaps=later)
        self.assertEqual(result.rows[0].ranked_symbols,("SOLUSDT",))
        self.assertNotIn("ETHUSDT",result.rows[0].ranked_symbols)

    def test_reject_noncausal_snapshots_and_missing_members(self):
        b,assets=fixture()
        s=snapshots(b)
        bads=[
            (s[1],s[0]),
            (s[0],s[0]),
            (s[0],replace(s[1],closed_at_ms=s[1].closed_at_ms+H)),
            (replace(s[0],recorded_at_ms=s[0].closed_at_ms),s[1]),
            (s[0],replace(s[1],recorded_at_ms=s[0].recorded_at_ms)),
            (s[0],replace(s[1],members=("ETHUSDT","ETHUSDT"))),
            (s[0],replace(s[1],members=("SOLUSDT","ETHUSDT"))),
            (s[0],replace(s[1],members=("BTCUSDT",))),
            (s[0],replace(s[1],members=("DOGEUSDT",))),
        ]
        for item in bads:
            with self.subTest(item=item),self.assertRaises(DataValidationError):
                run(snaps=item)
        with self.assertRaises(DataValidationError):
            run(cutoff=s[-1].recorded_at_ms-1)
        with self.assertRaises(DataValidationError):
            run(snaps=())
        with self.assertRaises(DataValidationError):
            run(snaps=(s[0],)*(MAX_REPLAY_SNAPSHOTS+1))
        with self.assertRaises(DataValidationError):
            run(snaps=s,assets={"ETHUSDT":assets["ETHUSDT"]})

    def test_no_forward_fill_btc_stale_and_asset_missing_latest_bar(self):
        b,assets=fixture()
        with self.assertRaises(DataValidationError):
            run(b=b[:-1])
        with self.assertRaises(DataValidationError):
            run(assets={"ETHUSDT":assets["ETHUSDT"],
                        "SOLUSDT":assets["SOLUSDT"][:-1]})
        with self.assertRaises(DataGapError):
            run(b=b[:2]+b[3:])
        bad_b=b[:-1]+(replace(b[-1],quality="real"),)
        with self.assertRaises(DataValidationError):
            run(b=bad_b)
        with self.assertRaises(DataValidationError):
            run(assets={**assets,"SOLUSDT":tuple(replace(c,exchange="other")
                                                 for c in assets["SOLUSDT"])})
        with self.assertRaises(DataValidationError):
            run(assets={**assets,"SOLUSDT":tuple(replace(c,close=D("NaN"))
                                                 for c in assets["SOLUSDT"])})

    def test_no_future_decision_and_no_network_or_order(self):
        b,assets=fixture()
        prior=run(snaps=snapshots(b)[:1],cutoff=b[5].close_time_ms+1000)
        with self.assertRaises(DataValidationError):
            run(snaps=snapshots(b)[:1],cutoff=b[5].close_time_ms+999)
        next_bar=replace(b[-1],open_time_ms=b[-1].open_time_ms+H,
                         close_time_ms=b[-1].close_time_ms+H,
                         open=D(999),high=D(1000),low=D(998),close=D(999))
        extended_b=b+(next_bar,)
        with patch("urllib.request.urlopen",side_effect=AssertionError("network")):
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                with localcontext() as ctx:
                    ctx.prec=6
                    self.assertEqual(
                        run(b=extended_b,snaps=snapshots(b)[:1],
                            cutoff=b[5].close_time_ms+1000),prior
                    )


if __name__=="__main__":
    unittest.main()
