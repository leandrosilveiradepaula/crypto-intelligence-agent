"""D448: D447 observed hypothesis -> AUTO2 fill -> AUTO4 -> D425/D444/J5.

No network, exchange fills, account data, J1 mutations, or real orders.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j2_observed_paper_entry_d447 import reserve_observed_paper_entry
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import (
    PaperEntryExitPolicy, arm_observed_paper_entry, materialize_observed_paper_entry,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    load_private_paper_routes,
)
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import read_owner_paper_positions
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderStatus
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitTranche,
)
from test_j2_observed_paper_entry_d447 import inputs


POLICY = PaperEntryExitPolicy(
    stop_distance_bps=Decimal("50"),
    target_distances_bps=(Decimal("200"), Decimal("300")),
    tranches=(
        SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal("30")),
        SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal("20")),
    ),
    runner_floor_percent=Decimal("50"),
    synthetic_lot_step_units=Decimal("0.01"),
    entry_fee_bps=Decimal("6"), exit_fee_bps=Decimal("6"),
    entry_adverse_slippage_bps=Decimal("3"),
    exit_adverse_slippage_bps=Decimal("3"),
    max_spread_bps=Decimal("30"),
    max_book_participation_bps=Decimal("2500"),
    min_fill_latency_ms=150,
    max_fill_wait_ms=60_000,
)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "POSIX non-root owner required")
class D448PaperLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home.chmod(0o700)
        self.order_path = self.home / "paper-orders.sqlite"
        self.position_path = self.home / "paper-positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.order_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        self.order_path.chmod(0o600)
        self.position_path.chmod(0o600)

    def pending(self, side="LONG"):
        args = inputs(side)
        result = reserve_observed_paper_entry(
            **args, journal=self.orders, position_journal_path=self.position_path,
        )
        self.assertEqual(result.status, "paper_open_intent_reserved_only")
        self.assertIsNotNone(result.intent_id)
        return result.intent_id, args

    def arm(self, intent_id, policy=POLICY):
        return arm_observed_paper_entry(
            private_paper_directory=self.home, intent_id=intent_id,
            policy=policy, allow_paper_entry_strategy=True,
        )

    def fill_quote(self, args):
        quote = args["quote"]
        return replace(
            quote, exchange_at_ms=args["now_ms"] + 400,
            received_at_ms=args["now_ms"] + 500,
            cross_sequence=quote.cross_sequence + 1,
            bid_size=Decimal("20"), ask_size=Decimal("20"),
        )

    def complete(self, intent_id, quote, at_ms):
        return materialize_observed_paper_entry(
            private_paper_directory=self.home, intent_id=intent_id,
            quote=quote, as_of_ms=at_ms,
            enable_hypothetical_open_fill=True,
        )

    def test_long_short_durable_position_is_visible_to_held_worker_and_j5(self):
        for side in ("LONG", "SHORT"):
            with self.subTest(side=side):
                # Every test case uses an independently isolated journal.
                # Repeat with a clean owner directory after the first case.
                if side == "SHORT":
                    self.tearDownNothing()
                intent, args = self.pending(side)
                self.assertEqual(self.arm(intent)["status"], "paper_entry_plan_armed")
                fill = self.fill_quote(args)
                done = self.complete(intent, fill, fill.received_at_ms)
                self.assertEqual(done["status"], "paper_position_routed_for_continuous_held_monitor")
                self.assertTrue(done["hypothetical_open_fill_written"])
                self.assertFalse(done["orders_sent"])
                entry = self.orders.load(intent)
                self.assertEqual(entry.snapshot.status, PaperOrderStatus.FILLED)
                self.assertEqual(len(entry.events), 1)
                self.assertEqual(entry.snapshot.filled_total_units, Decimal("2.50"))
                router = load_private_paper_routes(self.home)
                self.assertEqual(router.monitored_symbols, frozenset({"BTCUSDT"}))
                pos_id = router.monitored_position_ids[0]
                balance = self.positions.load(pos_id)
                self.assertEqual(balance.initial_confirmed_units, Decimal("2.50"))
                self.assertEqual(balance.leverage_at_intent, 50)
                self.assertEqual(balance.requested_margin_quote, Decimal("5"))
                self.assertEqual(balance.confirmed_remaining_units, Decimal("2.50"))
                self.assertEqual(balance.runner_floor_units, Decimal("1.25"))
                self.assertEqual(len(balance.exit_orders), 0)
                j5 = read_owner_paper_positions(directory=self.home)
                self.assertEqual(len(j5["positions"]), 1)
                # A later quote creates only a REDUCE_ONLY target or stop reservation.
                if side == "LONG":
                    mark, bid, ask = "102.2", "102.1", "102.3"
                else:
                    mark, bid, ask = "97.8", "97.7", "97.9"
                later = replace(
                    fill,
                    exchange_at_ms=fill.exchange_at_ms + 800,
                    received_at_ms=fill.received_at_ms + 800,
                    cross_sequence=fill.cross_sequence + 1,
                    mark_price=Decimal(mark), last_price=Decimal(mark),
                    bid_price=Decimal(bid), ask_price=Decimal(ask),
                )
                router.process(later)
                updated = self.positions.load(pos_id)
                self.assertEqual(len(updated.exit_orders), 1)
                self.assertEqual(updated.exit_orders[0].snapshot.filled_total_units, 0)
                self.assertEqual(updated.reserved_unfilled_units, Decimal("0.7500"))
                self.assertEqual(updated.filled_exit_units, Decimal(0))
                self.assertFalse(router.sanitized_report()["orders_sent"])
                # Replay post-target must not revoke or duplicate this partial exit.
                second = self.complete(intent, None, later.received_at_ms + 20)
                self.assertFalse(second["hypothetical_open_fill_written"])
                self.assertEqual(len(self.positions.load(pos_id).exit_orders), 1)

    def tearDownNothing(self):
        # Disjoint owner state for the second side of the parametrized case.
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home.chmod(0o700)
        self.order_path = self.home / "paper-orders.sqlite"
        self.position_path = self.home / "paper-positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.order_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        self.order_path.chmod(0o600)
        self.position_path.chmod(0o600)

    def test_crash_between_fill_and_position_repaired_without_new_quote(self):
        intent, args = self.pending()
        self.arm(intent)
        quote = self.fill_quote(args)
        with patch(
            "crypto_intelligence_agent.j4_automatic_entry_materializer_d448."
            "SQLitePaperPositionJournal.create_position",
            side_effect=OSError("injected crash after AUTO2 commit"),
        ):
            with self.assertRaises(OSError):
                self.complete(intent, quote, quote.received_at_ms)
        self.assertEqual(self.orders.load(intent).snapshot.status, PaperOrderStatus.FILLED)
        self.assertFalse((self.home / "paper-routes.json").exists())
        recovered = self.complete(intent, None, quote.received_at_ms + 1000)
        self.assertEqual(recovered["status"], "paper_position_routed_for_continuous_held_monitor")
        self.assertFalse(recovered["hypothetical_open_fill_written"])
        self.assertEqual(len(load_private_paper_routes(self.home).monitored_position_ids), 1)
        self.assertEqual(len(self.orders.load(intent).events), 1)

    def test_crash_after_position_before_route_repaired_without_duplicate(self):
        intent, args = self.pending()
        self.arm(intent)
        quote = self.fill_quote(args)
        with patch(
            "crypto_intelligence_agent.j4_automatic_entry_materializer_d448._route_position",
            side_effect=OSError("injected crash after AUTO4 commit"),
        ):
            with self.assertRaises(OSError):
                self.complete(intent, quote, quote.received_at_ms)
        self.assertFalse((self.home / "paper-routes.json").exists())
        recovered = self.complete(intent, None, quote.received_at_ms + 1000)
        self.assertEqual(recovered["positions_ready_for_held_worker"], 1)
        position_id = load_private_paper_routes(self.home).monitored_position_ids[0]
        self.assertEqual(self.positions.load(position_id).initial_confirmed_units,
                         Decimal("2.50"))
        self.assertEqual(len(self.orders.load(intent).events), 1)

    def test_no_optin_and_causal_market_guard_do_not_fill(self):
        intent, args = self.pending()
        self.assertEqual(arm_observed_paper_entry(
            private_paper_directory=self.home, intent_id=intent,
            policy=POLICY)["status"], "paper_strategy_optin_required")
        self.assertFalse(list(self.home.glob("paper-entry-plan-*")))
        self.arm(intent)
        def await_quote(quote, at):
            report = self.complete(intent, quote, at)
            self.assertFalse(report["hypothetical_open_fill_written"])
            self.assertEqual(self.orders.load(intent).snapshot.status, PaperOrderStatus.PENDING)
            self.assertFalse((self.home / "paper-routes.json").exists())
            return report["status"]
        self.assertEqual(await_quote(None, args["now_ms"]), "await_post_latency_bbo")
        early = replace(args["quote"], ask_size=Decimal(20), bid_size=Decimal(20))
        self.assertEqual(await_quote(early, early.received_at_ms), "await_post_latency_bbo")
        fresh = self.fill_quote(args)
        too_wide = replace(fresh, ask_price=Decimal("101"), bid_price=Decimal("99"))
        self.assertEqual(await_quote(too_wide, too_wide.received_at_ms),
                         "paper_entry_spread_veto")
        no_depth = replace(fresh, ask_size=Decimal("2"), bid_size=Decimal("2"))
        self.assertEqual(await_quote(no_depth, no_depth.received_at_ms),
                         "paper_entry_top_book_liquidity_veto")
        stale = self.complete(intent, fresh, fresh.received_at_ms + 5000)
        self.assertEqual(stale["status"], "open_fill_window_or_quote_stale")
        self.assertEqual(self.orders.load(intent).snapshot.status, PaperOrderStatus.PENDING)
        self.assertEqual(materialize_observed_paper_entry(
            private_paper_directory=self.home, intent_id=intent,
            quote=fresh, as_of_ms=fresh.received_at_ms)["status"],
            "hypothetical_open_fill_optin_required")

    def test_d489_expired_pending_open_is_cancelled_without_fictitious_fill(self):
        intent, args = self.pending()
        self.arm(intent)
        clock = args["now_ms"] + 60_500
        expired = self.complete(intent, None, clock)
        self.assertEqual(expired["status"], "paper_open_expired_cancelled")
        entry = self.orders.load(intent)
        self.assertEqual(entry.snapshot.status, PaperOrderStatus.CANCELLED)
        self.assertEqual(len(entry.events), 1)
        self.assertEqual(entry.events[0].kind.value, "CANCELLED")
        self.assertEqual(entry.snapshot.filled_total_units, Decimal("0"))
        self.assertFalse((self.home / "paper-routes.json").exists())

    def test_d489_quote_after_fill_window_cannot_create_order_or_position(self):
        intent, args = self.pending()
        self.arm(intent)
        delayed = replace(self.fill_quote(args),
                          exchange_at_ms=args["now_ms"] + 61_000,
                          received_at_ms=args["now_ms"] + 61_050)
        expired = self.complete(intent, delayed, delayed.received_at_ms)
        self.assertEqual(expired["status"], "paper_open_expired_cancelled")
        self.assertEqual(self.orders.load(intent).snapshot.status,
                         PaperOrderStatus.CANCELLED)
        self.assertFalse((self.home / "paper-routes.json").exists())

    def test_immutable_plan_replay_tamper_and_permission_rejections(self):
        intent, args = self.pending()
        self.arm(intent)
        self.assertEqual(self.arm(intent)["status"], "paper_entry_plan_armed")
        with self.assertRaises(DataValidationError):
            self.arm(intent, replace(POLICY, stop_distance_bps=Decimal("80")))
        path = next(self.home.glob("paper-entry-plan-*"))
        obj = json.loads(path.read_text(encoding="ascii"))
        obj["payload"]["stop_mark_price"] = "1"
        path.write_text(json.dumps(obj), encoding="ascii")
        path.chmod(0o600)
        with self.assertRaises(DataValidationError):
            self.complete(intent, self.fill_quote(args), self.fill_quote(args).received_at_ms)
        self.assertEqual(self.orders.load(intent).snapshot.status, PaperOrderStatus.PENDING)
        path.chmod(0o644)
        with self.assertRaises(DataValidationError):
            self.complete(intent, self.fill_quote(args), self.fill_quote(args).received_at_ms)


    def test_fill_time_j3_cost_and_stop_margin_veto_do_not_create_position(self):
        for variant, expected in (
            (replace(POLICY, entry_fee_bps=Decimal("100"),
                     exit_fee_bps=Decimal("100")),
             "paper_entry_target_after_costs_veto"),
            (replace(POLICY, stop_distance_bps=Decimal("900")),
             "paper_entry_stop_margin_veto"),
        ):
            with self.subTest(expected=expected):
                if next(self.home.glob("paper-entry-plan-*"), None) is not None:
                    self.tearDownNothing()
                intent, args = self.pending()
                self.arm(intent, variant)
                fresh = self.fill_quote(args)
                result = self.complete(intent, fresh, fresh.received_at_ms)
                self.assertEqual(result["status"], expected)
                self.assertEqual(self.orders.load(intent).snapshot.status,
                                 PaperOrderStatus.PENDING)
                self.assertFalse((self.home / "paper-routes.json").exists())


    def test_persisted_kill_switch_blocks_new_paper_fill_under_auto2_lock(self):
        intent, args = self.pending()
        self.arm(intent)
        quote = self.fill_quote(args)
        self.orders.set_local_kill_switch(
            pause=True, expected_sequence=0,
            changed_at_ms=quote.received_at_ms - 1,
        )
        with self.assertRaises(DataValidationError):
            self.complete(intent, quote, quote.received_at_ms)
        self.assertEqual(self.orders.load(intent).snapshot.status, PaperOrderStatus.PENDING)
        self.assertFalse((self.home / "paper-routes.json").exists())
        self.orders.set_local_kill_switch(
            pause=False, expected_sequence=1,
            changed_at_ms=quote.received_at_ms - 1,
            acknowledge_resume=True,
        )
        result = self.complete(intent, quote, quote.received_at_ms)
        self.assertTrue(result["hypothetical_open_fill_written"])
        self.assertEqual(self.orders.load(intent).snapshot.status, PaperOrderStatus.FILLED)

    def test_manifest_routes_still_get_protective_stop_first(self):
        intent, args = self.pending()
        self.arm(intent)
        quote = self.fill_quote(args)
        self.complete(intent, quote, quote.received_at_ms)
        router = load_private_paper_routes(self.home)
        position_id = router.monitored_position_ids[0]
        hit = replace(
            quote, exchange_at_ms=quote.exchange_at_ms + 800,
            received_at_ms=quote.received_at_ms + 800,
            cross_sequence=quote.cross_sequence + 1,
            mark_price=Decimal("99.3"), last_price=Decimal("99.3"),
            bid_price=Decimal("99.2"), ask_price=Decimal("99.4"),
        )
        router.process(hit)
        b = self.positions.load(position_id)
        self.assertTrue(b.protective_stop_seen)
        self.assertEqual(b.exit_orders[0].tranche_step, -1)
        self.assertEqual(b.protective_reserved_unfilled_units, Decimal("2.50"))
        self.assertEqual(b.filled_exit_units, Decimal(0))


if __name__ == "__main__":
    unittest.main()
