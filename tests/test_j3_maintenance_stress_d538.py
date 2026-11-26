"""D538 isolated-collateral stress, never a historical liquidation certificate."""
from decimal import Decimal as D
import unittest

from crypto_intelligence_agent.j3_funding_replay_d537 import ExposureChange,ObservedFundingHistory
from crypto_intelligence_agent.j3_maintenance_stress_d538 import stress_paths,parse_maintenance_grid
from crypto_intelligence_agent.j3_observed_exit_scenarios_d517 import compare_exit_scenarios,empty_replay_totals,accumulate_replay,summarize_replay
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_j3_observed_exit_scenarios_d517 import bar,END,HOUR,MARGIN,POLICY

LONG=ResearchDirection.LONG
SHORT=ResearchDirection.SHORT


def history(rows,rates=(),complete=True):
    return ObservedFundingHistory(start=END,end=END+3*HOUR,resolution="1h",
        funding={"query_coverage_complete":complete,"rows":tuple(rates)},
        mark={"query_coverage_complete":len(rows)==3,"rows":tuple(
            (END+i*HOUR,str(o),str(h),str(l),str(c)) for i,o,h,l,c in rows)})


def check(source,changes=(),side=LONG,grid=(50,100,150)):
    return stress_paths(source,direction=side,entry_at=END,end_at=END+3*HOUR,
        entry_price=D(100),margin=MARGIN,changes=changes,entry_cost_bps=D(9),
        close_reserve_bps=D(9),maintenance_grid=grid)


class MaintenanceStressTests(unittest.TestCase):
    def test_mmr_monotone_and_short_mark(self):
        source=history(((0,100,100,99,100),(1,100,100,100,100),(2,100,100,100,100)))
        got=check(source)
        self.assertIsNone(got[50].first_possible_breach_bar)
        self.assertEqual(got[100].first_possible_breach_bar,0)
        self.assertEqual(got[150].first_possible_breach_bar,0)
        self.assertGreaterEqual(got[50].worst_buffer_quote,got[100].worst_buffer_quote)
        self.assertGreaterEqual(got[100].worst_buffer_quote,got[150].worst_buffer_quote)
        short=check(history(((0,100,101,100,100),(1,100,100,100,100),(2,100,100,100,100))),side=SHORT)
        self.assertEqual(short[100].first_possible_breach_bar,0)

    def test_retained_debit_and_reduced_collateral(self):
        marks=((0,100,100,100,100),(1,100,100,100,100),(2,100,100,100,100))
        changes=(ExposureChange(0,D(1),D(".25"),D(".25")),)
        plain=check(history(marks),changes,grid=(50,))[50]
        debit=check(history(marks,((END+HOUR,".02"),)),changes,grid=(50,))[50]
        credit=check(history(marks,((END+HOUR,"-.02"),)),changes,grid=(50,))[50]
        self.assertIsNone(plain.first_possible_breach_bar)
        self.assertEqual(debit.first_possible_breach_bar,1)
        self.assertEqual(plain,credit)

    def test_full_exit_ignores_later_missing_marks_and_rates(self):
        changes=(ExposureChange(0,D(1),D(0),D(".25")),)
        got=check(history(((0,100,100,100,100),),((END+HOUR,".1"),)),changes)
        self.assertEqual(got[50].checked_bars,1)
        self.assertIsNone(got[50].first_possible_breach_bar)
        self.assertIsNone(check(history(((0,100,100,100,100),))))
        self.assertIsNone(check(history(((0,100,100,100,100),),complete=False),changes))
        with self.assertRaises(DataValidationError):
            check(history(((0,100,100,100,100),)),(ExposureChange(0,D(1),D(0)),))

    def test_full_exit_bar_retains_smallest_positive_quantity(self):
        cs=(bar(0,high="103",low="99"),)
        got=compare_exit_scenarios(cs,direction=LONG,decision_end_ms=END,
            now_ms=END+HOUR,margin=MARGIN,policy=POLICY,trace_exposure=True)
        self.assertEqual(got["adverse_first"].exposure_changes[0].minimum_positive,D(1))
        self.assertEqual(got["favorable_first"].exposure_changes[0].minimum_positive,D(".375"))

    def test_missing_counts_and_explicit_grid(self):
        for invalid in ((100,50),(50,50),(0,),(True,),(1,2,3,4)):
            with self.assertRaises(DataValidationError):
                parse_maintenance_grid(invalid)
        totals=empty_replay_totals(include_observed_funding=True,maintenance_grid=(50,))
        cs=(bar(0),)
        accumulate_replay(totals,cs,direction=LONG,decision_end_ms=END,
            now_ms=END+HOUR,margin=MARGIN,policy=POLICY,maintenance_grid=(50,))
        a=summarize_replay(totals,margin=MARGIN)["adverse_first"]
        self.assertEqual(a["stress_50bps_unavailable_count"],1)
        self.assertEqual(a["stress_50bps_evaluated_count"],0)
        self.assertEqual(a["stress_50bps_no_observed_breach_count"],0)


if __name__=="__main__":
    unittest.main()
