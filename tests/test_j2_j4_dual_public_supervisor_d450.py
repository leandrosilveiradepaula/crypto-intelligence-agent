"""D450: actual existing WS validators feeding a 50-member PAPER pipeline.

All sockets below are in-memory protocol sessions. None are public market
captures and no fixture claim can authorize a real broker order.
"""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS, SQLiteOfflineClosedStreamJournal
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.j2_j4_dual_public_supervisor_d450 import (
    DualPaperLeaseBudget, run_finite_n50_paper_streams,
)
from crypto_intelligence_agent.j2_j4_public_paper_cycle_d449 import PublicPaperCycle
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import load_private_paper_routes
from crypto_intelligence_agent.j4_durable_paper_risk_d452 import DurablePaperRiskSource
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.market_data import DataValidationError
from test_j2_j4_public_paper_cycle_d449 import (
    FIRST, LAST, RECEIPT, SIZE, SETTINGS,
    contract, frame, paper_risk, scope_and_symbols,
)


def ack(req="cia-ws-1"):
    return json.dumps({
        "op": "subscribe", "success": True,
        "ret_msg": "subscribe", "conn_id": "fixture", "req_id": req,
    })


def market_quote(*, ts: int, cs: int, mark: str = "105"):
    value = Decimal(mark)
    return json.dumps({
        "topic": "tickers.ETHUSDT", "type": "snapshot",
        "ts": ts, "cs": cs,
        "data": {
            "symbol": "ETHUSDT",
            "lastPrice": mark, "markPrice": mark, "indexPrice": mark,
            "bid1Price": str(value - Decimal("0.1")),
            "ask1Price": str(value + Decimal("0.1")),
            "bid1Size": "20", "ask1Size": "20",
            "turnover24h": "1000000", "volume24h": "10000",
            "fundingRate": "0",
        },
    })


class Clock:
    def __init__(self):
        self.mono_time = 0.0
        self.utc_ms = RECEIPT

    def monotonic(self):
        return self.mono_time

    def wall(self):
        return self.utc_ms

    def sleeper(self, seconds):
        self.mono_time += seconds
        self.utc_ms += int(seconds * 1000)


class Session:
    def __init__(self, clock: Clock, frames, *, after_close=None, signal_done=None):
        self.clock = clock
        self.frames = list(frames)
        self.after_close = after_close
        self.signal_done = signal_done
        self.sent = []
        self.closed = False

    def send(self, payload):
        parsed = json.loads(payload)
        if parsed.get("op") not in ("subscribe", "ping"):
            raise AssertionError("not a public WS control frame")
        self.sent.append(parsed)

    def recv(self, timeout):
        if self.frames:
            raw, received = self.frames[0]
            if (self.after_close is not None
                    and raw.startswith('{"topic": "tickers.')
                    and not self.after_close.wait(3)):
                raise TimeoutError("kline callbacks not ready")
            self.frames.pop(0)
            self.clock.utc_ms = received
            self.clock.mono_time += 0.001
            return raw
        if self.signal_done is not None:
            self.signal_done.set()
        self.clock.sleeper(timeout)
        raise TimeoutError("end of offline frames")

    def close(self):
        self.closed = True


BUDGET = DualPaperLeaseBudget(
    WSRunBudget(max_sessions=1, max_frames=200, max_seconds=5),
    TickerLeaseBudget(max_sessions=1, max_frames=200, max_seconds=5),
)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "POSIX non-root owner only")
class DualPublicStreamIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="cia-d450-")
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.paper = base / "paper"
        self.paper.mkdir(mode=0o700)
        self.market = base / "j2"
        self.market.mkdir(mode=0o700)
        self.closed = self.market / "closed.sqlite"
        self.scope, self.symbols = scope_and_symbols()
        store = SQLiteOfflineClosedStreamJournal.create(self.closed)
        # Bootstrap from explicitly OFFLINE historical frames only. It is
        # not silently labelled public; the final hour passes through the
        # actual reviewed public WS supervisor below.
        seed = [(ack(), FIRST + 1)]
        for hour in range(24):
            for symbol in self.symbols:
                seed.append(frame(symbol, hour))
        result = ingest_offline_ws_batch(
            frames=tuple(seed), scope=self.scope, journal=store,
        )
        self.assertEqual(result.appended, SIZE * 24)
        self.cycle = PublicPaperCycle(
            scope=self.scope, closed_journal_path=self.closed,
            private_paper_directory=self.paper, config=SETTINGS,
            contract_for_quote=contract, risk_for_quote=paper_risk,
        )

    def run_streams(self, *, omit_close=None, omit_ack=False, allow=True,
                    risk_source=None, postclose_trade_clock=False,
                    mixed_close_and_open=False, late_ticker_clock=False):
        ready = threading.Event()
        kc, tc = Clock(), Clock()
        last = [frame(s, 24) for s in self.symbols if s != omit_close]
        if postclose_trade_clock:
            updated = []
            for raw, received in last:
                payload = json.loads(raw)
                row = payload["data"][0]
                # Real Bybit observed 21/11/2026: trade timestamp=end+202ms,
                # server timestamp likewise end+202ms (bounded by receipt).
                row["timestamp"] = row["end"] + 202
                payload["ts"] = row["end"] + 202
                updated.append((json.dumps(payload), received))
            last = updated
        if mixed_close_and_open:
            # D466 reproduces one Bybit snapshot containing a fully closed
            # previous hour AND the next hour's unconfirmed first tick.
            # D1 accepts both after full validation but appends only one;
            # the PAPER callback must only forward the committed row.
            raw, received = last[0]
            payload = json.loads(raw)
            previous = payload["data"][0]
            next_hour = previous["start"] + HOUR_MS
            next_row = dict(previous)
            next_row.update({
                "start": next_hour, "end": next_hour + HOUR_MS - 1,
                "timestamp": next_hour + 100,
                "open": previous["close"], "high": previous["close"],
                "low": previous["close"], "close": previous["close"],
                "volume": "0", "turnover": "0", "confirm": False,
            })
            payload["ts"] = received - 100
            payload["data"] = [previous, next_row]
            last[0] = (json.dumps(payload), received)
        kframes = ([] if omit_ack else [(ack(), RECEIPT)]) + last
        tframes = [
            (ack("cia-ticker-1"), RECEIPT),
            (market_quote(ts=RECEIPT - (4000 if late_ticker_clock else 100),
                          cs=10), RECEIPT),
            (market_quote(ts=RECEIPT + 400, cs=11), RECEIPT + 500),
            (market_quote(ts=RECEIPT + 1100, cs=12, mark="107.3"), RECEIPT + 1200),
        ]
        ks = Session(kc, kframes, signal_done=ready)
        ts = Session(tc, tframes, after_close=ready)
        with patch(
            "socket.create_connection",
            side_effect=AssertionError("offline two-stream test must not connect network"),
        ):
            report = run_finite_n50_paper_streams(
                cycle=self.cycle, scope=self.scope,
                journal_path=self.closed, budget=BUDGET,
                allow_public_network=allow,
                allow_public_websocket=allow,
                confirm_personal_readonly_research=allow,
                confirm_region_eligible=allow,
                confirm_public_data_rights=allow,
                enable_hypothetical_paper_cycle=allow,
                kline_session_factory=lambda: ks,
                ticker_session_factory=lambda: ts,
                kline_clock_args={
                    "clock": kc.monotonic, "wall_ms": kc.wall, "sleeper": kc.sleeper,
                },
                ticker_clock_args={
                    "clock": tc.monotonic, "wall_ms": tc.wall, "sleeper": tc.sleeper,
                },
                risk_source=risk_source,
            )
        return report, ks, ts

    def test_d479_delayed_transport_ticker_does_not_kill_public_paper(self):
        source = DurablePaperRiskSource(private_paper_directory=self.paper)
        self.cycle._risk = source
        result, _, _ = self.run_streams(
            risk_source=source, late_ticker_clock=True,
        )
        self.assertEqual(result["status"], "finite_public_paper_research_closed")
        self.assertEqual(result["paper_quote_clock_abstentions"], 1)
        self.assertEqual(result["ticker_failure_category"], None)
        self.assertEqual(result["accepted_public_ticker_callbacks"], 3)
        self.assertFalse(result["orders_sent"])

    def test_d479_future_and_lagged_marks_stay_out_of_paper_risk(self):
        from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitTickerQuote
        from dataclasses import replace as dc_replace
        source = DurablePaperRiskSource(private_paper_directory=self.paper)
        q = BybitTickerQuote(
            symbol="ETHUSDT", exchange_at_ms=RECEIPT + 500,
            received_at_ms=RECEIPT, cross_sequence=1,
            last_price=Decimal("105"), mark_price=Decimal("105"),
            index_price=Decimal("105"), bid_price=Decimal("104.9"),
            ask_price=Decimal("105.1"), bid_size=Decimal("1"),
            ask_size=Decimal("1"), turnover_24h=None, volume_24h=None,
            funding_rate=None,
        )
        self.assertFalse(source.usable_public_quote_clock(q))
        self.assertFalse(source.usable_public_quote_clock(
            dc_replace(q, exchange_at_ms=RECEIPT - 4000)))
        self.assertTrue(source.usable_public_quote_clock(
            dc_replace(q, exchange_at_ms=RECEIPT - 100)))

    def test_d479_callback_stage_is_safe_and_not_labeled_bybit_failure(self):
        source = DurablePaperRiskSource(private_paper_directory=self.paper)
        self.cycle._risk = source
        with patch.object(source, "observe_public_quote",
                          side_effect=DataValidationError("D452 test")):
            risk_report, _, _ = self.run_streams(risk_source=source)
        self.assertEqual(risk_report["ticker_failure_category"],
                         "paper_risk_callback_failed")
        self.assertFalse(risk_report["orders_sent"])
        with patch.object(self.cycle, "on_public_quote",
                          side_effect=DataValidationError("D449 test")):
            cycle_report, _, _ = self.run_streams(risk_source=source)
        self.assertEqual(cycle_report["ticker_failure_category"],
                         "paper_execution_callback_failed")
        self.assertFalse(cycle_report["orders_sent"])

    def test_d479_gap_enabled_only_as_explicit_journal_metadata(self):
        from crypto_intelligence_agent.j2_j4_dual_public_supervisor_d450 import (
            supervise_ws_research as actual,
        )
        options = []
        def wrapped(**kwargs):
            options.append(kwargs.get("allow_declared_gaps"))
            return actual(**kwargs)
        with patch(
            "crypto_intelligence_agent.j2_j4_dual_public_supervisor_d450."
            "supervise_ws_research", side_effect=wrapped,
        ):
            result, _, _ = self.run_streams()
        self.assertEqual(options, [True])
        self.assertEqual(result["accepted_closed_callbacks"], SIZE)
        self.assertFalse(result["orders_sent"])

    def test_parallel_50_kline_and_ticker_ws_to_paper_and_partial(self):
        result, ks, ts = self.run_streams()
        self.assertTrue(ks.closed)
        self.assertTrue(ts.closed)
        self.assertEqual(len(ks.sent[0]["args"]), SIZE)
        self.assertEqual(len(ts.sent[0]["args"]), SIZE)
        self.assertEqual(result["status"], "finite_public_paper_research_closed")
        self.assertEqual(result["data_mode"], "injected_offline_protocol_replay")
        self.assertEqual(result["kline_acks"], 1)
        self.assertEqual(result["ticker_acks"], 1)
        self.assertEqual(result["accepted_closed_callbacks"], SIZE)
        self.assertEqual(result["accepted_public_ticker_callbacks"], 3)
        self.assertEqual(result["paper_cycle"]["held_paper_contract_count"], 1)
        self.assertEqual(result["paper_cycle"]["pending_paper_open_count"], 0)
        route = load_private_paper_routes(self.paper)
        pos = SQLitePaperPositionJournal(self.paper / "paper-positions.sqlite").load(
            route.monitored_position_ids[0],
        )
        self.assertEqual(pos.confirmed_remaining_units, Decimal("2"))
        self.assertEqual(pos.reserved_unfilled_units, Decimal("0.6"))
        self.assertEqual(pos.filled_exit_units, 0)
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["session_continues_after_return"])
        self.assertFalse(result["marketwide_n50_verified"])


    def test_mixed_closed_and_open_rows_still_complete_50_ws_callbacks(self):
        report, _, _ = self.run_streams(mixed_close_and_open=True)
        self.assertEqual(report["status"], "finite_public_paper_research_closed")
        self.assertEqual(report["kline_confirmed_events_appended"], SIZE)
        self.assertEqual(report["accepted_closed_callbacks"], SIZE)
        self.assertEqual(report["paper_cycle"]["event_counts"].get(
            "confirmed_close_observed"), SIZE)
        self.assertEqual(report["paper_cycle"]["event_counts"].get(
            "cohort_researched"), 1)
        self.assertEqual(report["kline_failure_category"], None)
        self.assertFalse(report["orders_sent"])
        from sqlite3 import connect
        with connect(self.closed) as db:
            rows = db.execute(
                "select count(*) from confirmed where open_ms=?", (LAST,),
            ).fetchone()[0]
            self.assertEqual(rows, SIZE)
            self.assertEqual(db.execute(
                "select count(*) from confirmed where open_ms=?", (LAST + HOUR_MS,),
            ).fetchone()[0], 0)

    def test_real_bybit_postclose_trade_clock_is_persisted_and_replayed(self):
        report, _, _ = self.run_streams(postclose_trade_clock=True)
        self.assertEqual(report["status"], "finite_public_paper_research_closed")
        self.assertEqual(report["accepted_closed_callbacks"], SIZE)
        self.assertEqual(report["kline_confirmed_events_appended"], SIZE)
        self.assertEqual(report["kline_postclose_trade_clock_accepted"], SIZE)
        self.assertEqual(report["kline_temporal_discard_count"], 0)
        self.assertIsNone(report["kline_failure_category"])
        # Exact same vetted journal that J2 feature research subsequently
        # reads: no duplicate REST backfill and no synthetic close.
        from sqlite3 import connect
        with connect(self.closed) as db:
            rows = db.execute(
                "SELECT COUNT(*) FROM confirmed WHERE open_ms=?", (LAST,),
            ).fetchone()[0]
        self.assertEqual(rows, SIZE)
        self.assertFalse(report["orders_sent"])

    def test_real_durable_risk_reader_with_two_supervisors_no_zero_fixture(self):
        risk = DurablePaperRiskSource(private_paper_directory=self.paper)
        self.cycle._risk = risk
        result, _, _ = self.run_streams(risk_source=risk)
        self.assertEqual(result["accepted_closed_callbacks"], 50)
        self.assertEqual(result["paper_cycle"]["held_paper_contract_count"], 1)
        self.assertEqual(result["paper_cycle"]["pending_paper_open_count"], 0)
        # A position whose opening cost/realized PnL was never measured is
        # not automatically allowed to open another position.
        from test_j2_j4_public_paper_cycle_d449 import ticker
        later = ticker(at=RECEIPT + 1400, mark="107.3", seq=13)
        risk.observe_public_quote(later)
        snapshot = risk.inspect(later)
        self.assertEqual(snapshot.filled_open_count, 1)
        self.assertGreater(snapshot.portfolio_exposure_quote, 0)
        self.assertFalse(snapshot.realized_loss_known_zero)

    def test_missing_one_close_abstains_openings_without_forging_cohort(self):
        report, _, _ = self.run_streams(omit_close="BTCUSDT")
        self.assertFalse(report["paper_cycle"]["research_cohort_complete"])
        self.assertEqual(report["paper_cycle"]["pending_paper_open_count"], 0)
        self.assertEqual(report["paper_cycle"]["held_paper_contract_count"], 0)
        self.assertFalse((self.paper / "paper-routes.json").exists())

    def test_failed_public_ws_stops_its_peer_before_full_lease(self):
        # Both error directions are exercised through the actual supervisor
        # receive loops and fake sockets. No orders, REST, or live sockets.
        for failing in ("kline", "ticker"):
            with self.subTest(failing=failing):
                kc, tc = Clock(), Clock()

                def bounded_wait(c):
                    def wait(seconds):
                        threading.Event().wait(0.001)
                        c.mono_time += min(seconds, 0.25)
                        c.utc_ms += int(min(seconds, 0.25) * 1000)
                    return wait

                kc.sleeper = bounded_wait(kc)
                tc.sleeper = bounded_wait(tc)
                bad = ('{"unexpected":true}', RECEIPT + 1)
                ks = Session(kc, [(ack(), RECEIPT)]
                             + ([bad] if failing == "kline" else []))
                ts = Session(tc, [(ack("cia-ticker-1"), RECEIPT)]
                             + ([bad] if failing == "ticker" else []))
                budget = DualPaperLeaseBudget(
                    WSRunBudget(max_sessions=1, max_frames=100000, max_seconds=120),
                    TickerLeaseBudget(max_sessions=1, max_frames=100000, max_seconds=120),
                )
                with patch(
                    "socket.create_connection",
                    side_effect=AssertionError("must not access network"),
                ):
                    report = run_finite_n50_paper_streams(
                        cycle=self.cycle, scope=self.scope,
                        journal_path=self.closed, budget=budget,
                        allow_public_network=True,
                        allow_public_websocket=True,
                        confirm_personal_readonly_research=True,
                        confirm_region_eligible=True,
                        confirm_public_data_rights=True,
                        enable_hypothetical_paper_cycle=True,
                        kline_session_factory=lambda: ks,
                        ticker_session_factory=lambda: ts,
                        kline_clock_args={
                            "clock": kc.monotonic, "wall_ms": kc.wall,
                            "sleeper": kc.sleeper,
                        },
                        ticker_clock_args={
                            "clock": tc.monotonic, "wall_ms": tc.wall,
                            "sleeper": tc.sleeper,
                        },
                    )
                # A peer may be stopped before its socket is ever opened.
                # An opened socket must be closed on return.
                self.assertTrue(ks.closed or not ks.sent)
                self.assertTrue(ts.closed or not ts.sent)
                self.assertEqual(
                    report["status"], "finite_public_paper_research_degraded",
                )
                self.assertEqual(report["accepted_closed_callbacks"], 0)
                if failing == "kline":
                    self.assertEqual(
                        report["ticker_failure_category"],
                        "paired_public_stream_stopped",
                    )
                else:
                    self.assertEqual(
                        report["kline_failure_category"],
                        "paired_public_stream_stopped",
                    )
                self.assertLess(kc.mono_time, 10)
                self.assertLess(tc.mono_time, 10)
                self.assertFalse(report["orders_sent"])


    def test_recover_transport_disconnect_inside_same_bounded_paper_lease(self):
        # The first ticker ACK is followed by an OSError. The second public
        # session must re-ACK and provide fresh BBO while the kline supervisor
        # retains 50 journaled closes. All protocols are in-memory fixtures.
        ready = threading.Event()
        kc, tc = Clock(), Clock()
        kline = Session(
            kc, [(ack(), RECEIPT)]
            + [frame(s, 24) for s in self.symbols],
            signal_done=ready,
        )

        class DropAfterAck(Session):
            def recv(self, timeout):
                if self.frames:
                    return super().recv(timeout)
                raise OSError("offline transport interruption")

        first = DropAfterAck(tc, [(ack("cia-ticker-1"), RECEIPT)])
        second = Session(tc, [
            (ack("cia-ticker-1"), RECEIPT),
            (market_quote(ts=RECEIPT - 100, cs=10), RECEIPT),
            (market_quote(ts=RECEIPT + 400, cs=11), RECEIPT + 500),
            (market_quote(ts=RECEIPT + 1100, cs=12, mark="107.3"),
             RECEIPT + 1200),
        ], after_close=ready)
        attempts = iter((first, second))
        budget = DualPaperLeaseBudget(
            WSRunBudget(max_sessions=2, max_frames=200, max_seconds=15),
            TickerLeaseBudget(max_sessions=2, max_frames=200, max_seconds=15),
        )
        with patch(
            "socket.create_connection",
            side_effect=AssertionError("transport replay must remain offline"),
        ):
            result = run_finite_n50_paper_streams(
                cycle=self.cycle, scope=self.scope,
                journal_path=self.closed, budget=budget,
                allow_public_network=True, allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True, confirm_public_data_rights=True,
                enable_hypothetical_paper_cycle=True,
                kline_session_factory=lambda: kline,
                ticker_session_factory=lambda: next(attempts),
                kline_clock_args={
                    "clock": kc.monotonic, "wall_ms": kc.wall, "sleeper": kc.sleeper,
                },
                ticker_clock_args={
                    "clock": tc.monotonic, "wall_ms": tc.wall, "sleeper": tc.sleeper,
                },
            )
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertTrue(kline.closed)
        self.assertEqual(result["status"], "finite_public_paper_research_closed")
        self.assertEqual(result["kline_confirmed_events_appended"], SIZE)
        self.assertEqual(result["accepted_closed_callbacks"], SIZE)
        self.assertEqual(result["ticker_acks"], 2)
        self.assertEqual(result["ticker_reconnects"], 1)
        self.assertEqual(result["accepted_public_ticker_callbacks"], 3)
        self.assertEqual(result["paper_cycle"]["held_paper_contract_count"], 1)
        self.assertFalse(result["orders_sent"])

    def test_reconnect_sessions_must_match_and_never_exceed_three(self):
        DualPaperLeaseBudget(
            WSRunBudget(max_sessions=3, max_frames=200, max_seconds=15),
            TickerLeaseBudget(max_sessions=3, max_frames=200, max_seconds=15),
        )
        with self.assertRaises(DataValidationError):
            DualPaperLeaseBudget(
                WSRunBudget(max_sessions=2, max_frames=200, max_seconds=15),
                TickerLeaseBudget(max_sessions=1, max_frames=200, max_seconds=15),
            )
        with self.assertRaises(DataValidationError):
            DualPaperLeaseBudget(
                WSRunBudget(max_sessions=4, max_frames=200, max_seconds=15),
                TickerLeaseBudget(max_sessions=4, max_frames=200, max_seconds=15),
            )

    def test_denied_without_explicit_optins_no_sockets(self):
        report, k, t = self.run_streams(allow=False)
        self.assertEqual(report["status"], "six_explicit_paper_public_data_optins_required")
        self.assertFalse(k.sent)
        self.assertFalse(t.sent)
        self.assertFalse(report["network_attempted"])

    def test_malformed_subscription_ack_never_accepts_kline_signal(self):
        report, k, _ = self.run_streams(omit_ack=True)
        self.assertEqual(report["kline_acks"], 0)
        self.assertEqual(report["accepted_closed_callbacks"], 0)
        self.assertEqual(report["paper_cycle"]["held_paper_contract_count"], 0)
        self.assertFalse(report["orders_sent"])


if __name__ == "__main__":
    unittest.main()
