"""OPS22: finite, read-only, owner-only WS and one REST call; offline fakes."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_ws_rest_one_candle_probe import (
    HOUR_MS, TOPIC, compare_one_candle_once, owner_compare_one_candle,
    public_rest_once,
)
from crypto_intelligence_agent.market_data import DataValidationError

START = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
END = START + HOUR_MS - 1
AT = END + 2001

ACK = {"op": "subscribe", "success": True, "ret_msg": "",
       "conn_id": "fake", "req_id": "cia-ops22-single"}


def ws(close=True):
    return {
        "topic": TOPIC, "type": "snapshot", "ts": AT - 500,
        "data": [{
            "start": START, "end": END, "interval": "60",
            "open": "1.00", "high": "1.03", "low": "0.99",
            "close": "1.01", "volume": "2.50", "turnover": "3.00",
            "confirm": close, "timestamp": END + 300 if close else END,
        }],
    }


def rest():
    return {"retCode": 0, "result": {
        "category": "linear", "symbol": "BTCUSDT",
        "list": [[str(START), "1.00", "1.03", "0.99", "1.01", "2.50", "3.00"]]}}


class FakeClock:
    def __init__(self):
        self.tick = 0.0

    def __call__(self):
        return self.tick


class FakeSession:
    def __init__(self, frames, clock):
        self.frames = list(frames)
        self.clock = clock
        self.sent = []
        self.closed = False

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self, _):
        if self.frames:
            item = self.frames.pop(0)
            return json.dumps(item)
        self.clock.tick += 100
        raise TimeoutError()

    def close(self):
        self.closed = True


class WSOneCandleTests(unittest.TestCase):
    def exercise(self, frames=None, reference=None, current=AT, fetch_exception=None,
                 include_ack=True, wait=None):
        clock = FakeClock()
        s = FakeSession(([ACK] if include_ack else []) +
                        ([ws()] if frames is None else frames), clock)
        get_calls = []
        sleep_calls = []
        wall_values = iter(wait) if wait is not None else None

        def fake_fetch(start, end):
            get_calls.append((start, end))
            if fetch_exception is not None:
                raise fetch_exception
            return rest() if reference is None else reference

        def wall():
            return next(wall_values) if wall_values is not None else current

        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            result = compare_one_candle_once(
                session_factory=lambda: s, rest_fetch_once=fake_fetch,
                clock=clock, wall_ms=wall,
                sleeper=lambda seconds: sleep_calls.append(seconds))
        self.assertTrue(s.closed)
        self.assertEqual(len(s.sent), 1)
        self.assertEqual(s.sent[0]["args"], [TOPIC])
        self.assertEqual(s.sent[0]["op"], "subscribe")
        self.assertLessEqual(len(get_calls), 1)
        self.assertFalse(result.sanitized_report()["ws_candle_approved"])
        return result, get_calls, sleep_calls

    def test_all_six_fields_equal_but_never_authorized(self):
        result, gets, sleeps = self.exercise()
        self.assertEqual(result.status, "ws_rest_match_unverified")
        self.assertEqual((result.fields_compared, result.fields_equal), (6, 6))
        self.assertEqual(gets, [(START, END)])
        self.assertEqual(result.rest_gets, 1)
        self.assertFalse(sleeps)
        payload = json.dumps(result.sanitized_report())
        for secret in ("BTCUSDT", str(START), str(END), "1.03", "2.50"):
            self.assertNotIn(secret, payload)
        self.assertFalse(result.sanitized_report()["source_authenticated"])

    def test_each_value_difference_remains_unverified(self):
        for column, value in [(1, "1.002"), (2, "1.04"), (3, "0.98"),
                              (4, "1.02"), (5, "2.6"), (6, "3.1")]:
            with self.subTest(column=column):
                data = rest()
                data["result"]["list"][0][column] = value
                result, gets, _ = self.exercise(reference=data)
                self.assertEqual(result.status, "ws_rest_diverge_abstain")
                self.assertEqual(result.fields_compared, 6)
                self.assertEqual(result.fields_equal, 5)
                self.assertEqual(len(gets), 1)

    def test_single_topic_sends_bounded_public_ping_and_accepts_pong(self):
        clock = FakeClock()
        class PingSession(FakeSession):
            def recv(self, timeout):
                if self.frames and self.frames[0] is None:
                    self.frames.pop(0)
                    self.clock.tick += 22
                    raise TimeoutError()
                return super().recv(timeout)
        session = PingSession([ACK, None, {"op": "ping", "ret_msg": "pong"}, ws()], clock)
        calls = []
        def fetch(start, end):
            calls.append((start, end))
            return rest()
        result = compare_one_candle_once(
            session_factory=lambda: session, rest_fetch_once=fetch,
            clock=clock, wall_ms=lambda: AT, sleeper=lambda _: None)
        self.assertTrue(session.closed)
        self.assertEqual([m["op"] for m in session.sent], ["subscribe", "ping"])
        self.assertEqual(result.status, "ws_rest_match_unverified")
        self.assertEqual(calls, [(START, END)])

    def test_10006_is_one_get_without_retry(self):
        result, gets, _ = self.exercise(reference={"retCode": 10006})
        self.assertEqual(result.status, "rest_rate_limit_abstain")
        self.assertEqual(result.rest_gets, 1)
        self.assertEqual(len(gets), 1)
        result, gets, _ = self.exercise(fetch_exception=OSError("secret /home/owner"))
        self.assertEqual(result.status, "rest_transport_abstain")
        self.assertEqual(len(gets), 1)
        self.assertNotIn("secret", json.dumps(result.sanitized_report()))

    def test_no_get_for_unconfirmed_or_missing_ack(self):
        result, gets, _ = self.exercise(frames=[ws(close=False)])
        self.assertEqual(result.status, "ws_no_qualifying_close_abstain")
        self.assertEqual(gets, [])
        result, gets, _ = self.exercise(include_ack=False)
        self.assertEqual(result.status, "ws_ack_missing_abstain")
        self.assertEqual(gets, [])
        result, gets, _ = self.exercise(frames=[ACK, ws()])
        self.assertEqual(result.status, "ws_ack_invalid_abstain")
        self.assertEqual(gets, [])

    def test_preack_market_then_ack_then_postack_closed_candle(self):
        # The pre-ACK frame is dropped; ONLY the closed frame after ACK
        # may become a candidate and trigger a single REST request.
        result, gets, _ = self.exercise(
            include_ack=False, frames=[ws(close=False), ACK, ws(close=True)])
        self.assertEqual(result.status, "ws_rest_match_unverified")
        self.assertEqual((result.fields_compared, result.fields_equal), (6, 6))
        self.assertEqual(result.rest_gets, 1)
        self.assertEqual(len(gets), 1)

    def test_preack_closed_candle_never_promoted_after_ack(self):
        # A closed candle received before ACK is never buffered or replayed.
        result, gets, _ = self.exercise(
            include_ack=False, frames=[ws(close=True), ACK])
        self.assertEqual(result.status, "ws_no_qualifying_close_abstain")
        self.assertEqual((result.fields_compared, result.fields_equal), (0, 0))
        self.assertEqual(gets, [])

    def test_preack_closed_candle_without_ack_never_calls_rest(self):
        result, gets, _ = self.exercise(
            include_ack=False, frames=[ws(close=True)])
        self.assertEqual(result.status, "ws_ack_missing_abstain")
        self.assertEqual(gets, [])
        self.assertEqual(result.rest_gets, 0)

    def test_preack_frame_limit_and_malformed_envelope_abstain(self):
        for frames, status in (
            ([ws(close=False)] * 9 + [ACK, ws()], "ws_preack_budget_abstain"),
            ([{**ws(), "topic": "kline.60.ETHUSDT"}, ACK, ws()],
             "ws_preack_envelope_abstain"),
            ([{**ws(), "data": None}, ACK, ws()],
             "ws_preack_envelope_abstain"),
            ([{**ws(), "extra": "bad"}, ACK, ws()],
             "ws_preack_envelope_abstain"),
        ):
            with self.subTest(status=status):
                result, gets, _ = self.exercise(include_ack=False, frames=frames)
                self.assertEqual(result.status, status)
                self.assertEqual(result.rest_gets, 0)
                self.assertEqual(gets, [])

    def test_preack_then_wrong_ack_is_rejected(self):
        wrong = dict(ACK, req_id="another-request")
        result, gets, _ = self.exercise(
            include_ack=False, frames=[ws(close=False), wrong, ws()])
        self.assertEqual(result.status, "ws_ack_invalid_abstain")
        self.assertEqual(gets, [])

    def test_two_rows_with_single_postack_close_compare_once(self):
        # A multi-row envelope may include the still-open row followed by the
        # one eligible close; only that close enters the OPS21 single-row audit.
        frame = ws(close=True)
        frame["data"] = [ws(close=False)["data"][0], frame["data"][0]]
        result, gets, _ = self.exercise(frames=[frame])
        self.assertEqual(result.status, "ws_rest_match_unverified")
        self.assertEqual((result.fields_compared, result.fields_equal), (6, 6))
        self.assertEqual(result.rest_gets, 1)
        self.assertEqual(len(gets), 1)

    def test_multirow_close_selection_is_order_independent(self):
        frame = ws(close=True)
        frame["data"] = [frame["data"][0], ws(close=False)["data"][0]]
        result, gets, _ = self.exercise(frames=[frame])
        self.assertEqual(result.status, "ws_rest_match_unverified")
        self.assertEqual(len(gets), 1)

    def test_multirow_invalid_later_row_blocks_candidate(self):
        frame = ws(close=True)
        bad = dict(ws(close=False)["data"][0], high="-1")
        frame["data"] = [frame["data"][0], bad]
        result, gets, _ = self.exercise(frames=[frame])
        self.assertEqual(result.status, "ws_row_abstain")
        self.assertEqual(gets, [])

    def test_multirow_duplicate_confirmed_close_is_never_selected(self):
        frame = ws(close=True)
        frame["data"] = [frame["data"][0], dict(frame["data"][0])]
        result, gets, _ = self.exercise(frames=[frame])
        self.assertEqual(result.status, "ws_multiple_closed_abstain")
        self.assertEqual(gets, [])

    def test_multirow_envelope_failure_categories_are_sanitized(self):
        base = ws()
        for frame, status in (
            ({**base, "topic": "kline.60.ETHUSDT"}, "ws_envelope_topic_abstain"),
            ({**base, "type": "delta"}, "ws_envelope_metadata_abstain"),
            ({**base, "ts": "invalid"}, "ws_envelope_metadata_abstain"),
            ({**base, "data": []}, "ws_envelope_rows_abstain"),
            ({**base, "data": [base["data"][0]] * 9}, "ws_envelope_rows_abstain"),
            ({**base, "data": [None]}, "ws_envelope_row_type_abstain"),
            ({**base, "other": "secret"}, "ws_envelope_keys_abstain"),
        ):
            with self.subTest(status=status):
                result, gets, _ = self.exercise(frames=[frame])
                self.assertEqual(result.status, status)
                self.assertEqual(result.rest_gets, 0)
                self.assertEqual(gets, [])
                report = json.dumps(result.sanitized_report())
                self.assertNotIn("secret", report)
                self.assertNotIn("ETHUSDT", report)

    def test_invalid_ws_is_rejected_without_get(self):
        modifications = (
            ("confirm", 1), ("timestamp", END), ("timestamp", END + 9000),
            ("high", "-1"), ("high", "0.98"), ("interval", "15"),
        )
        for field, value in modifications:
            with self.subTest(field=field, value=value):
                frame = ws()
                frame["data"][0][field] = value
                result, gets, _ = self.exercise(frames=[frame])
                self.assertEqual(gets, [])
                self.assertNotEqual(result.status, "ws_rest_match_unverified")

    def test_receipt_before_one_second_is_not_fabricated(self):
        # WS receipt 500ms after close; wait 500ms for REST. The auditor
        # still receives the original 500ms timestamp, not the wait time.
        early = END + 501
        frame = ws()
        frame["ts"] = END + 200
        frame["data"][0]["timestamp"] = END + 150
        result, gets, sleeps = self.exercise(
            frames=[frame], wait=[early, early, END + 1001])
        self.assertEqual(result.status, "ws_rest_match_unverified")
        self.assertEqual(gets, [(START, END)])
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 0.5, places=3)

    def test_no_get_if_window_missed_or_clock_skewed(self):
        result, gets, _ = self.exercise(current=END + 120_010)
        self.assertEqual(gets, [])
        self.assertNotEqual(result.status, "ws_rest_match_unverified")
        frame = ws()
        result, gets, _ = self.exercise(frames=[frame], wait=[AT, END, END])
        self.assertEqual(result.status, "rest_clock_abstain")
        self.assertEqual(gets, [])

    def test_malformed_rest_page_is_not_silently_fixed(self):
        for page in (
            {"retCode": 0, "result": {"category": "linear", "symbol": "BTCUSDT",
                                     "list": []}},
            {"retCode": 0, "result": {"category": "linear", "symbol": "ETHUSDT",
                                     "list": rest()["result"]["list"]}},
            {"retCode": 0, "result": {"category": "linear", "symbol": "BTCUSDT",
                                     "list": [[str(START-HOUR_MS)] + rest()["result"]["list"][0][1:]]}},
        ):
            with self.subTest(page=str(page)[:65]):
                result, gets, _ = self.exercise(reference=page)
                self.assertEqual(result.status, "validation_abstain")
                self.assertEqual(len(gets), 1)

    def test_owner_gates_prevent_network_creation(self):
        for args in ({}, {"allow_public_network": True,
                          "allow_public_websocket": True,
                          "confirm_region_and_personal_research": True}):
            with self.subTest(args=args), patch(
                "crypto_intelligence_agent.j1_ws_rest_one_candle_probe.public_rest_once",
                side_effect=AssertionError("REST must not run")
            ):
                result = owner_compare_one_candle(**args)
                self.assertEqual(result.status, "owner_opt_in_required")
                self.assertEqual(result.rest_gets, 0)

    def test_rest_input_hour_bounds_and_get_is_not_called(self):
        for start, end in ((START + 1, END + 1), (0, HOUR_MS-1),
                           (START, END + 1), (True, END)):
            with self.subTest(start=start, end=end), self.assertRaises(DataValidationError):
                public_rest_once(start, end)


if __name__ == "__main__":
    unittest.main()
