"""J1/OPS8: offline proof of the 52-topic Bybit handshake; NO actual network."""
from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_ws_linear_live_probe import (
    MAX_ARGS_CHARS, MAX_TOPICS, LinearWSProof,
    _validate_topics, owner_probe_linear_topics_once,
    probe_linear_topics_once, reviewed_candidate_topics,
)
from crypto_intelligence_agent.market_data import DataValidationError

TOPICS = tuple(sorted("kline.60.B" + str(i) + "USDT" for i in range(1, 53)))
HOUR_MS = 3_600_000
START = ((1_800_000_000_000 // HOUR_MS) - 1) * HOUR_MS
RECEIPT = START + HOUR_MS + 2000


def market(topic=TOPICS[0], closed=False):
    return {
        "topic": topic, "type": "snapshot", "ts": RECEIPT - 500,
        "data": [{
            "start": START, "end": START + HOUR_MS - 1,
            "interval": "60", "open": "1.00", "high": "1.02",
            "low": "0.99", "close": "1.01", "volume": "2.5",
            "turnover": "2.50", "confirm": closed,
            "timestamp": START + HOUR_MS - 1000,
        }],
    }


class Clock:
    def __init__(self):
        self.t = 0.0
    def __call__(self):
        return self.t


class Session:
    def __init__(self, clock, incoming=(), auto_ack=None, ping_pong=False):
        self.clock = clock
        self.incoming = list(incoming)
        self.auto_ack = auto_ack
        self.ping_pong = ping_pong
        self.sent = []
        self.closed = False
    def send(self, raw):
        obj = json.loads(raw)
        self.sent.append(obj)
        if obj["op"] == "subscribe" and self.auto_ack is not None:
            ack = dict(self.auto_ack)
            self.incoming.append(ack)
        if obj["op"] == "ping" and self.ping_pong:
            self.incoming.append({"op":"ping", "success": True,
                                  "conn_id": "fixture", "req_id": "",
                                  "ret_msg": "pong"})
    def recv(self, seconds):
        if not self.incoming:
            self.clock.t += seconds
            raise TimeoutError()
        self.clock.t += 0.05
        data = self.incoming.pop(0)
        if isinstance(data, Exception):
            raise data
        return json.dumps(data) if isinstance(data, dict) else data
    def close(self):
        self.closed = True


ACK = {"op":"subscribe", "success":True, "ret_msg":"",
       "conn_id":"fake", "req_id":""}


class LinearLiveProbeTests(unittest.TestCase):
    def run_probe(self, sequence=(), *, auto_ack=None, seconds=4, topics=TOPICS,
                  ping_pong=False, frames=512):
        clock = Clock()
        session = Session(clock, sequence, auto_ack=auto_ack, ping_pong=ping_pong)
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            report = probe_linear_topics_once(
                session_factory=lambda: session, topics=topics,
                clock=clock, wall_ms=lambda: RECEIPT,
                max_seconds=seconds, max_frames=frames)
        self.assertTrue(session.closed)
        self.assertEqual(len([x for x in session.sent if x["op"] == "subscribe"]), 1)
        self.assertEqual(session.sent[0]["args"], list(topics))
        return report, session

    def test_52_topics_single_request_and_ack_blank_missing_or_echo(self):
        for ack in (ACK, {k:v for k,v in ACK.items() if k != "req_id"},
                    dict(ACK, req_id="cia-probe-52")):
            with self.subTest(ack=ack):
                result, sock = self.run_probe([ack])
                self.assertEqual(result.status, "ws_ack_only_unverified")
                self.assertEqual(result.topics_requested, 52)
                self.assertEqual(result.subscription_acks, 1)
                self.assertEqual(result.valid_market_frames, 0)
                payload = json.dumps(sock.sent[0]["args"], separators=(",", ":"))
                self.assertLess(len(payload), MAX_ARGS_CHARS)
                self.assertFalse(result.sanitized_report()["all_topics_delivered_verified"])

    def test_valid_open_and_closed_candles_after_ack(self):
        result, _ = self.run_probe([ACK, market(closed=False), market(closed=True)])
        self.assertEqual(result.status, "ws_ack_with_market_frames_unverified")
        self.assertEqual(result.valid_market_frames, 2)
        self.assertEqual(result.validated_closed_events, 1)
        self.assertEqual(result.distinct_topics_seen, 1)
        self.assertEqual(result.distinct_closed_topics, 1)
        serialized = json.dumps(result.sanitized_report())
        self.assertNotIn("USDT", serialized)
        self.assertNotIn("1.01", serialized)
        for k in ("data_stored", "marketwide_top50_verified", "orders_sent",
                  "closed_24h_complete", "live_trading_authorized"):
            self.assertFalse(result.sanitized_report()[k])

    def test_preack_market_does_not_count_even_when_later_ack_succeeds(self):
        result, _ = self.run_probe([market(closed=True), ACK])
        self.assertEqual(result.pre_ack_market_frames, 1)
        self.assertEqual(result.valid_market_frames, 0)
        self.assertEqual(result.validated_closed_events, 0)
        self.assertEqual(result.status, "ws_ack_only_unverified")

    def test_preack_without_ack_never_approves_stream(self):
        result, _ = self.run_probe([market(closed=True)])
        self.assertEqual(result.status, "ws_ack_missing_abstain")
        self.assertEqual(result.subscription_acks, 0)
        self.assertEqual(result.validated_closed_events, 0)

    def test_wrong_req_rejected_nack_and_duplicate_ack(self):
        for frames in ([dict(ACK, req_id="WRONG")],
                       [dict(ACK, success=False)], [ACK, ACK]):
            with self.subTest(frames=frames):
                result, _ = self.run_probe(frames)
                self.assertEqual(result.status, "ws_ack_rejected_abstain")
                self.assertEqual(result.validated_closed_events, 0)

    def test_other_topic_and_malformed_candle_abstain(self):
        for bad in (market("kline.60.UNKNOWNUSDT"),
                    dict(market(), data=[dict(market()["data"][0], confirm="true")]),
                    dict(market(), ts=RECEIPT+6000),
                    {"op":"unsubscribe", "success":True}):
            with self.subTest(bad=bad):
                r, _ = self.run_probe([ACK, bad])
                self.assertEqual(r.status, "ws_frame_invalid_abstain")
                self.assertEqual(r.validated_closed_events, 0)

    def test_failed_socket_does_not_retry(self):
        result, _ = self.run_probe([ACK, OSError("offline EOF secret")])
        self.assertEqual(result.status, "ws_transport_abstain")
        self.assertEqual(result.frames_received, 1)
        self.assertNotIn("secret", json.dumps(result.sanitized_report()))

    def test_ping_pong_is_bounded(self):
        result, session = self.run_probe([ACK], seconds=26, ping_pong=True)
        self.assertGreaterEqual(len([x for x in session.sent if x["op"] == "ping"]), 1)
        self.assertGreaterEqual(result.heartbeat_pongs, 1)
        self.assertEqual(result.status, "ws_ack_only_unverified")

    def test_unknown_or_duplicate_topics_and_oversized_budget_prevent_connection(self):
        clock = Clock()
        for topics in ((TOPICS[0], TOPICS[0]), tuple(reversed(TOPICS)),
                       tuple(TOPICS) + ("kline.60.XYZUSDT",),
                       ("injection/BTC",)):
            with self.subTest(topics=topics), self.assertRaises(DataValidationError):
                probe_linear_topics_once(
                    session_factory=lambda: self.fail("socket called"), topics=topics,
                    clock=clock, wall_ms=lambda: RECEIPT)
        with self.assertRaises(DataValidationError):
            probe_linear_topics_once(
                session_factory=lambda: self.fail("socket called"), topics=TOPICS,
                clock=clock, wall_ms=lambda: RECEIPT, max_seconds=91)

    def test_negative_optin_is_zero_io_and_root_denied(self):
        with patch("crypto_intelligence_agent.bybit_ws_linear_live_probe.reviewed_candidate_topics",
                   side_effect=AssertionError("registry must not open")):
            a = owner_probe_linear_topics_once()
            self.assertEqual(a.status, "ws_owner_opt_in_required")
        b = owner_probe_linear_topics_once(
            allow_public_network=True, allow_public_websocket=True,
            confirm_region_and_personal_research=True,
            owner_check=lambda: False)
        self.assertEqual(b.status, "ws_owner_posix_unprivileged_required")
        self.assertEqual(b.topics_requested, 0)

    def test_owner_optin_uses_registry_and_one_injected_session(self):
        clock = Clock()
        sess = Session(clock, incoming=[ACK])
        with patch("crypto_intelligence_agent.bybit_ws_linear_live_probe.reviewed_candidate_topics",
                   return_value=TOPICS):
            result = owner_probe_linear_topics_once(
                allow_public_network=True, allow_public_websocket=True,
                confirm_region_and_personal_research=True,
                seconds=2, max_frames=100, owner_check=lambda: True,
                session_factory=lambda: sess, clock=clock, wall_ms=lambda: RECEIPT)
        self.assertEqual(result.status, "ws_ack_only_unverified")
        self.assertTrue(sess.closed)

    def test_candidate_names_only_not_proof_of_live_instrument(self):
        assets = tuple(SimpleNamespace(base="B"+str(i)) for i in range(1,53))
        with patch("crypto_intelligence_agent.bybit_ws_linear_live_probe.load_reviewed_registry",
                   return_value=SimpleNamespace(assets=assets)):
            topics = reviewed_candidate_topics(at_ms=RECEIPT)
        self.assertEqual(topics, TOPICS)
        self.assertEqual(len(topics), MAX_TOPICS)


if __name__ == "__main__":
    unittest.main()