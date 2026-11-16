"""D391: live-ticker-shaped events -> one existing AUTO4 PAPER position."""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path
import json
import tempfile
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import (
    BybitTickerQuote, BybitPublicTickerBook,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    supervise_public_tickers, TickerLeaseBudget,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_intrahour_coordinator_d389 import PaperIntrahourDecision
from crypto_intelligence_agent.paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from crypto_intelligence_agent.paper_intrahour_target_step_d387 import PaperIntrahourTargetPolicy
from crypto_intelligence_agent.paper_intrahour_quote_router_d391 import (
    PaperQuoteRoute, PaperIntrahourQuoteRouter,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderIntent, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderEffect, PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    SyntheticExitPlan, SyntheticExitTranche, ExitBasis,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

T=1_800_000_000_000
MIN=60_000
ENTRY=T+5*MIN


def tick(at, *, seq=1, mark="100", bid="100", ask=None,
         symbol="BTCUSDT", lag=10):
    if ask is None:
        ask=str(D(bid)+D("0.02"))
    return BybitTickerQuote(
        symbol=symbol, exchange_at_ms=at-lag, received_at_ms=at,
        cross_sequence=seq, last_price=D(bid), mark_price=D(mark),
        index_price=D(mark), bid_price=D(bid), ask_price=D(ask),
        bid_size=D(2), ask_size=D(3), turnover_24h=None,
        volume_24h=None, funding_rate=None,
    )


class RouterD391Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"paper.sqlite"
        self.position_id="fixture_d391_one"
        self.store=SQLitePaperPositionJournal(self.path)
        entry=PaperOrderIntent(
            "fixture_d391_entry", "fixture_d391_signal",
            PaperVenue.BYBIT_V5, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.BUY, PaperOrderEffect.OPEN, D(100), ENTRY-10,
        )
        self.store.create_position(
            position_id=self.position_id, opening_intent=entry,
            opening_events=(PaperOrderEvent(
                "fixture_d391_entry_fill", PaperOrderEventKind.FILL,
                ENTRY, D(100)),),
            exit_plan=SyntheticExitPlan(
                initial_units=D(100),
                tranches=(SyntheticExitTranche(ExitBasis.INITIAL_POSITION,D(30)),
                          SyntheticExitTranche(ExitBasis.INITIAL_POSITION,D(20))),
                residual_floor_percent=D(50),
            ),
            plan_version="d391-plan", synthetic_lot_step_units=D(1),
            as_of_ms=ENTRY,
        )
        self.route=PaperQuoteRoute(
            self.position_id, PaperEmergencyStopRule(D(99)),
            PaperIntrahourTargetPolicy("d391-plan", (D(101),D(103))),
        )
        self.router=PaperIntrahourQuoteRouter(
            position_path=self.path,routes=(self.route,),
        )

    def test_two_partial_events_then_stop_in_one_hour_without_fabricating_fills(self):
        t1=T+12*MIN
        target=self.router.process(tick(t1,seq=1,bid="101"))
        self.assertEqual(target.decision,PaperIntrahourDecision.TARGET_RESERVED)
        self.assertEqual(self.store.load(self.position_id).filled_exit_units,D(0))
        self.assertEqual(self.store.load(self.position_id).reserved_unfilled_units,D(30))
        unresolved=self.router.process(tick(t1+1,seq=2,mark="98",bid="110"))
        self.assertEqual(unresolved.decision,PaperIntrahourDecision.STOP_UNRESOLVED)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders),1)
        self.store.append_exit_events(
            self.position_id,target.created_intent_id,
            (PaperOrderEvent("fixture_d391_explicit_fill",
                             PaperOrderEventKind.FILL,t1+2,D(30)),),
            as_of_ms=t1+2,
        )
        stop=self.router.process(tick(T+19*MIN,seq=3,mark="98",bid="110"))
        self.assertEqual(stop.decision,PaperIntrahourDecision.STOP_RESERVED)
        self.assertEqual(stop.stop.reserved_units,D(70))
        balances=self.store.load(self.position_id)
        self.assertEqual([x.tranche_step for x in balances.exit_orders],[1,-1])
        self.assertEqual(balances.confirmed_remaining_units,D(70))
        self.assertFalse(self.router.sanitized_report()["orders_sent"])

    def test_simultaneous_stop_and_target_reserves_one(self):
        r=self.router.process(tick(T+12*MIN,mark="98",bid="110"))
        self.assertEqual(r.decision,PaperIntrahourDecision.STOP_RESERVED)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders),1)
        self.assertEqual(self.store.load(self.position_id).exit_orders[0].tranche_step,-1)

    def test_exact_replay_not_reprocessed_or_refreshed(self):
        q=tick(T+12*MIN,mark="100",bid="101")
        a=self.router.process(q)
        self.assertIsNone(self.router.process(q))
        self.assertEqual(len(self.store.load(self.position_id).exit_orders),1)
        self.assertEqual(self.router.sanitized_report()["exact_duplicates_skipped"],1)
        self.assertEqual(a.decision,PaperIntrahourDecision.TARGET_RESERVED)

    def test_conflicting_sequence_and_stale_transport_fail_before_write(self):
        t=T+12*MIN
        self.router.process(tick(t,seq=1,bid="100"))
        with self.assertRaises(DataGapError):
            self.router.process(tick(t+1,seq=1,bid="110"))
        with self.assertRaises(DataGapError):
            self.router.process(tick(t+2,seq=0,bid="101"))
        with self.assertRaises(DataGapError):
            self.router.process(tick(t+3,seq=2,bid="110",lag=3500))
        self.assertEqual(len(self.store.load(self.position_id).exit_orders),0)

    def test_unrelated_symbol_does_not_change_position(self):
        self.assertIsNone(self.router.process(tick(T+12*MIN,symbol="ETHUSDT",bid="110")))
        self.assertEqual(self.router.sanitized_report()["other_symbols_ignored"],1)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders),0)
        self.assertNotIn("BTCUSDT",json.dumps(self.router.sanitized_report()))
        self.assertNotIn("fixture_d391_one",json.dumps(self.router.sanitized_report()))

    def test_invalid_policy_version_prevents_router_construction(self):
        bad=PaperQuoteRoute(
            self.position_id,PaperEmergencyStopRule(D(99)),
            PaperIntrahourTargetPolicy("wrong-plan",(D(101),D(103))),
        )
        with self.assertRaises(DataValidationError):
            PaperIntrahourQuoteRouter(position_path=self.path,routes=(bad,))
        with self.assertRaises(DataValidationError):
            PaperIntrahourQuoteRouter(position_path=self.path,
                                     routes=(self.route,self.route))

    def test_d386_supervisor_callback_reserves_paper_only(self):
        event=tick(T+12*MIN,seq=1,bid="101")
        raw=json.dumps({
            "topic":"tickers.BTCUSDT","type":"snapshot",
            "ts":event.exchange_at_ms,"cs":1,
            "data":{"symbol":"BTCUSDT","lastPrice":"101","markPrice":"100",
                    "indexPrice":"100","bid1Price":"101",
                    "ask1Price":"101.02","bid1Size":"2","ask1Size":"3"},
        })
        ack=json.dumps({"op":"subscribe","success":True,"ret_msg":"subscribe",
                        "conn_id":"fixture","req_id":"cia-ticker-1"})
        class Clock:
            def __init__(self):self.seconds=0
            def mono(self):return self.seconds
            def wall(self):return T+12*MIN
            def advance(self,seconds):self.seconds+=seconds
        class Socket:
            def __init__(self):self.queue=[ack,raw];self.closed=False
            def send(self,_):pass
            def recv(self,timeout):
                if self.queue:return self.queue.pop(0)
                clock.advance(timeout)
                raise TimeoutError()
            def close(self):self.closed=True
        clock=Clock()
        socket=Socket()
        book=BybitPublicTickerBook(
            ranked_symbols=("BTCUSDT",),universe_at_ms=T+10*MIN,
        )
        report=supervise_public_tickers(
            session_factory=lambda:socket,book=book,
            budget=TickerLeaseBudget(max_sessions=1,max_frames=10,max_seconds=3),
            clock=clock.mono,wall_ms=clock.wall,sleeper=clock.advance,
            on_quote=self.router.process,
        )
        self.assertTrue(socket.closed)
        self.assertEqual(report.ticker_frames_accepted,1)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders),1)
        self.assertEqual(self.store.load(self.position_id).exit_orders[0].tranche_step,1)
        self.assertFalse(report.sanitized_report()["orders_sent"])


if __name__=="__main__":
    unittest.main()
