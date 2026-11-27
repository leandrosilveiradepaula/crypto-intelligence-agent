"""D545 mark-only evidence and matched PnL partitions."""
from decimal import Decimal as D
from dataclasses import replace
import unittest

from crypto_intelligence_agent.j3_funding_replay_d537 import ExposureChange
from crypto_intelligence_agent.j3_stress_attribution_d545 import (
    attribution_fields,record_attribution,format_attribution,decode_attribution,
)
from crypto_intelligence_agent.j3_maintenance_stress_d538 import MaintenanceStressResult
from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import (
    empty_replay_totals,accumulate_replay,summarize_replay,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_j3_maintenance_stress_d538 import history,check,LONG,SHORT
from test_j3_observed_exit_scenarios_d517 import bar,END,HOUR,MARGIN,POLICY


class StressAttributionTests(unittest.TestCase):
    def test_fixed_exposure_requires_later_unchanged_bar(self):
        clean=(0,100,100,100,100)
        bad=(1,100,100,98,100)
        tail=(2,100,100,100,100)
        a=check(history((clean,bad,tail)),grid=(50,))[50]
        self.assertTrue(a.fixed_exposure_mark_only_breach)
        self.assertEqual(a.first_breach_stage,"unchanged_bar")
        b=check(history((clean,bad,tail)),
                (ExposureChange(1,D(1),D(0),D(1)),),grid=(50,))[50]
        self.assertFalse(b.fixed_exposure_mark_only_breach)
        self.assertEqual(b.first_breach_stage,"reduction_bar")
        c=check(history(((0,100,100,98,100),(1,100,100,100,100),tail)),
                grid=(50,))[50]
        self.assertFalse(c.fixed_exposure_mark_only_breach)
        self.assertEqual(c.first_breach_stage,"entry_bar")
        short=check(history((clean,(1,100,102,100,100),tail)),side=SHORT,grid=(50,))[50]
        self.assertTrue(short.fixed_exposure_mark_only_breach)

    def test_funding_only_breach_is_not_fixed_mark_only(self):
        marks=tuple((i,100,100,100,100) for i in range(3))
        from test_j3_observed_exit_scenarios_d517 import END,HOUR
        a=check(history(marks,((END+HOUR,".04"),)),grid=(50,))[50]
        self.assertIsNotNone(a.first_possible_breach_bar)
        self.assertFalse(a.fixed_exposure_mark_only_breach)

    def test_matched_partition_reconciles_with_unavailable_stress(self):
        p="stress_50bps_"
        row={**attribution_fields(p),"funding_matched_path_count":3,
             "funding_matched_net_low_quote":D(2),"funding_matched_net_high_quote":D(5),
             p+"possible_breach_count":1,p+"no_observed_breach_count":1,
             p+"evaluated_count":2,p+"unavailable_count":2}
        record_attribution(row,p,MaintenanceStressResult(2,1,D(-1),"unchanged_bar",True),(D(4),D(5)))
        record_attribution(row,p,MaintenanceStressResult(2,None,D(1)),(D(-3),D(-2)))
        record_attribution(row,p,None,(D(1),D(2)))
        record_attribution(row,p,None,None)
        format_attribution(row,p)
        row["funding_matched_net_low_quote"]="2"
        row["funding_matched_net_high_quote"]="5"
        out=decode_attribution(row,p)
        self.assertEqual(out["fixed_exposure_mark_only_paths"],1)
        self.assertEqual(out["matched_pnl_by_stress_status"]["stress_unavailable"]["paths"],1)
        self.assertEqual(out["matched_pnl_by_stress_status"]["possible_breach"]["conditional_net_range_quote"],["4","5"])
        row[p+"attribution_stress_unavailable_net_high_quote"]="99"
        with self.assertRaises(DataValidationError):
            decode_attribution(row,p)

    def test_replay_preserves_pnl_and_separates_missing_mark(self):
        path=tuple(bar(i,high="100.2",low="99.8") for i in range(3))
        policy=replace(POLICY,stop_distance_bps=D(150))
        source=history(((0,100,100,100,100),(1,100,100,98,100),(2,100,100,100,100)))
        partial=history(((0,100,100,100,100),))
        totals=empty_replay_totals(include_observed_funding=True,maintenance_grid=(50,))
        for history_source in (source,partial,None):
            accumulate_replay(totals,path,direction=LONG,decision_end_ms=END,
                now_ms=END+3*HOUR,margin=MARGIN,policy=policy,
                observed_funding=history_source,maintenance_grid=(50,))
        row=summarize_replay(totals,margin=MARGIN)["adverse_first"]
        out=decode_attribution(row,"stress_50bps_")
        self.assertEqual(row["funding_matched_path_count"],2)
        self.assertEqual(out["fixed_exposure_mark_only_paths"],1)
        self.assertEqual(out["matched_pnl_by_stress_status"]["possible_breach"]["paths"],1)
        self.assertEqual(out["matched_pnl_by_stress_status"]["stress_unavailable"]["paths"],1)
        self.assertEqual(row["stress_50bps_unavailable_count"],2)
        self.assertIsNone(decode_attribution({}, "stress_50bps_"))


if __name__=="__main__":
    unittest.main()
