"""D387 / #676: intrahour automatic PAPER partials over the real AUTO4 journal.

No broker account, network, or fake broker fill on touch.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitTickerQuote
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_intrahour_target_step_d387 import (
    PaperIntrahourTargetPolicy, PaperAutoTargetState, step_paper_intrahour_target,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderIntent, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderEffect, PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    SyntheticExitPlan, SyntheticExitTranche, ExitBasis,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

START = 1_800_000_000_000  # UTC hour grid
MIN = 60_000
ENTRY = START + 5 * MIN


def sample_quote(at, *, bid="101", ask=None, last=None,
                 symbol="BTCUSDT", seq=1, qty="2"):
    if ask is None:
        ask = str(D(bid) + D("0.02"))
    if last is None:
        last = bid
    return BybitTickerQuote(
        symbol=symbol,
        exchange_at_ms=at - 20,
        received_at_ms=at,
        cross_sequence=seq,
        last_price=D(last),
        mark_price=D(bid),
        index_price=D(bid),
        bid_price=D(bid),
        ask_price=D(ask),
        bid_size=D(qty),
        ask_size=D(qty),
        turnover_24h=None, volume_24h=None, funding_rate=None,
    )


class PaperIntrahourAutoTargetD387Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "paper-position.sqlite"
        self.store = SQLitePaperPositionJournal(self.path)
        self.position_id = "fixture_auto_intrahour_A"
        self.policy = PaperIntrahourTargetPolicy(
            plan_version="auto-target-2026-11",
            prices=(D("101"), D("103")),
        )

    def open(self, *, side=SyntheticSide.LONG, venue=PaperVenue.BYBIT_V5,
             position_id=None):
        entry_id = "fixture_open_auto_long" if side is SyntheticSide.LONG else "fixture_open_auto_short"
        opening = PaperOrderIntent(
            intent_id=entry_id,
            fixture_signal_id="fixture_signal_auto_open",
            venue=venue, symbol="BTCUSDT",
            position_side=side,
            side=(PaperOrderSide.BUY if side is SyntheticSide.LONG else PaperOrderSide.SELL),
            effect=PaperOrderEffect.OPEN,
            requested_units=D(100),
            created_at_ms=ENTRY - 100,
        )
        evt = PaperOrderEvent(
            event_id="fixture_auto_open_fill",
            kind=PaperOrderEventKind.FILL,
            event_at_ms=ENTRY,
            filled_units=D(100),
        )
        plan = SyntheticExitPlan(
            initial_units=D(100),
            tranches=(
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(30)),
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(20)),
            ),
            residual_floor_percent=D(50),
        )
        return self.store.create_position(
            position_id=position_id or self.position_id,
            opening_intent=opening, opening_events=(evt,),
            exit_plan=plan, plan_version=self.policy.plan_version,
            synthetic_lot_step_units=D(1), as_of_ms=ENTRY,
        )

    def step(self, at, *, bid="101", ask=None, last=None, seq=1,
             policy=None, symbol="BTCUSDT", cutoff=None, qty="2"):
        q = sample_quote(at, bid=bid, ask=ask, last=last,
                         symbol=symbol, seq=seq, qty=qty)
        return step_paper_intrahour_target(
            self.path, self.position_id,
            policy=policy or self.policy, quote=q,
            as_of_ms=at if cutoff is None else cutoff,
        )

    def test_multiple_partial_targets_in_same_hour_without_click_or_fabricated_fill(self):
        self.open()
        t1, t2 = START + 12 * MIN, START + 19 * MIN
        first = self.step(t1, bid="101")
        self.assertEqual(first.state, PaperAutoTargetState.RESERVED)
        self.assertEqual(first.tranche_step, 1)
        self.assertEqual(first.reserved_units, D(30))
        self.assertEqual(first.remaining_units, D(100))
        self.assertFalse(first.orders_sent)
        self.assertFalse(first.native_stop_verified)
        self.assertFalse(first.sanitized_report()["real_fill_verified"])
        self.assertEqual(self.store.load(self.position_id).filled_exit_units, D(0))

        repeated = self.step(t1, bid="101", seq=1)
        self.assertEqual(repeated.state, PaperAutoTargetState.PENDING)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)
        too_early_second = self.step(t2, bid="103", seq=2)
        self.assertEqual(too_early_second.state, PaperAutoTargetState.PENDING)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)

        fill1 = PaperOrderEvent(
            "fixture_auto_fill_one", PaperOrderEventKind.FILL, t2 + 1, D(30),
        )
        b = self.store.append_exit_events(self.position_id, first.intent_id,
                                          (fill1,), as_of_ms=t2 + 1)
        self.assertEqual(b.confirmed_remaining_units, D(70))
        self.assertEqual(b.runner_floor_units, D(50))
        second = self.step(t2 + 2, bid="103", seq=3)
        self.assertEqual(second.state, PaperAutoTargetState.RESERVED)
        self.assertEqual(second.tranche_step, 2)
        self.assertEqual(second.reserved_units, D(20))
        self.assertEqual(second.remaining_units, D(70))
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 2)
        fill2 = PaperOrderEvent(
            "fixture_auto_fill_two", PaperOrderEventKind.FILL, t2 + 3, D(20),
        )
        b = self.store.append_exit_events(self.position_id, second.intent_id,
                                          (fill2,), as_of_ms=t2 + 3)
        self.assertEqual(b.confirmed_remaining_units, D(50))
        self.assertEqual(b.reserved_unfilled_units, D(0))
        self.assertEqual(self.step(START+27*MIN, bid="104", seq=4).state,
                         PaperAutoTargetState.DONE)

    def test_short_position_automatically_triggers_buy_reduce_only(self):
        self.policy = PaperIntrahourTargetPolicy(
            plan_version=self.policy.plan_version, prices=(D(99), D(97)),
        )
        self.open(side=SyntheticSide.SHORT)
        t = START + 12 * MIN
        hold = self.step(t, bid="99.00", ask="99.10")
        self.assertEqual(hold.state, PaperAutoTargetState.HOLD)
        reserved = self.step(t + 10, bid="98.95", ask="99.00")
        self.assertEqual(reserved.state, PaperAutoTargetState.RESERVED)
        order = self.store.load(self.position_id).exit_orders[0].intent
        self.assertEqual(order.side, PaperOrderSide.BUY)
        self.assertEqual(order.effect, PaperOrderEffect.REDUCE_ONLY)
        self.assertEqual(order.requested_units, D(30))

    def test_last_price_touch_without_executable_bid_does_not_trigger(self):
        self.open()
        t = START + 12 * MIN
        hold = self.step(t, bid="100.8", ask="100.82", last="110")
        self.assertEqual(hold.state, PaperAutoTargetState.HOLD)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 0)

    def test_unknown_and_partial_fills_keep_reservation_without_retry(self):
        self.open()
        t = START + 12 * MIN
        a = self.step(t, bid="101")
        unknown = PaperOrderEvent(
            "fixture_auto_unknown", PaperOrderEventKind.UNKNOWN, t + 1,
        )
        b = self.store.append_exit_events(
            self.position_id, a.intent_id, (unknown,), as_of_ms=t+1)
        self.assertEqual(b.reserved_unfilled_units, D(30))
        again = self.step(t+2, bid="103", seq=2)
        self.assertEqual(again.state, PaperAutoTargetState.PENDING)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)

        fill = PaperOrderEvent("fixture_auto_partial", PaperOrderEventKind.FILL,
                               t+3, D(10))
        b = self.store.append_exit_events(self.position_id, a.intent_id,
                                          (fill,), as_of_ms=t+3)
        self.assertEqual(b.reserved_unfilled_units, D(20))
        self.assertEqual(self.step(t+4, bid="105", seq=3).state,
                         PaperAutoTargetState.PENDING)

    def test_rejected_order_needs_review_never_auto_retries(self):
        self.open()
        t = START + 12 * MIN
        step = self.step(t, bid="101")
        rejected = PaperOrderEvent(
            "fixture_auto_rejected", PaperOrderEventKind.REJECTED, t+1)
        self.store.append_exit_events(self.position_id, step.intent_id,
                                      (rejected,), as_of_ms=t+1)
        r = self.step(t+2, bid="104", seq=2)
        self.assertEqual(r.state, PaperAutoTargetState.MANUAL_RECONCILIATION)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)

    def test_stale_spread_and_empty_book_abstain_without_reservation(self):
        self.open()
        t = START + 12 * MIN
        self.assertEqual(self.step(t, cutoff=t+3_100).state,
                         PaperAutoTargetState.STALE)
        self.assertEqual(self.step(t+10, bid="101", ask="110").state,
                         PaperAutoTargetState.SPREAD)
        self.assertEqual(self.step(t+20, bid="101", qty="0").state,
                         PaperAutoTargetState.STALE)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 0)

    def test_wrong_symbol_policy_venue_or_noncausal_quote_is_rejected(self):
        self.open()
        t = START + 12 * MIN
        with self.assertRaises(DataValidationError):
            self.step(t, symbol="ETHUSDT")
        bad = PaperIntrahourTargetPolicy(
            plan_version="different-plan", prices=(D(101), D(103)))
        with self.assertRaises(DataValidationError):
            self.step(t, policy=bad)
        with self.assertRaises(DataGapError):
            self.step(ENTRY-1000)
        with self.assertRaises(DataValidationError):
            step_paper_intrahour_target(
                self.path, self.position_id, policy=self.policy,
                quote=None, as_of_ms=t,
            )
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 0)

    def test_concurrent_identical_quote_reserves_only_one_intent(self):
        self.open()
        t = START+12*MIN

        def one(_):
            return self.step(t, bid="101")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(one, (1,2)))
        self.assertTrue(any(r.state is PaperAutoTargetState.RESERVED for r in results))
        current = self.store.load(self.position_id)
        self.assertEqual(current.reserved_unfilled_units, D(30))
        self.assertEqual(len(current.exit_orders), 1)
        self.assertEqual(current.filled_exit_units, D(0))
        self.assertEqual(current.exit_orders[0].snapshot.status, PaperOrderStatus.PENDING)

    def test_binance_historical_paper_position_cannot_be_managed_as_bybit(self):
        self.open(venue=PaperVenue.BINANCE_USDM)
        with self.assertRaises(DataValidationError):
            self.step(START+12*MIN)

    def test_input_and_output_guardrails(self):
        for levels in ((D(0), D(1)), (D("NaN"), D(2)), (D(101), D(101)),
                       (D(102), D(101))):
            if levels[0] == levels[1] or levels == (D(102), D(101)):
                # This is rejected at evaluation when we know LONG/SHORT.
                self.open()
                with self.assertRaises(DataValidationError):
                    self.step(START+12*MIN, policy=PaperIntrahourTargetPolicy(
                        plan_version=self.policy.plan_version, prices=levels))
                self.assertEqual(len(self.store.load(self.position_id).exit_orders), 0)
                break
            with self.assertRaises(DataValidationError):
                PaperIntrahourTargetPolicy(
                    plan_version=self.policy.plan_version, prices=levels)
        self.assertFalse(self.step(START+12*MIN).sanitized_report()["orders_sent"])


if __name__ == "__main__":
    unittest.main()
