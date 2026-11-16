"""D390: opt-in Bybit public ticker adapter, no real network in CI."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_optin_d390 import (
    run_readonly_bybit_ticker_lease,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.market_data import DataValidationError

T = 1_800_000_000_000


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.utc = T

    def mono(self):
        return self.t

    def wall(self):
        return self.utc

    def sleep(self, seconds):
        self.t += seconds
        self.utc += int(seconds * 1000)


class FakeSocket:
    def __init__(self, clock, frames):
        self.clock, self.frames, self.sent = clock, list(frames), []
        self.closed = False

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self, timeout):
        if self.frames:
            return self.frames.pop(0)
        self.clock.sleep(timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


def ack():
    return json.dumps({"success": True, "ret_msg": "subscribe",
                       "conn_id": "fixture", "op": "subscribe",
                       "req_id": "cia-ticker-1"})


def quote():
    return json.dumps({
        "topic": "tickers.BTCUSDT", "type": "snapshot",
        "ts": T - 50, "cs": 1,
        "data": {"symbol": "BTCUSDT", "lastPrice": "101",
                 "markPrice": "100", "indexPrice": "100",
                 "bid1Price": "100.9", "ask1Price": "101.1",
                 "bid1Size": "2", "ask1Size": "3"},
    })


def run(clock, *, frames, **more):
    sock = FakeSocket(clock, frames)
    result = run_readonly_bybit_ticker_lease(
        ranked_symbols=("BTCUSDT",),
        universe_at_ms=T-1000,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        session_factory=lambda: sock,
        clock=clock.mono, wall_ms=clock.wall, sleeper=clock.sleep,
        budget=TickerLeaseBudget(max_sessions=1, max_frames=20, max_seconds=4),
        **more,
    )
    return result, sock


class BybitPublicTickerOptinD390Tests(unittest.TestCase):
    def test_missing_opt_in_does_not_open_any_socket(self):
        for kwargs in ({}, {"allow_public_websocket": True},
                       {"allow_public_websocket": True,
                        "confirm_personal_readonly_research": True}):
            with self.subTest(gates=kwargs):
                with patch(
                    "crypto_intelligence_agent.bybit_public_ticker_optin_d390._public_bybit_session",
                    side_effect=AssertionError("transport must not open"),
                ):
                    result = run_readonly_bybit_ticker_lease(
                        ranked_symbols=("BTCUSDT",), universe_at_ms=T,
                        **kwargs,
                    )
                self.assertEqual(result["status"], "owner_opt_in_required_no_network")
                self.assertEqual(result["ticker_frames_accepted"], 0)
                self.assertFalse(result["orders_sent"])

    def test_exact_public_ticker_lease_with_injected_fake_socket(self):
        clock=FakeClock()
        result, sock=run(clock, frames=[ack(), quote()])
        self.assertEqual(result["status"], "lease_completed")
        self.assertEqual(result["ticker_frames_accepted"], 1)
        self.assertEqual(result["subscription_acks" if "subscription_acks" in result
                                    else "subscriptions_acknowledged"], 1)
        self.assertTrue(result["public_data_only"])
        self.assertTrue(result["no_service_installed"])
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["approved_for_live_use"])
        self.assertFalse(result["orders_sent"])
        self.assertTrue(sock.closed)
        self.assertEqual(sock.sent[0]["op"], "subscribe")
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn("100.9", json.dumps(result))

    def test_ack_alone_is_not_market_price_proof(self):
        clock=FakeClock()
        result, sock=run(clock, frames=[ack()])
        self.assertEqual(result["status"], "public_market_frames_not_verified")
        self.assertEqual(result["ticker_frames_accepted"], 0)
        self.assertTrue(sock.closed)
        self.assertFalse(result["orders_sent"])

    def test_bad_input_cannot_open_transport(self):
        for kwargs in [
            {"allow_public_websocket": 1},
            {"confirm_personal_readonly_research": "yes"},
            {"confirm_region_eligible": None},
        ]:
            with self.subTest(case=kwargs):
                with patch(
                    "crypto_intelligence_agent.bybit_public_ticker_optin_d390._public_bybit_session",
                    side_effect=AssertionError("no transport on invalid gate"),
                ):
                    with self.assertRaises(DataValidationError):
                        run_readonly_bybit_ticker_lease(
                            ranked_symbols=("BTCUSDT",), universe_at_ms=T,
                            **kwargs,
                        )

    def test_invalid_universe_refuses_factory_before_network(self):
        clock=FakeClock()
        called=[]
        def factory():
            called.append(1)
            raise AssertionError("not supposed to connect")
        with self.assertRaises(DataValidationError):
            run_readonly_bybit_ticker_lease(
                ranked_symbols=("BTCEUR",), universe_at_ms=T,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True, session_factory=factory,
                clock=clock.mono, wall_ms=clock.wall, sleeper=clock.sleep,
            )
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
