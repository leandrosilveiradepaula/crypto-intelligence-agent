"""D410: current J1 N50 + AUTO4 position WS routing, offline only."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.j2_current_j1_n50_public_scope_d406 import CurrentResearchN50
from crypto_intelligence_agent.j2_j4_current_n50_paper_lease_d410 import (
    run_current_n50_paper_lease_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    HOUR_START_MS, MINUTE_MS, POSITION_ID, _new_position, _route,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind,
)

NOW = HOUR_START_MS + 12 * MINUTE_MS
N50 = tuple(f"ALT{i:02d}USDT" for i in range(50))
STATE = Path(__file__).resolve().parents[1] / "d410-owner-dry-run-only"
CURRENT = CurrentResearchN50(
    symbols=N50, ranked_scope_sha256="a" * 64,
    metadata_sha256="b" * 64, activated_at_ms=HOUR_START_MS,
)


class Clock:
    def __init__(self):
        self.t = 0.0
        self.now = NOW

    def mono(self):
        return self.t

    def wall(self):
        return self.now

    def sleep(self, seconds):
        self.t += seconds
        self.now += round(seconds * 1000)


class Socket:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.sent = []
        self.closed = False

    def send(self, raw):
        packet = json.loads(raw)
        if packet.get("op") not in ("subscribe", "ping"):
            raise AssertionError("not a public Bybit WS operation")
        self.sent.append(packet)

    def recv(self, timeout):
        if self.frames:
            frame = self.frames.pop(0)
            if isinstance(frame, Exception):
                raise frame
            return frame
        self.clock.sleep(timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


def ack():
    return json.dumps({
        "op": "subscribe", "success": True, "ret_msg": "subscribe",
        "req_id": "cia-ticker-1", "conn_id": "sensitive-id-not-for-report",
    })


def ticker(symbol, *, seq=1, time_delta=0, bid="100", mark="100"):
    return json.dumps({
        "topic": "tickers." + symbol, "type": "snapshot",
        "ts": NOW - 10 + time_delta, "cs": seq,
        "data": {
            "symbol": symbol, "lastPrice": bid,
            "markPrice": mark, "indexPrice": mark,
            "bid1Price": bid, "ask1Price": "101.02",
            "bid1Size": "2", "ask1Size": "3",
        },
    })


class J2J4CurrentN50PaperD410Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "paper.sqlite"
        self.store = _new_position(self.path, short=False)
        self.router = _route(self.path, short=False)
        self.clock = Clock()

    def run_once(self, frames, *, epochs=(CURRENT, CURRENT), budget=None):
        sock = Socket(self.clock, frames)
        with patch(
            "crypto_intelligence_agent.j2_j4_current_n50_paper_lease_d410."
            "read_current_j1_n50_scope",
            side_effect=epochs,
        ) as reader, patch(
            "socket.create_connection",
            side_effect=AssertionError("offline test cannot access network"),
        ):
            result = run_current_n50_paper_lease_once(
                state_directory=STATE, paper_router=self.router,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                allow_synthetic_paper_reservations=True,
                budget=budget or TickerLeaseBudget(
                    max_sessions=1, max_frames=200, max_seconds=5,
                ),
                session_factory=lambda: sock,
                clock=self.clock.mono, wall_ms=self.clock.wall,
                sleeper=self.clock.sleep,
            )
        return result, sock, reader

    def test_50_plus_held_outside_rank_reaches_paper_when_all_fresh(self):
        frames = [ack()] + [ticker(s) for s in N50] + [
            ticker("BTCUSDT", bid="101"),
        ]
        result, sock, reader = self.run_once(frames)
        self.assertTrue(sock.closed)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(len(sock.sent[0]["args"]), 51)
        self.assertEqual(result["positions_outside_n50_subscribed"], 1)
        self.assertEqual(result["position_contracts_derived_from_existing_auto4_router"], 1)
        self.assertEqual(result["requested_distinct_contracts"], 51)
        self.assertEqual(result["unique_distinct_contracts_observed"], 51)
        self.assertEqual(result["paper_coverage_gate"]["quote_frames_deferred"], 50)
        self.assertEqual(result["paper_coverage_gate"]["quote_frames_delivered_to_paper"], 1)
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 1)
        self.assertEqual(str(self.store.load(POSITION_ID).reserved_unfilled_units), "30")
        self.assertEqual(str(self.store.load(POSITION_ID).filled_exit_units), "0")
        self.assertTrue(result["finite_coverage_observed_once"])
        self.assertFalse(result["finite_coverage_fresh_at_end"])
        self.assertEqual(result["status"], "finite_paper_lease_degraded_or_incomplete")
        self.assertEqual(result["data_mode"], "injected_offline_fixture")
        self.assertFalse(result["real_market_frames_verified"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["native_stop_verified"])
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn(POSITION_ID, json.dumps(result))
        self.assertNotIn("sensitive-id", json.dumps(result))

    def test_missing_one_contract_blocks_favorable_tick_without_journal_write(self):
        frames = [ack()] + [ticker(s) for s in N50[:-1]] + [
            ticker("BTCUSDT", bid="101"),
        ]
        result, sock, _ = self.run_once(frames)
        self.assertTrue(sock.closed)
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 0)
        self.assertEqual(result["paper_coverage_gate"]["quote_frames_delivered_to_paper"], 0)
        self.assertEqual(result["unique_distinct_contracts_observed"], 50)
        self.assertFalse(result["finite_coverage_observed_once"])
        self.assertEqual(result["status"], "finite_paper_lease_degraded_or_incomplete")

    def test_position_tick_before_full_coverage_does_not_open_until_new_tick(self):
        frames = [ack(), ticker("BTCUSDT", bid="101")] + [
            ticker(s) for s in N50
        ] + [ticker("BTCUSDT", seq=2, time_delta=1, bid="101")]
        result, sock, _ = self.run_once(frames)
        self.assertTrue(sock.closed)
        self.assertEqual(result["paper_coverage_gate"]["quote_frames_deferred"], 50)
        self.assertGreaterEqual(result["paper_coverage_gate"]["quote_frames_delivered_to_paper"], 1)
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 1)

    def test_changed_owner_epoch_after_lease_reports_degraded(self):
        rotated = replace(CURRENT, ranked_scope_sha256="c" * 64)
        frames = [ack()] + [ticker(s) for s in N50] + [
            ticker("BTCUSDT", bid="101"),
        ]
        result, _, _ = self.run_once(frames, epochs=(CURRENT, rotated))
        self.assertFalse(result["owner_scope_unchanged_after_lease"])
        self.assertEqual(result["status"], "finite_paper_lease_degraded_or_incomplete")
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 1)
        self.assertFalse(result["approved_for_live_use"])

    def test_missing_paper_write_optin_blocks_owner_read_and_network(self):
        with patch(
            "crypto_intelligence_agent.j2_j4_current_n50_paper_lease_d410."
            "read_current_j1_n50_scope",
            side_effect=AssertionError("owner never read without PAPER gate"),
        ), patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            result = run_current_n50_paper_lease_once(
                state_directory=STATE, paper_router=self.router,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
            )
        self.assertFalse(result["owner_scope_read"])
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["paper_journal_mutation_attempted"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 0)

    def test_fail_closed_when_owner_scope_revalidation_fails(self):
        with patch(
            "crypto_intelligence_agent.j2_j4_current_n50_paper_lease_d410."
            "read_current_j1_n50_scope", side_effect=DataGapError("private owner missing")
        ), self.assertRaises(DataGapError):
            run_current_n50_paper_lease_once(
                state_directory=STATE, paper_router=self.router,
                allow_private_pointer_read=True, allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True, allow_synthetic_paper_reservations=True,
                session_factory=lambda: (_ for _ in ()).throw(
                    AssertionError("no socket before scope verification")),
                clock=self.clock.mono, wall_ms=self.clock.wall,
                sleeper=self.clock.sleep,
            )
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 0)

    def test_d390_default_paper_behavior_kept_for_legacy_callers(self):
        from crypto_intelligence_agent.bybit_public_ticker_optin_d390 import (
            run_readonly_bybit_ticker_lease,
        )
        sock = Socket(self.clock, [ack(), ticker("BTCUSDT", bid="101")])
        result = run_readonly_bybit_ticker_lease(
            ranked_symbols=("BTCUSDT",), universe_at_ms=HOUR_START_MS,
            allow_public_websocket=True, confirm_personal_readonly_research=True,
            confirm_region_eligible=True, paper_router=self.router,
            budget=TickerLeaseBudget(max_sessions=1, max_frames=20, max_seconds=5),
            session_factory=lambda: sock, clock=self.clock.mono,
            wall_ms=self.clock.wall, sleeper=self.clock.sleep,
        )
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 1)
        self.assertNotIn("paper_coverage_gate", result)
        self.assertFalse(result["orders_sent"])

    def test_unknown_reservation_still_blocks_second_target_or_stop(self):
        frames = [ack()] + [ticker(s) for s in N50] + [
            ticker("BTCUSDT", bid="101"),
        ]
        self.run_once(frames)
        intent = self.store.load(POSITION_ID).exit_orders[-1].intent.intent_id
        at = NOW + 1
        self.store.append_exit_events(
            POSITION_ID, intent, (
                PaperOrderEvent(
                    "fixture_d410_unknown", PaperOrderEventKind.UNKNOWN, at,
                ),
            ), as_of_ms=at,
        )
        self.router = _route(self.path, short=False)
        self.clock = Clock()
        result, _, _ = self.run_once([ack()] + [ticker(s) for s in N50] + [
            ticker("BTCUSDT", bid="101"),
        ])
        self.assertEqual(len(self.store.load(POSITION_ID).exit_orders), 1)
        self.assertGreaterEqual(result["paper_coverage_gate"]["quote_frames_delivered_to_paper"], 1)
        self.assertEqual(str(self.store.load(POSITION_ID).reserved_unfilled_units), "30")


if __name__ == "__main__":
    unittest.main()
