"""J3 #369: offline PIT tiers, mark/trade separation and funding chronology."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_risk_tiers import (
    SyntheticMaintenanceTier, SyntheticRiskSnapshot, maintenance_for_mark,
)
from crypto_intelligence_agent.synthetic_mark_replay import (
    SyntheticMarkTick, SyntheticReplayState, replay_synthetic_mark_path,
)
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from test_synthetic_mark_replay import plan, tick, T
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection


def tier(lo, hi, rate, deduction="0"):
    return SyntheticMaintenanceTier(
        D(lo), None if hi is None else D(hi), D(rate), D(deduction))


def snapshot(*, effective=T-1000, observed=T-2000, version="fixture_v1",
             tiers=None, instrument="fixture_synthetic_usdt"):
    return SyntheticRiskSnapshot(
        instrument, version, observed, effective, tiers or (
            tier("0","200","50"),tier("200",None,"100","1")))


def replay(snapshots, ticks, *, direction=ResearchDirection.LONG, leverage=10,
           margin="20", max_gap=3000, age=30000, funding=()):
    return replay_synthetic_mark_path(
        plan(direction,leverage=leverage,margin=margin),ticks,funding,
        as_of_ms=ticks[-1].at_ms,
        risk_snapshots=tuple(snapshots),max_tick_gap_ms=max_gap,
        max_risk_snapshot_age_ms=age)


class TieredMarkReplayTests(unittest.TestCase):
    def test_boundary_continuity_and_mark_notional(self):
        x=snapshot()
        self.assertEqual(maintenance_for_mark(x,mark_notional_quote=D("199.99"),
                                close_reserve_quote=D("0")),D("0.99995"))
        self.assertEqual(maintenance_for_mark(x,mark_notional_quote=D("200"),
                                close_reserve_quote=D("0")),D("1"))
        self.assertEqual(maintenance_for_mark(x,mark_notional_quote=D("201"),
                                close_reserve_quote=D("0")),D("1.01"))

    def test_trade_target_cannot_override_mark_liquidation(self):
        high=snapshot(tiers=(tier("0",None,"9000"),))
        for side,mark,trade in (
            (ResearchDirection.LONG,"100","110"),
            (ResearchDirection.SHORT,"100","90"),
        ):
            with self.subTest(side=side):
                result=replay((high,),(tick(mark,trade),),
                              direction=side,leverage=10,margin="20")
                self.assertEqual(result.state,SyntheticReplayState.LIQUIDATION_CONDITION)
                self.assertIsNone(result.assumed_exit_trade_price)
                self.assertIsNone(result.conditional_net_quote)
                self.assertFalse(result.orders_sent)

    def test_new_snapshot_applies_only_at_effective_tick(self):
        healthy=snapshot(tiers=(tier("0",None,"50"),))
        adverse=snapshot(effective=T+1500,observed=T+1400,
                         version="fixture_v2",tiers=(tier("0",None,"9000"),))
        path=(tick("100","100",T+1000),tick("100","110",T+2000))
        first=replay((healthy,adverse),path)
        self.assertEqual(first.state,SyntheticReplayState.LIQUIDATION_CONDITION)
        self.assertEqual(len(first.observations),2)
        self.assertEqual(first.observations[0].state,SyntheticReplayState.OPEN_UNRESOLVED)
        self.assertEqual(first.observations[1].state,SyntheticReplayState.LIQUIDATION_CONDITION)
        with self.assertRaises(DataValidationError):
            replay((healthy,snapshot(effective=T+1500,observed=T+1501,
                   version="fixture_v2")),path)

    def test_funding_is_replayed_before_mark_risk(self):
        risky=snapshot(tiers=(tier("0",None,"980"),))
        funding=(SyntheticFundingEvent("fixture_funding_pit",T+500,D("200"),D("100")),)
        result=replay((risky,), (tick("100","100"),),funding=funding)
        self.assertEqual(result.state,SyntheticReplayState.LIQUIDATION_CONDITION)
        self.assertEqual(result.observations[0].signed_funding_paid_quote,D("2"))
        self.assertFalse(result.liquidation_formula_verified)

    def test_legacy_and_explicit_point_in_time_paths_are_separate(self):
        p=plan(leverage=10,margin="20")
        path=(tick("100","100"),)
        baseline=replay_synthetic_mark_path(p,path,as_of_ms=T+1000)
        self.assertEqual(baseline,replay_synthetic_mark_path(p,path,
                         as_of_ms=T+1000,max_tick_gap_ms=2000))
        self.assertEqual(baseline.state,SyntheticReplayState.OPEN_UNRESOLVED)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            self.assertEqual(replay((snapshot(),),path),replay((snapshot(),),path))

    def test_invalid_tiers_versions_and_gaps_fail_closed(self):
        invalid=[
            (tier("0","200","50"),tier("201",None,"100","1")),
            (tier("0","200","50"),tier("200",None,"40","0")),
            (tier("0","200","50"),tier("200",None,"100","0")),
            (tier("0","200","50"),),
        ]
        for rows in invalid:
            with self.subTest(rows=rows),self.assertRaises(DataValidationError):
                snapshot(tiers=rows)
        valid=snapshot()
        with self.assertRaises(DataValidationError):
            replay((valid,), (tick("100","100",T+5000),),max_gap=1000)
        with self.assertRaises(DataValidationError):
            replay((valid,), (tick("100","100",T+1000),),age=100)
        with self.assertRaises(DataValidationError):
            replay((valid,replace(valid,source_version="fixture_v2",
                                    effective_at_ms=T-500)),(tick("100","100"),))
        with self.assertRaises(DataValidationError):
            replay((valid,replace(valid,instrument_id="fixture_wrong",
                                    source_version="fixture_v2",
                                    effective_at_ms=T+500)),(tick("100","100"),))
        with self.assertRaises(DataValidationError):
            SyntheticMaintenanceTier(D("0"),None,D("NaN"),D("0"))

    def test_context_precision_invariant(self):
        expected=replay((snapshot(),),(tick("100","100"),))
        for precision in (2,4,28):
            with localcontext() as ctx:
                ctx.prec=precision
                self.assertEqual(expected,replay((snapshot(),),(tick("100","100"),)))

if __name__=="__main__":
    unittest.main()
