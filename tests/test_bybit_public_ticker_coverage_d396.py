"""D396: N50+held coverage across finite Bybit public WS sessions, offline."""
from __future__ import annotations

from dataclasses import replace
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_coverage_d396 import (
    TickerUniverseEpoch, run_finite_public_ticker_coverage_pilot,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

T = 1_800_000_000_000
FIRST = tuple(f"A{i:02d}USDT" for i in range(50))
SECOND = tuple(f"A{i:02d}USDT" for i in range(1, 51))
HELD = ("A00USDT", "HOLDUSDT")


class Clock:
    def __init__(self):
        self.mono_seconds = 0.0
        self.utc_ms = T

    def mono(self):
        return self.mono_seconds

    def wall(self):
        return self.utc_ms

    def sleep(self, seconds):
        self.mono_seconds += seconds
        self.utc_ms += round(seconds * 1000)


class FakeSession:
    def __init__(self, clock, events):
        self.clock, self.events = clock, list(events)
        self.sent = []
        self.closed = False

    def send(self, raw):
        payload = json.loads(raw)
        if payload.get("op") not in ("subscribe", "ping"):
            raise AssertionError("unexpected network operation")
        self.sent.append(payload)

    def recv(self, timeout):
        if self.events:
            item = self.events.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        self.clock.sleep(timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


def ack():
    return json.dumps({
        "success": True, "ret_msg": "subscribe",
        "conn_id": "fixture", "op": "subscribe", "req_id": "cia-ticker-1",
    })


def snapshot(symbol, timestamp, *, cs=1, depth="3", lag=50):
    return json.dumps({
        "topic": f"tickers.{symbol}",
        "type": "snapshot", "ts": timestamp - lag, "cs": cs,
        "data": {
            "symbol": symbol, "lastPrice": "100",
            "markPrice": "100", "indexPrice": "100",
            "bid1Price": "99.9", "ask1Price": "100.1",
            "bid1Size": depth, "ask1Size": "4",
        },
    }, sort_keys=True, separators=(",", ":"))


class TickerCoverageD396Tests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.a = TickerUniverseEpoch(FIRST, HELD, T - 1_000)
        self.b = TickerUniverseEpoch(SECOND, HELD, T + 1_000)
        self.created = []

    def factory(self, symbols, *, only=None, lagged=0, no_ack=False,
                no_depth=None, disconnect_after=False, extras=()):
        def new_session():
            now = self.clock.wall()
            selected = tuple(sorted(symbols if only is None else only))
            events = ([] if no_ack else [ack()])
            events += [
                snapshot(sym, now, lag=(2000 if idx < lagged else 50),
                         depth="0" if sym == no_depth else "3")
                for idx, sym in enumerate(selected)
            ]
            events += list(extras)
            if disconnect_after:
                events.append(OSError("fixture_disconnect"))
            sock = FakeSession(self.clock, events)
            self.created.append(sock)
            return sock
        return new_session

    def run(self, factories, *, epochs=None, seconds=3, sessions=1):
        return run_finite_public_ticker_coverage_pilot(
            epochs=(self.a, self.b) if epochs is None else epochs,
            session_factories=tuple(factories),
            budget=TickerLeaseBudget(
                max_sessions=sessions, max_frames=512,
                max_seconds=seconds,
            ),
            clock=self.clock.mono, wall_ms=self.clock.wall,
            sleeper=self.clock.sleep,
        )

    def test_two_50_ranked_epochs_and_open_position_outside_n50(self):
        a = self.factory(self.a.monitored)
        b = self.factory(self.b.monitored)
        report = self.run((a, b))
        self.assertEqual(report.status, "finite_samples_observed_not_continuous")
        self.assertEqual(report.attempted_epochs, 2)
        self.assertEqual(report.ranked_rotations, 1)
        self.assertTrue(report.all_observed_coverage)
        self.assertEqual([r.usable_ranked_observed for r in report.epochs], [50, 50])
        self.assertEqual([r.usable_positions_observed for r in report.epochs], [2, 2])
        self.assertEqual([r.monitored_count for r in report.epochs], [51, 52])
        self.assertEqual([r.fresh_monitored_at_lease_end for r in report.epochs],
                         [51, 52])
        self.assertEqual([r.ticker_frames_accepted for r in report.epochs],
                         [51, 52])
        self.assertEqual([r.p95_lag_bucket for r in report.epochs],
                         ["0_to_100ms", "0_to_100ms"])
        self.assertTrue(all(s.closed for s in self.created))
        self.assertEqual(len(self.created), 2)
        self.assertEqual(set(self.created[0].sent[0]["args"]),
                         {"tickers." + x for x in self.a.monitored})
        self.assertEqual(set(self.created[1].sent[0]["args"]),
                         {"tickers." + x for x in self.b.monitored})
        result = report.sanitized_report()
        self.assertFalse(result["continuous_24x7_verified"])
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["approved_for_live_use"])
        payload = json.dumps(result)
        for name in ("HOLDUSDT", "A00USDT", "A50USDT", "99.9", "100.1"):
            self.assertNotIn(name, payload)

    def test_50_ranked_without_held_outside_ranked_is_incomplete(self):
        f1 = self.factory(self.a.monitored, only=FIRST)
        f2 = self.factory(self.b.monitored)
        r = self.run((f1, f2))
        self.assertEqual(r.status, "abstained_incomplete_coverage")
        self.assertEqual(r.attempted_epochs, 1)
        self.assertEqual(r.ranked_rotations, 0)
        self.assertEqual(r.epochs[0].usable_ranked_observed, 50)
        self.assertEqual(r.epochs[0].usable_positions_observed, 1)
        self.assertEqual(r.epochs[0].fresh_monitored_at_lease_end, 50)
        self.assertEqual(len(self.created), 1)
        self.assertTrue(self.created[0].closed)

    def test_ack_alone_and_duplicate_volume_never_claim_coverage(self):
        no_quotes = self.run((
            self.factory(self.a.monitored, only=()),
            self.factory(self.b.monitored),
        ))
        self.assertFalse(no_quotes.all_observed_coverage)
        self.assertEqual(no_quotes.epochs[0].subscriptions_acknowledged, 1)
        self.assertEqual(no_quotes.epochs[0].ticker_frames_accepted, 0)
        self.assertEqual(no_quotes.epochs[0].p95_lag_bucket, None)

        self.setUp()
        duplicate = snapshot(FIRST[0], self.clock.wall())
        r = self.run((
            self.factory(self.a.monitored, only=(FIRST[0],),
                         extras=(duplicate,) * 90),
            self.factory(self.b.monitored),
        ))
        self.assertEqual(r.attempted_epochs, 1)
        self.assertEqual(r.epochs[0].usable_ranked_observed, 1)
        self.assertGreater(r.epochs[0].ticker_frames_accepted, 50)
        self.assertFalse(r.all_observed_coverage)

    def test_zero_book_depth_unusable_even_with_fifty_frames(self):
        r = self.run((
            self.factory(self.a.monitored, no_depth=FIRST[20]),
            self.factory(self.b.monitored),
        ))
        self.assertEqual(r.epochs[0].usable_ranked_observed, 49)
        self.assertFalse(r.all_observed_coverage)

    def test_coverage_seen_before_reconnect_is_not_fresh_new_session(self):
        first = self.factory(self.a.monitored, disconnect_after=True)
        after = self.factory(self.a.monitored, only=(FIRST[0],))
        selector = iter((first, after))
        r = self.run((
            lambda: next(selector)(),
            self.factory(self.b.monitored),
        ), seconds=8, sessions=2)
        self.assertEqual(r.epochs[0].usable_ranked_observed, 50)
        self.assertLess(r.epochs[0].fresh_monitored_at_lease_end, 51)
        self.assertEqual(r.epochs[0].reconnects, 1)
        self.assertFalse(r.all_observed_coverage)
        self.assertEqual(r.attempted_epochs, 1)
        self.assertTrue(all(x.closed for x in self.created))

    def test_missing_ack_or_wrong_symbol_is_terminal(self):
        r = self.run((
            self.factory(self.a.monitored, no_ack=True),
            self.factory(self.b.monitored),
        ))
        self.assertEqual(r.epochs[0].subscriptions_acknowledged, 0)
        self.assertEqual(r.epochs[0].usable_monitored_observed, 0)
        self.assertEqual(r.attempted_epochs, 1)

        self.setUp()
        r = self.run((
            self.factory(self.a.monitored,
                         extras=(snapshot("WRONGUSDT", T),)),
            self.factory(self.b.monitored),
        ))
        self.assertEqual(r.epochs[0].status, "finite_coverage_insufficient")
        self.assertEqual(r.epochs[0].failure_category, "invalid_market_data")
        self.assertFalse(r.all_observed_coverage)

    def test_binned_p95_is_honest_not_fabricated_millisecond_value(self):
        r = self.run((
            self.factory(self.a.monitored, lagged=10),
            self.factory(self.b.monitored),
        ))
        self.assertTrue(r.all_observed_coverage)
        self.assertEqual(r.epochs[0].p95_lag_bucket, "1001_to_5000ms")
        self.assertTrue(r.sanitized_report()["p95_is_binned_not_exact_ms"])

    def test_invalid_or_future_membership_does_not_open_socket(self):
        with self.assertRaises(DataValidationError):
            TickerUniverseEpoch(FIRST[:49], HELD, T)
        with self.assertRaises(DataGapError):
            self.run((
                self.factory(self.a.monitored),
                self.factory(self.b.monitored),
            ), epochs=(self.a, TickerUniverseEpoch(SECOND, ("HOLDUSDT",),
                                                   T+1000)))
        with self.assertRaises(DataGapError):
            self.run((
                self.factory(self.a.monitored),
                self.factory(self.b.monitored),
            ), epochs=(self.a, replace(self.b, universe_at_ms=T-1001)))
        with self.assertRaises(DataGapError):
            self.run((
                self.factory(self.a.monitored),
                self.factory(self.b.monitored),
            ), epochs=(replace(self.a, universe_at_ms=T+20_000), self.b))
        self.assertEqual(len(self.created), 0)

    def test_oversize_budget_or_missing_factory_fails_without_transport(self):
        bad = TickerLeaseBudget(max_sessions=1, max_frames=51, max_seconds=3)
        with self.assertRaises(DataValidationError):
            run_finite_public_ticker_coverage_pilot(
                epochs=(self.a, self.b),
                session_factories=(
                    self.factory(self.a.monitored),
                    self.factory(self.b.monitored),
                ),
                budget=bad,
            )
        with self.assertRaises(DataValidationError):
            self.run((self.factory(self.a.monitored),))
        self.assertFalse(self.created)

    def test_cli_subprocess_has_auditable_synthetic_50x2_result(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.demo_public_n50_coverage_d396"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        body = json.loads(result.stdout)
        self.assertEqual(body["planned_epochs"], 2)
        self.assertEqual(body["attempted_epochs"], 2)
        self.assertTrue(body["all_observed_coverage"])
        self.assertEqual([e["usable_ranked_observed"] for e in body["epochs"]],
                         [50, 50])
        self.assertEqual([e["monitored_count"] for e in body["epochs"]],
                         [51, 52])
        self.assertFalse(body["continuous_24x7_verified"])
        self.assertFalse(body["orders_sent"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
