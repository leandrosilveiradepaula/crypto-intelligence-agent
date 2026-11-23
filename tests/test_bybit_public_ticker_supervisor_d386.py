"""D386: fake sessions only, no internet, no orders, no on-host services."""
from __future__ import annotations

import json
import unittest
from decimal import Decimal

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import (
    BybitPublicTickerBook,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, supervise_public_tickers,
)

NOW = 1_800_000_000_000


def ticker(symbol="BTCUSDT", *, cs=1, ts=NOW, kind="snapshot", **overrides):
    data = {"symbol": symbol}
    if kind == "snapshot":
        data.update({
            "lastPrice": "100.0001", "markPrice": "100",
            "indexPrice": "99.9", "bid1Price": "99.99",
            "ask1Price": "100.01", "bid1Size": "2", "ask1Size": "3",
        })
    data.update(overrides)
    return json.dumps({"topic": "tickers." + symbol, "type": kind,
                       "ts": ts, "cs": cs, "data": data},
                      separators=(",", ":"))


def ack(*, req_id="cia-ticker-1", success=True):
    return json.dumps({
        "success": success, "ret_msg": "subscribe", "conn_id": "test",
        "op": "subscribe", "req_id": req_id,
    })


class FakeClock:
    def __init__(self):
        self.monotonic_time = 0.0
        self.utc_ms = NOW

    def monotonic(self):
        return self.monotonic_time

    def utc(self):
        return self.utc_ms

    def advance(self, seconds):
        self.monotonic_time += seconds
        self.utc_ms += int(seconds * 1000)


class Session:
    def __init__(self, clock, responses=(), *, pong_on_ping=False):
        self.clock = clock
        self.responses = list(responses)
        self.pong_on_ping = pong_on_ping
        self.sent = []
        self.closed = False

    def send(self, raw):
        self.sent.append(json.loads(raw))
        if self.pong_on_ping and self.sent[-1] == {"op": "ping"}:
            self.responses.append(json.dumps({"op": "pong", "args": ["12345"]}))

    def recv(self, timeout):
        if self.responses:
            next_item = self.responses.pop(0)
            if isinstance(next_item, Exception):
                raise next_item
            return next_item
        self.clock.advance(timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


def make_book(*, fifty=False):
    membership = (tuple(f"A{i}USDT" for i in range(50)) if fifty
                  else ("BTCUSDT", "ETHUSDT"))
    return BybitPublicTickerBook(
        ranked_symbols=membership,
        position_symbols=("BTCUSDT",) if fifty else (),
        universe_at_ms=NOW - 1000,
    )


def run(book, clock, sessions, *, budget=None, on_quote=None,
        on_session_reset=None):
    iterator = iter(sessions)

    def factory():
        return next(iterator)

    return supervise_public_tickers(
        session_factory=factory, book=book,
        budget=budget or TickerLeaseBudget(max_sessions=1, max_frames=100,
                                           max_seconds=10),
        clock=clock.monotonic, wall_ms=clock.utc,
        sleeper=clock.advance, on_quote=on_quote,
        on_session_reset=on_session_reset,
    )


class PublicTickerSupervisorD386Tests(unittest.TestCase):
    def test_one_subscribe_ack_and_real_ticker_callback_without_orders(self):
        clock = FakeClock()
        session = Session(clock, [ack(req_id=""), ticker()])
        received = []
        b = make_book()
        report = run(b, clock, [session], on_quote=received.append)
        self.assertEqual(report.status, "lease_completed")
        self.assertEqual(report.sessions_attempted, 1)
        self.assertEqual(report.subscriptions_sent, 1)
        self.assertEqual(report.subscriptions_acknowledged, 1)
        self.assertEqual(report.ticker_frames_accepted, 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].mark_price, Decimal("100"))
        self.assertEqual(session.sent[0]["args"], ["tickers.BTCUSDT", "tickers.ETHUSDT"])
        self.assertTrue(session.closed)
        metrics = report.sanitized_report()
        self.assertEqual(metrics["latency_0_to_100ms"], 1)
        for name in ("order_submission_enabled", "orders_sent", "approved_for_live_use"):
            self.assertFalse(metrics[name])
        self.assertNotIn("BTCUSDT", json.dumps(metrics))
        self.assertNotIn("100.0001", json.dumps(metrics))

    def test_multi_topic_single_request_up_to_fifty_plus_positions(self):
        clock = FakeClock()
        session = Session(clock, [ack(), ticker()])
        b = make_book(fifty=True)
        report = run(b, clock, [session])
        self.assertEqual(report.status, "lease_completed")
        self.assertEqual(len(session.sent[0]["args"]), 51)
        self.assertIn("tickers.BTCUSDT", session.sent[0]["args"])
        self.assertEqual(report.subscriptions_acknowledged, 1)

    def test_pre_ack_market_bootstraps_only_after_ack_no_callback_replay(self):
        clock = FakeClock()
        session = Session(clock, [ticker(), ack(), ticker(cs=2)])
        received = []
        report = run(make_book(), clock, [session], on_quote=received.append)
        self.assertEqual(report.preack_frames_discarded, 1)
        self.assertEqual(report.preack_frames_bootstrapped_after_ack, 1)
        self.assertEqual(report.ticker_frames_accepted, 1)
        self.assertEqual(received[0].cross_sequence, 2)

    def test_no_ack_cannot_produce_tradable_quote(self):
        clock = FakeClock()
        session = Session(clock, [ticker()])
        book = make_book()
        report = run(book, clock, [session])
        self.assertEqual(report.status, "lease_abstained")
        self.assertEqual(report.failure_category, "no_subscription_ack")
        self.assertEqual(report.ticker_frames_accepted, 0)
        self.assertIsNone(book.current("BTCUSDT", at_ms=clock.utc()))

    def test_wrong_or_duplicate_ack_is_fail_closed(self):
        for frames in [
            [ack(req_id="other"), ticker()],
            [ack(), ack(), ticker()],
            [ack(success=False), ticker()],
        ]:
            with self.subTest(frames=frames):
                clock = FakeClock()
                book = make_book()
                result = run(book, clock, [Session(clock, frames)])
                self.assertEqual(result.status, "lease_abstained")
                self.assertEqual(result.failure_category, "invalid_subscription_ack")
                self.assertIsNone(book.current("BTCUSDT", at_ms=clock.utc()))

    def test_n50_cross_sequence_stable_with_newer_timestamp_does_not_abort(self):
        # In a many-topic real stream the cross sequence can remain the
        # same while the ticker timestamp and partial fields advance.
        # The public supervisor must validate both and keep other topics
        # alive instead of stopping after the first such delta.
        clock = FakeClock()
        frames = [ack()]
        for symbol in make_book(fifty=True).topics:
            item = symbol.removeprefix("tickers.")
            frames.append(ticker(item, cs=100, ts=NOW-200))
        frames.extend([
            ticker("BTCUSDT", cs=100, ts=NOW-150, kind="delta",
                   markPrice="100.002"),
            ticker("BTCUSDT", cs=100, ts=NOW-100, kind="delta",
                   lastPrice="100.123"),
            ticker("A0USDT", cs=100, ts=NOW-50, kind="delta",
                   bid1Size="2.5"),
        ])
        received = []
        sock = Session(clock, frames)
        report = run(make_book(fifty=True), clock, [sock],
                     budget=TickerLeaseBudget(max_sessions=1,
                                              max_frames=300, max_seconds=5),
                     on_quote=received.append)
        self.assertEqual(report.status, "lease_completed")
        self.assertIsNone(report.failure_category)
        self.assertEqual(report.subscriptions_acknowledged, 1)
        self.assertEqual(report.ticker_frames_accepted, 54)
        self.assertEqual(len(received), 54)
        self.assertEqual(received[-3].cross_sequence, 100)
        self.assertEqual(received[-2].last_price, Decimal("100.123"))
        self.assertEqual(received[-1].bid_size, Decimal("2.5"))
        self.assertFalse(report.sanitized_report()["orders_sent"])
        self.assertTrue(sock.closed)

    def test_same_cross_sequence_same_timestamp_conflict_fails_closed(self):
        clock = FakeClock()
        sock = Session(clock, [
            ack(), ticker(cs=10, ts=NOW-100),
            ticker(cs=10, ts=NOW-100, kind="delta",
                   lastPrice="100.7"),
        ])
        received = []
        report = run(make_book(), clock, [sock], on_quote=received.append)
        self.assertEqual(report.status, "lease_abstained")
        self.assertEqual(report.failure_category, "conflicting_replay")
        self.assertEqual(report.ticker_frames_accepted, 1)
        self.assertEqual(len(received), 1)
        self.assertFalse(report.sanitized_report()["orders_sent"])
        self.assertTrue(sock.closed)


    def test_verified_sequence_gap_reconnects_and_requires_new_snapshot(self):
        # D473: a single out-of-order post-ACK delta cannot kill a whole
        # 50-member lease after 250k previously valid quotes. Drop ALL prior
        # book state, re-ACK and require a fresh snapshot before PAPER.
        clock = FakeClock()
        first = Session(clock, [
            ack(), ticker(cs=100, ts=NOW-200),
            ticker(cs=99, ts=NOW-100, kind="delta",
                   lastPrice="100.8"),
        ])
        second = Session(clock, [
            ack(), ticker(cs=1, ts=NOW+5000),
            ticker(cs=2, ts=NOW+5100, kind="delta",
                   lastPrice="101.1"),
        ])
        b = make_book()
        quotes = []
        r = run(b, clock, [first, second],
                budget=TickerLeaseBudget(max_sessions=2,
                                         max_frames=100, max_seconds=14),
                on_quote=quotes.append)
        self.assertEqual(r.status, "lease_completed")
        self.assertEqual(r.sessions_attempted, 2)
        self.assertEqual(r.subscriptions_acknowledged, 2)
        self.assertEqual(r.reconnects, 1)
        self.assertEqual(r.ticker_frames_accepted, 3)
        self.assertEqual([q.cross_sequence for q in quotes], [100, 1, 2])
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertFalse(r.sanitized_report()["orders_sent"])

    def test_resnapshot_must_abstain_without_budget_for_new_ack(self):
        clock = FakeClock()
        sock = Session(clock, [
            ack(), ticker(cs=100, ts=NOW-200),
            ticker(cs=99, ts=NOW-100, kind="delta",
                   lastPrice="100.8"),
        ])
        b = make_book()
        report = run(b, clock, [sock],
                     budget=TickerLeaseBudget(max_sessions=1,
                                              max_frames=100, max_seconds=14))
        self.assertEqual(report.status, "lease_abstained")
        self.assertEqual(report.failure_category, "sequence_regression")
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW))
        self.assertEqual(report.sessions_attempted, 1)

    def test_rejected_payload_never_retried_and_consumer_failure_separate(self):
        clock = FakeClock()
        malformed = Session(clock, [
            ack(), ticker(), ticker(cs=2, kind="delta", markPrice="-1"),
        ])
        never = Session(clock, [ack(), ticker(cs=3)])
        b = make_book()
        result = run(b, clock, [malformed, never],
                     budget=TickerLeaseBudget(max_sessions=3,
                                              max_frames=100, max_seconds=20))
        self.assertEqual(result.status, "lease_abstained")
        self.assertEqual(result.sessions_attempted, 1)
        self.assertFalse(never.closed)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW))
        self.assertFalse(result.sanitized_report()["orders_sent"])

        from crypto_intelligence_agent.market_data import DataValidationError
        clock2 = FakeClock()
        consumed = Session(clock2, [ack(), ticker()])
        retry = Session(clock2, [ack(), ticker(cs=2)])
        def failed_paper_gate(quote):
            raise DataValidationError("D449 local PAPER receipt failure")
        result2 = run(make_book(), clock2, [consumed, retry],
                      budget=TickerLeaseBudget(max_sessions=3,
                                               max_frames=100, max_seconds=20),
                      on_quote=failed_paper_gate)
        self.assertEqual(result2.status, "lease_abstained")
        self.assertEqual(result2.failure_category, "paper_cycle_callback_failed")
        self.assertEqual(result2.sessions_attempted, 1)
        self.assertFalse(retry.closed)
        self.assertFalse(result2.sanitized_report()["orders_sent"])

    def test_bad_market_payload_stops_without_reconnect(self):
        clock = FakeClock()
        b = make_book()
        s1 = Session(clock, [ack(), ticker(),
                             ticker(cs=2, kind="delta", markPrice="-1")])
        s2 = Session(clock, [ack(), ticker(cs=3)])
        received = []
        r = run(b, clock, [s1, s2],
                budget=TickerLeaseBudget(max_sessions=2, max_frames=100,
                                         max_seconds=20), on_quote=received.append)
        self.assertEqual(r.status, "lease_abstained")
        self.assertEqual(r.sessions_attempted, 1)
        self.assertEqual(r.ticker_frames_accepted, 1)
        self.assertEqual(len(received), 1)
        self.assertIsNone(b.current("BTCUSDT", at_ms=clock.utc()))
        self.assertFalse(s2.closed)

    def test_disconnect_and_reconnect_require_new_snapshot(self):
        clock = FakeClock()
        first = Session(clock, [ack(), ticker(), OSError("transient")])
        second = Session(clock, [ack(), ticker(cs=2, kind="delta")])
        b = make_book()
        r = run(b, clock, [first, second],
                budget=TickerLeaseBudget(max_sessions=2, max_frames=100,
                                         max_seconds=25))
        self.assertEqual(r.sessions_attempted, 2)
        self.assertEqual(r.reconnects, 1)
        self.assertEqual(r.failure_category, "snapshot_required")
        self.assertEqual(r.ticker_frames_accepted, 1)
        self.assertIsNone(b.current("BTCUSDT", at_ms=clock.utc()))

    def test_disconnect_reconnect_new_snapshot_resets_state(self):
        clock = FakeClock()
        s1 = Session(clock, [ack(), ticker(), OSError("disconnect")])
        s2 = Session(clock, [ack(), ticker(cs=1, ts=NOW + 5_000)])
        b = make_book()
        quotes = []
        r = run(b, clock, [s1, s2],
                budget=TickerLeaseBudget(max_sessions=2, max_frames=100,
                                         max_seconds=20), on_quote=quotes.append)
        # reconnect waits 5 seconds, so the second snapshot is current
        self.assertEqual(r.status, "lease_completed")
        self.assertEqual(r.reconnects, 1)
        self.assertEqual(r.ticker_frames_accepted, 2)
        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[1].cross_sequence, 1)

    def test_consumer_session_reset_precedes_reconnect_and_replayed_seq(self):
        clock = FakeClock()
        s1 = Session(clock, [ack(), ticker(cs=9), OSError("disconnect")])
        s2 = Session(clock, [ack(), ticker(cs=1, ts=NOW + 5000)])
        events = []
        result = run(make_book(), clock, [s1, s2],
                     budget=TickerLeaseBudget(max_sessions=2, max_frames=30,
                                              max_seconds=20),
                     on_session_reset=lambda: events.append("reset"),
                     on_quote=lambda quote: events.append(quote.cross_sequence))
        self.assertEqual(result.status, "lease_completed")
        self.assertEqual(events, ["reset", 9, "reset", 1])
        self.assertTrue(s1.closed and s2.closed)

    def test_session_reset_failure_never_opens_socket(self):
        clock = FakeClock()
        attempts = []
        def factory():
            attempts.append(1)
            raise AssertionError("socket must not be opened")
        def invalid_reset():
            raise DataGapError("cannot reset downstream")
        from crypto_intelligence_agent.market_data import DataGapError
        with self.assertRaises(DataGapError):
            supervise_public_tickers(
                session_factory=factory, book=make_book(),
                on_session_reset=invalid_reset,
            )
        self.assertEqual(attempts, [])

    def test_pings_pongs_and_missing_pong_budget(self):
        clock = FakeClock()
        s1 = Session(clock, [ack()], pong_on_ping=True)
        r = run(make_book(), clock, [s1],
                budget=TickerLeaseBudget(max_sessions=1, max_frames=100,
                                         max_seconds=55))
        self.assertEqual(r.status, "lease_completed")
        self.assertGreaterEqual(r.ping_frames, 2)
        self.assertGreaterEqual(r.pong_frames, 2)

        # Missing pong must end in bounded transport error, never endless spin
        c2 = FakeClock()
        s2 = Session(c2, [ack()])
        r2 = run(make_book(), c2, [s2],
                 budget=TickerLeaseBudget(max_sessions=1, max_frames=100,
                                          max_seconds=80))
        self.assertEqual(r2.status, "lease_abstained")
        self.assertEqual(r2.failure_category, "reconnect_budget_exhausted")
        self.assertEqual(r2.sessions_attempted, 1)
        self.assertTrue(s2.closed)

    def test_preack_overflow_abstains_with_no_quotes(self):
        clock = FakeClock()
        s = Session(clock, [ticker()] * 129 + [ack(), ticker(cs=2)])
        book = make_book()
        r = run(book, clock, [s],
                budget=TickerLeaseBudget(max_sessions=1, max_frames=200,
                                         max_seconds=20))
        self.assertEqual(r.status, "lease_abstained")
        self.assertEqual(r.preack_frames_discarded, 129)
        self.assertEqual(r.failure_category, "preack_limit_reached_before_ack")
        self.assertEqual(r.ticker_frames_accepted, 0)
        self.assertIsNone(book.current("BTCUSDT", at_ms=clock.utc()))

    def test_realistic_n50_preack_burst_over_128_then_ack_is_safe(self):
        # Real VPS 2026-11-17 showed exactly 129 market envelopes prior to
        # any accepted ACK, then abstained. With 50+held topics, pre-ACK
        # packets can exceed the legacy one-size 128 threshold. They must
        # remain DISCARDED, not replayed into PAPER on late ACK.
        clock = FakeClock()
        session = Session(clock, [ticker()] * 129 + [ack(), ticker(cs=2)])
        accepted = []
        b = make_book(fifty=True)
        report = run(
            b, clock, [session],
            budget=TickerLeaseBudget(max_sessions=1, max_frames=300,
                                     max_seconds=10),
            on_quote=accepted.append,
        )
        self.assertEqual(len(session.sent[0]["args"]), 51)
        self.assertTrue(session.closed)
        self.assertEqual(report.status, "lease_completed")
        self.assertEqual(report.preack_frames_discarded, 129)
        self.assertEqual(report.subscriptions_acknowledged, 1)
        self.assertEqual(report.ticker_frames_accepted, 1)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].cross_sequence, 2)
        self.assertFalse(report.sanitized_report()["orders_sent"])

    def test_large_preack_without_ack_never_approves_quotes(self):
        clock = FakeClock()
        session = Session(clock, [ticker()] * 129)
        b = make_book(fifty=True)
        quotes = []
        report = run(
            b, clock, [session],
            budget=TickerLeaseBudget(max_sessions=1, max_frames=300,
                                     max_seconds=10),
            on_quote=quotes.append,
        )
        self.assertEqual(report.status, "lease_abstained")
        self.assertEqual(report.failure_category, "no_subscription_ack")
        self.assertEqual(report.preack_frames_discarded, 129)
        self.assertEqual(report.subscriptions_acknowledged, 0)
        self.assertEqual(report.ticker_frames_accepted, 0)
        self.assertEqual(quotes, [])
        self.assertFalse(report.sanitized_report()["orders_sent"])

    def test_real_btc_pattern_preack_snapshot_then_ack_then_delta(self):
        # VPS D413: 7 pre-ACK, 1 ACK, then delta without a new snapshot.
        # Snapshot/deltas are quarantined, validated only on ACK and never
        # forwarded to a consumer. Post-ACK delta can then use that state.
        clock = FakeClock()
        pre = [ticker(cs=1)] + [
            ticker(cs=i+2, kind="delta", lastPrice=f"100.{i+2:03d}")
            for i in range(6)
        ]
        sock = Session(clock, pre + [
            ack(), ticker(cs=8, kind="delta", lastPrice="101.12345"),
        ])
        seen = []
        report = run(make_book(), clock, [sock],
                     budget=TickerLeaseBudget(max_sessions=1,
                                              max_frames=100,
                                              max_seconds=10),
                     on_quote=seen.append)
        self.assertEqual(report.status, "lease_completed")
        self.assertEqual(report.frames_seen, 9)
        self.assertEqual(report.preack_frames_discarded, 7)
        self.assertEqual(report.preack_frames_bootstrapped_after_ack, 7)
        self.assertEqual(report.subscriptions_acknowledged, 1)
        self.assertEqual(report.ticker_frames_accepted, 1)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].last_price, Decimal("101.12345"))
        self.assertEqual(seen[0].mark_price, Decimal("100"))
        self.assertTrue(sock.closed)
        self.assertFalse(report.sanitized_report()["orders_sent"])

    def test_real_n50_pattern_263_preack_then_ack_then_delta(self):
        clock = FakeClock()
        names = tuple(f"A{i}USDT" for i in range(50))
        # 50 snapshots and BTC snapshot, then 212 BTC deltas before ACK.
        first = [ticker(symbol, cs=1) for symbol in names] + [
            ticker("BTCUSDT", cs=1),
        ]
        updates = [
            ticker("BTCUSDT", kind="delta", cs=i+2,
                   lastPrice=f"101.{i:03d}") for i in range(212)
        ]
        self.assertEqual(len(first + updates), 263)
        sock = Session(clock, first + updates + [
            ack(), ticker("BTCUSDT", kind="delta", cs=214,
                          lastPrice="102.456"),
        ])
        received = []
        result = run(make_book(fifty=True), clock, [sock],
                     budget=TickerLeaseBudget(max_sessions=1,
                                              max_frames=500,
                                              max_seconds=10),
                     on_quote=received.append)
        self.assertEqual(result.status, "lease_completed")
        self.assertEqual(result.frames_seen, 265)
        self.assertEqual(result.preack_frames_discarded, 263)
        self.assertEqual(result.preack_frames_bootstrapped_after_ack, 263)
        self.assertEqual(result.subscriptions_acknowledged, 1)
        self.assertEqual(result.ticker_frames_accepted, 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].last_price, Decimal("102.456"))
        self.assertFalse(result.sanitized_report()["orders_sent"])

    def test_invalid_preack_delta_remains_fail_closed_even_after_ack(self):
        clock = FakeClock()
        sock = Session(clock, [
            ticker(kind="delta", cs=1, lastPrice="101"),
            ack(), ticker(cs=2),
        ])
        accepted = []
        result = run(make_book(), clock, [sock], on_quote=accepted.append)
        self.assertEqual(result.status, "lease_abstained")
        self.assertEqual(result.failure_category, "snapshot_required")
        self.assertEqual(result.preack_frames_bootstrapped_after_ack, 0)
        self.assertEqual(result.ticker_frames_accepted, 0)
        self.assertEqual(result.subscriptions_acknowledged, 1)
        self.assertEqual(accepted, [])
        self.assertTrue(sock.closed)

    def test_preack_bootstrap_cannot_cross_reconnection_without_ack(self):
        clock = FakeClock()
        first = Session(clock, [ticker(), OSError("drop_before_ack")])
        second = Session(clock, [
            ack(), ticker(kind="delta", ts=NOW + 5_000, cs=2),
        ])
        seen = []
        result = run(make_book(), clock, [first, second],
                     budget=TickerLeaseBudget(max_sessions=2,
                                              max_frames=30, max_seconds=15),
                     on_quote=seen.append)
        self.assertEqual(result.status, "lease_abstained")
        self.assertEqual(result.failure_category, "snapshot_required")
        self.assertEqual(result.sessions_attempted, 2)
        self.assertEqual(result.preack_frames_discarded, 1)
        self.assertEqual(result.preack_frames_bootstrapped_after_ack, 0)
        self.assertEqual(result.ticker_frames_accepted, 0)
        self.assertEqual(seen, [])
        self.assertTrue(first.closed and second.closed)

    def test_preack_memory_budget_abstains_before_ack_and_no_callback(self):
        from unittest.mock import patch
        clock = FakeClock()
        packet = ticker()
        sock = Session(clock, [packet, packet, ack(), ticker(cs=2)])
        received = []
        # Simulate memory ceiling without constructing an 8 MiB fixture.
        with patch(
            "crypto_intelligence_agent.bybit_public_ticker_supervisor_d386."
            "MAX_PREACK_BOOTSTRAP_BYTES", len(packet.encode("utf-8")) + 1,
        ):
            result = run(make_book(), clock, [sock], on_quote=received.append)
        self.assertEqual(result.status, "lease_abstained")
        self.assertEqual(result.failure_category, "preack_bootstrap_memory_limit")
        self.assertEqual(result.subscriptions_acknowledged, 0)
        self.assertEqual(result.preack_frames_bootstrapped_after_ack, 0)
        self.assertEqual(result.ticker_frames_accepted, 0)
        self.assertEqual(received, [])
        self.assertTrue(sock.closed)

    def test_wrong_ack_with_staged_snapshot_never_rehydrates(self):
        clock = FakeClock()
        sock = Session(clock, [
            ticker(cs=1), ack(req_id="not-our-lease"),
            ticker(cs=2,kind="delta", lastPrice="101"),
        ])
        received = []
        report = run(make_book(), clock, [sock], on_quote=received.append)
        self.assertEqual(report.status, "lease_abstained")
        self.assertEqual(report.failure_category, "invalid_subscription_ack")
        self.assertEqual(report.preack_frames_bootstrapped_after_ack, 0)
        self.assertEqual(report.ticker_frames_accepted, 0)
        self.assertEqual(received, [])

    def test_transport_never_opened_when_budget_invalid(self):
        b = make_book()
        with self.assertRaises(Exception):
            TickerLeaseBudget(max_sessions=0)
        with self.assertRaises(Exception):
            TickerLeaseBudget(max_frames=5_000_001)
        with self.assertRaises(Exception):
            supervise_public_tickers(session_factory=None, book=b)

    def test_frame_budget_abstention_and_no_pending_queue(self):
        c = FakeClock()
        b = make_book()
        s = Session(c, [ack(), ticker(), ticker(cs=2, kind="delta", lastPrice="100.11")])
        r = run(b, c, [s], budget=TickerLeaseBudget(max_sessions=1,
                                                     max_frames=2, max_seconds=20))
        self.assertEqual(r.status, "lease_abstained")
        self.assertEqual(r.failure_category, "frame_budget_exceeded")
        self.assertFalse(r.sanitized_report()["orders_sent"])
        self.assertTrue(r.sanitized_report()["no_unbounded_queue"])


if __name__ == "__main__":
    unittest.main()
