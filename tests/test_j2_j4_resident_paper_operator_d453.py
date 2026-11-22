"""D453: recurring public PAPER watch + held-only fallback on N50 failure."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import os
import threading
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.j2_j4_dual_public_supervisor_d450 import DualPaperLeaseBudget
from crypto_intelligence_agent.j2_j4_resident_paper_operator_d453 import (
    ResidentPaperRunPolicy, run_resident_paper_observer,
    run_held_paper_without_n50, _resident_lock,
)
from crypto_intelligence_agent.j2_observed_paper_entry_d447 import reserve_observed_paper_entry
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import (
    arm_observed_paper_entry, materialize_observed_paper_entry,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from test_j2_j4_public_paper_cycle_d449 import SETTINGS
from test_j4_automatic_entry_materializer_d448 import POLICY
from test_j2_observed_paper_entry_d447 import inputs
from test_j2_j4_dual_public_supervisor_d450 import Clock, Session, ack, market_quote


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "nonroot owner required")
class ResidentPaperOperatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cia-d453-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home.chmod(0o700)
        self.paper = self.home / "paper"
        self.paper.mkdir(mode=0o700)
        self.j2 = self.home / "j2"
        self.j2.mkdir(mode=0o700)
        self.budget = DualPaperLeaseBudget(
            WSRunBudget(max_sessions=1, max_frames=200, max_seconds=2),
            TickerLeaseBudget(max_sessions=1, max_frames=200, max_seconds=2),
        )
        self.flags = {
            "allow_public_network": True,
            "allow_public_websocket": True,
            "confirm_personal_readonly_research": True,
            "confirm_region_eligible": True,
            "confirm_public_data_rights": True,
            "enable_hypothetical_paper_cycle": True,
        }

    def test_three_leases_degraded_primary_switches_to_held_then_restarts(self):
        seen = []
        ticks = [1_800_000_000_000]
        good = {
            "status": "finite_public_paper_research_closed",
            "orders_sent": False,
        }
        state = iter((good,
                      {"status": "finite_public_paper_research_degraded",
                       "orders_sent": False},
                      DataGapError("simulated REST outage")))
        def primary():
            out = next(state)
            seen.append("primary")
            if isinstance(out, Exception):
                raise out
            return out
        def held():
            seen.append("held")
            return {"status": "no_held_paper_positions",
                    "orders_sent": False}
        def now():
            ticks[0] += 101
            return ticks[0]
        report = run_resident_paper_observer(
            private_j2_directory=self.j2,
            private_paper_directory=self.paper,
            config=SETTINGS,
            policy=ResidentPaperRunPolicy(self.budget, 0, 3),
            primary_lease=primary,
            held_fallback_lease=held,
            sleep=lambda _: seen.append("pause"),
            clock_ms=now,
            should_stop=lambda: False,
            **self.flags,
        )
        self.assertEqual(report["status"], "bounded_run_completed")
        self.assertEqual(report["cycles_attempted"], 3)
        self.assertEqual(report["primary_leases_completed"], 1)
        self.assertEqual(report["held_only_fallbacks"], 2)
        self.assertEqual(seen.count("held"), 2)
        self.assertFalse(report["orders_sent"])
        payload = json.loads(
            (self.paper / "paper-operator-state-d453.json").read_text(),
        )
        self.assertEqual(payload["state"], "bounded_run_completed")
        self.assertEqual(payload["held_only_fallbacks"], 2)
        self.assertFalse(payload["position_monitoring_guaranteed"])
        self.assertFalse(payload["native_protective_orders"])
        self.assertEqual(
            (self.paper / "paper-operator-state-d453.json").stat().st_mode & 0o777,
            0o600,
        )

    def test_long_primary_lease_status_stays_readable_and_pulses_in_j5(self):
        # D468: D453's old TTL was 2*3480s and D456 (max 375s)
        # rejected the status for the entire long observation window.
        from crypto_intelligence_agent import j2_j4_resident_paper_operator_d453 as operator
        from crypto_intelligence_agent.j5_resident_paper_status_d456 import (
            read_resident_paper_status,
        )
        fixed_ms = 1_800_000_000_000
        updates = []
        has_pulsed = threading.Event()
        original_writer = operator._atomic_private_write

        def record_write(directory, filename, raw):
            if filename == "paper-operator-state-d453.json":
                value = json.loads(raw)
                if value["state"] == "observing_public_lease":
                    updates.append(value)
                    if len(updates) > 1:
                        has_pulsed.set()
            return original_writer(directory, filename, raw)

        def primary():
            # This is a real read through the same strict reader J5 uses,
            # while the long (3480s) lease is nominally active.
            status = read_resident_paper_status(
                directory=self.paper, now_ms=fixed_ms,
            )
            self.assertEqual(status["status"], "observing_public_lease")
            self.assertFalse(status["native_stop_verified"])
            self.assertFalse(status["lease_now_guaranteed_active"])
            self.assertTrue(has_pulsed.wait(1.0))
            return {"status": "finite_public_paper_research_closed",
                    "orders_sent": False}

        policy = ResidentPaperRunPolicy(
            DualPaperLeaseBudget(
                WSRunBudget(max_sessions=1, max_frames=200, max_seconds=3480),
                TickerLeaseBudget(max_sessions=1, max_frames=200, max_seconds=3480),
            ), restart_pause_seconds=0, max_cycles=1,
        )
        with patch.object(operator, "_HEARTBEAT_INTERVAL_SECONDS", 0.005), patch.object(
            operator, "_atomic_private_write", side_effect=record_write,
        ):
            result = run_resident_paper_observer(
                private_j2_directory=self.j2,
                private_paper_directory=self.paper,
                config=SETTINGS, policy=policy,
                primary_lease=primary,
                held_fallback_lease=lambda: self.fail("unexpected fallback"),
                sleep=lambda _: None, clock_ms=lambda: fixed_ms,
                should_stop=lambda: False, **self.flags,
            )
        self.assertEqual(result["status"], "bounded_run_completed")
        self.assertEqual(result["primary_leases_completed"], 1)
        self.assertGreaterEqual(len(updates), 2)
        self.assertTrue(all(
            v["stale_after_ms"]-v["updated_at_ms"] == 45_000
            for v in updates
        ))
        terminal = json.loads(
            (self.paper / "paper-operator-state-d453.json").read_text()
        )
        self.assertEqual(terminal["state"], "bounded_run_completed")
        self.assertLessEqual(
            terminal["stale_after_ms"]-terminal["updated_at_ms"], 375_000,
        )
        self.assertFalse(terminal["position_monitoring_guaranteed"])
        # The worker was joined; no trailing pulse may erase terminal state.
        self.assertEqual(
            read_resident_paper_status(
                directory=self.paper, now_ms=fixed_ms,
            )["status"], "bounded_run_completed",
        )

    def test_unexpected_primary_exception_still_uses_held_fallback(self):
        seen = []
        def primary():
            raise KeyError("do not echo private program state")
        def fallback():
            seen.append("held")
            return {"status": "no_held_paper_positions", "orders_sent": False}
        outcome = run_resident_paper_observer(
            private_j2_directory=self.j2,
            private_paper_directory=self.paper,
            config=SETTINGS,
            policy=ResidentPaperRunPolicy(self.budget, 0, 1),
            primary_lease=primary, held_fallback_lease=fallback,
            sleep=lambda _: None,
            clock_ms=lambda: 1_800_000_000_000,
            should_stop=lambda: False,
            **self.flags,
        )
        self.assertEqual(outcome["status"], "bounded_run_completed")
        self.assertEqual(outcome["held_only_fallbacks"], 1)
        self.assertEqual(seen, ["held"])
        self.assertFalse(outcome["orders_sent"])

    def test_failing_held_fallback_persists_terminal_degraded_status(self):
        def primary():
            raise OSError("REST temporarily inaccessible")
        def held():
            raise DataValidationError("unsafe owner manifest")
        outcome = run_resident_paper_observer(
            private_j2_directory=self.j2,
            private_paper_directory=self.paper,
            config=SETTINGS,
            policy=ResidentPaperRunPolicy(self.budget, 0, 2),
            primary_lease=primary, held_fallback_lease=held,
            sleep=lambda _: None,
            clock_ms=lambda: 1_800_000_000_000,
            should_stop=lambda: False,
            **self.flags,
        )
        self.assertEqual(outcome["status"], "degraded_no_held_coverage")
        self.assertEqual(outcome["cycles_attempted"], 1)
        recorded = json.loads(
            (self.paper / "paper-operator-state-d453.json").read_text(),
        )
        self.assertEqual(recorded["state"], "degraded_no_held_coverage")
        self.assertFalse(recorded["position_monitoring_guaranteed"])
        self.assertNotIn("unsafe owner manifest", json.dumps(recorded))

    def test_long_primary_lease_clamps_held_fallback_budget_to_180_seconds(self):
        # Reproduce the actual D458 3480s failure: a primary 3600s budget
        # must not be passed unchanged to D453's <=180s fallback contract.
        long_policy = ResidentPaperRunPolicy(
            DualPaperLeaseBudget(
                WSRunBudget(max_sessions=1, max_frames=200, max_seconds=3480),
                TickerLeaseBudget(max_sessions=1, max_frames=200, max_seconds=3480),
            ),
            restart_pause_seconds=0, max_cycles=1,
        )
        primary = {
            "status": "finite_public_paper_research_degraded",
            "orders_sent": False,
            "dual_public_streams": {
                "kline_lease_status": "ws_fail_closed_abstain",
                "ticker_lease_status": "lease_completed",
                "kline_acks": 1, "ticker_acks": 1,
                "accepted_closed_callbacks": 0,
                "accepted_public_ticker_callbacks": 3390,
            },
        }
        module = "crypto_intelligence_agent.j2_j4_resident_paper_operator_d453."
        with patch(module + "run_dynamic_public_paper_lease_once",
                   return_value=primary), patch(
                   module + "run_held_paper_without_n50",
                   return_value={"status": "no_held_paper_positions",
                                 "orders_sent": False}) as held:
            outcome = run_resident_paper_observer(
                private_j2_directory=self.j2,
                private_paper_directory=self.paper,
                config=SETTINGS, policy=long_policy, **self.flags,
            )
        self.assertEqual(outcome["status"], "bounded_run_completed")
        self.assertEqual(outcome["held_only_fallbacks"], 1)
        self.assertEqual(held.call_args.kwargs["budget"].max_seconds, 180)
        diagnostic = json.loads(
            (self.paper / "paper-last-public-lease-d459.json").read_text()
        )
        self.assertEqual(diagnostic["kline_lease_status"],
                         "ws_fail_closed_abstain")
        self.assertEqual(diagnostic["ticker_lease_status"],
                         "lease_completed")
        self.assertEqual(diagnostic["accepted_public_ticker_callbacks"], 3390)
        self.assertFalse(diagnostic["real_orders_sent"])

    def test_d469_records_ticker_abstention_and_causal_cohort_without_untrusted_text(self):
        # D466 proved 50 closes but was degraded: the ticker reason must be
        # reported separately from kline's 50/50 success and PAPER health.
        primary = {
            "status": "finite_public_paper_research_degraded",
            "orders_sent": False,
            "historical_rest_validated_closed_candles": 1200,
            "dual_public_streams": {
                "kline_lease_status": "ws_budget_ended_research_only",
                "ticker_lease_status": "lease_abstained",
                "kline_acks": 1, "ticker_acks": 1,
                "accepted_closed_callbacks": 50,
                "kline_confirmed_events_appended": 50,
                "accepted_public_ticker_callbacks": 51045,
                "ticker_failure_category": "reconnect_budget_exhausted",
                "ticker_frames_seen": 51234,
                "ticker_sessions_attempted": 1,
                "ticker_reconnects": 0,
                "paper_cycle": {
                    "research_cohort_contracts": 50,
                    "research_cohort_complete": True,
                    "eligible_relative_btc_hypotheses": 2,
                    "pending_paper_open_count": 0,
                    "event_counts": {"cohort_researched": 1},
                },
            },
        }
        def run(given):
            return run_resident_paper_observer(
                private_j2_directory=self.j2,
                private_paper_directory=self.paper,
                config=SETTINGS,
                policy=ResidentPaperRunPolicy(self.budget, 0, 1),
                primary_lease=lambda: given,
                held_fallback_lease=lambda: {
                    "status": "no_held_paper_positions", "orders_sent": False,
                },
                sleep=lambda _: None, clock_ms=lambda: 1_800_000_000_000,
                should_stop=lambda: False, **self.flags,
            )
        outcome = run(primary)
        self.assertEqual(outcome["status"], "bounded_run_completed")
        self.assertEqual(outcome["primary_leases_completed"], 0)
        self.assertEqual(outcome["held_only_fallbacks"], 1)
        diagnostic_path = self.paper / "paper-last-public-lease-d459.json"
        report = json.loads(diagnostic_path.read_text())
        self.assertEqual(report["kline_confirmed_events_appended"], 50)
        self.assertEqual(report["accepted_confirmed_close_callbacks"], 50)
        self.assertEqual(report["historical_rest_validated_closed_candles"], 1200)
        self.assertEqual(report["ticker_lease_status"], "lease_abstained")
        self.assertEqual(report["ticker_failure_category"], "reconnect_budget_exhausted")
        self.assertEqual(report["ticker_frames_seen"], 51234)
        self.assertEqual(report["ticker_sessions_attempted"], 1)
        self.assertEqual(report["ticker_reconnects"], 0)
        self.assertEqual(report["paper_research_cohort_contracts"], 50)
        self.assertIs(report["paper_research_cohort_complete"], True)
        self.assertEqual(report["paper_relative_btc_hypotheses"], 2)
        self.assertEqual(report["paper_pending_open_count"], 0)
        self.assertEqual(report["paper_cohort_researched_count"], 1)
        self.assertFalse(report["real_orders_sent"])
        self.assertEqual(diagnostic_path.stat().st_mode & 0o777, 0o600)
        malicious = {
            **primary, "dual_public_streams": {
                **primary["dual_public_streams"],
                "ticker_failure_category": "PRIVATE_OR_SECRET_VENUE_PAYLOAD",
                "paper_cycle": {
                    **primary["dual_public_streams"]["paper_cycle"],
                    "event_counts": {"cohort_researched": "PRIVATE_EVENT"},
                },
            },
        }
        run(malicious)
        raw = diagnostic_path.read_text()
        self.assertNotIn("PRIVATE_OR_SECRET", raw)
        self.assertNotIn("PRIVATE_EVENT", raw)
        safe = json.loads(raw)
        self.assertEqual(safe["ticker_failure_category"], "none_or_unknown")
        self.assertIsNone(safe["paper_cohort_researched_count"])
        run({
            **primary, "dual_public_streams": {
                **primary["dual_public_streams"],
                "ticker_failure_category": "paper_cycle_callback_failed",
            },
        })
        self.assertEqual(
            json.loads(diagnostic_path.read_text())["ticker_failure_category"],
            "paper_cycle_callback_failed",
        )

    def test_private_diagnostic_never_echoes_unknown_provider_error(self):
        def broken():
            raise RuntimeError("SECRET_PRIVATE_VENUE_DATA")
        outcome = run_resident_paper_observer(
            private_j2_directory=self.j2,
            private_paper_directory=self.paper,
            config=SETTINGS,
            policy=ResidentPaperRunPolicy(self.budget, 0, 1),
            primary_lease=broken,
            held_fallback_lease=lambda: {
                "status": "no_held_paper_positions", "orders_sent": False,
            },
            sleep=lambda _: None,
            clock_ms=lambda: 1_800_000_000_000,
            should_stop=lambda: False,
            **self.flags,
        )
        self.assertEqual(outcome["status"], "bounded_run_completed")
        raw = (self.paper / "paper-last-public-lease-d459.json").read_text()
        self.assertNotIn("SECRET_PRIVATE_VENUE_DATA", raw)
        self.assertEqual(json.loads(raw)["primary_result"], "raised_exception")
        self.assertEqual((self.paper / "paper-last-public-lease-d459.json").stat().st_mode & 0o777, 0o600)

    def test_second_owner_instance_cannot_grab_resident_lock(self):
        lock = _resident_lock(self.paper)
        try:
            with self.assertRaises(BlockingIOError):
                _resident_lock(self.paper)
        finally:
            os.close(lock)

    def test_gate_denied_before_any_folders_or_network(self):
        called = []
        report = run_resident_paper_observer(
            private_j2_directory=self.j2, private_paper_directory=self.paper,
            config=SETTINGS,
            policy=ResidentPaperRunPolicy(self.budget, 0, 2),
            primary_lease=lambda: called.append("primary"),
        )
        self.assertEqual(report["status"], "six_explicit_paper_public_data_optins_required")
        self.assertEqual(called, [])
        self.assertFalse((self.paper / "paper-operator-state-d453.json").exists())

    def test_held_only_uses_existing_position_when_rest_n50_unavailable(self):
        args = inputs()
        original = args["quote"]
        orders = SQLitePaperOrderJournal(self.paper / "paper-orders.sqlite")
        positions = SQLitePaperPositionJournal(self.paper / "paper-positions.sqlite")
        (self.paper / "paper-orders.sqlite").chmod(0o600)
        (self.paper / "paper-positions.sqlite").chmod(0o600)
        intent = reserve_observed_paper_entry(
            **args, journal=orders,
            position_journal_path=self.paper / "paper-positions.sqlite",
        )
        self.assertEqual(intent.status, "paper_open_intent_reserved_only")
        arm_observed_paper_entry(
            private_paper_directory=self.paper, intent_id=intent.intent_id,
            policy=POLICY, allow_paper_entry_strategy=True,
        )
        fill_quote = replace(
            original,
            exchange_at_ms=args["now_ms"] + 400,
            received_at_ms=args["now_ms"] + 500,
            cross_sequence=original.cross_sequence + 1,
            bid_size=Decimal(20), ask_size=Decimal(20),
        )
        materialized = materialize_observed_paper_entry(
            private_paper_directory=self.paper, intent_id=intent.intent_id,
            quote=fill_quote, as_of_ms=fill_quote.received_at_ms,
            enable_hypothetical_open_fill=True,
        )
        self.assertEqual(materialized["status"],
                         "paper_position_routed_for_continuous_held_monitor")
        at = fill_quote.received_at_ms + 1200
        clock = Clock()
        clock.utc_ms = at - 500
        ticker = json.loads(market_quote(ts=at - 100, cs=22, mark="102.4"))
        ticker["topic"] = "tickers.BTCUSDT"
        ticker["data"]["symbol"] = "BTCUSDT"
        later = json.loads(market_quote(ts=at + 400, cs=23, mark="102.4"))
        later["topic"] = "tickers.BTCUSDT"
        later["data"]["symbol"] = "BTCUSDT"
        session = Session(clock, [
            (ack("cia-ticker-1"), at - 400),
            (json.dumps(ticker), at),
            # First quote only RESERVES the partial. This later quote may
            # record a simulated FILL under D394 liquidity/latency checks.
            (json.dumps(later), at + 500),
        ])
        with patch("socket.create_connection",
                   side_effect=AssertionError("D453 fallback never contacts network in test")):
            outcome = run_held_paper_without_n50(
                private_paper_directory=self.paper,
                budget=TickerLeaseBudget(max_sessions=1, max_frames=50, max_seconds=2),
                session_factory=lambda: session,
                clock_args={
                    "clock": clock.monotonic,
                    "wall_ms": clock.wall,
                    "sleeper": clock.sleeper,
                },
                **self.flags,
            )
        self.assertEqual(outcome["status"], "held_paper_lease_completed")
        self.assertEqual(outcome["data_mode"], "injected_offline_protocol_replay")
        self.assertEqual(outcome["ticker_acks"], 1)
        self.assertEqual(outcome["ticker_frames_accepted"], 2)
        self.assertEqual(outcome["held_contract_count"], 1)
        self.assertFalse(outcome["network_attempted"])
        self.assertFalse(outcome["orders_sent"])
        from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import load_private_paper_routes
        routes = load_private_paper_routes(self.paper)
        balance = positions.load(routes.monitored_position_ids[0])
        self.assertEqual(len(balance.exit_orders), 1)
        self.assertEqual(balance.exit_orders[0].tranche_step, 1)
        self.assertEqual(balance.filled_exit_units, Decimal("0.75"))
        self.assertEqual(balance.reserved_unfilled_units, 0)
        self.assertEqual(balance.confirmed_remaining_units, Decimal("1.75"))
        self.assertEqual(balance.exit_orders[0].snapshot.filled_total_units,
                         Decimal("0.75"))

    def test_fallback_symlink_manifest_is_fatal_not_silent(self):
        victim = self.home / "elsewhere.json"
        victim.write_text("{}")
        (self.paper / "paper-routes.json").symlink_to(victim)
        with self.assertRaises(DataValidationError):
            run_held_paper_without_n50(
                private_paper_directory=self.paper,
                budget=TickerLeaseBudget(1, 50, 2),
                **self.flags,
            )


if __name__ == "__main__":
    unittest.main()
