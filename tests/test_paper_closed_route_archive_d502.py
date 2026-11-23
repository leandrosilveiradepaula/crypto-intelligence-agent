"""D502: closed PAPER history survives 50-route rollover; no financial deletes."""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import (
    _route_position, _policy_payload,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    load_private_paper_routes,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_closed_route_archive_d502 import (
    archive_closed_route, read_closed_route_archive,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from scripts.serve_paper_profile_lab_d487 import _paper_session_read
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    _new_position, POSITION_ID, PLAN_VERSION,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind,
)
from scripts.serve_paper_profile_lab_d487 import (
    _paper_history_page,
)
from test_j4_automatic_entry_materializer_d448 import POLICY
from test_j4_held_multi_public_d445 import extra_position, ETH_ID
from test_paper_intrahour_quote_router_d391 import tick, T, MIN

SCHEMA = "j4-private-paper-routes-d425-v1"


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "owner-only PAPER archive")
class ClosedRouteArchiveD502Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cia-d502-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.home.chmod(0o700)
        self.file = self.home / "paper-positions.sqlite"
        self.store = _new_position(self.file, short=False)
        self.file.chmod(0o600)
        self.route = {
            "position_id": POSITION_ID, "plan_version": PLAN_VERSION,
            "stop_mark_price": "99", "target_prices": ["101","103"],
            "max_spread_bps": "30", "runner": None,
        }
        self.manifest = self.home / "paper-routes.json"
        self.manifest.write_text(json.dumps({
            "schema_version": SCHEMA, "positions": [self.route],
        }), encoding="ascii")
        self.manifest.chmod(0o600)

    def close_original(self):
        router = load_private_paper_routes(self.home)
        result = router.process(tick(T + 12 * MIN, seq=1, mark="98", bid="98"))
        self.assertEqual(result.stop.reserved_units, Decimal(100))
        self.store.append_exit_events(
            POSITION_ID, result.created_intent_id,
            (PaperOrderEvent(
                "fixture_d502_stop_complete", PaperOrderEventKind.FILL,
                T + 12 * MIN + 200, Decimal(100),
            ),),
            as_of_ms=T + 12 * MIN + 200,
        )
        self.assertEqual(self.store.load(POSITION_ID).confirmed_remaining_units, 0)

    def test_no_archive_while_open_and_closed_idempotent(self):
        with self.assertRaises(DataValidationError):
            archive_closed_route(self.home, self.route)
        self.assertEqual(list(self.home.glob("paper-closed-route-*.json")), [])
        self.close_original()
        self.assertTrue(archive_closed_route(self.home, self.route))
        self.assertFalse(archive_closed_route(self.home, self.route))
        self.assertEqual(read_closed_route_archive(self.home, POSITION_ID),
                         self.route)
        archived = list(self.home.glob("paper-closed-route-*.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].stat().st_mode & 0o777, 0o600)
        with self.assertRaises(DataValidationError):
            archive_closed_route(self.home, {**self.route,
                                             "stop_mark_price": "97"})

    def test_full_manifest_rolls_only_closed_and_history_page_survives(self):
        self.close_original()
        extra_position(self.store)
        planned = {
            "position_id": ETH_ID, "plan_version": PLAN_VERSION,
            "stop_mark_price": "99", "target_prices": ["101","103"],
            "symbol": "ETHUSDT", "policy": _policy_payload(POLICY),
        }
        # One slot models a full 50-slot manifest, without 50 fake fills.
        with patch("crypto_intelligence_agent.j4_automatic_entry_materializer_d448._MAX_POSITIONS", 1):
            _route_position(self.home, planned)
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual([r["position_id"] for r in manifest["positions"]],
                         [ETH_ID])
        self.assertEqual(read_closed_route_archive(self.home, POSITION_ID),
                         self.route)
        # Historical AUTO4 is untouched and can coexist with an active ETH.
        self.assertEqual(self.store.load(POSITION_ID).filled_exit_units, 100)
        self.assertEqual(self.store.load(ETH_ID).confirmed_remaining_units, 100)
        page = _paper_history_page(directory=self.home, offset=0, limit=2)
        self.assertEqual(page["position_count"], 2)
        self.assertEqual(len(page["positions"]), 2)
        self.assertEqual({p["symbol"] for p in page["positions"]},
                         {"BTCUSDT", "ETHUSDT"})
        self.assertFalse(page["orders_sent"])
        orders = self.home / "paper-orders.sqlite"
        SQLitePaperOrderJournal(orders)
        orders.chmod(0o600)
        session = _paper_session_read(directory=self.home)
        self.assertEqual(session["open_position_count"], 1)
        self.assertEqual(session["closed_position_count"], 1)
        self.assertEqual(session["position_count"], 2)
        self.assertFalse(session["orders_sent"])
        # Replaying same position after rollover cannot duplicate a route.
        with patch("crypto_intelligence_agent.j4_automatic_entry_materializer_d448._MAX_POSITIONS", 1):
            _route_position(self.home, planned)
        self.assertEqual(len(list(self.home.glob("paper-closed-route-*.json"))), 1)

    def test_d505_older_open_position_stays_visible_beyond_recent_limit(self):
        # Two REAL AUTO4 rows and a one-row display limit reproduce the
        # failure that otherwise needs 51 positions to observe.
        extra_position(self.store)
        eth_route = {
            "position_id": ETH_ID, "plan_version": PLAN_VERSION,
            "stop_mark_price": "99", "target_prices": ["101", "103"],
            "max_spread_bps": "30", "runner": None,
        }
        self.manifest.write_text(json.dumps({
            "schema_version": SCHEMA,
            "positions": [self.route, eth_route],
        }), encoding="ascii")
        self.manifest.chmod(0o600)
        router = load_private_paper_routes(self.home)
        trigger = router.process(tick(
            T + 12 * MIN, seq=1, mark="98", bid="98",
            symbol="ETHUSDT",
        ))
        self.assertIsNotNone(trigger.created_intent_id)
        self.store.append_exit_events(
            ETH_ID, trigger.created_intent_id,
            (PaperOrderEvent(
                "fixture_d505_eth_closed", PaperOrderEventKind.FILL,
                T + 12 * MIN + 200, Decimal(100),
            ),),
            as_of_ms=T + 12 * MIN + 200,
        )
        self.assertEqual(self.store.load(ETH_ID).confirmed_remaining_units, 0)
        self.assertEqual(self.store.load(POSITION_ID).confirmed_remaining_units, 100)
        order_db = self.home / "paper-orders.sqlite"
        SQLitePaperOrderJournal(order_db)
        order_db.chmod(0o600)

        with patch("scripts.serve_paper_profile_lab_d487._MAX_SESSION_POSITIONS", 1):
            session = _paper_session_read(directory=self.home)
        self.assertEqual(session["position_count"], 2)
        self.assertEqual(session["open_position_count"], 1)
        self.assertEqual(session["closed_position_count"], 1)
        self.assertEqual(session["displayed_position_count"], 2)
        self.assertTrue(session["more_history_available"])
        self.assertEqual([p["symbol"] for p in session["positions"]],
                         ["BTCUSDT", "ETHUSDT"])
        self.assertEqual([p["status"] for p in session["positions"]],
                         ["OPEN", "CLOSED"])
        self.assertFalse(session["orders_sent"])
        self.assertFalse(tuple(self.home.glob("paper-closed-route-*.json")))

    def test_full_capacity_with_only_active_routes_never_archives(self):
        extra_position(self.store)
        planned = {
            "position_id": ETH_ID, "plan_version": PLAN_VERSION,
            "stop_mark_price": "99", "target_prices": ["101", "103"],
            "symbol": "ETHUSDT", "policy": _policy_payload(POLICY),
        }
        with patch("crypto_intelligence_agent.j4_automatic_entry_materializer_d448._MAX_POSITIONS", 1):
            with self.assertRaises(DataValidationError):
                _route_position(self.home, planned)
        self.assertEqual(list(self.home.glob("paper-closed-route-*.json")), [])
        self.assertEqual(len(load_private_paper_routes(self.home).monitored_position_ids), 1)

    def test_tampered_or_unsafe_archive_fails_closed(self):
        self.close_original()
        archive_closed_route(self.home, self.route)
        file = next(self.home.glob("paper-closed-route-*.json"))
        raw = file.read_bytes()
        try:
            file.chmod(0o644)
            with self.assertRaises(DataValidationError):
                read_closed_route_archive(self.home, POSITION_ID)
        finally:
            file.chmod(0o600)
        file.write_bytes(raw.replace(b'"99"', b'"98"'))
        with self.assertRaises(DataValidationError):
            read_closed_route_archive(self.home, POSITION_ID)


if __name__ == "__main__":
    unittest.main()
