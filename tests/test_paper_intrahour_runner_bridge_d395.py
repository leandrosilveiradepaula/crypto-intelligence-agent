"""D395: real AUTO4 + RUNNER2 PAPER fixture, no venue actions."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitPublicTickerBook
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    HOUR_START_MS as T, MINUTE_MS as M, POSITION_ID,
    _new_position, _route, _tick, _explicit_fill,
)
from crypto_intelligence_agent.paper_intrahour_runner_bridge_d395 import (
    PaperRunnerTickDecision, step_paper_intrahour_with_runner,
)
from crypto_intelligence_agent.paper_runner_trailing import (
    PaperRunnerTrailPolicy, PaperRunnerTrailState,
)
from crypto_intelligence_agent.paper_runner_journal import load_paper_runner_journal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from crypto_intelligence_agent.paper_intrahour_target_step_d387 import PaperIntrahourTargetPolicy
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind, PaperOrderSide, PaperOrderStatus,
)


class IntrahourRunnerBridgeD395Tests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.position_path=Path(t.name)/"positions.sqlite"
        self.runner_path=Path(t.name)/"runner.sqlite"
        self.store=_new_position(self.position_path,short=False)
        self.book=BybitPublicTickerBook(
            ranked_symbols=("BTCUSDT",),universe_at_ms=T+M,
        )
        self.book.begin_acknowledged_session()
        self.stop=PaperEmergencyStopRule(D(99))
        self.targets=PaperIntrahourTargetPolicy(
            "d392-executable-proof-v1",(D(101),D(103)),
        )
        self.runner_policy=PaperRunnerTrailPolicy(
            D(100),D(50),5000,5000,
        )

    def step(self,q,*,policy=None):
        return step_paper_intrahour_with_runner(
            self.position_path,self.runner_path,POSITION_ID,
            stop_rule=self.stop,target_policy=self.targets,
            runner_policy=policy or self.runner_policy,
            quote=q,as_of_ms=q.received_at_ms,
        )

    def fully_confirm_runner(self,*,short=False):
        if short:
            # Establish a separate fixture, not an existing LONG reservation.
            self.position_path.unlink()
            self.store=_new_position(self.position_path,short=True)
            self.stop=PaperEmergencyStopRule(D(102))
            self.targets=PaperIntrahourTargetPolicy(
                "d392-executable-proof-v1",(D(99),D(97)),
            )
            q1=_tick(self.book,minute=12,cs=1,kind="snapshot",
                     mark="100",bid="98.98",ask="99")
        else:
            q1=_tick(self.book,minute=12,cs=1,kind="snapshot",
                     mark="100.5",bid="101",ask="101.02")
        one=self.step(q1)
        self.assertIsNone(one.trail)
        self.assertFalse(self.runner_path.exists())
        self.assertIsNotNone(one.created_intent_id)
        _explicit_fill(self.store,minute=12,intent_id=one.created_intent_id,
                       event_id="fixture_d395_fill1",units=D(30))
        if short:
            q2=_tick(self.book,minute=19,cs=2,kind="delta",
                     mark="97.5",bid="96.98",ask="97")
        else:
            q2=_tick(self.book,minute=19,cs=2,kind="delta",
                     mark="102.5",bid="103",ask="103.02")
        two=self.step(q2)
        self.assertIsNone(two.trail)
        self.assertIsNotNone(two.created_intent_id)
        _explicit_fill(self.store,minute=19,intent_id=two.created_intent_id,
                       event_id="fixture_d395_fill2",units=D(20))
        b=self.store.load(POSITION_ID)
        self.assertEqual(b.confirmed_remaining_units,D(50))
        self.assertEqual(b.runner_floor_units,D(50))
        self.assertEqual(b.reserved_unfilled_units,D(0))
        return _tick(self.book,minute=20,cs=3,kind="delta",
                     mark="100",bid="100",ask="100.02")

    def later(self,base,seconds,mark,cs):
        at=base.received_at_ms+seconds*1000
        return replace(
            base,received_at_ms=at,exchange_at_ms=at-25,
            cross_sequence=cs,mark_price=D(mark),
            bid_price=D(mark)-D("0.01"),
            ask_price=D(mark)+D("0.01"),
        )

    def test_full_long_trailing_runner_reservation_restart_and_closure(self):
        first=self.fully_confirm_runner()
        init=self.step(first)
        self.assertEqual(init.runner_decision,PaperRunnerTickDecision.ARMED)
        self.assertEqual(init.trail.state,PaperRunnerTrailState.NOT_ACTIVATED)
        self.assertTrue(self.runner_path.is_file())
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(50))

        up=self.step(self.later(first,2,"102",4))
        self.assertEqual(up.runner_decision,PaperRunnerTickDecision.TRACKING)
        self.assertEqual(up.trail.last_stop_mark_quote,D("101.490"))
        # Loading from a fresh instance preserves the ratchet after process restart.
        loaded=load_paper_runner_journal(
            self.runner_path,self.position_path,POSITION_ID,
            policy=self.runner_policy,as_of_ms=first.received_at_ms+2000,
        )
        self.assertEqual(loaded.last_stop_mark_quote,D("101.490"))
        down=self.step(self.later(first,4,"101",5))
        self.assertEqual(down.runner_decision,PaperRunnerTickDecision.EXIT_RESERVED)
        self.assertEqual(down.trail.state,PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY)
        self.assertIsNotNone(down.created_intent_id)
        b=self.store.load(POSITION_ID)
        self.assertEqual(len(b.exit_orders),3)
        self.assertEqual([o.tranche_step for o in b.exit_orders],[1,2,0])
        self.assertEqual(b.runner_reserved_unfilled_units,D(50))
        self.assertEqual(b.filled_exit_units,D(50))
        self.assertEqual(b.exit_orders[-1].intent.side,PaperOrderSide.SELL)
        self.assertFalse(down.sanitized_report()["orders_sent"])
        self.assertFalse(down.sanitized_report()["native_stop_verified"])

        # The next tick does not rewrite RUNNER2 or duplicate the exit.
        bytes_before=self.runner_path.read_bytes()
        pending=self.step(self.later(first,6,"103",6))
        self.assertEqual(pending.runner_decision,PaperRunnerTickDecision.EXIT_PENDING)
        self.assertIsNone(pending.created_intent_id)
        self.assertEqual(self.runner_path.read_bytes(),bytes_before)
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders),3)

        # A separate explicitly injected PAPER FILL is required for closure.
        fill=PaperOrderEvent(
            "fixture_d395_runner_fill",PaperOrderEventKind.FILL,
            first.received_at_ms+7000,D(50),
        )
        self.store.append_exit_events(
            POSITION_ID,down.created_intent_id,(fill,),
            as_of_ms=fill.event_at_ms,
        )
        closed=self.step(self.later(first,8,"104",7))
        self.assertEqual(closed.runner_decision,PaperRunnerTickDecision.EXIT_CLOSED)
        self.assertEqual(self.store.load(POSITION_ID).confirmed_remaining_units,D(0))
        self.assertEqual(self.runner_path.read_bytes(),bytes_before)

    def test_short_trailing_reverses_direction_after_partial_fills(self):
        first=self.fully_confirm_runner(short=True)
        self.assertEqual(self.step(first).runner_decision,PaperRunnerTickDecision.ARMED)
        up=self.step(self.later(first,2,"98",4))
        self.assertEqual(up.runner_decision,PaperRunnerTickDecision.TRACKING)
        self.assertEqual(up.trail.last_stop_mark_quote,D("98.490"))
        trigger=self.step(self.later(first,4,"99",5))
        self.assertEqual(trigger.runner_decision,PaperRunnerTickDecision.EXIT_RESERVED)
        self.assertEqual(self.store.load(POSITION_ID).exit_orders[-1].intent.side,
                         PaperOrderSide.BUY)
        self.assertEqual(self.store.load(POSITION_ID).runner_reserved_unfilled_units,D(50))

    def test_static_stop_takes_priority_even_during_active_trailing(self):
        first=self.fully_confirm_runner()
        self.step(first)
        self.step(self.later(first,2,"102",4))
        triggered=self.step(self.later(first,4,"98",5))
        self.assertEqual(triggered.runner_decision,PaperRunnerTickDecision.SKIPPED)
        self.assertEqual(triggered.coordinated.decision.value,"paper_stop_reserved")
        self.assertIsNone(triggered.runner_close)
        b=self.store.load(POSITION_ID)
        self.assertEqual([o.tranche_step for o in b.exit_orders],[1,2,-1])
        self.assertEqual(b.protective_reserved_unfilled_units,D(50))

    def test_unconfirmed_partial_or_unknown_never_arms_runner(self):
        start=_tick(self.book,minute=12,cs=1,kind="snapshot",
                    mark="100",bid="100",ask="100.02")
        self.assertEqual(self.step(start).runner_decision,PaperRunnerTickDecision.SKIPPED)
        self.assertFalse(self.runner_path.exists())
        target=_tick(self.book,minute=13,cs=2,kind="delta",
                     mark="101",bid="101",ask="101.02")
        a=self.step(target)
        self.assertIsNotNone(a.created_intent_id)
        unknown=PaperOrderEvent(
            "fixture_d395_unknown",PaperOrderEventKind.UNKNOWN,
            target.received_at_ms+1,
        )
        self.store.append_exit_events(
            POSITION_ID,a.created_intent_id,(unknown,),
            as_of_ms=unknown.event_at_ms,
        )
        later=self.later(target,2,"102",3)
        b=self.step(later)
        self.assertEqual(b.runner_decision,PaperRunnerTickDecision.SKIPPED)
        self.assertFalse(self.runner_path.exists())
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders),1)

    def test_gap_and_policy_drift_abstain_without_second_ledger_or_order(self):
        first=self.fully_confirm_runner()
        self.step(first)
        baseline=self.store.load(POSITION_ID)
        before=self.runner_path.read_bytes()
        with self.assertRaises(DataValidationError):
            self.step(self.later(first,9,"102",4))
        self.assertEqual(self.runner_path.read_bytes(),before)
        self.assertEqual(self.store.load(POSITION_ID),baseline)
        incompatible=PaperRunnerTrailPolicy(D(200),D(50),5000,5000)
        with self.assertRaises(DataValidationError):
            self.step(self.later(first,2,"102",4),policy=incompatible)
        self.assertEqual(self.runner_path.read_bytes(),before)

    def test_d391_callback_drives_optin_trailing_with_same_auto4_ledger(self):
        from crypto_intelligence_agent.paper_intrahour_quote_router_d391 import (
            PaperIntrahourQuoteRouter, PaperQuoteRoute,
        )
        first=self.fully_confirm_runner()
        route=PaperQuoteRoute(
            position_id=POSITION_ID,stop_rule=self.stop,
            target_policy=self.targets,runner_policy=self.runner_policy,
            runner_path=self.runner_path,
        )
        routed=PaperIntrahourQuoteRouter(
            position_path=self.position_path,routes=(route,),
        )
        armed=routed.process(first)
        self.assertEqual(armed.runner_decision,PaperRunnerTickDecision.ARMED)
        self.assertEqual(
            routed.process(self.later(first,2,"102",4)).runner_decision,
            PaperRunnerTickDecision.TRACKING,
        )
        fired=routed.process(self.later(first,4,"101",5))
        self.assertEqual(fired.runner_decision,PaperRunnerTickDecision.EXIT_RESERVED)
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders),3)
        self.assertEqual(self.store.load(POSITION_ID).runner_reserved_unfilled_units,D(50))
        self.assertEqual(routed.sanitized_report()["runner_decision_counts"],{
            "paper_runner_close_reserved":1,
            "paper_trailing_armed":1,
            "paper_trailing_tracking":1,
        })
        self.assertFalse(routed.sanitized_report()["orders_sent"])
        # D391's replay gate rejects a conflicting repeated cross sequence.
        with self.assertRaises(Exception):
            routed.process(self.later(first,4,"98",5))
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders),3)

    def test_optional_route_rejects_incomplete_config_and_same_sqlite(self):
        from crypto_intelligence_agent.paper_intrahour_quote_router_d391 import (
            PaperIntrahourQuoteRouter, PaperQuoteRoute,
        )
        with self.assertRaises(DataValidationError):
            PaperQuoteRoute(POSITION_ID,self.stop,self.targets,
                            runner_policy=self.runner_policy)
        with self.assertRaises(DataValidationError):
            PaperQuoteRoute(POSITION_ID,self.stop,self.targets,
                            runner_path=self.runner_path)
        same=PaperQuoteRoute(POSITION_ID,self.stop,self.targets,
                             runner_policy=self.runner_policy,
                             runner_path=self.position_path)
        with self.assertRaises(DataValidationError):
            PaperIntrahourQuoteRouter(
                position_path=self.position_path,routes=(same,),
            )

    def test_pending_runner_unknown_never_reissues_another_close(self):
        first=self.fully_confirm_runner()
        self.step(first)
        self.step(self.later(first,2,"102",4))
        reserved=self.step(self.later(first,4,"101",5))
        checkpoint=self.store.load(POSITION_ID)
        unknown=PaperOrderEvent(
            "fixture_d395_runner_unknown",PaperOrderEventKind.UNKNOWN,
            first.received_at_ms+5000,
        )
        self.store.append_exit_events(
            POSITION_ID,reserved.created_intent_id,(unknown,),
            as_of_ms=unknown.event_at_ms,
        )
        replay=self.step(self.later(first,6,"103",6))
        self.assertEqual(replay.runner_decision,PaperRunnerTickDecision.EXIT_PENDING)
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders),3)
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(50))
        self.assertEqual(self.store.load(POSITION_ID).runner_reserved_unfilled_units,D(50))


if __name__ == "__main__":
    unittest.main()
