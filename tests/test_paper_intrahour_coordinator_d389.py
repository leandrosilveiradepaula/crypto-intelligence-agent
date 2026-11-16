"""D389: one intrahour event, stop-before-target, real AUTO4 PAPER ledger.

No broker APIs, real fills, quotes downloaded from exchange, or orders sent.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitTickerQuote
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_intrahour_coordinator_d389 import (
    PaperIntrahourDecision, step_paper_intrahour_coordinated,
)
from crypto_intelligence_agent.paper_intrahour_target_step_d387 import (
    PaperIntrahourTargetPolicy,
)
from crypto_intelligence_agent.paper_intrahour_emergency_stop_d388 import (
    PaperEmergencyStopRule,
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

BASE = 1_800_000_000_000
MINUTE = 60_000
ENTRY = BASE + 5 * MINUTE


def make_quote(at, *, mark="100", bid="100", ask=None,
               symbol="BTCUSDT", depth="2"):
    if ask is None:
        ask = str(D(bid) + D("0.02"))
    return BybitTickerQuote(
        symbol=symbol, exchange_at_ms=at - 15, received_at_ms=at,
        cross_sequence=1, last_price=D(bid), mark_price=D(mark),
        index_price=D(mark), bid_price=D(bid), ask_price=D(ask),
        bid_size=D(depth), ask_size=D(depth), turnover_24h=None,
        volume_24h=None, funding_rate=None,
    )


class PaperIntrahourCoordinatorD389Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "position.sqlite"
        self.position_id = "fixture_d389_position"
        self.journal = SQLitePaperPositionJournal(self.path)
        self.targets = PaperIntrahourTargetPolicy(
            plan_version="d389-plan", prices=(D("101"), D("103")),
        )
        self.stop = PaperEmergencyStopRule(D("99"))

    def open(self, *, side=SyntheticSide.LONG):
        intent = PaperOrderIntent(
            "fixture_d389_open_long" if side is SyntheticSide.LONG else "fixture_d389_open_short",
            "fixture_d389_signal_open", PaperVenue.BYBIT_V5, "BTCUSDT", side,
            PaperOrderSide.BUY if side is SyntheticSide.LONG else PaperOrderSide.SELL,
            PaperOrderEffect.OPEN, D(100), ENTRY - 10,
        )
        plan = SyntheticExitPlan(
            initial_units=D(100),
            tranches=(
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(30)),
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, D(20)),
            ),
            residual_floor_percent=D(50),
        )
        self.journal.create_position(
            position_id=self.position_id, opening_intent=intent,
            opening_events=(PaperOrderEvent(
                "fixture_d389_open_fill", PaperOrderEventKind.FILL,
                ENTRY, D(100)),),
            exit_plan=plan, plan_version="d389-plan",
            synthetic_lot_step_units=D(1), as_of_ms=ENTRY,
        )

    def decide(self, at, *, mark="100", bid="100", ask=None, depth="2",
               cutoff=None, stop=None, targets=None, symbol="BTCUSDT"):
        return step_paper_intrahour_coordinated(
            self.path, self.position_id,
            stop_rule=stop or self.stop, target_policy=targets or self.targets,
            quote=make_quote(at, mark=mark, bid=bid, ask=ask,
                             depth=depth, symbol=symbol),
            as_of_ms=at if cutoff is None else cutoff,
        )

    def test_simultaneous_profitable_bid_and_breached_mark_reserves_only_stop(self):
        self.open()
        at = BASE + 12 * MINUTE
        step = self.decide(at, mark="98", bid="110")
        self.assertEqual(step.decision, PaperIntrahourDecision.STOP_RESERVED)
        self.assertIsNone(step.target)
        self.assertEqual(step.stop.reserved_units, D(100))
        saved = self.journal.load(self.position_id)
        self.assertEqual(len(saved.exit_orders), 1)
        self.assertEqual(saved.exit_orders[0].tranche_step, -1)
        self.assertEqual(saved.filled_exit_units, D(0))
        self.assertFalse(step.sanitized_report()["orders_sent"])
        self.assertFalse(step.sanitized_report()["native_stop_verified"])

    def test_target_then_reconciled_fill_then_emergency_stop_remaining(self):
        self.open()
        t1, t2 = BASE + 12 * MINUTE, BASE + 19 * MINUTE
        first = self.decide(t1, mark="100", bid="101")
        self.assertEqual(first.decision, PaperIntrahourDecision.TARGET_RESERVED)
        self.assertEqual(first.target.tranche_step, 1)
        self.assertEqual(self.journal.load(self.position_id).reserved_unfilled_units, D(30))
        # Crossing stop with an outstanding partial cannot double reserve.
        unresolved = self.decide(t1+1, mark="98", bid="102")
        self.assertEqual(unresolved.decision, PaperIntrahourDecision.STOP_UNRESOLVED)
        self.assertIsNone(unresolved.target)
        self.assertEqual(len(self.journal.load(self.position_id).exit_orders), 1)

        self.journal.append_exit_events(
            self.position_id, first.created_intent_id,
            (PaperOrderEvent("fixture_d389_partial_fill",
                             PaperOrderEventKind.FILL, t1+2, D(30)),),
            as_of_ms=t1+2,
        )
        second = self.decide(t2, mark="98", bid="110")
        self.assertEqual(second.decision, PaperIntrahourDecision.STOP_RESERVED)
        self.assertEqual(second.stop.reserved_units, D(70))
        saved = self.journal.load(self.position_id)
        self.assertEqual([x.tranche_step for x in saved.exit_orders], [1, -1])
        self.assertEqual(saved.confirmed_remaining_units, D(70))
        self.assertEqual(saved.reserved_unfilled_units, D(70))
        self.assertEqual(saved.filled_exit_units, D(30))

    def test_pending_protection_blocks_targets_until_explicit_fill(self):
        self.open()
        at=BASE + 12*MINUTE
        first=self.decide(at, mark="98", bid="110")
        pending=self.decide(at+1, mark="102", bid="105")
        self.assertEqual(pending.decision, PaperIntrahourDecision.STOP_PENDING)
        self.assertIsNone(pending.target)
        self.assertEqual(len(self.journal.load(self.position_id).exit_orders), 1)
        self.journal.append_exit_events(
            self.position_id, first.created_intent_id,
            (PaperOrderEvent("fixture_d389_stop_fill", PaperOrderEventKind.FILL,
                             at+2, D(100)),),
            as_of_ms=at+2,
        )
        closed=self.decide(at+3, mark="102", bid="106")
        self.assertEqual(closed.decision, PaperIntrahourDecision.STOP_CLOSED)
        self.assertIsNone(closed.target)
        self.assertEqual(self.journal.load(self.position_id).confirmed_remaining_units, D(0))

    def test_stale_or_zero_depth_never_falls_through_to_target(self):
        self.open()
        t=BASE+12*MINUTE
        old=self.decide(t, mark="100", bid="110", cutoff=t+3_200)
        self.assertEqual(old.decision, PaperIntrahourDecision.STOP_UNAVAILABLE)
        self.assertIsNone(old.target)
        empty=self.decide(t+1, mark="100", bid="110", depth="0")
        self.assertEqual(empty.decision, PaperIntrahourDecision.STOP_UNAVAILABLE)
        self.assertEqual(len(self.journal.load(self.position_id).exit_orders), 0)

    def test_hold_does_not_manufacture_fills_or_reservations(self):
        self.open()
        r=self.decide(BASE+11*MINUTE, mark="100", bid="100")
        self.assertEqual(r.decision, PaperIntrahourDecision.TARGET_HOLD)
        self.assertIsNotNone(r.target)
        self.assertFalse(r.sanitized_report()["new_intent_reserved"])
        self.assertEqual(len(self.journal.load(self.position_id).exit_orders), 0)

    def test_policy_mismatch_rejected_before_stop_could_reserve(self):
        self.open()
        different=PaperIntrahourTargetPolicy(
            plan_version="d389-plan", prices=(D("101"), D("103")),
            max_quote_age_ms=500,
        )
        with self.assertRaises(DataValidationError):
            self.decide(BASE+12*MINUTE, mark="98", bid="110", targets=different)
        self.assertEqual(len(self.journal.load(self.position_id).exit_orders), 0)

    def test_wrong_symbol_cannot_reserve_any_exit(self):
        self.open()
        with self.assertRaises(DataValidationError):
            self.decide(BASE+12*MINUTE, mark="98", bid="110", symbol="ETHUSDT")
        self.assertEqual(len(self.journal.load(self.position_id).exit_orders), 0)

    def test_concurrent_stop_and_target_reserve_only_single_stop(self):
        self.open()
        t=BASE+12*MINUTE
        def execute(_):
            return self.decide(t, mark="98", bid="110")
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(execute, (1, 2)))
        self.assertEqual(len(self.journal.load(self.position_id).exit_orders), 1)
        self.assertTrue(any(r.decision is PaperIntrahourDecision.STOP_RESERVED for r in result))
        self.assertTrue(all(r.decision in {
            PaperIntrahourDecision.STOP_RESERVED, PaperIntrahourDecision.STOP_PENDING,
        } for r in result))

    def test_short_stop_beats_buy_to_cover_target(self):
        self.targets=PaperIntrahourTargetPolicy(
            plan_version="d389-plan", prices=(D("99"), D("97")))
        self.stop=PaperEmergencyStopRule(D("102"))
        self.open(side=SyntheticSide.SHORT)
        r=self.decide(BASE+12*MINUTE, mark="103", bid="96", ask="96.01")
        self.assertEqual(r.decision, PaperIntrahourDecision.STOP_RESERVED)
        self.assertEqual(self.journal.load(self.position_id).exit_orders[0].intent.side,
                         PaperOrderSide.BUY)
        self.assertIsNone(r.target)


if __name__ == "__main__":
    unittest.main()
