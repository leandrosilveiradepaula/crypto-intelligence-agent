"""J3 PRE27: deterministic, conditional-only intrabar path/outage regressions."""
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch
import json
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_intrabar_stress import (
    VisionStressAssumptions, stress_vision_candle,
)
from crypto_intelligence_agent.vision_path_outage import (
    simulate_vision_path_outage, audit_vision_oos_path_outage,
)
from crypto_intelligence_agent.vision_stress_sensitivity import (
    compare_costed_vision_oos_stress_scenarios,
)
from test_vision_dynamic_replay import fixture
from test_vision_intrabar_stress import terms, bar


class PathOutageTests(unittest.TestCase):
    def test_high_low_paths_and_unavailable_stop_differ(self):
        # 1x ignores liquidation proxy on positive bars. Both paths touch
        # stop and target, and therefore reverse who is hypothetically first.
        candle=bar(o="100", h="105", l="95", c="96")
        conditions=terms(1)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            out=simulate_vision_path_outage(candle,long=True,assumptions=conditions)
        self.assertEqual(len(out),4)
        self.assertEqual([(x.path,x.stop_state) for x in out],[
            ("high_first","available"),("high_first","unavailable"),
            ("low_first","available"),("low_first","unavailable"),
        ])
        self.assertEqual(out[0].terminal,"target")
        self.assertEqual(out[2].terminal,"stop")
        self.assertEqual(out[3].terminal,"target")
        self.assertGreater(out[0].conditional_net_quote,
                           out[2].conditional_net_quote)
        self.assertFalse(any(x.liquidation_proxy_touched for x in out))

    def test_outage_can_worsen_loss_when_target_is_not_touched(self):
        candle=bar(o="100",h="101",l="90",c="90")
        out=simulate_vision_path_outage(candle,long=True,assumptions=terms(1))
        self.assertEqual(out[0].terminal,"stop")
        self.assertEqual(out[1].terminal,"close")
        self.assertLess(out[1].conditional_net_quote,out[0].conditional_net_quote)
        # Short analogue: missing stop can make adverse close worse.
        short=bar(o="100",h="115",l="99",c="115")
        s=simulate_vision_path_outage(short,long=False,assumptions=terms(1))
        self.assertEqual(s[0].terminal,"stop")
        self.assertEqual(s[1].terminal,"close")
        self.assertLess(s[1].conditional_net_quote,s[0].conditional_net_quote)

    def test_liquidation_proxy_preempts_unavailable_stop(self):
        o=simulate_vision_path_outage(bar(o="100",h="105",l="90",c="91"),
                                      long=True,assumptions=terms(50,fee="10"))
        self.assertTrue(any(x.liquidation_proxy_touched for x in o))
        self.assertTrue(all(x.terminal=="liquidation_proxy"
                            for x in o if x.stop_state=="unavailable"))
        self.assertLessEqual(o[-1].conditional_net_quote,-D(2))
        for x in o:
            self.assertNotIn("fill",str(x.sanitized_report()).lower())

    def test_invalid_inputs_do_not_create_approval(self):
        with self.assertRaises(DataValidationError):
            simulate_vision_path_outage(bar(),long=1,assumptions=terms())
        with self.assertRaises(DataValidationError):
            simulate_vision_path_outage(bar(),long=True,assumptions=None)
        with self.assertRaises(DataValidationError):
            simulate_vision_path_outage(bar(h="90"),long=True,assumptions=terms())

    @classmethod
    def setUpClass(cls):
        cls.a,cls.b=fixture("BTCUSDT"),fixture("ETHUSDT")
        cls.cutoff=cls.a[-1].end_open_exclusive_ms+3_600_000

    def replay(self,groups=None,grid=None):
        source=(self.a,self.b) if groups is None else groups
        cases=(terms(1),terms(50)) if grid is None else grid
        sensitivity=compare_costed_vision_oos_stress_scenarios(
            source,as_of_ms=self.cutoff,cost_bps_per_side=D(0),
            assumptions_grid=cases)
        return audit_vision_oos_path_outage(
            source,as_of_ms=self.cutoff,cost_bps_per_side=D(0),
            comparison=sensitivity), sensitivity

    def test_frozen_oos_counts_permutation_determinism_and_privacy(self):
        with patch("socket.create_connection",side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen",side_effect=AssertionError("network")):
            first,base=self.replay()
            second,_=self.replay(groups=(self.b,self.a))
        self.assertEqual(first,second)
        self.assertEqual(len(first.scenarios),2)
        self.assertEqual(len(first.scenarios[0].folds),1)
        self.assertEqual(first.scenarios[0].selection_fingerprint_sha256,
                         base.scenarios[0].audit.decision_fingerprint_sha256)
        self.assertEqual(first.scenarios[1].selection_fingerprint_sha256,
                         base.scenarios[1].audit.decision_fingerprint_sha256)
        for row,ref in zip(first.scenarios,base.scenarios):
            self.assertEqual(sum(x.exposures for x in row.folds),
                             ref.audit.stressed_count)
            self.assertEqual(len(row.net_by_path_stop),4)
        d=first.sanitized_report()
        self.assertFalse(d["fill_price_verified"])
        self.assertFalse(d["intrabar_path_verified"])
        self.assertFalse(d["liquidation_formula_verified"])
        self.assertFalse(d["live_trading_authorized"])
        self.assertFalse(d["orders_sent"])
        self.assertIsNone(d["recommended_leverage"])
        out=json.dumps(d)
        for forbidden in ("BTCUSDT","ETHUSDT","/home/",".sqlite","http"):
            self.assertNotIn(forbidden,out)

    def test_exposure_branches_and_cost_sensitivity(self):
        def trending(group):
            n=0
            result=[]
            for month in group:
                rows=[]
                for c in month.candles:
                    rows.append(replace(c,close=D("101")+D(n)/D(1000),
                                        high=D("104"),low=D("99")))
                    n+=1
                result.append(replace(month,candles=tuple(rows)))
            return tuple(result)
        groups=(trending(self.a),trending(self.b))
        first,baseline=self.replay(groups)
        second,_=self.replay(groups,grid=(terms(1,fee="10"),terms(50,fee="10")))
        self.assertGreater(first.scenarios[0].folds[0].exposures,0)
        self.assertEqual(first.scenarios[0].folds[0].exposures,
                         baseline.scenarios[0].audit.stressed_count)
        self.assertTrue(any(x.terminal in ("stop","target","liquidation_proxy")
                            for x in simulate_vision_path_outage(
                                groups[0][0].candles[20],long=True,
                                assumptions=terms(50))))
        self.assertTrue(all(b<=a for a,b in zip(
            first.scenarios[0].net_by_path_stop,
            second.scenarios[0].net_by_path_stop)))

    def test_foreign_decision_and_coverage_are_rejected(self):
        _,valid=self.replay()
        modified=replace(valid.scenarios[1],audit=replace(
            valid.scenarios[1].audit,decision_fingerprint_sha256="f"*64))
        with self.assertRaisesRegex(DataValidationError,"OOS decisions"):
            audit_vision_oos_path_outage(
                (self.a,self.b),as_of_ms=self.cutoff,cost_bps_per_side=D(0),
                comparison=replace(valid,scenarios=(valid.scenarios[0],modified)))
        with self.assertRaises(DataValidationError):
            audit_vision_oos_path_outage(
                (self.a,self.a),as_of_ms=self.cutoff,cost_bps_per_side=D(0),
                comparison=valid)


if __name__=="__main__":
    unittest.main()
