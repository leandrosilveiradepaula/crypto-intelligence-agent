"""D425: existing AUTO4 PAPER positions managed by public Bybit finite WS.

All tests use a fake WebSocket and a disposable synthetic PAPER SQLite journal.
No market network, account, exchange order or production service is touched.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    exclusive_paper_operator_lock, load_private_paper_routes,
    observe_existing_paper_positions_once,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    PLAN_VERSION, POSITION_ID, _new_position,
)
from scripts import run_j4_current_paper_ws_once_d425 as cli
from test_j2_j4_current_n50_paper_lease_d410 import (
    Clock, CURRENT, STATE, Socket, ack, ticker,
)

_SCHEMA = "j4-private-paper-routes-d425-v1"


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "POSIX nonroot only")
class PrivatePaperWSOperatorD425Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.home.chmod(0o700)
        self.paper = self.home / "paper-positions.sqlite"
        self.store = _new_position(self.paper, short=False)
        self.paper.chmod(0o600)
        self.manifest = self.home / "paper-routes.json"
        self.write_manifest()

    def route(self, **changes):
        result = {
            "position_id": POSITION_ID,
            "plan_version": PLAN_VERSION,
            "stop_mark_price": "99",
            "target_prices": ["101", "103"],
            "max_spread_bps": "30",
            "runner": None,
        }
        result.update(changes)
        return result

    def write_manifest(self, positions=None):
        payload = {
            "schema_version": _SCHEMA,
            "positions": [self.route()] if positions is None else positions,
        }
        self.manifest.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8",
        )
        self.manifest.chmod(0o600)

    def public_lease(self, frames, *, allow=True):
        sock_clock = Clock()
        sock = Socket(sock_clock, frames)
        with patch(
            "crypto_intelligence_agent.j2_j4_current_n50_paper_lease_d410."
            "read_current_j1_n50_scope",
            side_effect=(CURRENT, CURRENT),
        ) as reader, patch(
            "socket.create_connection",
            side_effect=AssertionError("no real network in PAPER test"),
        ):
            result = observe_existing_paper_positions_once(
                state_directory=STATE,
                private_paper_directory=self.home,
                allow_private_pointer_read=allow,
                allow_public_websocket=allow,
                confirm_personal_readonly_research=allow,
                confirm_region_eligible=allow,
                allow_synthetic_paper_reservations=allow,
                budget=TickerLeaseBudget(
                    max_sessions=1, max_frames=150, max_seconds=5,
                ),
                session_factory=lambda: sock,
                clock=sock_clock.mono, wall_ms=sock_clock.wall,
                sleeper=sock_clock.sleep,
            )
        return result, sock, reader

    def test_real_ledger_target_is_reserved_from_public_fixture_without_fill(self):
        result, sock, reader = self.public_lease([
            ack(), ticker("BTCUSDT", bid="101", mark="101"),
        ])
        self.assertTrue(sock.closed)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(len(sock.sent[0]["args"]), 51)
        self.assertEqual(result["positions_outside_n50_subscribed"], 1)
        self.assertEqual(result["paper_coverage_gate"]["quote_frames_delivered_to_paper"], 1)
        balance = self.store.load(POSITION_ID)
        self.assertEqual(len(balance.exit_orders), 1)
        self.assertEqual(str(balance.reserved_unfilled_units), "30")
        self.assertEqual(str(balance.filled_exit_units), "0")
        self.assertEqual(result["paper_monitoring"]["decision_counts"]["paper_target_reserved"], 1)
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["native_stop_verified"])
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn(POSITION_ID, json.dumps(result))

    def test_restart_repeats_same_price_without_a_second_intent(self):
        self.public_lease([ack(), ticker("BTCUSDT", bid="101", mark="101")])
        self.public_lease([ack(), ticker("BTCUSDT", bid="101", mark="101")])
        balance = self.store.load(POSITION_ID)
        self.assertEqual(len(balance.exit_orders), 1)
        self.assertEqual(str(balance.reserved_unfilled_units), "30")

    def test_fresh_stop_triggers_without_waiting_other_50_assets(self):
        result, _, _ = self.public_lease([
            ack(), ticker("BTCUSDT", bid="98", mark="98"),
        ])
        b = self.store.load(POSITION_ID)
        self.assertEqual(b.exit_orders[0].tranche_step, -1)
        self.assertEqual(str(b.protective_reserved_unfilled_units), "100")
        self.assertEqual(str(b.filled_exit_units), "0")
        self.assertEqual(result["paper_coverage_gate"]["quote_frames_delivered_to_paper"], 1)
        self.assertFalse(result["universe_health_sufficient_for_new_entries"])

    def test_no_optins_no_paper_file_read_or_socket(self):
        with patch(
            "crypto_intelligence_agent.j4_private_paper_ws_operator_d425."
            "load_private_paper_routes",
            side_effect=AssertionError("must not read private journal"),
        ):
            result = observe_existing_paper_positions_once(
                state_directory=Path("/private/nonexistent"),
                private_paper_directory=Path("/private/nonexistent"),
            )
        self.assertFalse(result["owner_scope_read"])
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["paper_journal_mutation_attempted"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 0)

    def test_private_manifest_rejects_changes_before_socket(self):
        original = self.route()
        bad = (
            [{"position_id": POSITION_ID, "plan_version": PLAN_VERSION}],
            [self.route(target_prices=["103", "101"])],
            [self.route(stop_mark_price=99)],
            [self.route(stop_mark_price="1e999999")],
            [self.route(plan_version="unknown")],
            [self.route(target_prices=["101"])],
            [self.route(max_spread_bps="-1")],
            [self.route(runner={"file":"../secrets", "activation_bps":"0",
                 "trail_distance_bps":"80", "max_tick_gap_ms":3000,
                 "max_last_tick_age_ms":3000})],
            [original, original],
        )
        for positions in bad:
            with self.subTest(positions=positions):
                self.write_manifest(positions)
                with self.assertRaises(DataValidationError):
                    load_private_paper_routes(self.home)
        self.write_manifest()
        with self.assertRaises(DataValidationError):
            self.manifest.write_text(
                '{"schema_version":"' + _SCHEMA +
                '","positions":[],"positions":[]}', encoding="ascii",
            )
            self.manifest.chmod(0o600)
            load_private_paper_routes(self.home)

    def test_owner_permissions_symlink_rejected_before_market(self):
        self.manifest.chmod(0o644)
        with self.assertRaises(DataValidationError):
            load_private_paper_routes(self.home)
        self.manifest.chmod(0o600)
        self.paper.chmod(0o644)
        with self.assertRaises(DataValidationError):
            load_private_paper_routes(self.home)
        self.paper.chmod(0o600)
        self.home.chmod(0o755)
        with self.assertRaises(DataValidationError):
            load_private_paper_routes(self.home)
        self.home.chmod(0o700)
        shadow = self.home / "manifest-copy"
        shutil.copy2(self.manifest, shadow)
        self.manifest.unlink()
        self.manifest.symlink_to(shadow)
        with self.assertRaises((OSError, DataValidationError)):
            load_private_paper_routes(self.home)

    def test_optional_runner_policy_is_typed_but_never_fills(self):
        self.write_manifest([self.route(runner={
            "file":"runner-shadow.sqlite", "activation_bps":"0",
            "trail_distance_bps":"70", "max_tick_gap_ms":3000,
            "max_last_tick_age_ms":3000,
        })])
        router = load_private_paper_routes(self.home)
        self.assertEqual(router.monitored_symbols, frozenset({"BTCUSDT"}))
        self.assertFalse((self.home / "runner-shadow.sqlite").exists())

    def test_concurrent_private_observer_is_refused(self):
        fd = exclusive_paper_operator_lock(self.home)
        try:
            with self.assertRaises(BlockingIOError):
                exclusive_paper_operator_lock(self.home)
        finally:
            os.close(fd)

    def test_cli_no_optin_and_invalid_owner_do_not_run(self):
        out = io.StringIO()
        with redirect_stdout(out), patch.object(
            cli, "observe_existing_paper_positions_once",
            side_effect=AssertionError("forbidden without consent"),
        ):
            self.assertEqual(cli.main([
                "--state-directory", str(STATE),
                "--private-paper-directory", str(self.home),
            ]), 77)
        self.assertIn("owner_market_and_paper_optin_required", out.getvalue())
        self.assertNotIn(str(self.home), out.getvalue())
        self.assertNotIn(POSITION_ID, out.getvalue())


class OfflineD425ImportTests(unittest.TestCase):
    def test_d425_never_adds_order_transport_or_live_flags(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "crypto_intelligence_agent" /
                  "j4_private_paper_ws_operator_d425.py").read_text(encoding="utf-8")
        cli_source = (root / "scripts" /
                      "run_j4_current_paper_ws_once_d425.py").read_text(encoding="utf-8")
        self.assertIn("run_current_n50_paper_lease_once", source)
        self.assertIn("allow_synthetic_paper_reservations", source)
        for forbidden in (
            "api.bybit.com", "new WebSocket", "order/create",
            "requests.post(", "POST /v5/order", "live_trading_enabled=True",
            "systemctl", "chmod 777",
        ):
            self.assertNotIn(forbidden, source + cli_source)


if __name__ == "__main__":
    unittest.main()
