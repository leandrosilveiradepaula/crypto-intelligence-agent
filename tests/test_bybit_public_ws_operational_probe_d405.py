"""D405 real public-WS probe logic exercised with no network or orders."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ws_operational_probe_d405 import (
    observe_finite_public_ws_once,
)
from crypto_intelligence_agent.market_data import DataValidationError

BASE = 1_800_000_000_000
ROOT = Path(__file__).resolve().parents[1]


def ack():
    return json.dumps({
        "success": True, "ret_msg": "subscribe", "conn_id": "fixture",
        "op": "subscribe", "req_id": "cia-ticker-1",
    })


def quote(symbol, *, utc=BASE, seq=1, bid="100.0", ask="100.1"):
    return json.dumps({
        "topic": "tickers." + symbol, "type": "snapshot",
        "ts": utc - 50, "cs": seq,
        "data": {
            "symbol": symbol, "lastPrice": "100",
            "markPrice": "100", "indexPrice": "100",
            "bid1Price": bid, "ask1Price": ask,
            "bid1Size": "2", "ask1Size": "3",
        },
    })


class Clock:
    def __init__(self):
        self.t = 0.0
        self.utc = BASE

    def mono(self):
        return self.t

    def wall(self):
        return self.utc

    def sleep(self, seconds):
        self.t += seconds
        self.utc += round(seconds * 1000)


class Socket:
    def __init__(self, clock, frames, *, late=None):
        self.clock = clock
        self.frames = list(frames)
        self.late = late
        self.sent = []
        self.closed = False

    def send(self, payload):
        data = json.loads(payload)
        if data.get("op") not in ("subscribe", "ping"):
            raise AssertionError("WS read-only request violated")
        self.sent.append(data)

    def recv(self, timeout):
        if self.frames:
            event = self.frames.pop(0)
            if isinstance(event, Exception):
                raise event
            return event
        if self.late is not None:
            if self.clock.t < 4:
                self.clock.sleep(min(timeout, 4 - self.clock.t))
                raise TimeoutError()
            event = self.late
            self.late = None
            return event
        self.clock.sleep(timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


def run(clock, sockets, *, symbols=("BTCUSDT",), positions=(),
        seconds=5, sessions=1, **opts):
    it = iter(sockets)
    return observe_finite_public_ws_once(
        symbols=symbols, position_symbols=positions,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        seconds=seconds, max_frames=256, max_sessions=sessions,
        session_factory=lambda: next(it),
        clock=clock.mono, wall_ms=clock.wall, sleeper=clock.sleep,
        **opts,
    )


class LiveWSProbeD405Tests(unittest.TestCase):
    def test_full_causal_coverage_with_recent_quote_and_no_order(self):
        c = Clock()
        sock = Socket(c, [ack()], late=quote("BTCUSDT", utc=BASE + 4_000))
        with patch("socket.create_connection",
                   side_effect=AssertionError("no real network")):
            result = run(c, [sock])
        self.assertEqual(result["status"], "lease_completed")
        self.assertTrue(result["finite_coverage_observed_once"])
        self.assertTrue(result["finite_coverage_fresh_at_end"])
        self.assertEqual(result["requested_contracts"], 1)
        self.assertEqual(result["received_distinct_contracts"], 1)
        self.assertEqual(result["fresh_contracts_at_end"], 1)
        self.assertEqual(result["p95_event_lag_bucket"], "0_to_100ms")
        self.assertEqual(result["p99_event_lag_bucket"], "0_to_100ms")
        self.assertEqual(result["subscription_acks"], 1)
        self.assertTrue(sock.closed)
        self.assertEqual(sock.sent[0]["op"], "subscribe")
        for flag in ("orders_sent", "approved_for_live_use",
                     "continuous_24x7_verified", "scope_independently_verified",
                     "marketwide_top50_verified", "paper_position_state_changed"):
            self.assertFalse(result[flag])
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn("100.0", json.dumps(result))
        self.assertNotIn("fixture", json.dumps(result))

    def test_missing_held_position_not_covered_even_if_btc_works(self):
        c = Clock()
        sock = Socket(c, [ack(), quote("BTCUSDT")])
        result = run(c, [sock], positions=("ETHUSDT",))
        self.assertEqual(result["requested_contracts"], 2)
        self.assertEqual(result["received_distinct_contracts"], 1)
        self.assertEqual(result["received_position_input_count"], 0)
        self.assertFalse(result["finite_coverage_observed_once"])
        self.assertFalse(result["finite_coverage_fresh_at_end"])
        self.assertTrue(sock.closed)

    def test_50_symbols_are_counted_distinct_no_false_missing(self):
        c = Clock()
        names = tuple(f"A{i:02d}USDT" for i in range(50))
        frames = [ack()] + [quote(name, seq=i + 1) for i, name in enumerate(names)]
        sock = Socket(c, frames)
        result = run(c, [sock], symbols=names)
        self.assertEqual(result["received_distinct_contracts"], 50)
        self.assertEqual(result["received_ranked_input_count"], 50)
        self.assertTrue(result["finite_coverage_observed_once"])
        self.assertFalse(result["finite_coverage_fresh_at_end"])
        self.assertFalse(result["marketwide_top50_verified"])

    def test_reconnect_loses_old_session_coverage(self):
        c = Clock()
        first = Socket(c, [ack(), quote("BTCUSDT"),
                           quote("ETHUSDT"), OSError("disconnect")])
        second = Socket(c, [ack(), quote("BTCUSDT", utc=BASE + 5_000)])
        result = run(c, [first, second], symbols=("BTCUSDT",),
                     positions=("ETHUSDT",), seconds=13, sessions=2)
        self.assertEqual(result["sessions_attempted"], 2)
        self.assertEqual(result["reconnects"], 1)
        self.assertEqual(result["received_distinct_contracts"], 1)
        self.assertFalse(result["finite_coverage_observed_once"])
        self.assertTrue(first.closed and second.closed)

    def test_missing_flags_do_not_even_open_injected_socket(self):
        calls = []
        def forbidden():
            calls.append(True)
            raise AssertionError("network forbidden")
        result = observe_finite_public_ws_once(
            symbols=("BTCUSDT",), session_factory=forbidden,
        )
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(calls, [])

    def test_invalid_budget_refuses_before_socket(self):
        for kwargs in ({"seconds": 61}, {"seconds": 0},
                       {"max_sessions": 3}, {"max_frames": 100_001},
                       {"symbols": ("BTCUSD",)}):
            c=Clock()
            with self.subTest(kwargs=kwargs), self.assertRaises(DataValidationError):
                args={"symbols": ("BTCUSDT",)}
                args.update(kwargs)
                observe_finite_public_ws_once(
                    **args, allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    session_factory=lambda: (_ for _ in ()).throw(
                        AssertionError("bad scope must not open network")),
                    clock=c.mono, wall_ms=c.wall, sleeper=c.sleep,
                )

    def test_cli_requires_flags_without_network(self):
        res = subprocess.run(
            [sys.executable, "-m",
             "scripts.probe_bybit_public_ws_once_d405",
             "--symbols", "BTCUSDT", "--seconds", "5"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(res.returncode, 65, res.stderr)
        body = json.loads(res.stdout)
        self.assertFalse(body["network_attempted"])
        self.assertFalse(body["orders_sent"])

    def test_cli_help_and_source_only_public_exchange(self):
        res = subprocess.run(
            [sys.executable, "-m",
             "scripts.probe_bybit_public_ws_once_d405", "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("--confirm-region-eligible", res.stdout)
        self.assertIn("--positions", res.stdout)
        source = (
            ROOT / "crypto_intelligence_agent" /
            "bybit_public_ws_operational_probe_d405.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("api_key", source.lower())
        self.assertNotIn("POST /v5/order", source)
        self.assertNotIn("sqlite3.connect", source)


if __name__ == "__main__":
    unittest.main()
