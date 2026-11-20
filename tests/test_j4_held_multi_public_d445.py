"""D445: all held PAPER assets routed by existing AUTO4, outside N50."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.j4_held_multi_public_d445 import (
    reviewed_held_instrument_pages, fetch_held_scope_from_public_rest,
    observe_existing_held_paper_once,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    HOUR_START_MS, MINUTE_MS, POSITION_ID, PLAN_VERSION, _new_position,
)
from crypto_intelligence_agent.paper_intrahour_quote_router_d391 import (
    PaperIntrahourQuoteRouter, PaperQuoteRoute,
)
from crypto_intelligence_agent.paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from crypto_intelligence_agent.paper_intrahour_target_step_d387 import PaperIntrahourTargetPolicy
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderIntent, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderEffect, PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from crypto_intelligence_agent.bybit_public_j1_transport import instruments_url
from test_j2_public_btc_scope_d441 import response
from test_j2_j4_current_n50_paper_lease_d410 import Clock, Socket, ack, ticker

MOD = "crypto_intelligence_agent.j4_held_multi_public_d445"
ETH_ID = "fixture_d445_held_eth"


def page(symbol: str, now: int, *, cursor=""):
    obj = response()
    obj["time"] = now - 200
    obj["result"]["list"][0]["symbol"] = symbol
    obj["result"]["list"][0]["baseCoin"] = symbol[:-4]
    obj["result"]["list"][0]["launchTime"] = str(now - 200_000)
    obj["result"]["nextPageCursor"] = cursor
    return obj


def two_contract_scope(now):
    return reviewed_held_instrument_pages(
        held_symbols=("ETHUSDT", "BTCUSDT"),
        pages=(page("BTCUSDT", now, cursor="cursor2"),
               page("ETHUSDT", now)),
        requested_cursors=(None, "cursor2"),
        page_received_at_ms=(now - 100, now - 70),
        observed_at_ms=now - 50,
    )


def extra_position(store):
    opened = HOUR_START_MS + 5 * MINUTE_MS
    store.create_position(
        position_id=ETH_ID,
        opening_intent=PaperOrderIntent(
            intent_id="fixture_d445_eth_open",
            fixture_signal_id="fixture_d445_eth_signal",
            venue=PaperVenue.BYBIT_V5, symbol="ETHUSDT",
            position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
            effect=PaperOrderEffect.OPEN, requested_units=Decimal(100),
            created_at_ms=opened - 10,
        ),
        opening_events=(PaperOrderEvent(
            "fixture_d445_eth_explicit_fake_fill",
            PaperOrderEventKind.FILL, opened, Decimal(100),
        ),),
        exit_plan=SyntheticExitPlan(
            initial_units=Decimal(100),
            tranches=(
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal(30)),
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal(20)),
            ),
            residual_floor_percent=Decimal(50),
        ),
        plan_version=PLAN_VERSION,
        synthetic_lot_step_units=Decimal(1),
        as_of_ms=opened,
    )


def held_router(db):
    return PaperIntrahourQuoteRouter(
        position_path=db,
        routes=(
            PaperQuoteRoute(
                POSITION_ID, PaperEmergencyStopRule(Decimal(99)),
                PaperIntrahourTargetPolicy(
                    PLAN_VERSION, (Decimal(101), Decimal(103)),
                ),
            ),
            PaperQuoteRoute(
                ETH_ID, PaperEmergencyStopRule(Decimal(99)),
                PaperIntrahourTargetPolicy(
                    PLAN_VERSION, (Decimal(101), Decimal(103)),
                ),
            ),
        ),
    )


class D445HeldScopeTests(unittest.TestCase):
    def test_two_pages_admit_only_current_held_contracts_not_n50(self):
        scope = two_contract_scope(1_800_000_000_000)
        self.assertEqual([x.symbol for x in scope.contracts],
                         ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(scope.asserted_full_catalog_rows, 2)
        self.assertEqual(scope.contracts[0].registry_sha256,
                         scope.contracts[1].registry_sha256)
        self.assertFalse(scope.contracts[0].live_metadata_authenticated)
        self.assertFalse(scope.contracts[1].public_or_commercial_use_authorized)

    def test_missing_duplicate_unavailable_or_cursor_swap_fails_closed(self):
        now = 1_800_000_000_000
        a, b = page("BTCUSDT", now, cursor="cursor2"), page("ETHUSDT", now)
        variants = [
            ((a,), (None,), (now - 100,)),
            ((a, page("BTCUSDT", now)), (None, "cursor2"),
             (now - 100, now - 70)),
            ((a, b), (None, "bad"), (now - 100, now - 70)),
            ((a, b), (None, "cursor2"), (now - 70, now - 100)),
        ]
        for pages, cursors, stamps in variants:
            with self.subTest(cursors=cursors), self.assertRaises(DataValidationError):
                reviewed_held_instrument_pages(
                    held_symbols=("BTCUSDT", "ETHUSDT"),
                    pages=pages, requested_cursors=cursors,
                    page_received_at_ms=stamps, observed_at_ms=now,
                )
        for field, value in (
            ("status", "PreLaunch"), ("quoteCoin", "USDC"),
            ("symbolType", "TradFi"), ("contractType", "LinearFutures"),
        ):
            mutated = deepcopy(b)
            mutated["result"]["list"][0][field] = value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                reviewed_held_instrument_pages(
                    held_symbols=("BTCUSDT", "ETHUSDT"),
                    pages=(a, mutated), requested_cursors=(None, "cursor2"),
                    page_received_at_ms=(now - 100, now - 70),
                    observed_at_ms=now,
                )
        with self.assertRaises(DataValidationError):
            reviewed_held_instrument_pages(
                held_symbols=("BTCUSDT", "ETHUSDT"),
                pages=(a, b), requested_cursors=(None, "cursor2"),
                page_received_at_ms=(now - 31_000, now - 70),
                observed_at_ms=now,
            )

    def test_live_transport_uses_paginated_list_not_per_symbol_get(self):
        now = 1_800_000_000_000
        class FakeClient:
            def __init__(self):
                self.urls = []
            def get(self, url):
                self.urls.append(url)
                return b"{}", (page("BTCUSDT", now, cursor="cursor2")
                               if len(self.urls) == 1 else page("ETHUSDT", now))
        client = FakeClient()
        with patch(MOD + ".BoundedBybitPublicClient", return_value=client):
            with patch(MOD + ".time.time_ns",
                       return_value=now * 1_000_000):
                result = fetch_held_scope_from_public_rest(
                    ("ETHUSDT", "BTCUSDT"))
        self.assertEqual(len(result.contracts), 2)
        self.assertEqual(client.urls, [
            instruments_url(), instruments_url(cursor="cursor2"),
        ])
        with patch(MOD + ".BoundedBybitPublicClient",
                   side_effect=AssertionError("network called")):
            with self.assertRaises(DataValidationError):
                fetch_held_scope_from_public_rest(("NOT_USDT",))


class D445MultiPaperIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "paper.sqlite"
        self.store = _new_position(self.db, short=False)
        extra_position(self.store)
        self.router = held_router(self.db)
        self.clock = Clock()

    def run_quotes(self, frames, *, duration=2):
        socket = Socket(self.clock, frames)
        with patch(MOD + ".fetch_held_scope_from_public_rest",
                   side_effect=AssertionError("offline test cannot reach REST")):
            with patch("socket.create_connection",
                       side_effect=AssertionError("offline test cannot reach WS")):
                report = observe_existing_held_paper_once(
                    session_factory=lambda: socket,
                    offline_scope=two_contract_scope(self.clock.now),
                    offline_router=self.router,
                    clock=self.clock.mono,
                    wall_ms=self.clock.wall,
                    sleeper=self.clock.sleep,
                    budget=TickerLeaseBudget(1, 120, duration),
                    allow_public_network=True, allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    allow_private_paper_reservations=True,
                )
        return report, socket

    def test_two_outside_n50_contracts_target_stop_and_no_fake_fill(self):
        result, socket = self.run_quotes([
            ack(), ticker("BTCUSDT", bid="101", mark="101"),
            ticker("ETHUSDT", bid="98", mark="98"),
        ])
        self.assertTrue(socket.closed)
        self.assertEqual(socket.sent[0]["args"],
                         ["tickers.BTCUSDT", "tickers.ETHUSDT"])
        self.assertEqual(result["held_position_contracts"], 2)
        self.assertEqual(result["held_quote_frames_forwarded"], 2)
        self.assertEqual(result["status"],
                         "finite_held_paper_quote_observed_unverified")
        btc = self.store.load(POSITION_ID)
        eth = self.store.load(ETH_ID)
        self.assertEqual(str(btc.reserved_unfilled_units), "30")
        self.assertEqual(str(eth.protective_reserved_unfilled_units), "100")
        self.assertEqual(str(btc.filled_exit_units), "0")
        self.assertEqual(str(eth.filled_exit_units), "0")
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["new_paper_position_created"])
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertNotIn("ETHUSDT", json.dumps(result))
        self.assertNotIn(POSITION_ID, json.dumps(result))

    def test_replay_on_same_sqlite_never_duplicates_either_position(self):
        self.run_quotes([ack(), ticker("BTCUSDT", bid="101", mark="101"),
                         ticker("ETHUSDT", bid="98", mark="98")])
        self.router = held_router(self.db)
        self.clock = Clock()
        result, _ = self.run_quotes([
            ack(), ticker("BTCUSDT", bid="101", mark="101"),
            ticker("ETHUSDT", bid="98", mark="98"),
        ])
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 1)
        self.assertEqual(len(self.store.load(ETH_ID).exit_orders), 1)
        self.assertFalse(result["synthetic_fill_inferred_from_ticker"])

    def test_missing_quote_for_one_held_symbol_is_degraded_not_success(self):
        result, _ = self.run_quotes([
            ack(), ticker("BTCUSDT", bid="101", mark="101")])
        self.assertEqual(result["held_position_contracts"], 2)
        self.assertEqual(result["held_quote_frames_forwarded"], 1)
        self.assertEqual(result["status"], "finite_held_paper_degraded_abstain")
        self.assertEqual(len(self.store.load(ETH_ID).exit_orders), 0)

    def test_missing_optin_rejects_before_journal_or_rest_or_socket(self):
        with patch(MOD + ".exclusive_paper_operator_lock",
                   side_effect=AssertionError("journal accessed")):
            with patch(MOD + ".fetch_held_scope_from_public_rest",
                       side_effect=AssertionError("REST accessed")):
                with patch(MOD + ".run_held_paper_lease",
                           side_effect=AssertionError("WS accessed")):
                    result = observe_existing_held_paper_once()
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["private_paper_journal_accessed"])
        self.assertFalse(result["orders_sent"])

    def test_mismatched_scope_rejected_before_ws_or_journal_mutation(self):
        scope = two_contract_scope(self.clock.now)
        from dataclasses import replace
        scope = replace(scope, contracts=scope.contracts[:1])
        with patch(MOD + ".fetch_held_scope_from_public_rest",
                   side_effect=AssertionError("REST accessed")):
            with self.assertRaises(DataValidationError):
                observe_existing_held_paper_once(
                    session_factory=lambda: AssertionError("socket called"),
                    offline_scope=scope, offline_router=self.router,
                    clock=self.clock.mono, wall_ms=self.clock.wall,
                    sleeper=self.clock.sleep,
                    allow_public_network=True, allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    allow_private_paper_reservations=True,
                )
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 0)
        self.assertEqual(len(self.store.load(ETH_ID).exit_orders), 0)
