"""D309: closed 24h evidence gate, fake systemd and owner audit only.

No VPS, provider, network, service modification or financial execution.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import HOUR_MS
from crypto_intelligence_agent.j1_n50_24h_witness import (
    _SERVICE_FIELDS, _TIMER_FIELDS, _systemd_unit_snapshot,
    evaluate_n50_24h_witness, observe_n50_24h_witness,
)

END = 1_794_492_000_000
NOW = END + 120_000


def units():
    def unit(unit_id, *, timer=False, n50=False):
        state = {
            "Id": unit_id, "LoadState": "loaded",
            "ActiveState": "active" if timer and n50 else "inactive",
            "SubState": "waiting" if timer and n50 else "dead",
            "UnitFileState": ("enabled" if timer and n50 else
                              "disabled" if timer else "static"),
        }
        if not timer:
            state.update(Result="success", ExecMainStatus="0")
        return state
    return {
        "n50_timer": unit("cia-j1-n50-managed.timer",timer=True,n50=True),
        "n50_service": unit("cia-j1-n50-managed.service"),
        "n2_timer": unit("cia-j1-rest-hourly.timer",timer=True,n50=False),
        "n2_service": unit("cia-j1-rest-hourly.service"),
    }


def health(**overrides):
    result = {
        "schema_version": "j1-n50-managed-owner-health-v1",
        "status": "verified_epoch_history",
        "owner_integrity_verified": True,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "systemd_modified": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "active_epoch_id": "epoch-1794456000000",
        "epoch_count": 2, "audited_journals": 2,
        "stored_candles": 50*48,
        "published_checkpoints": 30,
        "unique_published_utc_hours": 30,
        "missing_hours_between_publications": 4,
        "latest_published_end_ms": END,
        "latest_published_age_hours": 0,
        "published_last_24_closed_hours": 24,
        "expected_last_24_closed_hours": 24,
    }
    result.update(overrides)
    return result


class WitnessTests(unittest.TestCase):
    def test_exact_24_hours_integral_and_historical_gaps_still_reported(self):
        original = health(status="verified_with_missing_pit")
        checks = units()
        out = evaluate_n50_24h_witness(original, checks, now_ms=NOW)
        self.assertEqual(out["status"], "closed_24h_pit_evidence_verified")
        self.assertTrue(out["closed_24h_pit_verified"])
        self.assertTrue(out["observed_owner_integrity"])
        self.assertTrue(out["n50_timer_active_enabled"])
        self.assertTrue(out["n2_timer_inactive_disabled"])
        self.assertEqual(out["historical_missing_pit_hours"], 4)
        self.assertEqual(out["latest_published_end_ms"], END)
        self.assertEqual(out["published_last_24_closed_hours"], 24)
        self.assertFalse(out["automatic_epoch_rotation_verified"])
        self.assertFalse(out["continuous_collector_verified"])
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertFalse(out["approved_for_signals"])
        self.assertFalse(out["approved_for_live_use"])
        self.assertFalse(out["orders_sent"])
        self.assertEqual(out["network_requests"], 0)
        self.assertEqual(out["database_mutation_statements"], 0)
        self.assertEqual(original, health(status="verified_with_missing_pit"))
        self.assertEqual(checks, units())
        self.assertNotIn("BTCUSDT", json.dumps(out))

    def test_23_hours_is_not_24_and_no_pit_is_created(self):
        for count in (0, 1, 23):
            with self.subTest(count=count):
                out = evaluate_n50_24h_witness(
                    health(published_last_24_closed_hours=count),
                    units(), now_ms=NOW,
                )
                self.assertEqual(out["status"], "accumulating_24_closed_hours")
                self.assertEqual(out["published_last_24_closed_hours"], count)
                self.assertFalse(out["closed_24h_pit_verified"])
                self.assertFalse(out["continuous_collector_verified"])

    def test_no_writer_and_partial_first_writer_remain_unverified(self):
        for status in (
            "awaiting_first_epoch", "awaiting_first_writer",
            "in_progress_unverified", "partial_first_writer",
            "capture_in_progress_unverified",
            "rotation_in_progress_unverified",
        ):
            with self.subTest(status=status):
                out = evaluate_n50_24h_witness(
                    {"status": status}, units(), now_ms=NOW
                )
                self.assertEqual(out["status"], "awaiting_verified_writer")
                self.assertFalse(out["observed_owner_integrity"])

    def test_failback_and_competing_timers_fail_closed(self):
        fallback = units()
        fallback["n50_timer"]["ActiveState"] = "inactive"
        fallback["n50_timer"]["SubState"] = "dead"
        fallback["n50_timer"]["UnitFileState"] = "disabled"
        fallback["n2_timer"]["ActiveState"] = "active"
        fallback["n2_timer"]["SubState"] = "waiting"
        fallback["n2_timer"]["UnitFileState"] = "enabled"
        out = evaluate_n50_24h_witness(health(), fallback, now_ms=NOW)
        self.assertEqual(out["status"], "failback_to_n2_observed")
        self.assertFalse(out["closed_24h_pit_verified"])
        simultaneous = units()
        simultaneous["n2_timer"]["ActiveState"] = "active"
        simultaneous["n2_timer"]["UnitFileState"] = "enabled"
        out = evaluate_n50_24h_witness(health(), simultaneous, now_ms=NOW)
        self.assertEqual(out["status"], "isolation_or_service_gate_not_ready")

    def test_service_failure_and_inflight_writer_do_not_certify(self):
        failed = units()
        failed["n50_service"]["Result"] = "exit-code"
        failed["n50_service"]["ExecMainStatus"] = "65"
        out = evaluate_n50_24h_witness(health(), failed, now_ms=NOW)
        self.assertEqual(out["status"], "isolation_or_service_gate_not_ready")
        working = units()
        working["n50_timer"]["SubState"] = "running"
        working["n50_service"]["ActiveState"] = "activating"
        working["n50_service"]["SubState"] = "start"
        out = evaluate_n50_24h_witness(health(), working, now_ms=NOW)
        self.assertFalse(out["closed_24h_pit_verified"])

    def test_missing_current_close_and_exact_first_minute(self):
        old = health(
            latest_published_end_ms=END-HOUR_MS,
            latest_published_age_hours=1,
        )
        self.assertEqual(
            evaluate_n50_24h_witness(old, units(), now_ms=NOW)["status"],
            "missing_or_stale_current_closed_hour",
        )
        early = health(
            latest_published_end_ms=END-HOUR_MS,
            latest_published_age_hours=1,
        )
        # During HH:00:00..HH:00:59 the expected last eligible PIT is t-1.
        ready = evaluate_n50_24h_witness(
            early, units(), now_ms=END+40_000
        )
        self.assertTrue(ready["closed_24h_pit_verified"], ready)
        at_boundary = evaluate_n50_24h_witness(
            early, units(), now_ms=END+60_000
        )
        self.assertEqual(
            at_boundary["status"], "missing_or_stale_current_closed_hour"
        )
        stale = health(status="stale_active_publication")
        self.assertFalse(
            evaluate_n50_24h_witness(stale, units(), now_ms=NOW)[
                "closed_24h_pit_verified"
            ]
        )

    def test_audit_integrity_tampering_refuses_any_verified_evidence(self):
        cases = [
            ("unexpected_schema", {"schema_version": "bad"}),
            ("missing_digest_gate", {"owner_integrity_verified": False}),
            ("wrong_last", {"latest_published_end_ms": END+HOUR_MS}),
            ("rollback", {"latest_published_end_ms": END-HOUR_MS}),
            ("fake_age", {"latest_published_age_hours": 7}),
            ("25_in_24", {"published_last_24_closed_hours": 25}),
            ("no_24_expected", {"expected_last_24_closed_hours": 23}),
            ("duplicate", {"unique_published_utc_hours": 29}),
            ("false_crypto", {"crypto_identity_independently_verified": True}),
            ("false_marketwide", {"marketwide_top50_verified": True}),
            ("false_continuity", {"continuous_collector_verified": True}),
            ("trading", {"live_trading_authorized": True}),
            ("orders", {"orders_sent": True}),
            ("network", {"network_requests": 1}),
            ("SQL_mutation", {"database_mutation_statements": 1}),
            ("systemd_mutation", {"systemd_modified": True}),
            ("negative_gaps", {"missing_hours_between_publications": -1}),
            ("weak_candles", {"stored_candles": 49}),
            ("missing_epoch", {"active_epoch_id": "../bad"}),
            ("bad_status", {"status": "fictional_pass"}),
            ("bool_count", {"published_last_24_closed_hours": True}),
            ("no_audited_journal", {"audited_journals": 0}),
        ]
        for name, overrides in cases:
            with self.subTest(name=name):
                out = evaluate_n50_24h_witness(
                    health(**overrides), units(), now_ms=NOW
                )
                self.assertFalse(out["closed_24h_pit_verified"])
                self.assertFalse(out["observed_owner_integrity"])
                self.assertFalse(out["orders_sent"])

    def test_systemd_untrusted_extra_missing_unknown_and_unit_substitution(self):
        samples = []
        extra = units()
        extra["n50_timer"]["arbitrary_path"] = "/etc/shadow"
        samples.append(extra)
        missing = units()
        del missing["n2_service"]["Id"]
        samples.append(missing)
        forged_id = units()
        forged_id["n50_timer"]["Id"] = "other.timer"
        samples.append(forged_id)
        value = units()
        value["n50_timer"]["UnitFileState"] = "SUPERHEALTHY"
        samples.append(value)
        fail_code = units()
        fail_code["n50_service"]["ExecMainStatus"] = "9999"
        samples.append(fail_code)
        for candidate in samples:
            with self.subTest(candidate=candidate):
                out = evaluate_n50_24h_witness(
                    health(), candidate, now_ms=NOW
                )
                self.assertEqual(out["status"], "evidence_rejected")
                self.assertFalse(out["closed_24h_pit_verified"])

    def test_systemctl_argv_fixed_bounded_and_no_payload(self):
        expected_name = "cia-j1-n50-managed.timer"
        fake_text = "".join(
            name + "=" + value + "\n"
            for name, value in units()["n50_timer"].items()
        )
        fake = SimpleNamespace(returncode=0, stdout=fake_text, stderr="")
        with patch(
            "crypto_intelligence_agent.j1_n50_24h_witness.subprocess.run",
            return_value=fake,
        ) as run:
            result = _systemd_unit_snapshot(expected_name, _TIMER_FIELDS)
        self.assertEqual(result, units()["n50_timer"])
        kwargs = run.call_args.kwargs
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["timeout"], 8)
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/systemctl")
        self.assertIn(expected_name, run.call_args.args[0])
        with self.assertRaises(ValueError):
            _systemd_unit_snapshot("/etc/passwd", _TIMER_FIELDS)
        with self.assertRaises(ValueError):
            _systemd_unit_snapshot(expected_name, _SERVICE_FIELDS)
        for payload in (
            fake_text + "Escape=secret\n",
            fake_text.replace("Id=", "Id=other.timer\nId=", 1),
            fake_text.replace("SubState=waiting\n", ""),
            fake_text + "password=abc\n",
        ):
            with patch(
                "crypto_intelligence_agent.j1_n50_24h_witness.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=0, stdout=payload, stderr=""
                ),
            ):
                with self.assertRaises(ValueError):
                    _systemd_unit_snapshot(expected_name, _TIMER_FIELDS)

    def test_owner_one_shot_optins_do_not_query_auditor_without_flags(self):
        with patch(
            "crypto_intelligence_agent.j1_n50_24h_witness.audit_managed_n50_epochs",
            side_effect=AssertionError("no private I/O"),
        ):
            self.assertEqual(
                observe_n50_24h_witness()["status"], "owner_optin_required"
            )
        self.assertEqual(
            observe_n50_24h_witness(
                allow_private_readonly_audit=True,
                enable_closed24h_witness=True,
                owner_ok=False,
            )["status"], "owner_environment_abstain"
        )

    def test_one_shot_owner_audit_and_fixed_systemd_no_writes(self):
        with patch(
            "crypto_intelligence_agent.j1_n50_24h_witness.audit_managed_n50_epochs",
            return_value=health(),
        ) as auditor, patch(
            "crypto_intelligence_agent.j1_n50_24h_witness._systemd_snapshot",
            return_value=units(),
        ) as systemd:
            out = observe_n50_24h_witness(
                root_directory=Path.cwd(),
                owner_ok=True, now_ms=NOW,
                allow_private_readonly_audit=True,
                enable_closed24h_witness=True,
            )
        self.assertTrue(out["closed_24h_pit_verified"])
        self.assertEqual(auditor.call_count, 1)
        self.assertEqual(auditor.call_args.kwargs["now_ms"], NOW)
        self.assertIs(auditor.call_args.kwargs["owner_ok"], True)
        self.assertEqual(systemd.call_count, 1)
        self.assertEqual(out["database_mutation_statements"], 0)
        self.assertFalse(out["systemd_modified"])


if __name__ == "__main__":
    unittest.main()
