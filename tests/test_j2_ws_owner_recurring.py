"""J2 #663: offline owner-only timer candidate and one-tick idempotency."""
from __future__ import annotations

from io import StringIO
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from scripts import run_j2_ws_owner_recurring_once as tick
from scripts import render_j2_ws_prospective_timer_once as unit

END = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
NOW = END + 7 * 60_000 + 500
SHA = "a" * 40


def prepared_preflight() -> dict:
    from crypto_intelligence_agent.j2_ws_owner_preflight import _report
    report = _report("owner_preflight_ready_no_capture")
    report.update(
        owner_nonroot_posix_verified=True, owner_ledger_parent_dac_verified=True,
        os_ntp_sync_reported=True, capture_window_open=True,
        capture_eligible_now=True, owner_ws_50x24_readonly_replayed=True,
    )
    return report


def captured(status="owner_local_decision_captured_not_independent_attestation",
             candidates=0) -> dict:
    from crypto_intelligence_agent.j2_ws_prospective_ledger import _report
    value = _report(status)
    if status == "owner_local_decision_captured_not_independent_attestation":
        value.update(
            capture_records_created=1, candidates_captured=candidates,
            decision_closed_end_ms=END, owner_ws_sqlite_readonly_replayed=True,
            local_decision_record_consistency_verified=True,
        )
    return value


class OwnerTickTests(unittest.TestCase):
    def test_no_optins_no_owner_clock_source_or_capture(self):
        with patch.object(tick, "_owner_runtime", side_effect=AssertionError("owner")), \
             patch.object(tick, "preflight_owner_ws_decision_once",
                          side_effect=AssertionError("source")), \
             patch.object(tick, "capture_owner_ws_decision_once",
                          side_effect=AssertionError("capture")):
            result = tick.run_once()
        self.assertEqual(result["status"], "owner_scheduler_optins_required")
        self.assertFalse(result["decision_created_this_tick"])
        self.assertEqual(result["network_requests"], 0)
        self.assertFalse(result["orders_sent"])

    def _tick(self, *, now=NOW, next_now=None, ready=None, capture=None):
        if ready is None:
            ready = prepared_preflight()
        if capture is None:
            capture = captured()
        if next_now is None:
            next_now = now
        with patch.object(tick, "_owner_runtime", return_value=True), \
             patch.object(tick.time, "time_ns", side_effect=(
                 now * 1_000_000, next_now * 1_000_000
             )), \
             patch.object(tick, "preflight_owner_ws_decision_once",
                          return_value=ready) as probe, \
             patch.object(tick, "capture_owner_ws_decision_once",
                          return_value=capture) as writer:
            result = tick.run_once(
                allow_private_readonly_research=True,
                allow_private_ledger_write=True,
                confirm_dedicated_owner_tick=True,
            )
        return result, probe, writer

    def test_valid_capture_with_no_candidates_is_not_profit(self):
        result, probe, writer = self._tick()
        self.assertEqual(result["status"], "owner_new_decision_recorded_research_only")
        self.assertTrue(result["decision_created_this_tick"])
        self.assertEqual(result["decision_closed_end_ms"], END)
        self.assertEqual(result["candidates_captured"], 0)
        self.assertFalse(result["approved_for_signals"])
        self.assertFalse(result["live_trading_authorized"])
        probe.assert_called_once_with(allow_private_readonly_research=True)
        writer.assert_called_once_with(
            allow_private_readonly_research=True, allow_private_ledger_write=True
        )
        self.assertNotIn("BTCUSDT", json.dumps(result))

    def test_duplicate_is_idempotent_not_new_capture(self):
        result, probe, writer = self._tick(
            capture=captured("owner_decision_hour_already_recorded"))
        self.assertEqual(result["status"], "owner_hour_idempotent_no_new_record")
        self.assertFalse(result["decision_created_this_tick"])
        self.assertIsNone(result["decision_closed_end_ms"])
        writer.assert_called_once()

    def test_closed_scheduled_windows_do_not_read_source(self):
        for now in (END+6*60_000, END+13*60_000, END+59*60_000):
            with self.subTest(now=now):
                result, probe, writer = self._tick(now=now)
                self.assertEqual(result["status"], "outside_safe_utc_tick_window")
                probe.assert_not_called()
                writer.assert_not_called()

    def test_unready_clock_or_cohort_abstains_without_write(self):
        for ready in (
            dict(prepared_preflight(), capture_eligible_now=False),
            dict(prepared_preflight(), status="owner_ws_50x24_unavailable"),
            dict(prepared_preflight(), live_trading_authorized=True),
            dict(prepared_preflight(), systemd_modified=True),
            dict(prepared_preflight(), network_requests=1),
            dict(prepared_preflight(), owner_ledger_parent_dac_verified=False),
            dict(prepared_preflight(), database_mutation_statements=True),
        ):
            with self.subTest(ready=ready):
                result, _, writer = self._tick(ready=ready)
                self.assertEqual(result["status"], "owner_preflight_abstain")
                writer.assert_not_called()
        for next_now in (NOW-1, END+13*60_000, END+HOUR_MS+7*60_000):
            with self.subTest(next_now=next_now):
                result, _, writer = self._tick(next_now=next_now)
                self.assertEqual(result["status"], "owner_tick_clock_or_epoch_shift_abstain")
                writer.assert_not_called()

    def test_malformed_capture_rejected_fail_closed(self):
        for bad in (
            dict(captured(), candidates_captured=11),
            dict(captured(), live_trading_authorized=True),
            dict(captured(), decision_closed_end_ms=END-HOUR_MS),
            dict(captured(), private_symbol="BTCUSDT"),
            dict(captured(), database_mutation_statements=True),
        ):
            with self.subTest(bad=bad):
                result, _, writer = self._tick(capture=bad)
                self.assertEqual(result["status"], "owner_capture_abstain")
                self.assertFalse(result["decision_created_this_tick"])
                writer.assert_called_once()

    def test_owner_refusal_before_preflight(self):
        with patch.object(tick, "_owner_runtime", return_value=False), \
             patch.object(tick, "preflight_owner_ws_decision_once",
                          side_effect=AssertionError("no owner read")):
            report = tick.run_once(
                allow_private_readonly_research=True,
                allow_private_ledger_write=True,
                confirm_dedicated_owner_tick=True,
            )
        self.assertEqual(report["status"], "owner_nonroot_posix_required")


class UnitCandidateTests(unittest.TestCase):
    def test_render_is_side_effect_free_and_pinned(self):
        service = unit.service_unit(SHA)
        timer = unit.timer_unit()
        for required in (
            "User=cia-probe", "Group=cia-probe", "Type=oneshot",
            "NoNewPrivileges=yes", "PrivateNetwork=yes",
            "ProtectSystem=strict", "ProtectHome=read-only",
            "ReadWritePaths=/home/cia-probe/agent/j2-ws-prospective-private",
            "TimeoutStartSec=180", "UMask=0077",
            "scripts.run_j2_ws_owner_recurring_once",
            SHA[:12],
        ):
            with self.subTest(required=required):
                self.assertIn(required, service)
        self.assertIn("OnCalendar=*-*-* *:07:00 UTC", timer)
        self.assertIn("Persistent=false", timer)
        self.assertNotIn("ExecStart=", timer)
        self.assertNotIn("systemctl", service+timer)
        self.assertNotIn("runuser", service+timer)
        self.assertNotIn("NetworkTarget", service+timer)
        for invalid in ("main", "a"*39, "a"*41, "A"*40, "a"*40+";id"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                unit.service_unit(invalid)

    def test_cli_emits_one_readonly_json_and_fails_without_flags(self):
        with patch.object(tick, "run_once", return_value=tick._empty(
            "owner_scheduler_optins_required")) as run, \
             patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(tick.main([]), 65)
        run.assert_called_once_with(
            allow_private_readonly_research=False,
            allow_private_ledger_write=False,
            confirm_dedicated_owner_tick=False,
        )
        self.assertEqual(json.loads(output.getvalue())["orders_sent"], False)


if __name__ == "__main__":
    unittest.main()
