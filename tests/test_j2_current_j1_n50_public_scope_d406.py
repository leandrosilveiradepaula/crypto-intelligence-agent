"""D406: current J1 owner N50 -> J2 Bybit PUBLIC WS, no private data in CI."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import crypto_intelligence_agent.j2_current_j1_n50_public_scope_d406 as bridge
from crypto_intelligence_agent.j1_n50_ws_epoch_rotation import ActiveN50WSEpoch
from crypto_intelligence_agent.j1_n50_ws_private_cache import N50WSPrivateAdmission
from crypto_intelligence_agent.j1_n50_ws_dynamic_scope import DynamicN50WSAdmission
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

ROOT = Path(__file__).resolve().parents[1]
NOW = 1_800_000_000_000
SHA = "a" * 64
META = "b" * 64
NAMES = tuple(f"A{i:02d}USDT" for i in range(50))
# Mock-only fixture path: absolute on Linux AND Windows; no file is created.
PRIVATE = ROOT / "d406-private-owner-test-fixture"
MANIFEST = PRIVATE / "manifest"
WS_CACHE = PRIVATE / "metadata"


def active(*, metadata=META, activated=NOW - 100_000):
    return ActiveN50WSEpoch(
        status="active_n50_ws_epoch_revalidated",
        manifest_directory=MANIFEST, ws_directory=WS_CACHE,
        ranked_scope_sha256=SHA, ws_metadata_sha256=metadata,
        activated_at_ms=activated,
    )


def cached(*, symbols=NAMES, metadata=META):
    admission = DynamicN50WSAdmission(
        ws_scope=SimpleNamespace(
            contracts=tuple(SimpleNamespace(symbol=s) for s in symbols)),
        ranked_scope_sha256=SHA,
        metadata_sha256=metadata,
        observed_at_ms=NOW - 100_000,
    )
    return N50WSPrivateAdmission(
        status="private_n50_ws_admission_loaded_revalidated",
        admission=admission,
        ranked_scope={"not_public": "validated_by_owner"},
    )


def patches(active_states=None, cache=None, members=NAMES):
    stack = ExitStack()
    owner = stack.enter_context(patch.object(
        bridge, "load_active_n50_ws_epoch",
        side_effect=active_states if active_states is not None else
        [active(), active()],
    ))
    reader = stack.enter_context(patch.object(
        bridge, "load_n50_ws_dynamic_admission",
        return_value=cache if cache is not None else cached(),
    ))
    rank = stack.enter_context(patch.object(
        bridge, "validate_ranked_research_scope", return_value=(members, SHA),
    ))
    return stack, owner, reader, rank


class Clock:
    def __init__(self):
        self.t = 0.0
        self.at = NOW

    def mono(self):
        return self.t

    def wall(self):
        return self.at

    def sleep(self, seconds):
        self.t += seconds
        self.at += round(seconds * 1000)


def quote(name, seq):
    return json.dumps({
        "topic": "tickers." + name,
        "type": "snapshot", "ts": NOW - 50,
        "cs": seq,
        "data": {
            "symbol": name, "lastPrice": "101", "markPrice": "100",
            "indexPrice": "100", "bid1Price": "100.9",
            "ask1Price": "101.1", "bid1Size": "2", "ask1Size": "3",
        },
    })


class Socket:
    def __init__(self, clock, symbols):
        self.clock = clock
        self.raw = [json.dumps({
            "op": "subscribe", "success": True,
            "ret_msg": "subscribe", "conn_id": "secret-socket-id",
            "req_id": "cia-ticker-1",
        })] + [quote(name, index + 1)
              for index, name in enumerate(symbols)]
        self.sent = []
        self.closed = False

    def send(self, raw):
        packet = json.loads(raw)
        if packet.get("op") not in ("subscribe", "ping"):
            raise AssertionError("D406 attempted private or order operation")
        self.sent.append(packet)

    def recv(self, timeout):
        if self.raw:
            return self.raw.pop(0)
        self.clock.sleep(timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


class J2CurrentJ1N50D406Tests(unittest.TestCase):
    def test_no_owner_flag_never_reads_or_opens_network(self):
        with patch.object(bridge, "load_active_n50_ws_epoch",
                          side_effect=AssertionError("no owner read")), patch.object(
            bridge, "observe_finite_public_ws_once",
            side_effect=AssertionError("no WS")
        ):
            result = bridge.probe_current_j1_n50_ws_once(
                state_directory=PRIVATE, allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
            )
        self.assertEqual(result["status"], "owner_scope_and_public_ws_optin_required")
        self.assertFalse(result["private_state_read"])
        self.assertFalse(result["network_attempted"])

    def test_valid_private_pointer_is_checked_twice_with_same_scope(self):
        stack, pointer, reader, validator = patches()
        with stack:
            scope = bridge.read_current_j1_n50_scope(
                state_directory=PRIVATE, now_ms=NOW,
                allow_private_pointer_read=True,
            )
        self.assertEqual(len(scope.symbols), 50)
        self.assertEqual(scope.ranked_scope_sha256, SHA)
        self.assertNotIn("A00USDT", repr(scope))
        self.assertNotIn("A00USDT", json.dumps(scope.sanitized_report()))
        self.assertEqual(pointer.call_count, 2)
        reader.assert_called_once_with(
            directory=WS_CACHE, current_at_ms=NOW,
            expected_ranked_scope_sha256=SHA,
            allow_private_scope_read=True,
        )
        validator.assert_called_once_with(
            {"not_public": "validated_by_owner"},
            now_ms=NOW, max_assets=50,
        )
        self.assertFalse(scope.sanitized_report()["marketwide_top50_verified"])

    def test_rotation_between_reads_aborts_without_network(self):
        stack, _, _, _ = patches(
            active_states=[active(), active(activated=NOW - 50_000)],
        )
        with stack, self.assertRaises(DataGapError):
            bridge.read_current_j1_n50_scope(
                state_directory=PRIVATE, now_ms=NOW,
                allow_private_pointer_read=True,
            )

    def test_stale_untrusted_or_mismatched_cohort_aborts(self):
        variants = (
            {"active_states": [ActiveN50WSEpoch("active_n50_ws_epoch_read_abstain")]},
            {"cache": cached(symbols=NAMES[:-1])},
            {"cache": cached(metadata="f" * 64)},
            {"members": NAMES[:-1]},
            {"members": NAMES[:-1] + ("BTCUSDT",)},
        )
        for variant in variants:
            with self.subTest(variant=tuple(variant)):
                stack, _, _, _ = patches(**variant)
                with stack, self.assertRaises(DataGapError):
                    bridge.read_current_j1_n50_scope(
                        state_directory=PRIVATE, now_ms=NOW,
                        allow_private_pointer_read=True,
                    )

    def test_reuses_same_current_n50_plus_held_outside_rank_in_actual_pipeline(self):
        clock = Clock()
        extra = "BTCUSDT"  # Held PAPER instrument outside current J1 cohort.
        sock = Socket(clock, NAMES + (extra,))
        with patch.object(bridge, "read_current_j1_n50_scope",
                          return_value=bridge.CurrentResearchN50(
                              symbols=NAMES, ranked_scope_sha256=SHA,
                              metadata_sha256=META,
                              activated_at_ms=NOW - 100_000,
                          )):
            result = bridge.probe_current_j1_n50_ws_once(
                state_directory=PRIVATE,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                position_symbols=(extra,),
                seconds=5, session_factory=lambda: sock,
                clock=clock.mono, wall_ms=clock.wall, sleeper=clock.sleep,
            )
        self.assertEqual(result["owner_scope_members"], 50)
        self.assertEqual(result["requested_contracts"], 51)
        self.assertEqual(result["received_distinct_contracts"], 51)
        self.assertEqual(result["received_position_input_count"], 1)
        self.assertEqual(result["subscription_acks"], 1)
        self.assertTrue(result["finite_coverage_observed_once"])
        self.assertFalse(result["finite_coverage_fresh_at_end"])
        self.assertFalse(result["real_market_frames_verified"])
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(result["data_mode"], "injected_offline_fixture")
        self.assertEqual(len(sock.sent[0]["args"]), 51)
        self.assertTrue(sock.closed)
        serialized = json.dumps(result)
        self.assertNotIn("A00USDT", serialized)
        self.assertNotIn("BTCUSDT", serialized)
        self.assertNotIn("secret-socket-id", serialized)

    def test_invalid_owner_arguments_refused_without_read(self):
        for directory, now in (
            (Path("relative"), NOW),
            ("/private/current-n50-owner", NOW),
            (PRIVATE, 0),
            (PRIVATE, "1800000000000"),
        ):
            with self.subTest(directory=directory, now=now):
                with patch.object(bridge, "load_active_n50_ws_epoch",
                                  side_effect=AssertionError("no read")):
                    with self.assertRaises(DataValidationError):
                        bridge.read_current_j1_n50_scope(
                            state_directory=directory, now_ms=now,
                            allow_private_pointer_read=True,
                        )

    def test_bad_positions_or_duration_refused_before_owner_file(self):
        for positions, seconds in (
            (("INVALID",), 20),
            (("BTCUSDT", "BTCUSDT"), 20),
            (["BTCUSDT"], 20),
            ((), 0),
            ((), 61),
            ((), True),
        ):
            with self.subTest(positions=positions, seconds=seconds), patch.object(
                bridge, "read_current_j1_n50_scope",
                side_effect=AssertionError("must reject before reading J1 owner"),
            ), self.assertRaises(DataValidationError):
                bridge.probe_current_j1_n50_ws_once(
                    state_directory=PRIVATE,
                    allow_private_pointer_read=True,
                    allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    position_symbols=positions, seconds=seconds,
                    wall_ms=lambda: NOW,
                )

    def test_cli_no_explicit_permissions_cannot_access_private_scope(self):
        args = [
            sys.executable, "-m",
            "scripts.probe_current_j1_n50_bybit_ws_d406",
            "--state-directory", str(PRIVATE),
        ]
        completed = subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(completed.returncode, 77, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertFalse(report["network_attempted"])
        self.assertFalse(report["private_state_read"])
        self.assertFalse(report["orders_sent"])


if __name__ == "__main__":
    unittest.main()
