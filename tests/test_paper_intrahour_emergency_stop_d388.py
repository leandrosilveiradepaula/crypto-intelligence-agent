"""D388: early protective stop before target tranches in existing PAPER journal."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitTickerQuote
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from crypto_intelligence_agent.paper_intrahour_emergency_stop_d388 import (
    PaperEmergencyStopRule, PaperEmergencyStopState, step_paper_emergency_stop,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderIntent, PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    SyntheticExitPlan, SyntheticExitTranche, ExitBasis,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide

START = 1_800_000_000_000
MIN = 60_000
ENTRY = START + 5 * MIN


def quote(at, *, mark="98", last="101", bid="100", ask="100.02", qty="2",
          symbol="BTCUSDT"):
    return BybitTickerQuote(
        symbol=symbol, exchange_at_ms=at - 10, received_at_ms=at,
        cross_sequence=1, last_price=D(last), mark_price=D(mark),
        index_price=D(mark), bid_price=D(bid), ask_price=D(ask),
        bid_size=D(qty), ask_size=D(qty),
        turnover_24h=None, volume_24h=None, funding_rate=None,
    )


class ProtectivePaperStopD388Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)/"paper-stop.sqlite"
        self.position_id = "fixture_stop_position"
        self.store = SQLitePaperPositionJournal(self.path)
        self.rule = PaperEmergencyStopRule(D(99))

    def open(self, *, side=SyntheticSide.LONG):
        intent = PaperOrderIntent(
            "fixture_stop_open_long" if side is SyntheticSide.LONG else "fixture_stop_open_short",
            "fixture_stop_open_signal",
            PaperVenue.BYBIT_V5, "BTCUSDT", side,
            PaperOrderSide.BUY if side is SyntheticSide.LONG else PaperOrderSide.SELL,
            PaperOrderEffect.OPEN, D(100), ENTRY - 100,
        )
        ev = PaperOrderEvent("fixture_stop_open_fill", PaperOrderEventKind.FILL,
                             ENTRY, D(100))
        plan = SyntheticExitPlan(
            initial_units=D(100),
            tranches=(SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(30)),
                      SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(20))),
            residual_floor_percent=D(50),
        )
        return self.store.create_position(
            position_id=self.position_id, opening_intent=intent,
            opening_events=(ev,), exit_plan=plan, plan_version="stop-plan-v1",
            synthetic_lot_step_units=D(1), as_of_ms=ENTRY,
        )

    def step(self, t, *, mark="98", last="110", bid="100", ask="100.02",
             qty="2", rule=None, cutoff=None):
        return step_paper_emergency_stop(
            self.path, self.position_id,
            rule=rule or self.rule,
            quote=quote(t, mark=mark, last=last, bid=bid, ask=ask, qty=qty),
            as_of_ms=t if cutoff is None else cutoff,
        )

    def test_stop_triggers_before_first_target_no_fictitious_fill(self):
        self.open()
        t=START+8*MIN
        result=self.step(t, mark="98", last="110", bid="100")
        self.assertEqual(result.state, PaperEmergencyStopState.RESERVED)
        self.assertEqual(result.reserved_units, D(100))
        self.assertEqual(result.confirmed_remaining_units, D(100))
        self.assertFalse(result.orders_sent)
        self.assertFalse(result.native_stop_verified)
        self.assertFalse(result.sanitized_report()["real_fill_verified"])
        saved=self.store.load(self.position_id)
        self.assertEqual(saved.filled_exit_units, D(0))
        self.assertEqual(saved.protective_reserved_unfilled_units, D(100))
        self.assertEqual(saved.runner_floor_units, D(50))
        self.assertEqual(saved.runner_unallocated_units, D(0))
        self.assertTrue(saved.protective_stop_seen)
        self.assertEqual(saved.exit_orders[0].tranche_step, -1)
        self.assertEqual(saved.exit_orders[0].intent.side, PaperOrderSide.SELL)
        self.assertEqual(saved.exit_orders[0].intent.effect, PaperOrderEffect.REDUCE_ONLY)

        duplicated=self.step(t+1)
        self.assertEqual(duplicated.state, PaperEmergencyStopState.PENDING)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)
        fill=PaperOrderEvent("fixture_stop_filled_all", PaperOrderEventKind.FILL,
                             t+2, D(100))
        after=self.store.append_exit_events(
            self.position_id, result.created_intent_id, (fill,), as_of_ms=t+2)
        self.assertEqual(after.confirmed_remaining_units, D(0))
        self.assertEqual(after.protective_filled_units, D(100))
        self.assertEqual(after.protective_reserved_unfilled_units, D(0))
        self.assertEqual(self.step(t+3).state, PaperEmergencyStopState.CLOSED)

    def test_stop_after_first_partial_fill_covers_remaining_not_initial(self):
        b=self.open()
        t=START+12*MIN
        partial=PaperOrderIntent(
            "fixture_partial_before_stop", "fixture_partial_before_signal",
            PaperVenue.BYBIT_V5, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.SELL, PaperOrderEffect.REDUCE_ONLY,
            D(30), t, D(100),
        )
        self.store.reserve_exit(self.position_id, 1, partial, as_of_ms=t)
        e=PaperOrderEvent("fixture_prior_partial_fill", PaperOrderEventKind.FILL,
                          t+1, D(30))
        updated=self.store.append_exit_events(
            self.position_id, partial.intent_id, (e,), as_of_ms=t+1)
        self.assertEqual(updated.confirmed_remaining_units, D(70))
        s=self.step(t+2, mark="98")
        self.assertEqual(s.state, PaperEmergencyStopState.RESERVED)
        self.assertEqual(s.reserved_units, D(70))
        saved=self.store.load(self.position_id)
        self.assertEqual(saved.reserved_unfilled_units, D(70))
        self.assertEqual(saved.unreserved_units, D(0))
        self.assertEqual(saved.filled_exit_units, D(30))
        self.assertEqual(saved.tranches[0].filled_units, D(30))

    def test_pending_or_unknown_partial_blocks_competing_stop(self):
        self.open()
        t=START+12*MIN
        partial=PaperOrderIntent(
            "fixture_pending_prior", "fixture_pending_signal",
            PaperVenue.BYBIT_V5, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.SELL, PaperOrderEffect.REDUCE_ONLY,
            D(30), t, D(100),
        )
        self.store.reserve_exit(self.position_id, 1, partial, as_of_ms=t)
        r=self.step(t+1)
        self.assertEqual(r.state, PaperEmergencyStopState.OLDER_ORDER_UNRESOLVED)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)
        e=PaperOrderEvent("fixture_prior_unknown", PaperOrderEventKind.UNKNOWN, t+2)
        self.store.append_exit_events(self.position_id, partial.intent_id,
                                      (e,), as_of_ms=t+2)
        self.assertEqual(self.step(t+3).state,
                         PaperEmergencyStopState.OLDER_ORDER_UNRESOLVED)
        # After an explicit cancellation, remaining quantity is no longer reserved.
        cancel=PaperOrderEvent("fixture_prior_cancelled", PaperOrderEventKind.CANCELLED,
                               t+4)
        self.store.append_exit_events(self.position_id, partial.intent_id,
                                      (cancel,), as_of_ms=t+4)
        self.assertEqual(self.step(t+5).state, PaperEmergencyStopState.RESERVED)

    def test_short_stop_uses_mark_not_last_and_is_buy_reduce_only(self):
        self.open(side=SyntheticSide.SHORT)
        self.rule=PaperEmergencyStopRule(D(102))
        t=START+8*MIN
        self.assertEqual(self.step(t, mark="101", last="110").state,
                         PaperEmergencyStopState.HOLD)
        # Last has already crossed but mark has not: no stop yet.
        step=self.step(t+1, mark="103", last="100")
        self.assertEqual(step.state, PaperEmergencyStopState.RESERVED)
        intent=self.store.load(self.position_id).exit_orders[0].intent
        self.assertEqual(intent.side, PaperOrderSide.BUY)

    def test_older_order_terminal_stop_requires_reconciliation_not_retry(self):
        self.open()
        t=START+8*MIN
        first=self.step(t)
        self.store.append_exit_events(
            self.position_id, first.created_intent_id,
            (PaperOrderEvent("fixture_stop_unknown", PaperOrderEventKind.UNKNOWN, t+1),),
            as_of_ms=t+1,
        )
        self.assertEqual(self.step(t+2).state, PaperEmergencyStopState.PENDING)
        self.store.append_exit_events(
            self.position_id, first.created_intent_id,
            (PaperOrderEvent("fixture_stop_cancel", PaperOrderEventKind.CANCELLED, t+3),),
            as_of_ms=t+3,
        )
        self.assertEqual(self.step(t+4).state,
                         PaperEmergencyStopState.MANUAL_RECONCILIATION)
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 1)

    def test_new_manual_tranche_after_protective_stop_rejected(self):
        self.open()
        t=START+8*MIN
        self.step(t)
        b=self.store.load(self.position_id)
        before=self.path.read_bytes()
        second=PaperOrderIntent(
            "fixture_after_stop_partial", "fixture_after_stop_signal",
            PaperVenue.BYBIT_V5, "BTCUSDT", SyntheticSide.LONG,
            PaperOrderSide.SELL, PaperOrderEffect.REDUCE_ONLY,
            D(30), t+1, D(100),
        )
        with self.assertRaises(DataValidationError):
            self.store.reserve_exit(self.position_id, 1, second, as_of_ms=t+1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(b.protective_stop_seen)

    def test_stale_wrong_symbol_futures_and_zero_depth_fail_without_new_order(self):
        self.open()
        t=START+8*MIN
        self.assertEqual(self.step(t, cutoff=t+3_100).state,
                         PaperEmergencyStopState.STALE)
        self.assertEqual(self.step(t+1, qty="0").state,
                         PaperEmergencyStopState.STALE)
        self.assertEqual(self.step(t+2, bid="110", ask="100").state,
                         PaperEmergencyStopState.STALE)
        with self.assertRaises(DataValidationError):
            step_paper_emergency_stop(
                self.path, self.position_id, rule=self.rule,
                quote=quote(t, symbol="ETHUSDT"), as_of_ms=t,
            )
        with self.assertRaises(DataGapError):
            self.step(ENTRY-100, mark="98")
        self.assertEqual(len(self.store.load(self.position_id).exit_orders), 0)

    def test_concurrent_stop_calls_one_protective_reservation(self):
        self.open()
        t=START+8*MIN
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:self.step(t), (0,1)))
        self.assertTrue(any(x.state is PaperEmergencyStopState.RESERVED for x in results))
        saved=self.store.load(self.position_id)
        self.assertEqual(len(saved.exit_orders), 1)
        self.assertEqual(saved.protective_reserved_unfilled_units, D(100))
        self.assertEqual(saved.filled_exit_units, D(0))

    def test_input_safety_and_readonly_output(self):
        for price in [D(0), D("-1"), D("NaN")]:
            with self.assertRaises(DataValidationError):
                PaperEmergencyStopRule(price)
        self.open()
        t=START+8*MIN
        result=self.step(t)
        self.assertFalse(result.sanitized_report()["orders_sent"])
        self.assertFalse(result.sanitized_report()["approved_for_live_use"])
        self.assertFalse(result.sanitized_report()["native_stop_verified"])
        self.assertNotIn(self.position_id, str(result.sanitized_report()))


if __name__ == "__main__":
    unittest.main()
