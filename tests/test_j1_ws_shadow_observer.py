"""OPS30: bounded shadow observation against injected public fake frames."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_ws_shadow_observer import observe_shadow_once
from scripts.observe_j1_ws_shadow_once import run_owner_shadow, DEFAULT_TOPICS

HOUR = 3_600_000
START = 1_800_000_000_000 // HOUR * HOUR
END = START + HOUR - 1
AT = END + 2_001
ACK = {
    "op": "subscribe", "success": True, "ret_msg": "",
    "conn_id": "fake", "req_id": "cia-ops30-shadow",
}


def market(topic="kline.60.BTCUSDT", *, confirm=True, stamp=None):
    return {
        "topic": topic, "type": "snapshot", "ts": AT - 200,
        "data": [{
            "start": START, "end": END, "interval": "60",
            "open": "1.00", "high": "1.03", "low": "0.99",
            "close": "1.01", "volume": "2.5", "turnover": "3.0",
            "confirm": confirm,
            "timestamp": (END + 150 if confirm else END)
            if stamp is None else stamp,
        }],
    }


class Clock:
    def __init__(self):
        self.mono = 0

    def clock(self):
        return self.mono

    def wall(self):
        return AT


class Session:
    def __init__(self, events, fake):
        self.events = list(events)
        self.fake = fake
        self.sent = []
        self.closed = False

    def send(self, payload):
        item = json.loads(payload)
        self.sent.append(item)
        if item.get("op") == "ping":
            # A healthy fake connection acknowledges public heartbeats, so
            # finite leases reach their deadline without a false pong timeout.
            self.events.append({"op": "ping", "ret_msg": "pong"})

    def recv(self, timeout):
        if self.events:
            obj = self.events.pop(0)
            self.fake.mono += 0.1
            return json.dumps(obj)
        self.fake.mono += max(1, timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


class ShadowTests(unittest.TestCase):
    def exercise(self, events, **kwargs):
        fake = Clock()
        session = Session(events, fake)
        with patch("socket.create_connection",
                   side_effect=AssertionError("real sockets forbidden")):
            report = observe_shadow_once(
                session_factory=lambda: session, topics=DEFAULT_TOPICS,
                clock=fake.clock, wall_ms=fake.wall,
                max_seconds=90, max_frames=256, **kwargs)
        self.assertTrue(session.closed)
        self.assertEqual(session.sent[0]["op"], "subscribe")
        self.assertEqual(session.sent[0]["args"], list(DEFAULT_TOPICS))
        self.assertEqual(session.sent[0]["req_id"], "cia-ops30-shadow")
        self.assertEqual(len([s for s in session.sent
                              if s.get("op") == "subscribe"]), 1)
        output = report.sanitized_report()
        self.assertFalse(output["continuous_collector_authorized"])
        self.assertFalse(output["canonical_ohlcv_approved"])
        self.assertFalse(output["marketwide_top50_verified"])
        self.assertFalse(output["live_trading_authorized"])
        self.assertEqual(output["rest_gets"], 0)
        self.assertEqual(output["storage_writes"], 0)
        self.assertFalse(output["orders_sent"])
        for secret in ("BTCUSDT", "ETHUSDT", str(START),
                       str(END), "1.03", "2.5"):
            self.assertNotIn(secret, json.dumps(output))
        return report

    def test_two_topics_close_only_in_quarantine(self):
        z = self.exercise([
            ACK, market(), market("kline.60.ETHUSDT"),
        ])
        self.assertEqual(z.status, "shadow_closes_observed_quarantined")
        self.assertEqual(z.unique_closed, 2)
        self.assertEqual(z.topics_observed, 2)
        self.assertEqual(z.closed_bands[2], 2)

    def test_preack_close_is_discarded_then_postack_only(self):
        z = self.exercise([
            market(), ACK, market("kline.60.ETHUSDT"),
        ])
        self.assertEqual(z.status, "shadow_closes_observed_quarantined")
        self.assertEqual(z.preack_discarded, 1)
        self.assertEqual(z.unique_closed, 1)
        self.assertEqual(z.topics_observed, 1)

    def test_no_ack_and_ack_only_not_positive(self):
        z = self.exercise([market()])
        self.assertEqual(z.status, "shadow_no_ack_abstain")
        self.assertEqual(z.unique_closed, 0)
        self.assertEqual(z.preack_discarded, 1)
        z = self.exercise([ACK])
        self.assertEqual(z.status, "shadow_no_closed_candle_unverified")

    def test_closed_duplicate_is_not_a_new_candle(self):
        z = self.exercise([ACK, market(), market()])
        self.assertEqual(z.unique_closed, 1)
        self.assertEqual(z.duplicate_closes, 1)
        self.assertEqual(sum(z.closed_bands), 1)

    def test_open_and_anomalous_close_bands(self):
        f = market(confirm=False)
        z = self.exercise([ACK, f, market(stamp=END + 1),
                           market("kline.60.ETHUSDT", stamp=END + 1_001)])
        self.assertEqual(z.open_rows, 1)
        self.assertEqual(z.open_bands[0], 1)
        self.assertEqual(z.closed_bands[1], 1)
        self.assertEqual(z.closed_bands[3], 1)

    def test_atomic_multirow_rejects_bad_after_valid(self):
        f = market()
        f["data"].append(dict(f["data"][0], high="0.5",
                              confirm=False, timestamp=END))
        z = self.exercise([ACK, f])
        self.assertEqual(z.status, "shadow_row_abstain")
        self.assertEqual(z.unique_closed, 0)
        self.assertEqual(z.postack_market_frames, 0)

    def test_malformed_topic_ack_and_unexpected_controls(self):
        cases = (
            ([dict(ACK, req_id="wrong"), market()], "shadow_ack_invalid_abstain"),
            ([ACK, ACK, market()], "shadow_ack_invalid_abstain"),
            ([ACK, market("kline.60.XRPUSDT")], "shadow_envelope_abstain"),
            ([ACK, dict(market(), extra="private")], "shadow_envelope_abstain"),
            ([ACK, dict(market(), data=[])], "shadow_envelope_abstain"),
            ([ACK, {"op": "unknown"}], "shadow_control_abstain"),
        )
        for payload, status in cases:
            with self.subTest(status=status):
                self.assertEqual(self.exercise(payload).status, status)

    def test_postend_invalid_trade_clock_and_financial_values(self):
        f = market()
        f["data"][0]["timestamp"] = AT + 300
        self.assertEqual(self.exercise([ACK, f]).status,
                         "shadow_row_abstain")
        f = market()
        f["data"][0]["close"] = "9.99"
        self.assertEqual(self.exercise([ACK, f]).status,
                         "shadow_row_abstain")
        f = market()
        f["ts"] = AT + 1
        self.assertEqual(self.exercise([ACK, f]).status,
                         "shadow_clock_abstain")

    def test_no_retro_promotion_after_frame_limit(self):
        fake = Clock()
        session = Session([market()] * 129, fake)
        z = observe_shadow_once(
            session_factory=lambda: session, topics=DEFAULT_TOPICS,
            clock=fake.clock, wall_ms=fake.wall, max_frames=256)
        self.assertEqual(z.status, "shadow_preack_budget_abstain")
        self.assertEqual(z.unique_closed, 0)
        self.assertEqual(z.preack_discarded, 129)

    def test_bad_caps_without_opening_network(self):
        called = []
        for topics in ((), ("bad",), DEFAULT_TOPICS * 27):
            z = observe_shadow_once(
                session_factory=lambda: called.append(True), topics=topics)
            self.assertEqual(z.status, "shadow_configuration_abstain")
        self.assertFalse(called)

    def test_cli_requires_explicit_optin_and_unprivileged_user(self):
        called = []
        self.assertEqual(run_owner_shadow(
            session_factory=lambda: called.append(True),
            owner_check=lambda: True).status, "shadow_owner_optin_required")
        self.assertEqual(run_owner_shadow(
            allow_public_network=True, allow_public_websocket=True,
            confirm_region_and_personal_research=True,
            owner_check=lambda: False,
            session_factory=lambda: called.append(True)).status,
            "shadow_nonroot_required")
        self.assertFalse(called)
        fake = Clock()
        session = Session([ACK, market()], fake)
        z = run_owner_shadow(
            allow_public_network=True, allow_public_websocket=True,
            confirm_region_and_personal_research=True,
            owner_check=lambda: True, session_factory=lambda: session,
            clock=fake.clock, wall_ms=fake.wall)
        self.assertEqual(z.status, "shadow_closes_observed_quarantined")
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
