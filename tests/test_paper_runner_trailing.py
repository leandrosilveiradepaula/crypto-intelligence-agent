"""J4 #383: real PAPER journal fixtures, synthetic mark trailing only."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_runner_trailing import (
    PaperRunnerMark, PaperRunnerTrailPolicy, PaperRunnerTrailState,
    inspect_paper_runner_trail,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderEventKind
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_paper_position_reservations import T, e, exit_order, opened_order, plan


def policy(**kwargs):
    values=dict(activation_bps=D("100"),trail_distance_bps=D("50"),
                max_tick_gap_ms=5000,max_last_tick_age_ms=5000)
    return PaperRunnerTrailPolicy(**{**values,**kwargs})


def ticks(*prices, sym="BTCUSDT", start=T+100):
    return tuple(PaperRunnerMark(sym,start+1000*i,D(p))
                 for i,p in enumerate(prices))


class RunnerTrailingTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.journal=SQLitePaperPositionJournal(Path(tmp.name)/"paper.sqlite")
        self.balance=self.journal.create_position(
            position_id="fixture_runner_A",opening_intent=opened_order(),
            opening_events=(e("runner_open",PaperOrderEventKind.FILL,1,"100"),),
            exit_plan=plan(),plan_version="fixture_runner_v1",
            synthetic_lot_step_units=D(1),as_of_ms=T+1)

    def fill_runner(self):
        current=self.balance
        for n,amount in enumerate(("50","30","14"),start=1):
            order=exit_order("trailing"+str(n),amount,
                             current.as_of_ms-T,cap=str(current.confirmed_remaining_units))
            current=self.journal.reserve_exit(current.position_id,n,order,
                                               as_of_ms=current.as_of_ms)
            current=self.journal.append_exit_events(
                current.position_id,order.intent_id,
                (e("trailing_fill_"+str(n),PaperOrderEventKind.FILL,
                   current.as_of_ms-T+1,amount),),
                as_of_ms=current.as_of_ms+1)
        self.assertEqual(current.confirmed_remaining_units,D("6"))
        return self.journal.load(current.position_id)

    def audit(self,balance,marks=None,**overrides):
        marks=marks if marks is not None else ticks("100","102","103","102")
        return inspect_paper_runner_trail(balance,marks,policy=policy(**overrides),
                                           as_of_ms=marks[-1].at_ms)

    def test_no_trailing_before_confirmed_runner(self):
        r=self.audit(self.balance)
        self.assertEqual(r.state,PaperRunnerTrailState.WAITING_FOR_CONFIRMED_RUNNER)
        self.assertFalse(r.activated)
        self.assertIsNone(r.last_stop_mark_quote)
        self.assertFalse(r.sanitized_report()["orders_sent"])
        current=self.journal.reserve_exit(
            self.balance.position_id,1,
            exit_order("unknowntrailing","50",1),as_of_ms=T+1)
        self.assertEqual(self.audit(current).state,
                         PaperRunnerTrailState.WAITING_FOR_CONFIRMED_RUNNER)

    def test_long_trailing_after_real_paper_fill_ledger(self):
        balance=self.fill_runner()
        marks=ticks("100","102","103","102")
        result=self.audit(balance,marks)
        self.assertEqual(result.state,PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY)
        self.assertTrue(result.activated)
        self.assertEqual(result.triggered_tick_number,4)
        self.assertEqual(result.last_stop_mark_quote,D("102.485"))
        self.assertEqual(result.runner_units,D("6"))
        self.assertEqual(result,self.audit(balance,marks))
        report=result.sanitized_report()
        for forbidden in ("BTCUSDT","fixture_runner_A","102.485"):
            self.assertNotIn(forbidden,str(report))
        for k in ("native_stop_verified","financial_pnl_available","orders_sent",
                  "order_submission_enabled","approved_for_live_use",
                  "live_trading_authorized"):
            self.assertFalse(report[k])
        self.assertEqual(report["network_requests"],0)

    def test_short_trailing_ratchets_down_and_triggers_up(self):
        confirmed=self.fill_runner()
        short=replace(confirmed,side=SyntheticSide.SHORT)
        result=self.audit(short,ticks("100","98","97","98"))
        self.assertEqual(result.state,PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY)
        self.assertEqual(result.triggered_tick_number,4)
        self.assertEqual(result.last_stop_mark_quote,D("97.485"))
        other=self.audit(short,ticks("100","98","97","97.1"))
        self.assertEqual(other.state,PaperRunnerTrailState.TRACKING)
        self.assertIsNone(other.triggered_tick_number)

    def test_activation_is_causal_and_no_lookahead(self):
        b=self.fill_runner()
        not_active=self.audit(b,ticks("100","100.5","100.4"))
        self.assertEqual(not_active.state,PaperRunnerTrailState.NOT_ACTIVATED)
        started=self.audit(b,ticks("100","101"))
        self.assertEqual(started.state,PaperRunnerTrailState.TRACKING)
        self.assertEqual(started.last_stop_mark_quote,D("100.495"))
        # On activation tick, calculation of the new stop does not synthesize
        # a fill even when the threshold sits above a previous mark.
        self.assertIsNone(started.triggered_tick_number)

    def test_invalid_precision_ages_and_identity_fail_closed(self):
        b=self.fill_runner()
        for bad in (D("NaN"),D("Infinity"),D("-1"),D("10000"),1.5,True):
            with self.subTest(bad=bad),self.assertRaises(DataValidationError):
                policy(trail_distance_bps=bad)
        with self.assertRaises(DataValidationError):
            self.audit(b,ticks("100","101",start=T))
        with self.assertRaises(DataValidationError):
            self.audit(b,ticks("100","101",start=T+100),max_tick_gap_ms=10)
        with self.assertRaises(DataValidationError):
            self.audit(b,ticks("100","101",sym="ETHUSDT"))
        with self.assertRaises(DataValidationError):
            self.audit(b,ticks("100","101",start=T+100),
                       max_last_tick_age_ms=0)
        with self.assertRaises(DataValidationError):
            self.audit(b,(PaperRunnerMark("BTCUSDT",T+100,D("100")),
                         PaperRunnerMark("BTCUSDT",T+100,D("101"))))
        with self.assertRaises(DataValidationError):
            PaperRunnerMark("BTCUSDT",T+100,D("NaN"))

    def test_exact_decimal_no_network_or_persistence_changes(self):
        b=self.fill_runner()
        marks=ticks("100","102","103","102")
        baseline=self.audit(b,marks)
        before=self.journal.load(b.position_id)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            self.assertEqual(baseline,self.audit(b,marks))
        for prec in (2,4,28):
            with localcontext() as ctx:
                ctx.prec=prec
                self.assertEqual(baseline,self.audit(b,marks))
        self.assertEqual(self.journal.load(b.position_id),before)


if __name__=="__main__":
    unittest.main()
