"""D386: deterministic injected Bybit public WS control tests; zero network."""
from __future__ import annotations

import json
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitPublicTickerBook
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    BybitPublicTickerSupervisor, ENDPOINT, MAX_LAG_SAMPLES,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

NOW = 1_800_000_000_000


def frame(symbol="BTCUSDT", *, kind="snapshot", seq=10, ts=NOW - 50, **values):
    data = {
        "symbol": symbol,
        "lastPrice": "100.1", "markPrice": "100.0", "indexPrice": "99.9",
        "bid1Price": "100.0", "ask1Price": "100.2",
        "bid1Size": "1.5", "ask1Size": "2.5",
    }
    if kind == "delta":
        data = {"symbol": symbol}
    data.update(values)
    return json.dumps({
        "topic": "tickers." + symbol, "type": kind,
        "ts": ts, "cs": seq, "data": data,
    }, separators=(",", ":"))


def ack(*, req_id=None, ok=True):
    value = {"success": ok, "ret_msg": "", "conn_id": "synthetic",
             "op": "subscribe"}
    if req_id is not None:
        value["req_id"] = req_id
    return json.dumps(value)


def make(*, ranked=("BTCUSDT",), positions=(), **settings):
    book = BybitPublicTickerBook(
        ranked_symbols=ranked, position_symbols=positions,
        universe_at_ms=NOW - 1000)
    return BybitPublicTickerSupervisor(book=book, **settings)


def ready(sup, now=NOW):
    commands = sup.start_attempt(at_ms=now)
    for index, _ in commands:
        sup.receive(index, ack(), received_at_ms=now + index + 1)
    return commands


class D386PublicTickerSupervisorTests(unittest.TestCase):
    def test_no_transport_capability_and_one_bounded_subscribe_per_socket(self):
        sup = make()
        commands = ready(sup)
        self.assertEqual(ENDPOINT, "wss://stream.bybit.com/v5/public/linear")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], 0)
        self.assertEqual(json.loads(commands[0][1]),
                         {"op": "subscribe", "args": ["tickers.BTCUSDT"]})
        quote = sup.receive(0, frame(), received_at_ms=NOW + 100)
        self.assertEqual(str(quote.mark_price), "100.0")
        self.assertEqual(sup.phase, "ready")
        self.assertIsNotNone(sup.book.current("BTCUSDT", at_ms=NOW + 101))
        self.assertFalse(sup.sanitized_report(at_ms=NOW + 101)["orders_sent"])

    def test_52_topics_are_sharded_one_subscribe_per_distinct_socket(self):
        fifty = tuple("ASSET" + str(i) + "USDT" for i in range(50))
        sup = make(ranked=fifty, positions=("BTCUSDT", "ETHUSDT"))
        commands = sup.start_attempt(at_ms=NOW)
        self.assertEqual(len(commands), 2)
        self.assertEqual([len(json.loads(p)["args"]) for _, p in commands], [50, 2])
        self.assertEqual(sup.phase, "awaiting_ack")
        sup.receive(0, ack(), received_at_ms=NOW + 1)
        # A frame after ACK on shard 0 must not escape into strategy before 1 ACKs.
        self.assertIsNone(sup.receive(0, frame("ASSET0USDT"),
                                      received_at_ms=NOW + 2))
        self.assertEqual(sup.sanitized_report(at_ms=NOW + 2)["pending_buffered"], 1)
        self.assertIsNone(sup.book.current("ASSET0USDT", at_ms=NOW + 2))
        sup.receive(1, ack(), received_at_ms=NOW + 3)
        self.assertEqual(sup.phase, "ready")
        self.assertIsNotNone(sup.book.current("ASSET0USDT", at_ms=NOW + 3))
        self.assertEqual(sup.sanitized_report(at_ms=NOW + 3)["pending_buffered"], 0)

    def test_pre_ack_market_is_discarded_and_never_promoted(self):
        sup = make()
        sup.start_attempt(at_ms=NOW)
        sup.receive(0, frame(), received_at_ms=NOW + 1)
        sup.receive(0, ack(), received_at_ms=NOW + 2)
        self.assertEqual(sup.sanitized_report(at_ms=NOW + 2)["preack_dropped"], 1)
        self.assertIsNone(sup.book.current("BTCUSDT", at_ms=NOW + 2))
        with self.assertRaises(DataGapError):
            sup.receive(0, frame(kind="delta", seq=11, ts=NOW + 3, lastPrice="102"),
                        received_at_ms=NOW + 4)
        self.assertEqual(sup.phase, "backoff")

    def test_preack_limit_fails_closed(self):
        sup = make(max_preack_frames=1)
        sup.start_attempt(at_ms=NOW)
        sup.receive(0, frame(), received_at_ms=NOW + 1)
        with self.assertRaises(DataGapError):
            sup.receive(0, frame(), received_at_ms=NOW + 2)
        self.assertEqual(sup.phase, "backoff")

    def test_invalid_or_duplicate_ack_aborts_whole_cohort(self):
        for bad in [ack(ok=False), ack(req_id="unexpected"),
                    json.dumps({"op": "subscribe", "success": True})]:
            with self.subTest(bad=bad):
                sup = make()
                sup.start_attempt(at_ms=NOW)
                with self.assertRaises(DataGapError):
                    sup.receive(0, bad, received_at_ms=NOW + 1)
                self.assertEqual(sup.phase, "backoff")
        sup = make()
        ready(sup)
        with self.assertRaises(DataGapError):
            sup.receive(0, ack(), received_at_ms=NOW + 10)
        self.assertEqual(sup.phase, "backoff")

    def test_topic_from_wrong_socket_is_rejected(self):
        fifty = tuple("ASSET" + str(i) + "USDT" for i in range(50))
        sup = make(ranked=fifty, positions=("BTCUSDT", "ETHUSDT"))
        ready(sup)
        with self.assertRaises(DataGapError):
            sup.receive(0, frame("BTCUSDT"), received_at_ms=NOW + 100)
        self.assertEqual(sup.phase, "backoff")

    def test_ping_pong_and_timeout_without_network_or_trade_actions(self):
        sup = make(ping_every_ms=1000, pong_timeout_ms=1200,
                   idle_timeout_ms=10_000)
        ready(sup)
        self.assertEqual(sup.poll(at_ms=NOW + 1000),
                         ((0, '{"op":"ping"}'),))
        sup.receive(0, json.dumps({"op": "ping", "ret_msg": "pong"}),
                    received_at_ms=NOW + 1010)
        self.assertEqual(sup.poll(at_ms=NOW + 2010),
                         ((0, '{"op":"ping"}'),))
        self.assertEqual(sup.poll(at_ms=NOW + 3211), ())
        self.assertEqual(sup.phase, "backoff")
        report = sup.sanitized_report(at_ms=NOW + 3211)
        self.assertEqual(report["heartbeat_pings"], 2)
        self.assertEqual(report["heartbeat_pongs"], 1)

    def test_unsolicited_pong_is_invalid(self):
        sup = make()
        ready(sup)
        with self.assertRaises(DataGapError):
            sup.receive(0, '{"op":"ping","ret_msg":"pong"}',
                        received_at_ms=NOW + 20)
        self.assertEqual(sup.phase, "backoff")

    def test_ack_timeout_and_bounded_backoff(self):
        sup = make(max_attempts=2, ack_timeout_ms=200, retry_base_ms=500)
        sup.start_attempt(at_ms=NOW)
        sup.poll(at_ms=NOW + 201)
        self.assertEqual(sup.phase, "backoff")
        with self.assertRaises(DataGapError):
            sup.start_attempt(at_ms=NOW + 700)
        self.assertEqual(len(sup.start_attempt(at_ms=NOW + 701)), 1)
        sup.poll(at_ms=NOW + 902)
        self.assertEqual(sup.phase, "exhausted")
        with self.assertRaises(DataGapError):
            sup.start_attempt(at_ms=NOW + 999999)

    def test_backpressure_fails_closed_and_requires_new_snapshot(self):
        sup = make(max_backlog=2, retry_base_ms=100)
        ready(sup)
        sup.receive(0, frame(), received_at_ms=NOW + 100)
        self.assertEqual(sup.poll(at_ms=NOW + 200, queued_frames=3), ())
        self.assertEqual(sup.phase, "backoff")
        self.assertIsNone(sup.book.current("BTCUSDT", at_ms=NOW + 200))
        self.assertEqual(sup.sanitized_report(at_ms=NOW + 200)["max_backlog_seen"], 3)
        sup.start_attempt(at_ms=NOW + 300)
        sup.receive(0, ack(), received_at_ms=NOW + 301)
        self.assertIsNone(sup.book.current("BTCUSDT", at_ms=NOW + 301))
        sup.receive(0, frame(seq=1, ts=NOW + 302), received_at_ms=NOW + 303)
        self.assertIsNotNone(sup.book.current("BTCUSDT", at_ms=NOW + 303))

    def test_rotation_is_complete_resubscribe_and_preserves_position_membership(self):
        sup = make(ranked=("BTCUSDT", "ETHUSDT"),
                   positions=("SOLUSDT",), retry_base_ms=100)
        ready(sup)
        sup.rotate(ranked_symbols=("BTCUSDT", "AVAXUSDT"),
                   position_symbols=("SOLUSDT",),
                   universe_at_ms=NOW + 200)
        self.assertEqual(sup.phase, "backoff")
        self.assertIsNone(sup.book.current("SOLUSDT", at_ms=NOW + 201))
        commands = sup.start_attempt(at_ms=NOW + 300)
        subscribed = json.loads(commands[0][1])["args"]
        self.assertIn("tickers.SOLUSDT", subscribed)
        self.assertIn("tickers.AVAXUSDT", subscribed)
        self.assertNotIn("tickers.ETHUSDT", subscribed)
        sup.receive(0, ack(), received_at_ms=NOW + 301)
        self.assertEqual(sup.phase, "ready")
        self.assertIsNone(sup.book.current("SOLUSDT", at_ms=NOW + 302))

    def test_bad_transport_json_and_future_time_deny_data(self):
        for raw in ['{"topic":"bad"', '{}', '[]',
                    frame(ts=NOW + 60_000)]:
            with self.subTest(raw=raw[:30]):
                sup = make()
                ready(sup)
                with self.assertRaises(DataGapError):
                    sup.receive(0, raw, received_at_ms=NOW + 100)
                self.assertEqual(sup.phase, "backoff")

    def test_budget_validation_clock_and_idle_stale(self):
        with self.assertRaises(DataValidationError):
            make(topics_per_socket=51)
        with self.assertRaises(DataValidationError):
            make(max_frames=True)
        sup = make(idle_timeout_ms=1000)
        ready(sup)
        sup.poll(at_ms=NOW + 1001)
        self.assertEqual(sup.phase, "backoff")
        sup = make()
        ready(sup)
        with self.assertRaises(DataGapError):
            sup.poll(at_ms=NOW - 1)
        self.assertEqual(sup.phase, "backoff")

    def test_lag_statistics_are_bounded_and_report_count_only(self):
        sup = make()
        ready(sup)
        for i in range(MAX_LAG_SAMPLES + 4):
            sup.receive(0, frame(seq=i + 1, ts=NOW + 100 + i),
                        received_at_ms=NOW + 110 + i)
        report = sup.sanitized_report(at_ms=NOW + 500)
        self.assertEqual(len(sup._lag_samples), MAX_LAG_SAMPLES)
        self.assertEqual(report["ingress_age_p95_ms"], 10)
        self.assertEqual(report["ingress_age_p99_ms"], 10)
        self.assertEqual(report["accepted_frames"], MAX_LAG_SAMPLES + 4)
        self.assertNotIn("BTCUSDT", json.dumps(report))
        self.assertNotIn("100.1", json.dumps(report))
        self.assertFalse(report["network_connector_installed"])
        self.assertFalse(report["live_trading_authorized"])

    def test_explicit_close_blocks_reentry(self):
        sup = make()
        ready(sup)
        sup.close()
        with self.assertRaises(DataGapError):
            sup.start_attempt(at_ms=NOW + 100)
        self.assertEqual(sup.sanitized_report(at_ms=NOW + 100)["fresh_quotes"], 0)


if __name__ == "__main__":
    unittest.main()
