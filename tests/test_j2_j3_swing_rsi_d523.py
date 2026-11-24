"""D523: own-asset Wilder RSI, same-entry stop comparisons, no live trades."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j2_configurable_indicators_d513 import (
    RelativeStrengthIndex, parse_indicator_selection, wilder_rsi, rsi_directions,
    combination_directions,
)
from crypto_intelligence_agent.j3_combination_research_d520 import parse_matrix, run_matrix
from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import empty_replay_totals, accumulate_replay, summarize_replay
from crypto_intelligence_agent.j3_intrahour_replay_d518 import decode_intrahour
from crypto_intelligence_agent.j3_retrospective_warmup_d516 import WarmupSupplement
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j2_configurable_indicators_d513 import sma_only
from test_j2_ema_cross_d503 import case
from test_j3_archived_strategy_comparison_d512 import archive, END, HOUR, CFG
from test_j3_intrahour_replay_d518 import envelope
from test_j3_observed_exit_scenarios_d517 import bar, MARGIN, POLICY
from test_j3_combination_research_d520 import row, matrix


class SwingRSITests(unittest.TestCase):
    def test_wilder_seed_update_flat_and_causality(self):
        c = tuple(map(D,(10,11,10,12,11,12,9,11)))
        cfg = RelativeStrengthIndex(True,3)
        r = wilder_rsi(c,cfg)
        self.assertEqual(r[:3],(None,None,None))
        self.assertEqual(r[3],D(75))
        self.assertAlmostEqual(r[4],D(600)/11,places=24)
        for i in range(1,len(c)+1):
            self.assertEqual(wilder_rsi(c[:i],cfg),r[:i])
        self.assertEqual(wilder_rsi((D(10),)*5,cfg)[-1],50)
        self.assertEqual(wilder_rsi(tuple(map(D,range(10,15))),cfg)[-1],100)
        self.assertEqual(wilder_rsi(tuple(map(D,range(15,10,-1))),cfg)[-1],0)
        self.assertEqual(rsi_directions(c,cfg)[4],1)
        self.assertEqual(rsi_directions(c,replace(cfg,long_max=100))[3],1)
        self.assertEqual(rsi_directions(tuple(D(30)-x for x in c),cfg)[4],-1)
        self.assertEqual(rsi_directions((D(10),)*5,cfg)[-1],0)

    def test_optional_roundtrip_and_disabled_compatibility(self):
        old=sma_only()
        self.assertNotIn("rsi",old.as_json())
        self.assertEqual(parse_indicator_selection(old.as_json()),old)
        disabled=replace(old,rsi=RelativeStrengthIndex(False,120))
        source,_=case("113",bars=40)
        self.assertEqual(combination_directions(source.candles,old),
                         combination_directions(source.candles,disabled))
        self.assertEqual(old.minimum_closed_bars(2),disabled.minimum_closed_bars(2))
        enabled=replace(disabled,rsi=RelativeStrengthIndex(True,120))
        self.assertEqual(enabled.minimum_closed_bars(2),122)
        self.assertEqual(parse_indicator_selection(enabled.as_json()),enabled)
        for change in ({"period":121},{"long_min":49},{"long_max":50},{"enabled":1}):
            raw=enabled.as_json()
            raw["rsi"].update(change)
            with self.subTest(change=change),self.assertRaises(DataValidationError):
                parse_indicator_selection(raw)

    def test_swing_matrix_contains_controls_and_rsi_pairs(self):
        p=Path(__file__).resolve().parents[1]/"docs/examples/d523_swing_rsi_research_matrix.json"
        _,profiles,labels=parse_matrix(p.read_bytes())
        self.assertEqual(len(labels),18)
        rules={n:(s,t) for n,s,t in profiles}
        control,threshold=rules["sma_20_50"]
        with_rsi,rs=rules["sma_20_50_rsi"]
        self.assertEqual(replace(with_rsi,rsi=None),control)
        self.assertEqual(with_rsi.rsi.period,14)
        self.assertEqual(rs,threshold)

    def test_stop_then_recovery_is_not_an_execution_claim(self):
        bars=(bar(0,high="100.4",low="99.3",close="99.8"),
              bar(1,opening="99.8",high="102.1",low="99.7",close="101.7"))
        result=[]
        for distance in (50,100):
            totals=empty_replay_totals()
            accumulate_replay(totals,bars,direction=ResearchDirection.LONG,
                decision_end_ms=END,now_ms=END+3*HOUR,margin=MARGIN,
                policy=replace(POLICY,stop_distance_bps=D(distance)))
            result.append(summarize_replay(totals,margin=MARGIN)["adverse_first"])
        a,b=result
        self.assertEqual(a["stop_before_tp1_count"],1)
        self.assertEqual(a["stop_before_tp1_first_hour_count"],1)
        self.assertEqual(a["stop_before_tp1_then_later_tp1_count"],1)
        self.assertEqual(b["stop_before_tp1_count"],0)
        self.assertEqual(a["mean_full_path_mae_bps"],"70.00")
        self.assertEqual(a["mean_full_path_mfe_bps"],"210.00")
        self.assertEqual(a["mean_full_path_mae_bps"],b["mean_full_path_mae_bps"])
        self.assertGreater(D(b["conditional_before_funding_quote"]),D(a["conditional_before_funding_quote"]))

    def test_stop_override_leaves_profile_and_entry_counts_unchanged(self):
        h0,h1=archive(0),archive(1)
        now=END+10*HOUR
        intra=decode_intrahour(envelope(h0,h1),now_ms=now)
        warm=WarmupSupplement(END+2*HOUR,24,"a"*64,())
        policy=SimpleNamespace(research=CFG,exits=POLICY,margin_quote=D(1),
                               leverage=SimpleNamespace(for_new_positions=50))
        target="crypto_intelligence_agent.j3_combination_research_d520."
        with patch(target+"read_comparison_archives",return_value=(h0,h1)), \
             patch(target+"read_latest_supplement",return_value=warm), \
             patch(target+"read_latest_intrahour",return_value=intra):
            args=dict(directory=Path("."),owner_policy=policy,matrix_raw=matrix([row()]),
                      as_of_ms=now,horizon_hours=1)
            a=run_matrix(**args)
            b=run_matrix(**args,research_stop_bps=100)
            with self.assertRaises(DataValidationError):
                run_matrix(**args,research_stop_bps=True)
        self.assertEqual(policy.exits.stop_distance_bps,50)
        self.assertEqual(b["common_exit_policy"]["stop_distance_bps"],D(100))
        self.assertEqual(b["stop_gross_loss_margin_pct"],"50")
        self.assertEqual({r["name"]:(r["candidates"],r["complete"]) for r in a["rows"]},
                         {r["name"]:(r["candidates"],r["complete"]) for r in b["rows"]})
        self.assertFalse(b["liquidation_verified"])
        self.assertFalse(b["profile_modified"])
        self.assertFalse(b["orders_sent"])


if __name__ == "__main__":
    unittest.main()
