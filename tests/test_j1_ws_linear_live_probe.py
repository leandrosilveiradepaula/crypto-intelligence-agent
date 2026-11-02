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
                  ping_pong=False, frames=512, diagnose=False):
        clock = Clock()
        session = Session(clock, sequence, auto_ack=auto_ack, ping_pong=ping_pong)
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            report = probe_linear_topics_once(
                session_factory=lambda: session, topics=topics,
                clock=clock, wall_ms=lambda: RECEIPT,
                max_seconds=seconds, max_frames=frames,
                diagnostic_trade_stamp=diagnose)
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

    def test_trade_stamp_direction_and_confirm_are_privately_classified(self):
        for closed in (False, True):
            for direction, stamp in (("before", START-1),
                                     ("after", START+HOUR_MS)):
                row = dict(market(closed=closed)["data"][0], timestamp=stamp)
                bad = dict(market(closed=closed), data=[row])
                report, _ = self.run_probe([ACK, bad])
                expected = "clock_trade_stamp_" + direction + ("_closed" if closed else "_open")
                self.assertEqual(report.failure_category, expected)
                self.assertEqual(report.status, "ws_frame_invalid_abstain")
                self.assertEqual(report.validated_closed_events, 0)
                self.assertNotIn(str(stamp), json.dumps(report.sanitized_report()))

    def test_diagnostic_quarantines_open_and_closed_no_false_approval(self):
        open_bad = dict(market(closed=False), data=[
            dict(market()["data"][0], timestamp=START-1, confirm=False)])
        closed_bad = dict(market(closed=True), data=[
            dict(market(closed=True)["data"][0],
                 timestamp=START+HOUR_MS, confirm=True)])
        report, _ = self.run_probe([ACK, open_bad, closed_bad],
                                   frames=512, diagnose=True)
        self.assertEqual(report.status, "ws_timestamp_diagnostic_unverified")
        self.assertIsNone(report.failure_category)
        self.assertEqual(report.quarantined_open_stamp_frames, 1)
        self.assertEqual(report.quarantined_closed_stamp_frames, 1)
        self.assertEqual(report.stamp_before_frames, 1)
        self.assertEqual(report.stamp_after_frames, 1)
        self.assertEqual(report.validated_closed_events, 0)
        self.assertEqual(report.valid_market_frames, 0)
        self.assertFalse(report.sanitized_report()["all_topics_delivered_verified"])

    def test_closed_count_is_atomic_when_later_row_invalid(self):
        clean = dict(market(closed=True)["data"][0])
        invalid = dict(market(closed=False)["data"][0], timestamp=START-1)
        multi = dict(market(closed=True), data=[clean, invalid])
        report, _ = self.run_probe([ACK, multi])
        self.assertEqual(report.status, "ws_frame_invalid_abstain")
        self.assertEqual(report.valid_market_frames, 0)
        self.assertEqual(report.validated_closed_events, 0)
        self.assertEqual(report.failure_category, "clock_trade_stamp_before_open")
        diagnostic, _ = self.run_probe([ACK, multi], diagnose=True)
        self.assertEqual(diagnostic.validated_closed_events, 0)
        self.assertEqual(diagnostic.valid_market_frames, 0)
        self.assertEqual(diagnostic.quarantined_open_stamp_frames, 1)

    def test_trade_stamp_quarantine_never_hides_another_bad_row(self):
        first = dict(market(closed=False)["data"][0], timestamp=START-1)
        for later in (
            dict(market()["data"][0], high="0.1"),
            dict(market()["data"][0], confirm="false"),
            dict(market()["data"][0], volume="NaN"),
        ):
            with self.subTest(later=later):
                packet = dict(market(), data=[first, later])
                report, _ = self.run_probe([ACK, packet], diagnose=True)
                self.assertEqual(report.status, "ws_frame_invalid_abstain")
                self.assertEqual(report.valid_market_frames, 0)
                self.assertEqual(report.validated_closed_events, 0)
                self.assertEqual(report.quarantined_open_stamp_frames, 0)

    def test_trade_stamp_with_bad_ohlc_or_confirmation_fails_closed(self):
        for bad_field, value in (("high", "0.1"), ("confirm", "false"),
                                 ("turnover", "NaN")):
            with self.subTest(field=bad_field):
                row = dict(market()["data"][0], timestamp=START-1)
                row[bad_field] = value
                report, _ = self.run_probe([ACK, dict(market(), data=[row])],
                                           diagnose=True)
                self.assertEqual(report.status, "ws_frame_invalid_abstain")
                self.assertEqual(report.validated_closed_events, 0)
                self.assertEqual(report.quarantined_open_stamp_frames, 0)

    def test_multiple_timestamp_rows_count_one_frame_and_no_close(self):
        before = dict(market()["data"][0], timestamp=START-1, confirm=False)
        after = dict(market(closed=True)["data"][0],
                     timestamp=START+HOUR_MS, confirm=True)
        packet = dict(market(), data=[before, after])
        report, _ = self.run_probe([ACK, packet], diagnose=True)
        self.assertEqual(report.status, "ws_timestamp_diagnostic_unverified")
        self.assertEqual(report.quarantined_open_stamp_frames, 1)
        self.assertEqual(report.quarantined_closed_stamp_frames, 1)
        self.assertEqual(report.stamp_before_frames, 1)
        self.assertEqual(report.stamp_after_frames, 1)
        self.assertEqual(report.validated_closed_events, 0)
        self.assertEqual(report.valid_market_frames, 0)

    def test_default_strict_trade_stamp_gate_unchanged(self):
        from crypto_intelligence_agent.bybit_public_ws_once import _validate_one_kline_row
        row = dict(market()["data"][0], timestamp=START-1)
        with self.assertRaises(DataValidationError):
            _validate_one_kline_row(row, RECEIPT-500, RECEIPT)
        with self.assertRaises(DataValidationError):
            _validate_one_kline_row(row, RECEIPT-500, RECEIPT,
                                    diagnostic_ignore_trade_stamp=1)

    def test_stamp_overrun_coarse_bands_are_exact_at_boundaries(self):
        cases = ((1, "1ms"), (2, "2_to_1000ms"),
                 (1000, "2_to_1000ms"), (1001, "1001_to_5000ms"),
                 (5000, "1001_to_5000ms"), (5001, "over_5000ms"))
        for closed in (False, True):
            for delta, category in cases:
                with self.subTest(closed=closed, delta=delta):
                    stamp = START+HOUR_MS-1 + delta
                    row = dict(market(closed=closed)["data"][0], timestamp=stamp)
                    packet = dict(market(closed=closed), data=[row])
                    result, _ = self.run_probe([ACK, packet], diagnose=True)
                    bands = (result.sanitized_report()["stamp_overrun_closed_bands"]
                             if closed else result.sanitized_report()["stamp_overrun_open_bands"])
                    self.assertEqual(bands[category], 1)
                    self.assertEqual(sum(bands.values()), 1)
                    self.assertEqual(result.validated_closed_events, 0)
                    self.assertNotIn(str(stamp), json.dumps(result.sanitized_report()))

    def test_multirow_same_band_counts_one_frame(self):
        end = START + HOUR_MS - 1
        a = dict(market(closed=False)["data"][0], timestamp=end+2)
        b = dict(market(closed=False)["data"][0], timestamp=end+1000)
        packet = dict(market(), data=[a, b])
        result, _ = self.run_probe([ACK, packet], diagnose=True)
        self.assertEqual(result.quarantined_open_stamp_frames, 1)
        self.assertEqual(result.sanitized_report()["stamp_overrun_open_bands"]["2_to_1000ms"], 1)
        self.assertEqual(result.valid_market_frames, 0)

    def test_multirow_distinct_bands_count_only_worst_per_frame(self):
        end = START + HOUR_MS - 1
        rows = [
            dict(market(closed=True)["data"][0], timestamp=end+1, confirm=True),
            dict(market(closed=True)["data"][0], timestamp=end+5001, confirm=True),
            dict(market()["data"][0], timestamp=end+1000, confirm=False),
        ]
        packet = dict(market(), data=rows)
        report, _ = self.run_probe([ACK, packet], diagnose=True)
        bins = report.sanitized_report()
        closed = bins["stamp_overrun_closed_bands"]
        opened = bins["stamp_overrun_open_bands"]
        self.assertEqual(sum(closed.values()), 1)
        self.assertEqual(sum(opened.values()), 1)
        self.assertEqual(closed["over_5000ms"], 1)
        self.assertEqual(closed["1ms"], 0)
        self.assertEqual(opened["2_to_1000ms"], 1)
        self.assertEqual(report.quarantined_closed_stamp_frames, 1)
        self.assertEqual(report.quarantined_open_stamp_frames, 1)
        self.assertEqual(report.stamp_after_frames, 1)
        self.assertEqual(report.validated_closed_events, 0)
        self.assertFalse(bins["closed_24h_complete"])

    def test_strict_mode_never_counts_overrun_as_approved(self):
        stamp = START + HOUR_MS
        row = dict(market(closed=True)["data"][0], timestamp=stamp)
        packet = dict(market(closed=True), data=[row])
        result, _ = self.run_probe([ACK, packet])
        self.assertEqual(result.status, "ws_frame_invalid_abstain")
        self.assertEqual(result.validated_closed_events, 0)
        self.assertEqual(sum(result.sanitized_report()["stamp_overrun_closed_bands"].values()), 0)

    def test_unrelated_validation_still_fails_closed_in_diagnostic(self):
        broken = dict(market(), data=[dict(market()["data"][0], high="0.1")])
        report, _ = self.run_probe([ACK, broken], diagnose=True)
        self.assertEqual(report.status, "ws_frame_invalid_abstain")
        self.assertEqual(report.failure_category, "kline_ohlc")
        self.assertEqual(report.validated_closed_events, 0)

    def test_frame_cap_before_deadline_is_abstention_not_success(self):
        result, session = self.run_probe(
            [ACK, market(closed=False), market(closed=False)],
            seconds=20, frames=3,
        )
        self.assertEqual(result.status, "ws_frame_budget_exhausted_abstain")
        self.assertEqual(result.failure_category, "frame_budget")
        self.assertEqual(result.subscription_acks, 1)
        self.assertEqual(result.valid_market_frames, 2)
        self.assertFalse(result.sanitized_report()["all_topics_delivered_verified"])
        self.assertTrue(session.closed)

    def test_service_sized_live_probe_budget_is_bounded(self):
        from crypto_intelligence_agent.bybit_ws_linear_live_probe import MAX_FRAMES
        self.assertGreaterEqual(MAX_FRAMES, 52 * 90)
        self.assertLessEqual(MAX_FRAMES, 8192)
        result, _ = self.run_probe([ACK], seconds=4, frames=MAX_FRAMES)
        self.assertEqual(result.status, "ws_ack_only_unverified")

    def test_sanitized_kline_close_failure_categories_without_market_leak(self):
        samples = (
            ("ws_clock_trade_stamp_invalid", "clock_trade_stamp"),
            ("ws_clock_closed_before_server_end", "clock_closed_before_server_end"),
            ("ws_clock_closed_before_local_end", "clock_closed_before_local_end"),
            ("ws_clock_closed_too_old", "clock_closed_too_old"),
            ("ws_clock_grid_invalid", "clock_grid"),
            ("ws_kline_fields_invalid", "kline_fields"),
            ("ws_ohlc_invalid", "kline_ohlc"),
            ("ws_confirm_type_invalid", "kline_confirmation"),
            ("secret path /root/key and 123456", "kline_invalid"),
        )
        for internal_reason, expected in samples:
            with self.subTest(internal_reason=internal_reason), patch(
                "crypto_intelligence_agent.bybit_ws_linear_live_probe._validate_one_kline_row",
                side_effect=DataValidationError(internal_reason),
            ):
                result, _ = self.run_probe([ACK, market(closed=True)])
                self.assertEqual(result.status, "ws_frame_invalid_abstain")
                self.assertEqual(result.failure_category, expected)
                self.assertEqual(result.validated_closed_events, 0)
                sanitized = json.dumps(result.sanitized_report())
                self.assertNotIn("secret", sanitized)
                self.assertNotIn("123456", sanitized)
                self.assertNotIn("USDT", sanitized)

    def test_non_validation_exception_is_generic_not_echoed(self):
        with patch(
            "crypto_intelligence_agent.bybit_ws_linear_live_probe._validate_one_kline_row",
            side_effect=ValueError("secret credentials"),
        ):
            report, _ = self.run_probe([ACK, market(closed=True)])
        self.assertEqual(report.failure_category, "processing")
        self.assertNotIn("secret", json.dumps(report.sanitized_report()))

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