"""D323: adverse read-only WS continuity and N2 fallback cases."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import OfflineStreamAudit, HOUR_MS
from crypto_intelligence_agent import j1_n50_ws_24h_witness as w
from scripts.audit_j1_n50_ws_24h_once import main as cli_main

NOW = 1_794_492_000_000 + 600_000
SHA = "a" * 64


def units():
    return {
        "ws_timer": {"LoadState": "loaded", "ActiveState": "active", "UnitFileState": "enabled"},
        "ws_service": {"LoadState": "loaded", "ActiveState": "inactive", "UnitFileState": "static"},
        "rotation_timer": {"LoadState": "loaded", "ActiveState": "active", "UnitFileState": "enabled"},
        "n2_timer": {"LoadState": "loaded", "ActiveState": "inactive", "UnitFileState": "disabled"},
        "old_n50_timer": {"LoadState": "loaded", "ActiveState": "inactive", "UnitFileState": "disabled"},
    }


def audit(complete=50, *, hour=50, rows=1200):
    return OfflineStreamAudit(
        status=("offline_reviewed_24h_complete_not_top50" if complete == 50 else
                "offline_closed_stream_incomplete_abstain"),
        persisted_rows=rows, observed_symbols=50,
        journal_digest_sha256=SHA, missing_24h_symbols=50-complete,
        complete_24h_symbols=complete,
        rank_digest_sha256=SHA if complete==50 else None,
        hour_evidence_expected=50, hour_evidence_confirmed=hour,
        hour_evidence_sha256=SHA if hour==50 else None,
    )


def evaluate(report, group=None, now=NOW):
    return w.evaluate_n50_ws_24h(
        report, units() if group is None else group, now_ms=now,
        ranked_scope_sha256=SHA, ws_metadata_sha256=SHA,
    )


class WS24hWitnessTests(unittest.TestCase):
    def test_local_24h_requires_all_fifty_but_not_live_claims(self):
        result=evaluate(audit())
        self.assertEqual(result["status"],"ws_24h_local_evidence_verified")
        self.assertEqual(result["verified_closed_hours"],24)
        self.assertEqual(result["verified_contracts_per_hour"],50)
        self.assertEqual(result["persisted_ws_rows"],1200)
        self.assertTrue(result["ws_closed_24h_local_verified"])
        for key in ("rotation_36h_live_verified","continuous_collector_verified",
                    "marketwide_top50_verified","crypto_identity_independently_verified",
                    "source_authenticated","approved_for_signals",
                    "live_trading_authorized","orders_sent","systemd_modified"):
            self.assertFalse(result[key])
        self.assertEqual(result["network_requests"],0)
        self.assertEqual(result["database_mutation_statements"],0)
        self.assertNotIn("BTCUSDT",str(result))

    def test_49_or_23_hours_never_certify_24h(self):
        for evidence in (audit(49,rows=1199),audit(50,hour=49),
                         audit(50,rows=1199)):
            with self.subTest(complete=evidence.complete_24h_symbols):
                result=evaluate(evidence)
                self.assertEqual(result["status"],"accumulating_or_incomplete_ws_24h")
                self.assertFalse(result["ws_closed_24h_local_verified"])

    def test_failure_and_n2_failback_block_a_perfect_journal(self):
        old=units()
        old["ws_timer"]["ActiveState"]="inactive"
        old["n2_timer"]["ActiveState"]="active"
        old["n2_timer"]["UnitFileState"]="enabled"
        self.assertEqual(evaluate(audit(),old)["status"],"n2_failback_observed")
        failed=units()
        failed["ws_service"]["ActiveState"]="failed"
        self.assertEqual(evaluate(audit(),failed)["status"],
                         "ws_systemd_isolation_or_service_not_ready")
        broken=units()
        broken["rotation_timer"]["ActiveState"]="inactive"
        self.assertFalse(evaluate(audit(),broken)["ws_closed_24h_local_verified"])

    def test_time_types_tamper_and_unsafe_systemd_are_rejected(self):
        self.assertEqual(evaluate(audit(),now=NOW-600_000)["status"],
                         "awaiting_safe_closed_hour_audit_window")
        self.assertEqual(evaluate(audit(),now=NOW//HOUR_MS*HOUR_MS+3_590_000)["status"],
                         "awaiting_safe_closed_hour_audit_window")
        self.assertEqual(w.evaluate_n50_ws_24h(audit(),units(),now_ms=True)["status"],
                         "invalid_or_untrusted_witness_input")
        self.assertEqual(evaluate({"fake":"report"})["status"],
                         "owner_ws_journal_integrity_abstain")
        fake=units()
        fake["n2_timer"]["ActiveState"]="unknown!"
        self.assertEqual(evaluate(audit(),fake)["status"],
                         "invalid_or_untrusted_witness_input")
        self.assertEqual(evaluate(None)["status"],"awaiting_owner_ws_journal_audit")

    def test_bad_digest_or_inconsistent_complete_counts_cannot_pass(self):
        report=audit()
        object.__setattr__(report,"journal_digest_sha256","-"*64)
        self.assertEqual(evaluate(report)["status"],"owner_ws_journal_integrity_abstain")
        self.assertEqual(w.evaluate_n50_ws_24h(
            audit(),units(),now_ms=NOW,ranked_scope_sha256="0"*63,
            ws_metadata_sha256=SHA)["status"],"owner_ws_journal_integrity_abstain")

    def test_owner_gate_prevents_all_io_without_both_flags(self):
        with patch.object(w,"_systemd_state",side_effect=AssertionError("unapproved")), \
             patch.object(w,"load_active_n50_ws_epoch",side_effect=AssertionError("unapproved")):
            self.assertEqual(w.observe_n50_ws_24h()["status"],"owner_optin_required")
            self.assertEqual(w.observe_n50_ws_24h(
                enable_ws_24h_witness=True)["status"],"owner_optin_required")
            with patch.object(w.os,"geteuid",return_value=0):
                self.assertEqual(w.observe_n50_ws_24h(
                    enable_ws_24h_witness=True,allow_private_readonly_audit=True
                )["status"],"owner_environment_abstain")
            self.assertEqual(w.observe_n50_ws_24h(
                enable_ws_24h_witness=True,allow_private_readonly_audit=True,
                state_directory=Path("/tmp/unapproved")
            )["status"],"owner_environment_abstain")

    def test_readonly_owner_abstains_cleanly_if_pointer_unavailable(self):
        with patch.object(w.os,"getuid",return_value=1234), \
             patch.object(w.os,"geteuid",return_value=1234), \
             patch.object(w,"_systemd_state",return_value=units()) as show, \
             patch.object(w,"load_active_n50_ws_epoch",side_effect=OSError("unavailable")):
            result=w.observe_n50_ws_24h(
                enable_ws_24h_witness=True,allow_private_readonly_audit=True,
                now_ms=NOW,
            )
        self.assertEqual(result["status"],"owner_ws_readonly_audit_abstain")
        show.assert_called_once()

    def test_cli_default_is_inert(self):
        with patch("scripts.audit_j1_n50_ws_24h_once.observe_n50_ws_24h") as call:
            call.return_value=w._result("owner_optin_required")
            self.assertEqual(cli_main([]),65)
            self.assertEqual(call.call_args.kwargs, {
                "allow_private_readonly_audit":False,
                "enable_ws_24h_witness":False,
            })


if __name__=="__main__":
    unittest.main()
