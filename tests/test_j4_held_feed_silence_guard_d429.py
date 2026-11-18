"""D429: an ACKed public stream is not proof the HELD PAPER ticker is alive.

Offline-only tests: fake Bybit frames, actual D385/D386/D390/D410/D391 and
AUTO4 synthetic journal. No real WS, account, credentials, service or orders.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, supervise_public_tickers,
)
from crypto_intelligence_agent.bybit_public_ticker_optin_d390 import (
    run_readonly_bybit_ticker_lease,
)
from crypto_intelligence_agent.j2_j4_current_n50_paper_lease_d410 import (
    run_current_n50_paper_lease_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    _new_position, _route,
)
from test_bybit_public_ticker_supervisor_d386 import (
    FakeClock, Session, ack as generic_ack, make_book,
)
from test_j2_j4_current_n50_paper_lease_d410 import (
    Clock, Socket, STATE, CURRENT, ack, ticker,
)


class D429TickerIdleHookTests(unittest.TestCase):
    def test_post_ack_loop_hook_fails_closed_during_ws_silence(self):
        clock = FakeClock()
        conn = Session(clock, (generic_ack(),))
        polls = []
        def guard():
            polls.append(clock.monotonic_time)
            if clock.monotonic_time >= 6:
                raise DataGapError("paper_held_quote_silence_exceeded")
        report = supervise_public_tickers(
            session_factory=lambda: conn, book=make_book(),
            budget=TickerLeaseBudget(
                max_sessions=1, max_frames=100, max_seconds=20,
            ),
            clock=clock.monotonic, wall_ms=clock.utc,
            sleeper=clock.advance, on_acked_poll=guard,
        )
        self.assertEqual(report.status, "lease_abstained")
        self.assertEqual(report.failure_category, "held_paper_feed_silent")
        self.assertTrue(conn.closed)
        self.assertGreaterEqual(len(polls), 2)
        self.assertEqual(report.subscriptions_acknowledged, 1)
        self.assertEqual(report.ticker_frames_accepted, 0)
        self.assertFalse(report.sanitized_report()["orders_sent"])

    def test_pre_ack_data_never_invokes_idle_supervision(self):
        clock = FakeClock()
        conn = Session(clock, ())
        polls = []
        report = supervise_public_tickers(
            session_factory=lambda: conn, book=make_book(),
            budget=TickerLeaseBudget(max_sessions=1, max_frames=100,
                                     max_seconds=6),
            clock=clock.monotonic, wall_ms=clock.utc,
            sleeper=clock.advance, on_acked_poll=lambda: polls.append(1),
        )
        self.assertEqual(polls, [])
        self.assertEqual(report.status, "lease_abstained")
        self.assertEqual(report.subscriptions_acknowledged, 0)
        self.assertTrue(conn.closed)

    def test_noncallable_idle_hook_rejected_before_socket(self):
        with self.assertRaises(DataValidationError):
            supervise_public_tickers(
                session_factory=lambda: (_ for _ in ()).throw(
                    AssertionError("no socket after invalid hook")
                ),
                book=make_book(), on_acked_poll="bad",
            )


class D429ActualPaperRouterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.journal = Path(tmp.name) / "positions.sqlite"
        _new_position(self.journal, short=False)
        self.router = _route(self.journal, short=False)
        self.clock = Clock()

    def run_owner_paper(self, frames, *, guard=True, budget_seconds=15):
        conn = Socket(self.clock, frames)
        with patch(
            "crypto_intelligence_agent.j2_j4_current_n50_paper_lease_d410."
            "read_current_j1_n50_scope", side_effect=(CURRENT, CURRENT),
        ) as reader, patch(
            "socket.create_connection",
            side_effect=AssertionError("offline fake must not access network"),
        ):
            report = run_current_n50_paper_lease_once(
                state_directory=STATE, paper_router=self.router,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                allow_synthetic_paper_reservations=True,
                guard_held_feed_during_lease=guard,
                budget=TickerLeaseBudget(
                    max_sessions=1, max_frames=150, max_seconds=budget_seconds,
                ),
                session_factory=lambda: conn,
                clock=self.clock.mono, wall_ms=self.clock.wall,
                sleeper=self.clock.sleep,
            )
        return report, conn, reader

    def test_busy_other_symbol_cannot_hide_silent_held_contract(self):
        frames = [
            ack(), ticker("BTCUSDT", seq=1),
            ("delay", 5.5), ticker("ALT00USDT", seq=10, time_delta=5500),
        ]
        observed, socket, reader = self.run_owner_paper(frames)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(observed["underlying_ws_status"], "lease_abstained")
        self.assertEqual(observed["failure_category"], "held_paper_feed_silent")
        self.assertEqual(observed["subscriptions_acknowledged"], 1)
        self.assertEqual(observed["paper_coverage_gate"][
            "quote_frames_delivered_to_paper"], 1)
        self.assertTrue(socket.closed)
        self.assertFalse(observed["orders_sent"])
        self.assertFalse(observed["native_stop_verified"])

    def test_new_held_quotes_inside_age_limit_do_not_trigger_false_abort(self):
        frames = [ack(), ticker("BTCUSDT", seq=1)]
        for i in range(1, 5):
            frames.extend((
                ("delay", 2.5),
                ticker("BTCUSDT", seq=i+1, time_delta=i*2500),
            ))
        result, _, _ = self.run_owner_paper(frames, budget_seconds=10)
        self.assertEqual(result["underlying_ws_status"], "lease_completed")
        self.assertNotEqual(result.get("failure_category"),
                            "held_paper_feed_silent")
        self.assertEqual(result["subscriptions_acknowledged"], 1)
        self.assertFalse(result["orders_sent"])

    def test_held_guard_cannot_be_enabled_without_paper_router_or_gate(self):
        with self.assertRaises(DataValidationError):
            run_readonly_bybit_ticker_lease(
                ranked_symbols=("BTCUSDT",),
                universe_at_ms=CURRENT.activated_at_ms,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                guard_held_feed_during_lease=True,
                session_factory=lambda: (_ for _ in ()).throw(
                    AssertionError("no network")
                ),
            )

    def test_held_guard_accepts_only_boolean_optin(self):
        with self.assertRaises(DataValidationError):
            run_current_n50_paper_lease_once(
                state_directory=STATE, paper_router=self.router,
                guard_held_feed_during_lease=1,
            )


if __name__ == "__main__":
    unittest.main()
