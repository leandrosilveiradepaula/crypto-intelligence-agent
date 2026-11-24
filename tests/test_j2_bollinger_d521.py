"""D521: exact bands, causal directional events and legacy compatibility."""
from dataclasses import replace
from decimal import Decimal
import unittest

from crypto_intelligence_agent.j2_configurable_indicators_d513 import (
    BollingerBands, IndicatorSelection, MovingAverageSlot, bollinger_bands,
    bollinger_directions, combination_directions, parse_indicator_selection,
)
from crypto_intelligence_agent.j2_observed_bybit_research import evaluate_observed_bybit_research
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_j2_configurable_indicators_d513 import OFF, PIVOT_OFF, sma_only
from test_j2_ema_cross_d503 import CONFIG, case

D=Decimal


class BollingerTests(unittest.TestCase):
    def test_population_sigma_and_prefix_invariance(self):
        closes=tuple(map(D,(1,1,3,3,7,2,5)))
        config=BollingerBands(True,4,D(1))
        bands=bollinger_bands(closes,config)
        self.assertEqual(bands[:3],(None,None,None))
        self.assertEqual(bands[3],(D(1),D(2),D(3)))
        for n in range(1,len(closes)+1):
            self.assertEqual(bollinger_bands(closes[:n],config),bands[:n])
            self.assertEqual(bollinger_directions(closes[:n],config),
                             bollinger_directions(closes,config)[:n])

    def test_breakout_and_reentry_long_short(self):
        for price,side in ((D(80),-1),(D(120),1)):
            closes=(D(100),)*23+(price,D(100),D(100))
            breakout=BollingerBands(True)
            reentry=replace(breakout,mode="reentry")
            self.assertEqual(bollinger_directions(closes,breakout)[-4:],(0,side,0,0))
            self.assertEqual(bollinger_directions(closes,reentry)[-4:],(0,0,-side,0))
        self.assertEqual(bollinger_directions((D(100),)*24,BollingerBands(True))[-1],0)

    def test_real_evaluator_allows_bb_only_and_sma_confluence(self):
        for price,side in (("113",SyntheticSide.LONG),("87",SyntheticSide.SHORT)):
            source,now=case(price,bars=40)
            active=BollingerBands(True,20,D(2))
            for sma in (OFF,(MovingAverageSlot(True,10),MovingAverageSlot(True,30),OFF[2])):
                selection=IndicatorSelection(OFF,sma,PIVOT_OFF,active)
                cfg=replace(CONFIG,entry_mode="indicator_combo",indicators=selection)
                result=evaluate_observed_bybit_research(source,config=cfg,decision_at_ms=now)
                self.assertEqual(len(result.hypotheses),1)
                self.assertEqual(result.hypotheses[0].side,side)
                self.assertFalse(result.hypotheses[0].orders_sent)
            self.assertEqual(combination_directions(source.candles,
                IndicatorSelection(OFF,OFF,PIVOT_OFF,replace(active,enabled=False)))[-1],0)

    def test_disabled_preserves_legacy_and_warmup(self):
        original=sma_only()
        self.assertNotIn("bollinger",original.as_json())
        self.assertEqual(parse_indicator_selection(original.as_json()),original)
        disabled=replace(original,bollinger=BollingerBands(False,120,D(3),"reentry"))
        source,_=case("113",bars=24)
        self.assertEqual(disabled.minimum_closed_bars(2),original.minimum_closed_bars(2))
        self.assertEqual(combination_directions(source.candles,disabled),
                         combination_directions(source.candles,original))
        self.assertEqual(parse_indicator_selection(disabled.as_json()),disabled)
        enabled=replace(disabled,bollinger=BollingerBands(True,120,D(3)))
        self.assertEqual(enabled.minimum_closed_bars(2),122)
        for patch in ({"period":121},{"deviations":"NaN"},{"deviations":"0"},
                      {"mode":"unknown"},{"enabled":"true"},{"deviations":2}):
            value=enabled.as_json()
            value["bollinger"].update(patch)
            with self.subTest(patch=patch),self.assertRaises(DataValidationError):
                parse_indicator_selection(value)


if __name__=="__main__":
    unittest.main()
