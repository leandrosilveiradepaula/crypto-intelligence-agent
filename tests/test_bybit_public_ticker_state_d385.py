"""J2 #677 / D385: synthetic Bybit ticker snapshots, deltas and fail-closed state.

Offline-only. No socket, HTTP, account key, J1 database, positions or orders.
"""
from __future__ import annotations

from decimal import Decimal
import json
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import (
    BybitPublicTickerBook, MAX_MONITORED,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

NOW = 1_800_000_000_000


def ticker(symbol="BTCUSDT", *, kind="snapshot", cs=10, ts=NOW - 100, **fields):
    body = {
        "symbol": symbol,
        "lastPrice": "100.10",
        "markPrice": "100.00",
        "indexPrice": "99.98",
        "bid1Price": "100.00",
        "ask1Price": "100.20",
        "bid1Size": "1.5",
        "ask1Size": "2.0",
        "turnover24h": "125000000.01000001",
        "volume24h": "125000.1234",
        "fundingRate": "-0.0000125",
    }
    if kind == "delta":
        body = {"symbol": symbol}
    body.update(fields)
    return json.dumps({
        "topic": "tickers." + symbol,
        "type": kind, "ts": ts, "cs": cs, "data": body,
    }, separators=(",", ":"), sort_keys=True)


def book():
    b = BybitPublicTickerBook(
        ranked_symbols=("BTCUSDT", "ETHUSDT"),
        universe_at_ms=NOW - 10_000,
    )
    b.begin_acknowledged_session()
    return b


class BybitTickerStateD385Tests(unittest.TestCase):
    def test_snapshot_delta_retains_omitted_fields_at_exact_decimal_precision(self):
        b = book()
        q = b.ingest(ticker(), received_at_ms=NOW)
        self.assertEqual(q.last_price, Decimal("100.10"))
        self.assertEqual(q.mark_price, Decimal("100.00"))
        self.assertEqual(q.turnover_24h, Decimal("125000000.01000001"))
        self.assertEqual(q.funding_rate, Decimal("-0.0000125"))
        self.assertTrue(q.has_positive_book_depth)
        self.assertEqual(q.source, "bybit_v5_public_linear_ticker_unverified")
        delta = ticker(kind="delta", cs=11, ts=NOW + 100, lastPrice="100.15")
        q2 = b.ingest(delta, received_at_ms=NOW + 110)
        self.assertEqual(q2.last_price, Decimal("100.15"))
        self.assertEqual(q2.mark_price, q.mark_price)
        self.assertEqual(q2.bid_price, q.bid_price)
        self.assertEqual(q2.ask_price, q.ask_price)
        self.assertEqual(q2.funding_rate, q.funding_rate)
        self.assertIsNotNone(b.current("BTCUSDT", at_ms=NOW + 110))
        report = b.sanitized_report(at_ms=NOW + 110)
        self.assertEqual(report["fresh_quotes"], 1)
        self.assertEqual(report["snapshots"], 1)
        self.assertEqual(report["deltas"], 1)
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["order_submission_enabled"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertNotIn("BTCUSDT", json.dumps(report))
        self.assertNotIn("100.15", json.dumps(report))


    def test_exchange_clock_expires_quote_before_recent_receipt_clock(self):
        # Real D418 probe reported 49 book-fresh versus 45 exchange-fresh:
        # a 2.5s-old exchange event received just now is invalid after
        # another 0.501s, even though its TCP receipt is very recent.
        b = book()
        q = b.ingest(ticker(ts=NOW - 2500), received_at_ms=NOW)
        self.assertIsNotNone(q)
        self.assertIsNotNone(b.current("BTCUSDT", at_ms=NOW + 500))
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW + 501))
        state = b.sanitized_report(at_ms=NOW + 501)
        self.assertEqual(state["fresh_quotes"], 0)
        self.assertEqual(state["unavailable_quotes"], 2)
        self.assertFalse(state["orders_sent"])

    def test_future_exchange_timestamp_never_masquerades_as_current_quote(self):
        # A publisher timestamp within the allowed skew is parseable but
        # should not be usable as a fresh price before its event time.
        b = book()
        quote = b.ingest(ticker(ts=NOW + 500), received_at_ms=NOW)
        self.assertEqual(quote.exchange_at_ms, NOW + 500)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW))
        self.assertEqual(b.sanitized_report(at_ms=NOW)["fresh_quotes"], 0)
        self.assertIsNotNone(b.current("BTCUSDT", at_ms=NOW + 500))
        self.assertFalse(b.sanitized_report(at_ms=NOW + 500)["orders_sent"])

    def test_duplicate_exact_sequence_does_not_refresh_market_time(self):
        b = book()
        raw = ticker()
        first = b.ingest(raw, received_at_ms=NOW)
        duplicate = b.ingest(raw, received_at_ms=NOW + 600)
        self.assertIs(duplicate, first)
        self.assertEqual(duplicate.received_at_ms, NOW)
        self.assertEqual(b.sanitized_report(at_ms=NOW + 601)["duplicates"], 1)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW + 3100))

    def test_same_cross_sequence_with_newer_exchange_time_is_distinct_delta(self):
        # Bybit calls cs a cross sequence, not a per-message unique ID.
        # Funding/index/mark/BBO may advance without a new trade sequence.
        b = book()
        initial = b.ingest(ticker(cs=10, ts=NOW-100), received_at_ms=NOW)
        advanced = b.ingest(
            ticker(kind="delta", cs=10, ts=NOW+80,
                   markPrice="100.02", bid1Size="1.7"),
            received_at_ms=NOW+90,
        )
        self.assertEqual(advanced.cross_sequence, 10)
        self.assertEqual(advanced.exchange_at_ms, NOW+80)
        self.assertEqual(advanced.mark_price, Decimal("100.02"))
        self.assertEqual(advanced.last_price, initial.last_price)
        self.assertEqual(advanced.bid_size, Decimal("1.7"))
        newer = b.ingest(
            ticker(kind="delta", cs=10, ts=NOW+120,
                   lastPrice="100.16"),
            received_at_ms=NOW+130,
        )
        self.assertEqual(newer.last_price, Decimal("100.16"))
        self.assertEqual(newer.mark_price, Decimal("100.02"))
        self.assertEqual(newer.cross_sequence, 10)
        self.assertIsNotNone(b.current("BTCUSDT", at_ms=NOW+130))
        report = b.sanitized_report(at_ms=NOW+130)
        self.assertEqual(report["snapshots"], 1)
        self.assertEqual(report["deltas"], 2)
        self.assertEqual(report["duplicates"], 0)
        self.assertTrue(report["connected"])
        self.assertFalse(report["orders_sent"])

    def test_exact_replay_same_cs_and_newer_timestamp_does_not_renew_quote(self):
        b = book()
        b.ingest(ticker(cs=10), received_at_ms=NOW)
        update = ticker(kind="delta", cs=10, ts=NOW+100, lastPrice="100.19")
        accepted = b.ingest(update, received_at_ms=NOW+110)
        duplicate = b.ingest(update, received_at_ms=NOW+150)
        self.assertIs(duplicate, accepted)
        self.assertEqual(duplicate.received_at_ms, NOW+110)
        self.assertEqual(b.sanitized_report(at_ms=NOW+150)["duplicates"], 1)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW+3200))

    def test_same_cs_same_exchange_time_different_payload_still_abstains(self):
        b = book()
        b.ingest(ticker(cs=10), received_at_ms=NOW)
        b.ingest(ticker(kind="delta", cs=10, ts=NOW+20,
                        lastPrice="100.14"), received_at_ms=NOW+30)
        with self.assertRaisesRegex(DataGapError,
                                   "ticker_same_sequence_conflicting_payload"):
            b.ingest(
                ticker(kind="delta", cs=10, ts=NOW+20,
                       markPrice="100.03"),
                received_at_ms=NOW+40,
            )
        self.assertFalse(b.sanitized_report(at_ms=NOW+40)["connected"])
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW+40))

    def test_lower_cs_even_with_higher_exchange_time_stays_rejected(self):
        b = book()
        b.ingest(ticker(cs=12), received_at_ms=NOW)
        with self.assertRaisesRegex(DataGapError,
                                   "ticker_retrograde_sequence_or_time"):
            b.ingest(ticker(kind="delta", cs=11, ts=NOW+30,
                            lastPrice="100.15"), received_at_ms=NOW+60)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW+60))

    def test_reordered_or_conflicting_sequence_fails_and_erases_state(self):
        for change in [
            ticker(kind="delta", cs=9, ts=NOW + 40, lastPrice="100.11"),
            ticker(kind="delta", cs=10, ts=NOW - 100, lastPrice="100.11"),
            ticker(kind="delta", cs=11, ts=NOW - 200, lastPrice="100.11"),
        ]:
            with self.subTest(delta=change[:60]):
                b = book()
                b.ingest(ticker(), received_at_ms=NOW)
                with self.assertRaises(DataGapError):
                    b.ingest(change, received_at_ms=NOW + 200)
                self.assertIsNone(b.current("BTCUSDT", at_ms=NOW + 200))
                self.assertFalse(b.sanitized_report(at_ms=NOW + 200)["connected"])

    def test_delta_before_snapshot_and_after_reconnection_must_abstain(self):
        b = book()
        with self.assertRaises(DataGapError):
            b.ingest(ticker(kind="delta", cs=11), received_at_ms=NOW)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW))
        b.begin_acknowledged_session()
        b.ingest(ticker(), received_at_ms=NOW)
        b.mark_disconnected()
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW))
        b.begin_acknowledged_session()
        with self.assertRaises(DataGapError):
            b.ingest(ticker(kind="delta", cs=12), received_at_ms=NOW + 300)
        self.assertEqual(b.sanitized_report(at_ms=NOW + 300)["fresh_quotes"], 0)

    def test_absent_quote_and_zero_book_depth_are_not_executable(self):
        b = book()
        b.ingest(ticker(bid1Size="0"), received_at_ms=NOW)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW + 100))
        self.assertIsNone(b.current("ETHUSDT", at_ms=NOW + 100))
        q = b.ingest(ticker(kind="delta", cs=11, bid1Size="1"),
                     received_at_ms=NOW + 200)
        self.assertTrue(q.has_positive_book_depth)
        self.assertIsNotNone(b.current("BTCUSDT", at_ms=NOW + 200))
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW + 3500))

    def test_bad_prices_crossed_book_and_floats_fail_closed(self):
        for change in [
            {"lastPrice": "NaN"}, {"markPrice": "-1"},
            {"ask1Price": "99.00"}, {"bid1Price": "1e5"},
            {"lastPrice": 100.01}, {"bid1Size": "-2"},
        ]:
            with self.subTest(fields=change):
                b = book()
                with self.assertRaises((DataValidationError, DataGapError)):
                    b.ingest(ticker(**change), received_at_ms=NOW)
                self.assertFalse(b.sanitized_report(at_ms=NOW)["connected"])

    def test_invalid_time_topic_and_json_duplicate_keys_fail_closed(self):
        bad = [
            ticker(ts=NOW + 6000),
            ticker(ts=NOW - 31000),
            ticker(cs=True),
            ticker(symbol="ABCUSDT"),
            ticker(ts=NOW - 100, cs=10).replace('"markPrice":"100.00"',
                                                  '"markPrice":"100.00","markPrice":"101"'),
        ]
        for raw in bad:
            with self.subTest(raw=raw[:60]):
                b = book()
                with self.assertRaises((DataValidationError, DataGapError)):
                    b.ingest(raw, received_at_ms=NOW)
                self.assertEqual(b.sanitized_report(at_ms=NOW)["fresh_quotes"], 0)

    def test_membership_includes_open_positions_beyond_top50(self):
        fifty = tuple(f"ASSET{i}USDT" for i in range(50))
        b = BybitPublicTickerBook(
            ranked_symbols=fifty, position_symbols=("BTCUSDT", "ETHUSDT"),
            universe_at_ms=NOW - 10_000,
        )
        self.assertEqual(len(b.topics), 52)
        self.assertEqual(len(b.topic_batches()), 2)
        self.assertIn("tickers.BTCUSDT", b.topics)
        b.begin_acknowledged_session()
        b.ingest(ticker(), received_at_ms=NOW)
        added, removed = b.rotate_membership(
            ranked_symbols=fifty[1:] + ("NEWAUSDT",),
            position_symbols=("BTCUSDT", "ETHUSDT"),
            universe_at_ms=NOW + 100,
        )
        self.assertIn("tickers.NEWAUSDT", added)
        self.assertIn("tickers.ASSET0USDT", removed)
        self.assertIsNotNone(b.current("BTCUSDT", at_ms=NOW + 100))
        self.assertIn("tickers.BTCUSDT", b.topics)
        self.assertEqual(b.sanitized_report(at_ms=NOW + 100)["position_contracts"], 2)

    def test_forged_or_duplicate_universe_cannot_enter_state(self):
        with self.assertRaises(DataValidationError):
            BybitPublicTickerBook(ranked_symbols=("BTCUSDT", "BTCUSDT"),
                                  universe_at_ms=NOW)
        with self.assertRaises(DataValidationError):
            BybitPublicTickerBook(ranked_symbols=("ABCUSD",),
                                  universe_at_ms=NOW)
        with self.assertRaises(DataValidationError):
            BybitPublicTickerBook(ranked_symbols=tuple(f"A{i}USDT" for i in range(51)),
                                  universe_at_ms=NOW)
        b = book()
        with self.assertRaises(DataGapError):
            b.rotate_membership(
                ranked_symbols=("BTCUSDT",), position_symbols=(),
                universe_at_ms=NOW - 10_000)
        self.assertIn("tickers.ETHUSDT", b.topics)

    def test_added_dynamic_ticker_needs_its_own_ack_and_new_snapshot(self):
        b = book()
        added, removed = b.rotate_membership(
            ranked_symbols=("BTCUSDT", "SOLUSDT"),
            position_symbols=(), universe_at_ms=NOW + 100,
        )
        self.assertEqual(added, ("tickers.SOLUSDT",))
        self.assertEqual(removed, ("tickers.ETHUSDT",))
        self.assertEqual(b.sanitized_report(at_ms=NOW + 100)["pending_subscription_acks"], 1)
        with self.assertRaises(DataValidationError):
            b.acknowledge_added_topics(("tickers.BTCUSDT",))
        b.acknowledge_added_topics(added)
        q = b.ingest(ticker("SOLUSDT", ts=NOW + 110, cs=8),
                     received_at_ms=NOW + 120)
        self.assertEqual(q.symbol, "SOLUSDT")
        self.assertIsNotNone(b.current("SOLUSDT", at_ms=NOW + 120))
        self.assertEqual(b.sanitized_report(at_ms=NOW + 120)["pending_subscription_acks"], 0)

        fail = book()
        fail.rotate_membership(
            ranked_symbols=("BTCUSDT", "SOLUSDT"),
            position_symbols=(), universe_at_ms=NOW + 100,
        )
        with self.assertRaises(DataGapError):
            fail.ingest(ticker("SOLUSDT", ts=NOW + 110, cs=9),
                        received_at_ms=NOW + 120)
        self.assertFalse(fail.sanitized_report(at_ms=NOW + 120)["connected"])

    def test_future_universe_is_not_causally_available(self):
        b = book()
        b.ingest(ticker(), received_at_ms=NOW)
        b.rotate_membership(
            ranked_symbols=("BTCUSDT", "ETHUSDT"),
            position_symbols=(), universe_at_ms=NOW + 1000,
        )
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW + 300))
        with self.assertRaises(DataGapError):
            b.ingest(ticker(kind="delta", cs=11, ts=NOW + 100),
                     received_at_ms=NOW + 300)
        self.assertFalse(b.sanitized_report(at_ms=NOW + 300)["connected"])

    def test_failed_frame_cannot_leave_a_partial_updated_state(self):
        b = book()
        b.ingest(ticker(), received_at_ms=NOW)
        with self.assertRaises(DataGapError):
            b.ingest(ticker(kind="delta", cs=11, ts=NOW + 100,
                            markPrice="110", bid1Price="110",
                            ask1Price="109"), received_at_ms=NOW + 150)
        self.assertIsNone(b.current("BTCUSDT", at_ms=NOW + 150))
        self.assertEqual(b.sanitized_report(at_ms=NOW + 150)["invalidations"], 1)


if __name__ == "__main__":
    unittest.main()
