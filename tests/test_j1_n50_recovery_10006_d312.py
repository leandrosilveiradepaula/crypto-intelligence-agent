"""D312: current N50 10006 HALT recovery is safely gated and reversible.

Pure mocks: never touches the real VPS, provider, SQLite or systemd.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import audit_j1_n50_recovery_candidate_once as owner
from scripts import release_j1_n50_recovery_10006_once as root


def forensic():
    return {
        "status": "halted_owner_review_verified",
        "halted_reason": "provider_denied_owner_review",
        "saved_rows_integrity_verified": True,
        "resume_authorized": False,
        "historical_missing_publication_hours": 0,
        "last_published_end_ms": 1794495600000,
        "published_hours": 1,
        "partial_contracts_at_next_hour": 3,
        "stored_candles": 1203,
        "scope_digest_sha256": "a"*64,
        "orders_sent": False, "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def candidate():
    return {
        "schema_version": "j1-n50-recovery-candidate-v1",
        "status": "current_halted_epoch_candidate_verified",
        "active_epoch_id": owner.EXPECTED_HALTED_EPOCH,
        "halted_reason": "provider_denied_owner_review",
        "owner_integrity_verified": True,
        "resume_authorized": False,
        "last_published_end_ms": 1794495600000,
        "published_hours": 1,
        "partial_contracts_at_next_hour": 3,
        "stored_candles": 1203,
        "scope_digest_sha256": "a"*64,
        "network_requests": 0, "database_mutation_statements": 0,
        "systemd_modified": False,
        "live_trading_authorized": False,
        "marketwide_top50_verified": False,
        "orders_sent": False,
    }


def gate():
    return {
        "current_halt_verified": True,
        "original_service": "pinned-original",
        "replacement_service": "pinned-new-version",
    }


def state(unit, *, cutover=False):
    if unit == root.N2_TIMER:
        return {"LoadState": "loaded",
                "ActiveState": "inactive" if cutover else "active",
                "UnitFileState": "disabled" if cutover else "enabled"}
    if unit == root.N50_TIMER:
        return {"LoadState": "loaded",
                "ActiveState": "active" if cutover else "inactive",
                "UnitFileState": "enabled" if cutover else "disabled"}
    return {"LoadState": "loaded", "ActiveState": "inactive",
            "UnitFileState": "static"}


class OwnerCandidateTests(unittest.TestCase):
    def test_unopted_or_wrong_epoch_never_enters_private_auditor(self):
        with patch.object(owner, "_pointer_read",
                          side_effect=AssertionError("private read forbidden")):
            self.assertEqual(owner.candidate()["status"], "optin_required")
            self.assertEqual(owner.candidate(
                allow_private_readonly_audit=True, expected_epoch_id="old",
            )["status"], "blocked")

    def test_current_10006_archive_is_verified_without_repair(self):
        with (
            patch.object(owner, "_strict_owner"),
            patch.object(owner, "_pointer_read",
                         return_value={"epoch_id": owner.EXPECTED_HALTED_EPOCH}),
            patch.object(owner, "audit_halted_n50_epoch",
                         return_value=forensic()) as audit,
        ):
            result = owner.candidate(allow_private_readonly_audit=True)
        self.assertEqual(result["status"],
                         "current_halted_epoch_candidate_verified")
        self.assertEqual((result["stored_candles"],
                          result["partial_contracts_at_next_hour"]), (1203, 3))
        self.assertTrue(result["owner_integrity_verified"])
        self.assertFalse(result["resume_authorized"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(result["network_requests"], 0)
        audit.assert_called_once()
        self.assertTrue(audit.call_args.kwargs["allow_private_readonly_audit"])

    def test_wrong_active_pointer_never_audits_archived_epoch(self):
        with (
            patch.object(owner, "_strict_owner"),
            patch.object(owner, "_pointer_read",
                         return_value={"epoch_id": "epoch-1794456000000"}),
            patch.object(owner, "audit_halted_n50_epoch",
                         side_effect=AssertionError("no archived audit")) as audit,
        ):
            result = owner.candidate(allow_private_readonly_audit=True)
        self.assertEqual(result["status"], "blocked")
        audit.assert_not_called()

    def test_bad_halt_or_corruption_denies_current_candidate(self):
        invalids = [
            ("halted_reason", "candle_or_storage_integrity"),
            ("saved_rows_integrity_verified", False),
            ("resume_authorized", True),
            ("historical_missing_publication_hours", 1),
            ("partial_contracts_at_next_hour", 0),
            ("partial_contracts_at_next_hour", 50),
            ("stored_candles", 1204),
            ("scope_digest_sha256", "b"*64),
            ("orders_sent", True),
            ("network_requests", 1),
            ("status", "blocked"),
        ]
        for key, bad in invalids:
            report = forensic()
            report[key] = bad
            with self.subTest(key=key, bad=bad), (
                patch.object(owner, "_strict_owner"),
                patch.object(owner, "_pointer_read", return_value={
                    "epoch_id":owner.EXPECTED_HALTED_EPOCH,
                    "scope_digest_sha256":"a"*64,
                }),
                patch.object(owner, "audit_halted_n50_epoch",
                             return_value=report),
            ):
                got = owner.candidate(allow_private_readonly_audit=True)
            self.assertEqual(got["status"], "blocked", (key, got))

    def test_existing_d304_accepts_legitimate_50_bar_first_pit_offset(self):
        f = forensic()
        f["stored_candles"] = 1253
        with (
            patch.object(owner, "_strict_owner"),
            patch.object(owner, "_pointer_read", return_value={
                "epoch_id":owner.EXPECTED_HALTED_EPOCH,
                "scope_digest_sha256":"a"*64,
            }),
            patch.object(owner, "audit_halted_n50_epoch", return_value=f),
        ):
            got = owner.candidate(allow_private_readonly_audit=True)
        self.assertEqual(got["status"],
                         "current_halted_epoch_candidate_verified")


class RootReleaseTests(unittest.TestCase):
    def test_forensic_contract_does_not_trust_just_success_or_three_candles(self):
        good = candidate()
        self.assertTrue(root._valid_candidate(good))
        for key, bad in (
            ("status", "blocked"), ("active_epoch_id", "epoch-1794456000000"),
            ("owner_integrity_verified", False), ("resume_authorized", True),
            ("stored_candles", 1204), ("published_hours", 0),
            ("partial_contracts_at_next_hour", 50),
            ("scope_digest_sha256", "not-sha"),
            ("marketwide_top50_verified", True),
            ("orders_sent", True), ("network_requests", 1),
        ):
            with self.subTest(key=key):
                fake = deepcopy(good)
                fake[key] = bad
                self.assertFalse(root._valid_candidate(fake))

    def test_preflight_is_default_and_cannot_modify_service(self):
        with (
            patch.object(root, "preflight", return_value=gate()) as pre,
            patch.object(root, "_call",
                         side_effect=AssertionError("no systemctl")),
            patch.object(root, "_owner_report",
                         side_effect=AssertionError("no GET")),
        ):
            for flags in ({}, {"confirm_recovery_cutover":True},
                          {"allow_systemd_modifications":True}):
                with self.subTest(flags=flags):
                    report = root.execute(
                        source=Path("/home/cia-probe/agent/d312-code"),
                        expected_sha="a"*40, **flags,
                    )
                    self.assertEqual(report["status"], "preflight_pass_no_changes")
                    self.assertFalse(report["systemd_modified"])
                    self.assertFalse(report["new_epoch_started"])
        self.assertEqual(pre.call_count, 3)

    def test_outside_early_utc_window_has_no_changes(self):
        with (
            patch.object(root, "preflight", return_value=gate()),
            patch.object(root.time, "time_ns", return_value=1_800_000_000_000*1_000_000),
            patch.object(root, "_call",
                         side_effect=AssertionError("must not systemctl")),
        ):
            report = root.execute(
                source=Path("/home/cia-probe/agent/d312-code"),
                expected_sha="a"*40,
                confirm_recovery_cutover=True, allow_systemd_modifications=True,
            )
        self.assertEqual(report["status"], "early_utc_close_window_required")
        self.assertFalse(report["systemd_modified"])

    def test_success_repoints_only_unit_and_activates_n50_after_new_epoch(self):
        begin = 1_800_000_000_000 // 3_600_000 * 3_600_000 + 70_000
        enabled = [False]
        calls = []
        def call(argv, *, timeout=20):
            calls.append(argv)
            if argv[1:3] == ["enable", "--now"] and argv[-1] == root.N50_TIMER:
                enabled[0] = True
            return ""
        def states(unit):
            return state(unit, cutover=enabled[0])
        proof = {
            "status":"new_epoch_sealed_old_halt_preserved",
            "old_epoch_preserved":True, "old_journal_sha256_unchanged":True,
            "old_scope_sha256_unchanged":True,"new_scope_created":True,
            "orders_sent":False, "requests_attempted":372,
        }
        with TemporaryDirectory() as d:
            target = Path(d) / root.N50_SERVICE
            target.write_text("pinned-original", encoding="ascii")
            with (
                patch.object(root, "UNIT_ROOT", Path(d)),
                patch.object(root, "preflight", return_value=gate()),
                patch.object(root.time, "time_ns", return_value=begin*1_000_000),
                patch.object(root, "_state", side_effect=states),
                patch.object(root, "n50_systemd_n2_quiescence",
                             return_value={"status":"n2_quiesced_preflight_only"}),
                patch.object(root, "_owner_report", return_value=proof) as owner_run,
                patch.object(root, "_atomic_service_replace",
                             side_effect=lambda text, **kw: target.write_text(text)),
                patch.object(root, "_call", side_effect=call),
            ):
                out = root.execute(
                    source=Path("/home/cia-probe/agent/d312-code"),
                    expected_sha="a"*40,
                    confirm_recovery_cutover=True, allow_systemd_modifications=True,
                )
        self.assertEqual(out["status"], "new_n50_epoch_timer_enabled", out)
        self.assertTrue(out["n50_timer_enabled"])
        self.assertTrue(out["current_halt_verified"])
        self.assertEqual(out["network_requests"], 372)
        self.assertEqual(owner_run.call_args.kwargs["module"],
                         "scripts.recover_j1_n50_halted_epoch_once")
        self.assertTrue(any("disable" in row for row in calls))
        self.assertTrue(any("enable" in row for row in calls))
        self.assertFalse(out["orders_sent"])

    def test_capture_failure_restores_n2_and_does_not_mark_n50_healthy(self):
        begin = 1_800_000_000_000 // 3_600_000 * 3_600_000 + 70_000
        with (
            patch.object(root, "preflight", return_value=gate()),
            patch.object(root.time, "time_ns", return_value=begin*1_000_000),
            patch.object(root, "_state",
                         side_effect=lambda unit: state(unit)),
            patch.object(root, "n50_systemd_n2_quiescence",
                         return_value={"status":"n2_quiesced_preflight_only"}),
            patch.object(root, "_owner_report", return_value={
                "status":"blocked",
                "failure_category":"provider_rate_limit_no_retry",
                "requests_attempted":4,
                "orders_sent":False,
            }),
            patch.object(root, "_return_to_n2", return_value=True) as backup,
            patch.object(root, "_call", return_value=""),
            patch.object(root, "_atomic_service_replace") as unit_write,
        ):
            result = root.execute(
                source=Path("/home/cia-probe/agent/d312-code"),
                expected_sha="a"*40,
                confirm_recovery_cutover=True, allow_systemd_modifications=True,
            )
        self.assertEqual(result["status"], "rolled_back_to_n2")
        self.assertEqual(result["failure_category"], "provider_rate_limit_no_retry")
        self.assertEqual(result["network_requests"], 4)
        self.assertFalse(result["new_epoch_started"])
        self.assertFalse(result["n50_timer_enabled"])
        backup.assert_called_once()
        unit_write.assert_not_called()

    def test_rollback_failed_is_critical_never_claims_n50_success(self):
        begin = 1_800_000_000_000 // 3_600_000 * 3_600_000 + 70_000
        with (
            patch.object(root, "preflight", return_value=gate()),
            patch.object(root.time, "time_ns", return_value=begin*1_000_000),
            patch.object(root, "_state", side_effect=lambda unit: state(unit)),
            patch.object(root, "n50_systemd_n2_quiescence",
                         return_value={"status":"blocked"}),
            patch.object(root, "_return_to_n2", return_value=False),
            patch.object(root, "_call", return_value=""),
        ):
            result = root.execute(
                source=Path("/home/cia-probe/agent/d312-code"),
                expected_sha="a"*40,
                confirm_recovery_cutover=True, allow_systemd_modifications=True,
            )
        self.assertEqual(result["status"], "CRITICAL_rollback_unverified")
        self.assertFalse(result["n50_timer_enabled"])
        self.assertFalse(result["orders_sent"])


if __name__ == "__main__":
    unittest.main()
