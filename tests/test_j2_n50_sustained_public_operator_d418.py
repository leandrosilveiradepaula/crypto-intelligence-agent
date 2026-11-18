"""D418 offline tests: prolonged PUBLIC Bybit N50 monitor, no network/account."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import crypto_intelligence_agent.j2_n50_sustained_public_operator_d418 as operator
from crypto_intelligence_agent.j2_current_j1_n50_public_scope_d406 import (
    CurrentResearchN50,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_bybit_public_ws_operational_probe_d405 import (
    BASE, Clock, Socket, ack, quote,
)

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "d418-private-owner-test-fixture"  # no backing files created
N50 = tuple(f"A{i:02d}USDT" for i in range(50))
SCOPE = CurrentResearchN50(
    symbols=N50, ranked_scope_sha256="a" * 64,
    metadata_sha256="b" * 64, activated_at_ms=BASE-100_000,
)


def run_once(
    clock: Clock, sockets: list[Socket], *, scopes=(SCOPE, SCOPE),
    position_symbols=(), seconds=60, max_sessions=1, **extra,
):
    sessions = iter(sockets)
    with patch.object(operator, "read_current_j1_n50_scope",
                      side_effect=scopes) as reader, patch(
        "socket.create_connection",
        side_effect=AssertionError("offline must not create real socket"),
    ):
        result = operator.observe_current_n50_sustained_once(
            state_directory=STATE,
            position_symbols=position_symbols,
            allow_private_pointer_read=True,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            seconds=seconds, max_sessions=max_sessions, max_frames=10_000,
            session_factory=lambda: next(sessions),
            clock=clock.mono, wall_ms=clock.wall, sleeper=clock.sleep,
            **extra,
        )
    return result, reader


class SustainedPublicN50D418Tests(unittest.TestCase):
    def test_one_minute_live_protocol_simulation_and_exchange_staleness(self):
        c = Clock()
        sock = Socket(c, [ack()] + [
            quote(s, seq=i+1) for i, s in enumerate(N50)
        ])
        result, reader = run_once(c, [sock])
        self.assertEqual(result["status"], "sustained_market_observed_once")
        self.assertEqual(result["underlying_ws_status"], "lease_completed")
        self.assertEqual(result["requested_distinct_contracts"], 50)
        self.assertEqual(result["unique_distinct_contracts_observed"], 50)
        self.assertEqual(result["validated_quote_contracts"], 50)
        self.assertEqual(result["fresh_distinct_contracts_at_end"], 0)
        self.assertEqual(result["eligible_quote_expired_at_end_contracts"], 50)
        self.assertTrue(result["finite_coverage_observed_once"])
        self.assertFalse(result["finite_coverage_fresh_at_end"])
        self.assertTrue(result["finite_current_owner_scope_observed_once"])
        self.assertTrue(result["owner_scope_unchanged_after_lease"])
        self.assertEqual(result["observation_elapsed_seconds"], 60)
        self.assertGreaterEqual(result["heartbeat_pings"], 2)
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["real_market_frames_verified"])
        self.assertFalse(result["paper_reservations_enabled"])
        self.assertFalse(result["continuous_24x7_verified"])
        self.assertFalse(result["approved_for_signals"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(reader.call_count, 2)
        self.assertTrue(sock.closed)
        serialized = json.dumps(result)
        for s in (N50[0], N50[20], "100.9", "sensitive_owner_path", "account_key"):
            self.assertNotIn(s, serialized)

    def test_existing_position_outside_n50_is_subscribed_but_never_managed(self):
        c = Clock()
        extra = "BTCUSDT"
        sock = Socket(c, [ack()] + [
            quote(s, seq=i+1) for i, s in enumerate(N50 + (extra,))
        ])
        result, _ = run_once(c, [sock], position_symbols=(extra,))
        self.assertEqual(result["requested_distinct_contracts"], 51)
        self.assertEqual(result["unique_distinct_contracts_observed"], 51)
        self.assertEqual(result["positions_outside_n50_subscribed"], 1)
        self.assertEqual(result["requested_position_contracts"], 1)
        self.assertTrue(result["finite_current_owner_scope_observed_once"])
        self.assertFalse(result["paper_position_state_changed"])
        self.assertFalse(result["orders_sent"])
        self.assertNotIn(extra, json.dumps(result))

    def test_epoch_rotation_degrades_lease_without_remapping_symbols(self):
        c = Clock()
        rotated = replace(SCOPE, activated_at_ms=SCOPE.activated_at_ms + 1)
        sock = Socket(c, [ack()] + [
            quote(s, seq=i+1) for i, s in enumerate(N50)
        ])
        result, _ = run_once(c, [sock], scopes=(SCOPE, rotated))
        self.assertEqual(result["status"], "sustained_owner_scope_changed_or_unavailable")
        self.assertTrue(result["finite_coverage_observed_once"])
        self.assertFalse(result["finite_current_owner_scope_observed_once"])
        self.assertFalse(result["owner_scope_unchanged_after_lease"])
        self.assertFalse(result["approved_for_signals"])
        self.assertFalse(result["orders_sent"])

    def test_unavailable_epoch_after_lease_abstains_without_private_exception(self):
        c = Clock()
        sock = Socket(c, [ack(), quote(N50[0])])
        with patch.object(operator, "read_current_j1_n50_scope",
                          side_effect=[SCOPE, DataGapError("sensitive owner path")]):
            result = operator.observe_current_n50_sustained_once(
                state_directory=STATE,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                seconds=60, max_frames=10_000, max_sessions=1,
                session_factory=lambda: sock,
                clock=c.mono, wall_ms=c.wall, sleeper=c.sleep,
            )
        self.assertEqual(result["status"], "sustained_owner_scope_changed_or_unavailable")
        self.assertFalse(result["owner_scope_unchanged_after_lease"])
        self.assertFalse(result["finite_current_owner_scope_observed_once"])
        self.assertNotIn("sensitive owner path", json.dumps(result))
        self.assertFalse(result["orders_sent"])

    def test_transient_network_reconnect_requires_fresh_session_quotes(self):
        c = Clock()
        first = Socket(c, [ack(), quote(N50[0]), OSError("offline disconnect")])
        second = Socket(c, [ack()] + [
            quote(s, seq=i+1, utc=BASE + 5_000) for i, s in enumerate(N50)
        ])
        report, _ = run_once(c, [first, second], max_sessions=2)
        self.assertEqual(report["status"], "sustained_market_observed_once")
        self.assertEqual(report["sessions_attempted"], 2)
        self.assertEqual(report["reconnects"], 1)
        self.assertEqual(report["unique_distinct_contracts_observed"], 50)
        self.assertTrue(report["finite_current_owner_scope_observed_once"])
        self.assertFalse(report["approved_for_live_use"])
        self.assertTrue(first.closed and second.closed)

    def test_missing_gates_never_read_private_owner_or_open_network(self):
        with patch.object(operator, "read_current_j1_n50_scope",
                          side_effect=AssertionError("no owner")):
            result = operator.observe_current_n50_sustained_once(
                state_directory=STATE,
            )
        self.assertEqual(result["status"], "owner_and_public_network_optin_required")
        self.assertFalse(result["private_state_read"])
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["orders_sent"])

    def test_clock_nan_blocks_owner_before_any_network(self):
        c = Clock()
        with patch.object(
            operator, "read_current_j1_n50_scope",
            side_effect=AssertionError("invalid clock must not read owner"),
        ), self.assertRaises(DataValidationError):
            operator.observe_current_n50_sustained_once(
                state_directory=STATE,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                session_factory=lambda: (_ for _ in ()).throw(
                    AssertionError("invalid clock must not open socket")),
                clock=lambda: float("nan"), wall_ms=c.wall,
                sleeper=c.sleep,
            )

    def test_recent_owner_epoch_activation_sets_causal_lower_bound(self):
        c = Clock()
        recent = replace(SCOPE, activated_at_ms=BASE - 10_000)
        def lease(**params):
            self.assertEqual(params["universe_at_ms"], BASE - 10_000)
            self.assertEqual(params["ranked_symbols"], N50)
            self.assertNotIn("paper_router", params)
            c.sleep(60)
            return {
                "status": "lease_completed",
                "subscriptions_acknowledged": 1,
                "ticker_frames_accepted": 50,
                "finite_coverage_observed_once": True,
            }
        with patch.object(operator, "read_current_j1_n50_scope",
                          side_effect=(recent, recent)), patch.object(
            operator, "run_readonly_bybit_ticker_lease",
            side_effect=lease,
        ):
            report = operator.observe_current_n50_sustained_once(
                state_directory=STATE,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                seconds=60, max_frames=10_000, max_sessions=1,
                session_factory=lambda: None,
                clock=c.mono, wall_ms=c.wall, sleeper=c.sleep,
            )
        self.assertTrue(report["full_finite_duration_observed"])
        self.assertTrue(report["finite_current_owner_scope_observed_once"])
        self.assertFalse(report["approved_for_signals"])

    def test_fast_fake_completion_cannot_claim_prolonged_observation(self):
        c = Clock()
        with patch.object(operator, "read_current_j1_n50_scope",
                          side_effect=(SCOPE, SCOPE)), patch.object(
            operator, "run_readonly_bybit_ticker_lease",
            return_value={
                "status": "lease_completed",
                "subscriptions_acknowledged": 1,
                "ticker_frames_accepted": 50,
                "finite_coverage_observed_once": True,
            },
        ):
            report = operator.observe_current_n50_sustained_once(
                state_directory=STATE,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                seconds=60, max_frames=10_000, max_sessions=1,
                session_factory=lambda: None,
                clock=c.mono, wall_ms=c.wall, sleeper=c.sleep,
            )
        self.assertFalse(report["full_finite_duration_observed"])
        self.assertFalse(report["finite_current_owner_scope_observed_once"])
        self.assertEqual(report["status"], "sustained_market_degraded_or_partial")

    def test_invalid_inputs_block_before_owner_read(self):
        args = {
            "state_directory": STATE,
            "allow_private_pointer_read": True,
            "allow_public_websocket": True,
            "confirm_personal_readonly_research": True,
            "confirm_region_eligible": True,
        }
        for invalid in (
            {"seconds": 59}, {"seconds": 901}, {"seconds": True},
            {"max_frames": 999}, {"max_frames": 200_001},
            {"max_sessions": 3}, {"position_symbols": ["BTCUSDT"]},
            {"position_symbols": ("BTCEUR",)},
            {"allow_public_websocket": "yes"},
        ):
            with self.subTest(invalid=invalid), patch.object(
                operator, "read_current_j1_n50_scope",
                side_effect=AssertionError("no owner on invalid settings"),
            ), self.assertRaises(DataValidationError):
                operator.observe_current_n50_sustained_once(
                    **{**args, **invalid},
                    session_factory=lambda: (_ for _ in ()).throw(
                        AssertionError("no network on invalid settings")),
                )

    def test_cli_without_flags_abstains_and_no_network(self):
        proc = subprocess.run([
            sys.executable, "-m",
            "scripts.probe_current_j1_n50_sustained_bybit_ws_d418",
            "--state-directory", str(STATE),
        ], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 77, proc.stderr)
        body = json.loads(proc.stdout)
        self.assertFalse(body["private_state_read"])
        self.assertFalse(body["network_attempted"])
        self.assertFalse(body["orders_sent"])
        self.assertNotIn("BTCUSDT", proc.stdout)


if __name__ == "__main__":
    unittest.main()
