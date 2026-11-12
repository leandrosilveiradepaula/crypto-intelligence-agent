"""D306 release gate: no systemd write without explicit owner and SHA proof."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts import release_j1_n50_halt_recovery_once as mod

T=1_800_000_000_000//3_600_000*3_600_000
SHA="a"*40
SOURCE=Path("/home/cia-probe/agent/test-git-owner-worktree")


def plan():
    return {
        "old_halt_verified":True,
        "n2_last_published_end_ms":T,
        "n2_stored_candles":400,
    }


def state(unit: str):
    if unit==mod.N2_TIMER:
        return {"LoadState":"loaded","ActiveState":"active",
                "UnitFileState":"enabled"}
    if unit==mod.N2_SERVICE:
        return {"LoadState":"loaded","ActiveState":"inactive",
                "UnitFileState":"static"}
    if unit==mod.N50_TIMER:
        return {"LoadState":"loaded","ActiveState":"inactive",
                "UnitFileState":"disabled"}
    return {"LoadState":"loaded","ActiveState":"failed",
            "UnitFileState":"static"}


class N50RecoveryReleasePolicyTests(unittest.TestCase):
    def test_original_forensic_rejects_any_modified_counts_or_scope(self):
        good={
            "schema_version":"j1-n50-halted-owner-forensic-v1",
            "status":"halted_owner_review_verified",
            "halted_reason":"provider_denied_owner_review",
            "saved_rows_integrity_verified":True,
            "resume_authorized":False,
            "scope_digest_sha256":mod.ORIGINAL_SCOPE_DIGEST,
            "stored_candles":1306,
            "published_hours":3,
            "partial_contracts_at_next_hour":6,
            "historical_missing_publication_hours":0,
            "orders_sent":False,"network_requests":0,
            "database_mutation_statements":0,"systemd_modified":False,
        }
        self.assertTrue(mod._valid_old_forensic(good))
        for key,value in (
            ("stored_candles",1307),
            ("partial_contracts_at_next_hour",7),
            ("scope_digest_sha256","0"*64),
            ("resume_authorized",True),
            ("status","blocked"),
            ("historical_missing_publication_hours",1),
            ("network_requests",1),
        ):
            with self.subTest(key=key):
                altered=dict(good)
                altered[key]=value
                self.assertFalse(mod._valid_old_forensic(altered))

    def test_preflight_without_two_release_flags_never_modifies_systemd(self):
        with patch.object(mod,"preflight",return_value=plan()), patch.object(
            mod,"_call",side_effect=AssertionError("no systemctl")), patch.object(
            mod,"_owner_report",side_effect=AssertionError("no GET")):
            for confirm,modify in ((False,False),(True,False),(False,True)):
                out=mod.execute(source=SOURCE,expected_sha=SHA,
                                confirm_recovery_cutover=confirm,
                                allow_systemd_modifications=modify)
                self.assertEqual(out["status"],"preflight_pass_no_changes",out)
                self.assertFalse(out["systemd_modified"])
                self.assertFalse(out["new_epoch_started"])

    def test_outside_early_window_never_disables_n2(self):
        with patch.object(mod,"preflight",return_value=plan()), patch.object(
            mod.time,"time_ns",return_value=(T+17*60_000)*1_000_000), patch.object(
            mod,"_call",side_effect=AssertionError("cannot change timer")):
            out=mod.execute(source=SOURCE,expected_sha=SHA,
                            confirm_recovery_cutover=True,
                            allow_systemd_modifications=True)
        self.assertEqual(out["status"],"early_utc_close_window_required")
        self.assertFalse(out["systemd_modified"])

    def test_success_isolated_new_epoch_enables_n50_only(self):
        commands=[]
        def call(argv,*,timeout=20):
            commands.append(argv)
            return ""
        def switched_state(unit):
            if unit==mod.N2_TIMER:
                if any("disable" in x for x in commands):
                    return {"LoadState":"loaded","ActiveState":"inactive",
                            "UnitFileState":"disabled"}
                return state(unit)
            if unit==mod.N50_TIMER:
                if any("enable" in x for x in commands):
                    return {"LoadState":"loaded","ActiveState":"active",
                            "UnitFileState":"enabled"}
                return state(unit)
            return state(unit)
        result={
            "status":"new_epoch_sealed_old_halt_preserved",
            "requests_attempted":372,
            "old_epoch_preserved":True,
            "old_journal_sha256_unchanged":True,
            "old_scope_sha256_unchanged":True,
            "new_scope_created":True,
            "orders_sent":False,
        }
        with patch.object(mod,"preflight",return_value=plan()), patch.object(
             mod.time,"time_ns",return_value=(T+80_000)*1_000_000), patch.object(
             mod,"_state",side_effect=switched_state), patch.object(
             mod,"_call",side_effect=call), patch.object(
             mod,"_owner_report",return_value=result), patch.object(
             mod,"n50_systemd_n2_quiescence",
             return_value={"status":"n2_quiesced_preflight_only"}):
            out=mod.execute(source=SOURCE,expected_sha=SHA,
                            confirm_recovery_cutover=True,
                            allow_systemd_modifications=True)
        self.assertEqual(out["status"],"new_n50_epoch_timer_enabled",out)
        self.assertEqual(out["network_requests"],372)
        self.assertTrue(out["n50_timer_enabled"])
        self.assertFalse(out["orders_sent"])
        self.assertEqual(commands[0][-2:],
                         ["--now",mod.N2_TIMER])
        self.assertEqual(commands[-1][-2:],
                         ["--now",mod.N50_TIMER])

    def test_capture_failure_restores_n2_without_false_n50_status(self):
        calls=[]
        def call(argv,*,timeout=20):
            calls.append(argv)
            return ""
        fallback={"status":"blocked","requests_attempted":7,
                  "failure_category":"provider_rate_limit_no_retry",
                  "orders_sent":False}
        with patch.object(mod,"preflight",return_value=plan()), patch.object(
             mod.time,"time_ns",return_value=(T+80_000)*1_000_000), patch.object(
             mod,"_state",side_effect=state), patch.object(
             mod,"_call",side_effect=call), patch.object(
             mod,"_owner_report",return_value=fallback), patch.object(
             mod,"n50_systemd_n2_quiescence",
             return_value={"status":"n2_quiesced_preflight_only"}), patch.object(
             mod,"_return_to_n2",return_value=True) as restore:
            out=mod.execute(source=SOURCE,expected_sha=SHA,
                            confirm_recovery_cutover=True,
                            allow_systemd_modifications=True)
        self.assertEqual(out["status"],"rolled_back_to_n2",out)
        self.assertEqual(out["network_requests"],7)
        self.assertEqual(out["failure_category"],"provider_rate_limit_no_retry")
        self.assertFalse(out["n50_timer_enabled"])
        self.assertFalse(out["new_epoch_started"])
        self.assertTrue(out["n2_restored_after_failure"])
        restore.assert_called_once()

    def test_no_n2_isolation_never_runs_owner_capture(self):
        with patch.object(mod,"preflight",return_value=plan()), patch.object(
             mod.time,"time_ns",return_value=(T+80_000)*1_000_000), patch.object(
             mod,"_state",side_effect=state), patch.object(
             mod,"_call",return_value=""), patch.object(
             mod,"n50_systemd_n2_quiescence",
             return_value={"status":"blocked"}), patch.object(
             mod,"_owner_report",side_effect=AssertionError("no owner GET")), patch.object(
             mod,"_return_to_n2",return_value=True):
            out=mod.execute(source=SOURCE,expected_sha=SHA,
                            confirm_recovery_cutover=True,
                            allow_systemd_modifications=True)
        self.assertEqual(out["status"],"rolled_back_to_n2")
        self.assertFalse(out["new_epoch_started"])


if __name__=="__main__":
    unittest.main()
