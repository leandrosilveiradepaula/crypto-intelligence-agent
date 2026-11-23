"""D443 existing durable PAPER BTC: integrated market tick to AUTO4."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j2_public_btc_scope_d441 import reviewed_single_btc_scope
from crypto_intelligence_agent.j4_held_btc_public_d443 import (
    observe_existing_btc_paper_once, run_held_btc_paper_lease,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    POSITION_ID, _new_position, _route,
)
from test_j2_j4_current_n50_paper_lease_d410 import (
    Clock, Socket, ack, ticker,
)
from test_j2_public_btc_scope_d441 import response

MODULE = "crypto_intelligence_agent.j4_held_btc_public_d443"


def scope_at(now):
    obj = response()
    obj["time"] = now - 200
    obj["result"]["list"][0]["launchTime"] = str(now - 200_000)
    return reviewed_single_btc_scope(obj, observed_at_ms=now - 50)


class D443PersistedPaperTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "persisted-paper.sqlite"
        self.store = _new_position(self.db, short=False)
        self.router = _route(self.db, short=False)
        self.clock = Clock()

    def run_tick(self, frames, *, duration=2):
        socket = Socket(self.clock, frames)
        with patch(MODULE + ".fetch_single_btc_scope_from_public_rest",
                   side_effect=AssertionError("network REST forbidden in offline test")):
            with patch("socket.create_connection",
                       side_effect=AssertionError("network WS forbidden in offline test")):
                result = observe_existing_btc_paper_once(
                    allow_public_network=True, allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    allow_private_paper_reservations=True,
                    session_factory=lambda: socket, offline_scope=scope_at(self.clock.now),
                    offline_router=self.router,
                    budget=TickerLeaseBudget(1, 80, duration),
                    clock=self.clock.mono, wall_ms=self.clock.wall,
                    sleeper=self.clock.sleep,
                )
        return result, socket

    def test_durable_auto4_target_reserved_without_any_inferred_fill(self):
        result, socket = self.run_tick([ack(), ticker("BTCUSDT", bid="101")])
        balance = self.store.load(POSITION_ID)
        self.assertTrue(socket.closed)
        self.assertEqual(socket.sent[0]["args"], ["tickers.BTCUSDT"])
        self.assertEqual(result["held_quote_frames_forwarded"], 1)
        self.assertEqual(result["status"], "finite_held_paper_quote_observed_unverified")
        self.assertTrue(result["held_quote_fresh_at_lease_end"])
        self.assertEqual(len(balance.exit_orders), 1)
        self.assertEqual(str(balance.reserved_unfilled_units), "30")
        self.assertEqual(str(balance.filled_exit_units), "0")
        self.assertFalse(result["synthetic_fill_inferred_from_ticker"])
        self.assertTrue(result["existing_auto4_journal_reused"])
        self.assertFalse(result["new_paper_position_created"])
        self.assertFalse(result["orders_sent"])
        self.assertNotIn(POSITION_ID, json.dumps(result))
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn("101.02", json.dumps(result))

    def test_existing_held_stop_first_when_no_n50_is_loaded(self):
        result, socket = self.run_tick([ack(), ticker("BTCUSDT", bid="98", mark="98")])
        balance = self.store.load(POSITION_ID)
        self.assertEqual(len(balance.exit_orders), 1)
        self.assertEqual(balance.exit_orders[0].tranche_step, -1)
        self.assertEqual(str(balance.protective_reserved_unfilled_units), "100")
        self.assertEqual(str(balance.filled_exit_units), "0")
        self.assertEqual(result["held_quote_frames_forwarded"], 1)
        self.assertFalse(result["j1_state_accessed"])

    def test_same_position_replay_never_creates_second_exit(self):
        self.run_tick([ack(), ticker("BTCUSDT", bid="101")])
        first = self.store.load(POSITION_ID)
        self.assertEqual(len(first.exit_orders), 1)
        # A fresh router simulates process restart; old financial reservations
        # remain in the same actual SQLite ledger.
        self.router = _route(self.db, short=False)
        self.clock = Clock()
        result, _ = self.run_tick([ack(), ticker("BTCUSDT", bid="101")])
        second = self.store.load(POSITION_ID)
        self.assertEqual(len(second.exit_orders), 1)
        self.assertEqual(second.reserved_unfilled_units, first.reserved_unfilled_units)
        self.assertFalse(result["orders_sent"])

    def test_missing_optin_refuses_before_private_read_or_ws(self):
        with patch(MODULE + ".exclusive_paper_operator_lock",
                   side_effect=AssertionError("owner journal accessed")):
            with patch(MODULE + ".fetch_single_btc_scope_from_public_rest",
                       side_effect=AssertionError("REST accessed")):
                with patch(MODULE + ".run_held_btc_paper_lease",
                           side_effect=AssertionError("WS accessed")):
                    result = observe_existing_btc_paper_once()
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["private_paper_journal_accessed"])
        self.assertFalse(result["orders_sent"])

    def test_acked_only_no_quote_never_claims_held_monitoring(self):
        result, _ = self.run_tick([ack()])
        self.assertEqual(result["held_quote_frames_forwarded"], 0)
        self.assertEqual(result["status"], "finite_held_paper_degraded_abstain")
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 0)

    def test_root_or_injected_real_hooks_denied(self):
        flags = {
            "allow_public_network": True, "allow_public_websocket": True,
            "confirm_personal_readonly_research": True,
            "confirm_region_eligible": True, "allow_private_paper_reservations": True,
        }
        with self.assertRaises(Exception):
            observe_existing_btc_paper_once(
                private_paper_directory=Path("/tmp/never-read"), 
                offline_scope=scope_at(self.clock.now), **flags)
        with patch(MODULE + ".os.geteuid", return_value=0, create=True):
            result = observe_existing_btc_paper_once(
                private_paper_directory=Path("/tmp/never-read"), **flags)
        self.assertEqual(result["status"], "unprivileged_owner_required")
        self.assertFalse(result["network_attempted"])
