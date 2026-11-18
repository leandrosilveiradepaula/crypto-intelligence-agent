"""D426: first real-style public tick seeds an ephemeral PAPER scenario.

This suite NEVER opens a real public socket. It reuses D386's fake session,
the existing AUTO4 transaction engine and the current J1 owner scope fixture.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from decimal import Decimal
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget,
)
from crypto_intelligence_agent.j4_shadow_public_paper_pilot_d426 import (
    ShadowPaperPolicy, observe_shadow_paper_once,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts import run_j4_shadow_public_paper_once_d426 as cli
from test_j2_j4_current_n50_paper_lease_d410 import (
    CURRENT, STATE, Clock, Socket, ack, ticker,
)

MODULE = "crypto_intelligence_agent.j4_shadow_public_paper_pilot_d426"
_SYMBOL = "BTCUSDT"


def frame(*, bid="100", ask="100.02", mark="100", seq=1, delta=0):
    obj = json.loads(ticker(_SYMBOL, bid=bid, mark=mark,
                            seq=seq, time_delta=delta))
    obj["data"]["ask1Price"] = ask
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


class ShadowPAPERPublicD426Tests(unittest.TestCase):
    def policy(self, *, side=SyntheticSide.LONG, **kw):
        return ShadowPaperPolicy(symbol=_SYMBOL, side=side, **kw)

    def run_once(self, frames, *, policy=None, gate=True):
        clock = Clock()
        socket = Socket(clock, frames)
        with patch(MODULE + ".read_current_j1_n50_scope",
                   side_effect=(CURRENT, CURRENT)) as reader, patch(
            "socket.create_connection",
            side_effect=AssertionError("no network for D426 fixtures"),
        ):
            r = observe_shadow_paper_once(
                state_directory=STATE, policy=policy or self.policy(),
                allow_private_pointer_read=gate,
                allow_public_websocket=gate,
                confirm_personal_readonly_research=gate,
                confirm_region_eligible=gate,
                allow_hypothetical_paper_open=gate,
                budget=TickerLeaseBudget(
                    max_sessions=1, max_frames=120, max_seconds=4,
                ),
                session_factory=lambda: socket,
                clock=clock.mono, wall_ms=clock.wall,
                sleeper=clock.sleep,
            )
        return r, socket, reader

    def test_real_d386_path_hypothetical_open_then_auto4_target_without_any_click(self):
        result, sock, reader = self.run_once([
            ack(),
            frame(),
            ("delay", 1),
            frame(seq=2, delta=1_000, bid="101", ask="101.02", mark="101"),
        ])
        self.assertTrue(sock.closed)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(len(sock.sent[0]["args"]), 51)
        self.assertEqual(result["status"], "shadow_public_quote_routed_paper_only")
        self.assertEqual(result["subscription_acks"], 1)
        self.assertEqual(result["ticker_frames_accepted"], 2)
        self.assertTrue(result["synthetic_open_created"])
        self.assertTrue(result["synthetic_entry_fill_fabricated_for_research"])
        self.assertEqual(result["position_quote_events_after_open"], 1)
        self.assertEqual(result["synthetic_exit_intents_reserved"], 1)
        self.assertEqual(result["paper_decision_counts"]["paper_target_reserved"], 1)
        self.assertEqual(result["configured_leverage"], 50)
        self.assertEqual(result["requested_margin_quote_synthetic_only"], "3")
        for key in ("native_stop_verified", "market_quote_is_executable_fill",
                    "requested_margin_is_actual_collateral",
                    "orders_sent", "entry_signal_generated",
                    "fixture_venue_lot_step_verified",
                    "synthetic_position_persisted_after_run"):
            self.assertIs(result[key], False)
        wire = json.dumps(result)
        self.assertNotIn(_SYMBOL, wire)
        self.assertNotIn("fixture_d426_open", wire)
        self.assertNotIn("101.02", wire)

    def test_stop_before_targets_with_fresh_mark(self):
        result, _, _ = self.run_once([
            ack(), frame(),
            ("delay", 1),
            frame(seq=2, delta=1_000, bid="98", ask="98.02", mark="98"),
        ])
        self.assertEqual(result["synthetic_exit_intents_reserved"], 1)
        self.assertEqual(result["paper_decision_counts"]["paper_stop_reserved"], 1)
        self.assertNotIn("paper_target_reserved", result["paper_decision_counts"])

    def test_short_side_auto_partial_reuses_same_journal_logic(self):
        result, _, _ = self.run_once([
            ack(), frame(),
            ("delay", 1),
            frame(seq=2, delta=1_000, bid="98", ask="98.02", mark="98"),
        ], policy=self.policy(side=SyntheticSide.SHORT))
        self.assertEqual(result["status"], "shadow_public_quote_routed_paper_only")
        self.assertEqual(result["synthetic_exit_intents_reserved"], 1)
        self.assertEqual(result["paper_decision_counts"]["paper_target_reserved"], 1)

    def test_preack_quotes_do_not_seed_paper_and_no_trading(self):
        result, _, _ = self.run_once([frame(), ack()])
        self.assertEqual(result["subscription_acks"], 1)
        self.assertFalse(result["synthetic_open_created"])
        self.assertEqual(result["synthetic_exit_intents_reserved"], 0)
        self.assertFalse(result["orders_sent"])

    def test_not_fresh_at_seed_never_opens_position(self):
        result, _, _ = self.run_once([
            ack(), ("delay", 4), frame(),
        ])
        self.assertFalse(result["synthetic_open_created"])
        self.assertEqual(result["synthetic_exit_intents_reserved"], 0)

    def test_seed_tick_is_never_reused_as_exit_decision(self):
        result, _, _ = self.run_once([ack(), frame()])
        self.assertEqual(result["status"], "shadow_opened_no_followup_quote")
        self.assertEqual(result["position_quote_events_after_open"], 0)
        self.assertEqual(result["synthetic_exit_intents_reserved"], 0)

    def test_without_any_optin_scope_network_and_position_are_never_touched(self):
        with patch(MODULE + ".read_current_j1_n50_scope",
                   side_effect=AssertionError("no private owner read")), patch(
            MODULE + ".TemporaryDirectory",
            side_effect=AssertionError("no fake position created"),
        ):
            r = observe_shadow_paper_once(
                state_directory=Path("/never-read-owner"),
                policy=self.policy(),
            )
        self.assertFalse(r["owner_scope_read"])
        self.assertFalse(r["synthetic_open_created"])
        self.assertFalse(r["network_attempted"])
        self.assertFalse(r["orders_sent"])

    def test_rejects_noncausal_or_unsafe_sizing_and_leverage(self):
        for overrides in (
            {"margin_quote": Decimal("0")},
            {"margin_quote": Decimal("NaN")},
            {"leverage": 0},
            {"leverage": 101},
            {"leverage": True},
            {"target1_distance_bps": Decimal("0")},
            {"target1_distance_bps": Decimal("20"),
             "target2_distance_bps": Decimal("10")},
            {"stop_distance_bps": Decimal("1100")},
            {"max_entry_spread_bps": Decimal("101")},
            {"symbol": "BTC"},
            {"symbol": "ETHUSDT/../../"},
        ):
            with self.subTest(changes=overrides), self.assertRaises(DataValidationError):
                self.policy(**overrides)

    def test_cli_without_gates_does_not_connect(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout), patch.object(
            cli, "observe_shadow_paper_once",
            side_effect=AssertionError("opt-in required"),
        ):
            exitcode = cli.main([
                "--state-directory", str(STATE), "--symbol", _SYMBOL,
                "--side", "LONG",
            ])
        self.assertEqual(exitcode, 77)
        self.assertIn("optins_required", stdout.getvalue())
        self.assertNotIn(_SYMBOL, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
