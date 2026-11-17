"""D394 fake Bybit market replay -> one real AUTO4 PAPER ledger, offline."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_causal_fill_d394 import (
    PaperFillDecision, PaperObservedFillAssumptions, apply_causal_paper_fill_assumption,
)
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    HOUR_START_MS as T, MINUTE_MS as M, POSITION_ID,
    _new_position, _route, _tick,
)
from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitPublicTickerBook
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind,
)

POLICY = PaperObservedFillAssumptions()


class CausalPaperFillD394Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"paper.sqlite"
        self.store=_new_position(self.path,short=False)
        self.router=_route(self.path,short=False)
        self.book=BybitPublicTickerBook(
            ranked_symbols=("BTCUSDT",),universe_at_ms=T+M,
        )
        self.book.begin_acknowledged_session()
        self.at=T+12*M
        self.trigger=_tick(
            self.book,minute=12,cs=1,kind="snapshot",
            mark="100.5",bid="101",ask="101.02",
        )
        self.reserved=self.router.process(self.trigger)
        self.assertIsNotNone(self.reserved.created_intent_id)
        self.intent=self.reserved.created_intent_id

    def later(self,*,ms=200,cs=2,bid="101",ask="101.02",
              bid_size="40",ask_size="40"):
        return replace(self.trigger,
            received_at_ms=self.at+ms,
            exchange_at_ms=self.at+ms-25,
            cross_sequence=cs,
            bid_price=D(bid),ask_price=D(ask),
            bid_size=D(bid_size),ask_size=D(ask_size),
        )

    def apply(self,quote=None,*,at=None,optin=True,policy=POLICY):
        q=quote or self.later()
        return apply_causal_paper_fill_assumption(
            self.path,POSITION_ID,self.intent,quote=q,
            as_of_ms=q.received_at_ms if at is None else at,
            policy=policy,enable_synthetic_ledger_fills=optin,
        )

    def test_disabled_produces_no_fill_or_db_mutation(self):
        result=self.apply(optin=False)
        self.assertEqual(result.decision,PaperFillDecision.DISABLED)
        self.assertIsNone(result.receipt)
        b=self.store.load(POSITION_ID)
        self.assertEqual(b.filled_exit_units,D(0))
        self.assertEqual(b.reserved_unfilled_units,D(30))
        self.assertFalse(result.sanitized_report()["venue_fill_verified"])
        self.assertFalse(result.sanitized_report()["orders_sent"])

    def test_must_wait_beyond_intent_latency_and_not_derive_fill_from_trigger(self):
        early=self.apply(self.later(ms=100))
        self.assertEqual(early.decision,PaperFillDecision.TOO_EARLY)
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(0))
        result=self.apply(self.later(ms=200))
        self.assertEqual(result.decision,PaperFillDecision.ASSUMED_PARTIAL)
        self.assertEqual(result.recorded_units,D(10))
        self.assertEqual(result.remaining_order_units,D(20))
        self.assertEqual(result.receipt.reference_exit_price_quote,D("101"))
        saved=self.store.load(POSITION_ID)
        self.assertEqual(saved.filled_exit_units,D(10))
        self.assertEqual(saved.reserved_unfilled_units,D(20))
        self.assertEqual(len(saved.exit_orders),1)
        self.assertEqual(len(saved.exit_orders[0].events),1)

    def test_second_new_observation_fills_remainder_but_replay_does_not(self):
        first=self.apply(self.later(ms=200))
        replay=self.apply(self.later(ms=200))
        self.assertEqual(replay.decision,PaperFillDecision.ALREADY_RECORDED)
        self.assertEqual(replay.recorded_units,D(0))
        self.assertIsNone(replay.receipt)
        second=self.apply(self.later(ms=400,cs=3,bid_size="100"))
        self.assertEqual(second.decision,PaperFillDecision.ASSUMED_FULL)
        self.assertEqual(second.recorded_units,D(20))
        self.assertEqual(second.remaining_order_units,D(0))
        closed=self.apply(self.later(ms=600,cs=4))
        self.assertEqual(closed.decision,PaperFillDecision.BLOCKED)
        b=self.store.load(POSITION_ID)
        self.assertEqual(b.filled_exit_units,D(30))
        self.assertEqual(b.reserved_unfilled_units,D(0))
        self.assertEqual(len(b.exit_orders[0].events),2)
        self.assertNotEqual(first.event.event_id,second.event.event_id)

    def test_no_depth_or_spread_above_limit_abstains(self):
        insufficient=self.apply(self.later(bid_size="3"))
        self.assertEqual(insufficient.decision,PaperFillDecision.NO_LIQUIDITY)
        wide=self.apply(self.later(bid="100",ask="101",bid_size="100"))
        self.assertEqual(wide.decision,PaperFillDecision.TOO_WIDE)
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(0))
        self.assertEqual(self.store.load(POSITION_ID).reserved_unfilled_units,D(30))

    def test_stale_future_and_unmatched_scope_never_append(self):
        q=self.later(ms=200)
        stale=self.apply(q,at=q.received_at_ms+4000)
        self.assertEqual(stale.decision,PaperFillDecision.STALE)
        with self.assertRaises(DataValidationError):
            self.apply(replace(q,received_at_ms=q.exchange_at_ms-1))
        with self.assertRaises(DataValidationError):
            self.apply(replace(q,symbol="ETHUSDT"))
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(0))
    def test_unknown_blocks_hypothetical_fill_even_with_favorable_quote(self):
        event=PaperOrderEvent(
            "fixture_d394_unknown",PaperOrderEventKind.UNKNOWN,
            self.at+1,
        )
        self.store.append_exit_events(
            POSITION_ID,self.intent,(event,),as_of_ms=self.at+1,
        )
        result=self.apply()
        self.assertEqual(result.decision,PaperFillDecision.BLOCKED)
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(0))
        self.assertEqual(self.store.load(POSITION_ID).reserved_unfilled_units,D(30))

    def test_expired_observation_needs_reconciliation_not_fabricated_fill(self):
        q=self.later(ms=70_000)
        r=self.apply(q)
        self.assertEqual(r.decision,PaperFillDecision.TIMED_OUT)
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(0))

    def test_lot_size_rounds_down_never_increases_exposure(self):
        r=self.apply(self.later(bid_size="5"))
        self.assertEqual(r.decision,PaperFillDecision.ASSUMED_PARTIAL)
        self.assertEqual(r.recorded_units,D(1))
        self.assertEqual(r.remaining_order_units,D(29))

    def test_short_uses_ask_size_and_ask_price_for_buy_to_cover(self):
        from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
        with tempfile.TemporaryDirectory() as p:
            db=Path(p)/"short.sqlite"
            store=_new_position(db,short=True)
            router=_route(db,short=True)
            book=BybitPublicTickerBook(
                ranked_symbols=("BTCUSDT",),universe_at_ms=T+M,
            )
            book.begin_acknowledged_session()
            at=T+12*M
            trigger=_tick(
                book,minute=12,cs=1,kind="snapshot",
                mark="100",bid="98.98",ask="99",
            )
            reserved=router.process(trigger)
            self.assertIsNotNone(reserved.created_intent_id)
            later=replace(trigger,
                received_at_ms=at+200,exchange_at_ms=at+175,
                cross_sequence=2,ask_size=D(40),bid_size=D(2),
            )
            result=apply_causal_paper_fill_assumption(
                db,POSITION_ID,reserved.created_intent_id,
                quote=later,as_of_ms=at+200,
                policy=POLICY,enable_synthetic_ledger_fills=True,
            )
            self.assertEqual(result.decision,PaperFillDecision.ASSUMED_PARTIAL)
            self.assertEqual(result.recorded_units,D(10))
            self.assertEqual(result.receipt.reference_exit_price_quote,D(99))
            self.assertEqual(store.load(POSITION_ID).side,SyntheticSide.SHORT)

    def test_entire_post_latency_fill_cycle_connects_to_existing_d393_cost_audit(self):
        """D389 intents -> D394 hypothetical FILLs -> D393 conditional costs."""
        from crypto_intelligence_agent.paper_closed_cost_audit_d393 import (
            audit_closed_paper_costs,
        )
        from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
        from crypto_intelligence_agent.synthetic_partial_costed_replay import (
            SyntheticPartialCostRates,
        )

        receipts=[]
        def hypothesize(trigger,intent_id):
            at=trigger.received_at_ms
            post=replace(
                trigger,exchange_at_ms=at+175,
                received_at_ms=at+200,
                cross_sequence=trigger.cross_sequence+100,
                bid_size=D(500),ask_size=D(500),
            )
            result=apply_causal_paper_fill_assumption(
                self.path,POSITION_ID,intent_id,quote=post,
                as_of_ms=at+200,policy=POLICY,
                enable_synthetic_ledger_fills=True,
            )
            self.assertEqual(result.decision,PaperFillDecision.ASSUMED_FULL)
            self.assertIsNotNone(result.receipt)
            receipts.append(result.receipt)
            return result

        first=hypothesize(self.trigger,self.intent)
        self.assertEqual(first.recorded_units,D(30))
        q2=_tick(self.book,minute=19,cs=2,kind="delta",
                 mark="102.5",bid="103",ask="103.02")
        target2=self.router.process(q2)
        self.assertIsNotNone(target2.created_intent_id)
        second=hypothesize(q2,target2.created_intent_id)
        self.assertEqual(second.recorded_units,D(20))
        q3=_tick(self.book,minute=27,cs=3,kind="delta",
                 mark="98",bid="98",ask="98.02")
        stop=self.router.process(q3)
        self.assertIsNotNone(stop.created_intent_id)
        third=hypothesize(q3,stop.created_intent_id)
        self.assertEqual(third.recorded_units,D(50))
        snapshot=self.store.load(POSITION_ID)
        self.assertEqual(snapshot.filled_exit_units,D(100))
        self.assertEqual(snapshot.confirmed_remaining_units,D(0))
        self.assertEqual(len(snapshot.exit_orders),3)
        funding=(SyntheticFundingEvent(
            "fixture_funding_d394",T+13*M,D(7000),D(2),
        ),)
        audit=audit_closed_paper_costs(
            self.path,POSITION_ID,
            entry_reference_price_quote=D(100),
            fill_references=tuple(receipts),
            cost_rates=SyntheticPartialCostRates(D(10),D(10),D(5),D(5)),
            funding_events=funding,
        )
        self.assertEqual(
            audit.conditional_net_after_supplied_costs_quote,D("-41.385"),
        )
        self.assertFalse(audit.sanitized_report()["net_pnl_verified"])
        self.assertFalse(audit.sanitized_report()["liquidation_risk_verified"])
        self.assertFalse(third.sanitized_report()["venue_fill_verified"])

    def test_invalid_settings_abstain_before_any_write(self):
        zero_spread=PaperObservedFillAssumptions(max_spread_bps=D(0))
        self.assertEqual(self.apply(self.later(),policy=zero_spread).decision,
                         PaperFillDecision.TOO_WIDE)
        short_age=PaperObservedFillAssumptions(max_quote_age_ms=100)
        q=self.later()
        self.assertEqual(self.apply(q,policy=short_age,at=q.received_at_ms+250).decision,
                         PaperFillDecision.STALE)
        for kwargs in ({"max_top_level_participation_bps":D(0)},
                       {"min_quote_after_intent_ms":0},
                       {"max_quote_age_ms":0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(DataValidationError):
                    PaperObservedFillAssumptions(**kwargs)
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units,D(0))


if __name__ == "__main__":
    unittest.main()
