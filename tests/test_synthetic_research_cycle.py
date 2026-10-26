from decimal import Decimal
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError, MARKET
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticCostScenario
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_financial_scenarios import ConditionalFinancialScenario, ScenarioResolution
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection, SyntheticBarrier, SyntheticBarrierPlan
from crypto_intelligence_agent.synthetic_label_purging import SyntheticLabelHorizonConfig
from crypto_intelligence_agent.synthetic_research_cycle import SyntheticResearchCycleConfig, run_synthetic_research_cycle
from crypto_intelligence_agent.synthetic_walk_forward import SyntheticWalkForwardConfig

D, H = Decimal, 3_600_000
ROWS = (("100","110","90","10"),("101","111","91","10"),("101","102","100","10"),("101","102","100","10"),("101","102","100","10"),("105","106","101","50"),("111","112","104","100"))

def candles(n=12):
    rows=list(ROWS)
    while len(rows)<n:
        c=rows[-1][0]; rows.append((c,str(D(c)+1),str(D(c)-1),"10"))
    return tuple(ClosedCandle("fixture_exchange",MARKET,"BTCUSDT","1h",(10+i)*H,(11+i)*H-1,D(o),D(hi),D(lo),D(o),D(1),D(v),"synthetic_fixture") for i,(o,hi,lo,v) in enumerate(rows))

def config(safety=1000):
    return SyntheticResearchCycleConfig(CompressionBreakoutConfig(FeatureConfig(2,2,2,2),2,2,D("0.6"),D(2),1),SyntheticWalkForwardConfig(4,1,2,2),SyntheticLabelHorizonConfig(1),safety)

def cycle(rows, *, safety=1000, plans={}, scenarios={}):
    return run_synthetic_research_cycle(rows,config=config(safety),decision_at_ms=rows[-1].close_time_ms+safety,barrier_plans=plans,financial_scenarios=scenarios)

class SyntheticResearchCycleTests(unittest.TestCase):
    def test_close_safety_skips_immediate_next_open_and_replays_deterministically(self):
        rows=candles()
        baseline=cycle(rows)
        event=baseline.events[0]
        self.assertEqual(event.candidate_index,5)
        self.assertEqual(event.first_eligible_candle_index,7)
        self.assertEqual(event.abstention_reason,"missing_explicit_barrier_plan")
        plan=SyntheticBarrierPlan(ResearchDirection.LONG,D("105"),D("100"),D("110"),event.candidate_available_at_ms)
        exit_at=rows[7].open_time_ms+1
        costs=SyntheticCostScenario(ResearchDirection.LONG,event.candidate_available_at_ms,exit_at,D("210"),D("220"),D(0),D(0),D(0),D(0))
        branch=ConditionalFinancialScenario("fixture_financial_cycle","fixture_exchange","BTCUSDT","1h",ResearchDirection.LONG,SyntheticBarrier.TARGET,D("105"),D(2),ScenarioResolution.EXPLICIT_EXIT,D("110"),None,"SYNTHETIC_QUOTE",costs)
        full=cycle(rows,plans={5:plan},scenarios={5:(branch,)})
        self.assertEqual(full.events[0].conditional_results[0].gross_price_movement_quote_units,D("10"))
        self.assertEqual(full,cycle(rows,plans={5:plan},scenarios={5:(branch,)}))

    def test_zero_safety_allows_next_open_but_positive_safety_does_not_move_time_back(self):
        rows=candles()
        self.assertEqual(cycle(rows,safety=0).events[0].first_eligible_candle_index,6)
        self.assertEqual(cycle(rows,safety=1000).events[0].first_eligible_candle_index,7)

    def test_missing_future_barrier_or_financial_premise_abstains_and_flags_are_false(self):
        rows=candles(7)
        report=cycle(rows)
        self.assertEqual(report.events[0].abstention_reason,"no_future_candle_after_close_safety")
        for name in ("approved_for_live_use","orders_sent","financial_backtest_approved","out_of_sample_results_validated","net_pnl_verified"):
            self.assertFalse(getattr(report,name))

    def test_bad_plan_binding_and_no_network_or_orders(self):
        rows=candles(); event=cycle(rows).events[0]
        bad=SyntheticBarrierPlan(ResearchDirection.LONG,D("106"),D("100"),D("110"),event.candidate_available_at_ms)
        with self.assertRaises(DataValidationError): cycle(rows,plans={5:bad})
        source=(Path(__file__).resolve().parent.parent/"crypto_intelligence_agent"/"synthetic_research_cycle.py").read_text()
        for forbidden in ("urllib.request","requests.","sqlite3","create_order(","send_order(","socket"):
            self.assertNotIn(forbidden,source)

if __name__=="__main__": unittest.main()
