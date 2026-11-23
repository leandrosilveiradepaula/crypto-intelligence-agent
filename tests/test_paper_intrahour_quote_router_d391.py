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
from crypto_intelligence_agent.paper_causal_fill_d394 import PaperObservedFillAssumptions
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

    def test_closed_history_kept_and_later_same_symbol_can_be_monitored(self):
        opened = self.router.process(tick(T+12*MIN,seq=1,mark="98",bid="98"))
        self.assertEqual(opened.decision,PaperIntrahourDecision.STOP_RESERVED)
        self.store.append_exit_events(
            self.position_id, opened.created_intent_id,
            (PaperOrderEvent("fixture_d501_close_old",PaperOrderEventKind.FILL,
                             T+12*MIN+200,D(100)),),
            as_of_ms=T+12*MIN+200,
        )
        old=self.store.load(self.position_id)
        self.assertEqual(old.confirmed_remaining_units,D(0))
        new_id="fixture_d501_reopened_btc"
        new_time=T+16*MIN
        self.store.create_position(
            position_id=new_id,
            opening_intent=PaperOrderIntent(
                "fixture_d501_new_open","fixture_d501_new_signal",
                PaperVenue.BYBIT_V5,"BTCUSDT",SyntheticSide.LONG,
                PaperOrderSide.BUY,PaperOrderEffect.OPEN,D(50),new_time-10,
            ),
            opening_events=(PaperOrderEvent(
                "fixture_d501_new_open_fill",PaperOrderEventKind.FILL,
                new_time,D(50)),),
            exit_plan=SyntheticExitPlan(
                initial_units=D(50),
                tranches=(SyntheticExitTranche(ExitBasis.INITIAL_POSITION,D(30)),
                          SyntheticExitTranche(ExitBasis.INITIAL_POSITION,D(20))),
                residual_floor_percent=D(50),
            ),
            plan_version="d501-plan",synthetic_lot_step_units=D(1),
            as_of_ms=new_time,
        )
        replacement=PaperQuoteRoute(
            new_id,PaperEmergencyStopRule(D(99)),
            PaperIntrahourTargetPolicy("d501-plan",(D(101),D(103))),
        )
        reopened=PaperIntrahourQuoteRouter(
            position_path=self.path,routes=(self.route,replacement),
        )
        self.assertEqual(reopened.monitored_symbols,frozenset({"BTCUSDT"}))
        self.assertEqual(set(reopened.monitored_position_ids),
                         {self.position_id,new_id})
        self.assertEqual(reopened.route_for_position(self.position_id),
                         self.route)
        self.assertEqual(reopened.route_for_position(new_id),replacement)
        self.assertEqual(
            reopened.process(tick(T+20*MIN,seq=2,mark="100",bid="100")).decision,
            PaperIntrahourDecision.TARGET_HOLD,
        )
        self.assertEqual(self.store.load(self.position_id).confirmed_remaining_units,D(0))
        self.assertEqual(self.store.load(new_id).confirmed_remaining_units,D(50))

    def test_exact_replay_not_reprocessed_or_refreshed(self):
        q=tick(T+12*MIN,mark="100",bid="101")
        a=self.router.process(q)
        self.assertIsNone(self.router.process(q))
        self.assertEqual(len(self.store.load(self.position_id).exit_orders),1)
        self.assertEqual(self.router.sanitized_report()["exact_duplicates_skipped"],1)
        self.assertEqual(a.decision,PaperIntrahourDecision.TARGET_RESERVED)

    def test_opt_in_fill_waits_for_later_quote_and_never_retries_unknown(self):
        router = PaperIntrahourQuoteRouter(
            position_path=self.path, routes=(self.route,),
            fill_assumptions=PaperObservedFillAssumptions(
                min_quote_after_intent_ms=150,
                max_top_level_participation_bps=D(10000),
            ), enable_synthetic_ledger_fills=True,
        )
        first = router.process(tick(T + 12 * MIN, seq=1, bid="101"))
        self.assertEqual(first.decision, PaperIntrahourDecision.TARGET_RESERVED)
        # The quote that created the reservation is never a fill witness.
        self.assertEqual(self.store.load(self.position_id).filled_exit_units, D(0))
        later = router.process(tick(T + 12 * MIN + 200, seq=2, bid="101"))
        self.assertEqual(later.decision, PaperIntrahourDecision.TARGET_PENDING)
        self.assertEqual(self.store.load(self.position_id).filled_exit_units, D(2))
        # A byte-identical replay cannot append a second assumed fill.
        self.assertIsNone(router.process(tick(T + 12 * MIN + 200, seq=2, bid="101")))
        self.assertEqual(self.store.load(self.position_id).filled_exit_units, D(2))

    def test_default_and_optin_keep_existing_d391_health_report_contract(self):
        # D412's strict mobile reader consumes exactly the legacy D391 fields.
        # A simulated FILL must not silently mutate the D391 report schema v1.
        normal = self.router.sanitized_report()
        self.assertEqual(normal["schema_version"], "paper-intrahour-quote-router-d391-v1")
        expected = {
            "schema_version", "status", "configured_positions", "events_seen",
            "exact_duplicates_skipped", "other_symbols_ignored",
            "decision_counts", "runner_decision_counts", "feed_authenticated",
            "marketwide_top50_verified", "native_stop_verified",
            "order_submission_enabled", "orders_sent", "approved_for_live_use",
        }
        self.assertEqual(set(normal), expected)
        opted_in = PaperIntrahourQuoteRouter(
            position_path=self.path, routes=(self.route,),
            fill_assumptions=PaperObservedFillAssumptions(
                min_quote_after_intent_ms=150,
                max_top_level_participation_bps=D(10000),
            ), enable_synthetic_ledger_fills=True,
        )
        t = T + 12 * MIN
        opted_in.process(tick(t, seq=1, bid="101"))
        opted_in.process(tick(t + 200, seq=2, bid="101"))
        self.assertEqual(self.store.load(self.position_id).filled_exit_units, D(2))
        report = opted_in.sanitized_report()
        self.assertEqual(set(report), expected)
        self.assertFalse(report["orders_sent"])

    def test_router_optin_unknown_remains_unresolved_and_never_assumes_fill(self):
        router = PaperIntrahourQuoteRouter(
            position_path=self.path, routes=(self.route,),
            fill_assumptions=PaperObservedFillAssumptions(
                min_quote_after_intent_ms=150,
                max_top_level_participation_bps=D(10000),
            ), enable_synthetic_ledger_fills=True,
        )
        t = T + 12 * MIN
        reserved = router.process(tick(t, seq=1, bid="101"))
        self.store.append_exit_events(
            self.position_id, reserved.created_intent_id,
            (PaperOrderEvent(
                "fixture_d433_unknown_exit", PaperOrderEventKind.UNKNOWN, t + 1,
            ),), as_of_ms=t + 1,
        )
        router.process(tick(t + 200, seq=2, bid="101"))
        before = self.store.load(self.position_id)
        self.assertEqual(before.filled_exit_units, D(0))
        self.assertEqual(before.reserved_unfilled_units, D(30))
        self.assertEqual(len(before.exit_orders), 1)
        self.assertIsNone(router.process(tick(t + 200, seq=2, bid="101")))
        after = self.store.load(self.position_id)
        self.assertEqual(after.filled_exit_units, D(0))
        self.assertEqual(len(after.exit_orders), 1)

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

    def test_reconnect_restarts_sequence_not_time_or_paper_reservations(self):
        earlier = tick(T + 12 * MIN, seq=99, bid="101")
        original = self.router.process(earlier)
        self.assertEqual(original.decision, PaperIntrahourDecision.TARGET_RESERVED)
        self.router.begin_new_market_session()
        # A delayed replay from a previous socket cannot be admitted just
        # because the Bybit cross-sequence counter restarted.
        with self.assertRaises(DataGapError):
            self.router.process(tick(T + 12 * MIN, seq=1, bid="101"))
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)
        newer = self.router.process(tick(T + 12 * MIN + 1000, seq=1, bid="101"))
        self.assertIsNotNone(newer)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)
        self.assertFalse(self.router.sanitized_report()["orders_sent"])

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


    def test_d401_optin_lease_routes_only_valid_post_ack_paper_quotes(self):
        from crypto_intelligence_agent.bybit_public_ticker_optin_d390 import (
            run_readonly_bybit_ticker_lease,
        )
        clock_ms = T + 12 * MIN
        raw = json.dumps({
            "topic": "tickers.BTCUSDT", "type": "snapshot",
            "ts": clock_ms - 10, "cs": 1,
            "data": {"symbol": "BTCUSDT", "lastPrice": "101",
                     "markPrice": "100", "indexPrice": "100",
                     "bid1Price": "101", "ask1Price": "101.02",
                     "bid1Size": "2", "ask1Size": "3"},
        })
        ack = json.dumps({"op": "subscribe", "success": True,
                          "ret_msg": "subscribe", "conn_id": "fixture",
                          "req_id": "cia-ticker-1"})
        class Clock:
            elapsed = 0
            def mono(self): return self.elapsed
            def wall(self): return clock_ms + int(self.elapsed * 1000)
            def sleep(self, seconds): self.elapsed += seconds
        class Socket:
            def __init__(self, clock, responses):
                self.clock = clock
                self.responses = list(responses)
                self.closed = False
            def send(self, _payload): pass
            def recv(self, timeout):
                if self.responses:
                    item = self.responses.pop(0)
                    if isinstance(item, Exception): raise item
                    return item
                self.clock.sleep(timeout)
                raise TimeoutError()
            def close(self): self.closed = True
        c = Clock()
        socket = Socket(c, [ack, raw])
        config = dict(
            ranked_symbols=("BTCUSDT",),
            universe_at_ms=T + 10 * MIN,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            budget=TickerLeaseBudget(max_sessions=1, max_frames=12,
                                     max_seconds=3),
            session_factory=lambda: socket, clock=c.mono,
            wall_ms=c.wall, sleeper=c.sleep,
            paper_router=self.router,
        )
        report = run_readonly_bybit_ticker_lease(**config)
        self.assertTrue(socket.closed)
        self.assertEqual(report["ticker_frames_accepted"], 1)
        self.assertEqual(report["paper_monitoring"]["configured_positions"], 1)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)
        self.assertEqual(self.store.load(self.position_id).filled_exit_units, D(0))
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["paper_monitoring"]["orders_sent"])
        self.assertNotIn(self.position_id, json.dumps(report))

    def test_d401_out_of_scope_paper_position_rejected_before_socket(self):
        from crypto_intelligence_agent.bybit_public_ticker_optin_d390 import (
            run_readonly_bybit_ticker_lease,
        )
        called = []
        with self.assertRaises(DataValidationError):
            run_readonly_bybit_ticker_lease(
                ranked_symbols=("ETHUSDT",), universe_at_ms=T,
                paper_router=self.router,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                session_factory=lambda: called.append(1),
            )
        self.assertEqual(called, [])
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 0)


if __name__=="__main__":
    unittest.main()
