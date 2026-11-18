"""D428: multi-lease PAPER trial must preserve D391 router and AUTO4 lock.

No network or actual private owner data in this test suite. D410 receives an
injected *mock* report with cumulative D391 decisions across two leases.
All real decisions/reservations are covered separately in D425/D391 suites.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from decimal import Decimal
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import (
    BybitTickerQuote,
)
from crypto_intelligence_agent.paper_intrahour_quote_router_d391 import (
    PaperIntrahourQuoteRouter,
)
from crypto_intelligence_agent.j4_paper_bounded_trial_d428 import (
    PaperTrialBudget, run_bounded_paper_trial,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    exclusive_paper_operator_lock,
)
from crypto_intelligence_agent.j5_paper_watch_d427 import (
    read_paper_watch,
)
from crypto_intelligence_agent.market_data import (
    DataGapError, DataValidationError,
)
from scripts import run_j4_paper_bounded_trial_d428 as cli
from test_j5_paper_watch_d427 import fake_source

MODULE = "crypto_intelligence_agent.j4_paper_bounded_trial_d428"


def reports(*, count=2):
    out = []
    for i in range(count):
        r = fake_source(reserved=1, reconcile=(i + 1) * 241)
        r["existing_paper_position_quote_processed"] = True
        r["reconnects"] = i % 2
        out.append(r)
    return out


class D428PolicyTests(unittest.TestCase):
    def test_trial_limits_enforce_no_unbounded_daemon_or_frame_budget(self):
        for changed in (
            {"max_leases": 1}, {"max_leases": 5},
            {"max_leases": True},
            {"lease_seconds": 5}, {"lease_seconds": 61},
            {"max_total_seconds": 15}, {"max_total_seconds": 301},
            {"max_interlease_gap_ms": 0},
            {"max_interlease_gap_ms": 15_001},
            {"max_frames_per_lease": 100_000},
            {"max_frames_per_lease": -1},
        ):
            with self.subTest(changed=changed), self.assertRaises(DataValidationError):
                PaperTrialBudget(**changed)

    def test_no_optins_means_no_state_reads_lock_files_or_websocket(self):
        with patch(MODULE + ".exclusive_paper_operator_lock",
                   side_effect=AssertionError("must not create PAPER lock")), patch(
            MODULE + ".publish_paper_watch",
            side_effect=AssertionError("must not publish watch"),
        ), patch(
            MODULE + ".run_current_n50_paper_lease_once",
            side_effect=AssertionError("must not open Bybit WS"),
        ):
            result = run_bounded_paper_trial(
                state_directory=Path("/private/invalid-j1"),
                private_paper_directory=Path("/private/invalid-paper"),
                watch_directory=Path("/private/invalid-watch"),
            )
            self.assertEqual(result["status"], "explicit_seven_optins_required")
            self.assertEqual(result["leases_attempted"], 0)
            self.assertFalse(result["orders_sent"])

    def test_cli_without_seven_optins_never_opens_socket(self):
        with patch.object(cli, "run_bounded_paper_trial",
                          side_effect=AssertionError("no optins")):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = cli.main([
                    "--state-directory", "/owner/unused",
                    "--private-paper-directory", "/paper/unused",
                    "--paper-watch-directory", "/watch/unused",
                ])
            self.assertEqual(code, 65)
            self.assertIn("seven_explicit_owner_optins_required", stdout.getvalue())


class D428HeldPositionFreshnessTests(unittest.TestCase):
    def test_liveness_requires_fresh_price_for_each_held_contract_and_new_ack(self):
        now = time.time_ns() // 1_000_000
        q = BybitTickerQuote(
            symbol="BTCUSDT", exchange_at_ms=now-1000,
            received_at_ms=now-900, cross_sequence=5,
            last_price=Decimal("100"), mark_price=Decimal("100"),
            index_price=Decimal("100"), bid_price=Decimal("99"),
            ask_price=Decimal("101"), bid_size=Decimal("1"),
            ask_size=Decimal("1"), turnover_24h=None,
            volume_24h=None, funding_rate=None,
        )
        # Construct an in-memory router shell solely for testing the count
        # method. The financial journal constructor is covered elsewhere.
        router = object.__new__(PaperIntrahourQuoteRouter)
        router._by_symbol = {"BTCUSDT": None, "ETHUSDT": None}
        router._last = {"BTCUSDT": q}
        router._last_exchange_at_ms = {"BTCUSDT": q.exchange_at_ms}
        self.assertEqual(router.fresh_held_contract_count(at_ms=now), 1)
        self.assertEqual(router.fresh_held_contract_count(at_ms=now+4000), 0)
        with self.assertRaises(DataValidationError):
            router.fresh_held_contract_count(at_ms=True)
        router.begin_new_market_session()
        self.assertEqual(router.fresh_held_contract_count(at_ms=now), 0)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid"
                     and os.geteuid() != 0, "unprivileged POSIX owner required")
class D428OwnerTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.owner = base / "j1"
        self.paper = base / "paper"
        self.watch = base / "watch"
        for p in (self.owner, self.paper, self.watch):
            p.mkdir()
            p.chmod(0o700)

    def run_trial(self, source_reports, *, budget=None, clock=None,
                  fresh_held=1):
        class FakeRouter:
            def fresh_held_contract_count(self, *, at_ms):
                return fresh_held

        fake_router = FakeRouter()
        with patch(
            MODULE + ".load_private_paper_routes",
            return_value=fake_router,
        ) as load_routes, patch(
            MODULE + ".run_current_n50_paper_lease_once",
            side_effect=source_reports,
        ) as backend:
            result = run_bounded_paper_trial(
                state_directory=self.owner,
                private_paper_directory=self.paper,
                watch_directory=self.watch,
                allow_private_pointer_read=True,
                allow_public_websocket=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                allow_synthetic_paper_reservations=True,
                allow_multiple_finite_leases=True,
                allow_paper_watch_output=True,
                budget=budget or PaperTrialBudget(
                    max_leases=2, lease_seconds=10,
                    max_total_seconds=32, max_frames_per_lease=300,
                ),
                clock=clock or (lambda: 11.0),
            )
        return result, backend, load_routes, fake_router

    def test_two_leases_same_router_lock_and_cumulative_decision_deltas(self):
        sources = reports()
        seen = []

        def step(*args, **kwargs):
            self.assertTrue(kwargs["allow_synthetic_paper_reservations"])
            self.assertEqual(kwargs["budget"].max_sessions, 2)
            self.assertEqual(kwargs["budget"].max_seconds, 10)
            seen.append(kwargs["paper_router"])
            # A separate D425 operator can NEVER lock the same PAPER journal
            # while this entire bounded trial is in progress.
            with self.assertRaises(BlockingIOError):
                exclusive_paper_operator_lock(self.paper)
            return sources[len(seen)-1]

        result, backend, load, router = self.run_trial(step)
        self.assertEqual(result["status"], "bounded_trial_completed_no_live_protection")
        self.assertEqual(result["leases_attempted"], 2)
        self.assertEqual(result["leases_with_fresh_position_quotes"], 2)
        self.assertEqual(result["quotes_forwarded_to_paper"], 484)
        self.assertEqual(result["synthetic_exit_reservation_events"], 1)
        self.assertEqual(result["reconciliation_required_events"], 482)
        self.assertEqual(result["public_ws_reconnect_events"], 1)
        self.assertEqual(backend.call_count, 2)
        load.assert_called_once()
        self.assertEqual(seen, [router, router])
        self.assertFalse(result["active_position_supervision_verified"])
        self.assertFalse(result["continuous_24x7_verified"])
        self.assertFalse(result["orders_sent"])
        self.assertNotIn("BTCUSDT", json.dumps(result))
        # Last watch ONLY describes second terminal lease, not cumulative data.
        last = read_paper_watch(
            directory=self.watch, now_ms=time.time_ns() // 1_000_000,
        )
        self.assertEqual(last["hypothetical_reservations_observed"], 0)
        self.assertEqual(last["reconciliation_events_observed"], 241)
        self.assertEqual(last["status"], "finite_paper_lease_ended")
        self.assertTrue(last["finite_lease_ended"])
        self.assertFalse(last["continuous_supervision_verified"])
        # Lock is released; a later real D425 may start if separately gated.
        fd = exclusive_paper_operator_lock(self.paper)
        os.close(fd)

    def test_absent_held_quote_stops_before_second_lease_and_writes_failure(self):
        blank = fake_source(reserved=0, reconcile=0)
        blank["existing_paper_position_quote_processed"] = False
        blank["reconnects"] = 0
        blank["paper_coverage_gate"]["quote_frames_delivered_to_paper"] = 0
        blank["paper_monitoring"]["decision_counts"] = {}
        result, backend, _, _ = self.run_trial(
            [blank, AssertionError("must not run another lease")],
        )
        self.assertEqual(backend.call_count, 1)
        self.assertEqual(result["status"], "held_paper_feed_unverified_or_owner_changed")
        self.assertEqual(result["leases_with_fresh_position_quotes"], 0)
        watch = read_paper_watch(
            directory=self.watch, now_ms=time.time_ns() // 1_000_000,
        )
        self.assertEqual(watch["status"], "finite_paper_lease_failed_closed")
        self.assertEqual(watch["configured_position_routes"], 0)
        self.assertFalse(watch["market_lease_completed"])

    def test_owner_cohort_changed_triggers_fail_closed_without_new_session(self):
        bad = reports()[0]
        bad["owner_scope_unchanged_after_lease"] = False
        result, backend, _, _ = self.run_trial([bad])
        self.assertEqual(backend.call_count, 1)
        self.assertEqual(result["status"], "held_paper_feed_unverified_or_owner_changed")
        self.assertEqual(read_paper_watch(
            directory=self.watch, now_ms=time.time_ns() // 1_000_000,
        )["status"], "finite_paper_lease_failed_closed")

    def test_transport_or_sqlite_exception_preserves_pending_and_abstains(self):
        result, backend, _, _ = self.run_trial([
            DataGapError("ticker_ws_disconnect"),
        ])
        self.assertEqual(backend.call_count, 1)
        self.assertEqual(result["status"], "paper_lease_failed_review_existing_journal")
        self.assertEqual(result["leases_attempted"], 1)
        self.assertEqual(result["synthetic_exit_reservation_events"], 0)
        self.assertFalse(result["real_fills_verified"])
        self.assertEqual(read_paper_watch(
            directory=self.watch, now_ms=time.time_ns() // 1_000_000,
        )["status"], "finite_paper_lease_failed_closed")

    def test_gapped_monotonic_clock_prevents_next_socket(self):
        times = iter((1.0, 1.0, 11.0, 11.0, 19.0))
        result, backend, _, _ = self.run_trial(
            reports(), clock=lambda: next(times),
        )
        self.assertEqual(result["status"], "interlease_feed_gap_exceeded")
        self.assertEqual(backend.call_count, 1)
        self.assertEqual(result["leases_with_fresh_position_quotes"], 1)
        self.assertFalse(result["active_position_supervision_verified"])
        self.assertEqual(read_paper_watch(
            directory=self.watch, now_ms=time.time_ns() // 1_000_000,
        )["status"], "finite_paper_lease_failed_closed")

    def test_stale_held_contract_at_end_stops_even_if_some_ticks_were_routed(self):
        result, backend, _, _ = self.run_trial(reports(), fresh_held=0)
        self.assertEqual(result["status"], "held_paper_feed_not_fresh_at_end")
        self.assertEqual(backend.call_count, 1)
        self.assertEqual(result["leases_with_fresh_position_quotes"], 0)
        self.assertEqual(read_paper_watch(
            directory=self.watch, now_ms=time.time_ns() // 1_000_000,
        )["status"], "finite_paper_lease_failed_closed")

    def test_regressed_d391_cumulative_counts_refused(self):
        source = reports()
        source[1]["paper_monitoring"]["decision_counts"] = {
            "paper_stop_reserved": 0, "paper_stop_reconciliation_required": 0,
        }
        result, backend, _, _ = self.run_trial(source)
        self.assertEqual(result["status"], "paper_lease_failed_review_existing_journal")
        self.assertEqual(backend.call_count, 2)
        self.assertEqual(result["leases_with_fresh_position_quotes"], 1)
        self.assertEqual(read_paper_watch(
            directory=self.watch, now_ms=time.time_ns() // 1_000_000,
        )["status"], "finite_paper_lease_failed_closed")

    def test_watch_nested_in_private_journal_is_denied_before_lock_or_ws(self):
        nested = self.paper / "watch"
        nested.mkdir()
        nested.chmod(0o700)
        with patch(MODULE + ".exclusive_paper_operator_lock",
                   side_effect=AssertionError("never lock financial dir")), patch(
            MODULE + ".run_current_n50_paper_lease_once",
            side_effect=AssertionError("never use WebSocket"),
        ):
            with self.assertRaises(DataValidationError):
                run_bounded_paper_trial(
                    state_directory=self.owner,
                    private_paper_directory=self.paper,
                    watch_directory=nested,
                    allow_private_pointer_read=True, allow_public_websocket=True,
                    confirm_personal_readonly_research=True,
                    confirm_region_eligible=True,
                    allow_synthetic_paper_reservations=True,
                    allow_multiple_finite_leases=True,
                    allow_paper_watch_output=True,
                )


if __name__ == "__main__":
    unittest.main()
