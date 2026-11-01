"""J1/OPS1 monitoring: offline, owner-private, no code path for data writes."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.j1_ops_status import (
    PrivateJ1StatusError, observe_private_exit5,
)
from scripts.observe_private_j1_exit5 import main
from contextlib import redirect_stdout
from io import StringIO


@unittest.skipUnless(os.name == "posix", "0700/0600 private owner state requires POSIX")
class J1OPS1StatusTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.path.chmod(0o700)

    def put(self, name, value):
        p = self.path / name
        p.write_text(json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8")
        p.chmod(0o600)
        return p

    def progress(self, phase="waiting_for_next_closed_hour", gets=156, updates=1):
        return self.put("exit5-resume.log", {
            "event": "private_j1_resume_progress", "phase": phase,
            "network_gets_attempted": gets,
            "distinct_pit_updates_after_initial": updates,
            "marketwide_top50_verified": False,
        })

    def audit(self, **changes):
        data = {
            "status": "private_bybit_progress_readonly_verified",
            "sqlite_integrity_passed": True,
            "private_page_replay_passed": True,
            "first_pit_720h_coverage": True,
            "sample_asset_count": 50,
            "latest_selected_asset_count": 50,
            "stored_closed_candle_rows": 36100,
            "immutable_pit_snapshots": 3,
            "consecutive_snapshots_at_end": 1,
            "min_hours_per_asset": 720,
            "network_requests": 0,
        }
        data.update(changes)
        return self.put("exit5-audit.json", data)

    def result(self, resume=0, audit=0):
        return self.put("exit5-result.json", {
            "resume_exit_code": resume, "audit_exit_code": audit,
        })

    def report(self):
        return observe_private_exit5(
            directory=self.path, allow_private_readonly_status=True,
        )

    def test_empty_status_never_claims_success(self):
        result = self.report()
        self.assertEqual(result["status"], "sem_resultado_final")
        self.assertFalse(result["audit_accepted"])
        self.assertFalse(result["worker_running_verified"])

    def test_progress_from_owner_run_reports_pending(self):
        self.progress()
        report = self.report()
        self.assertEqual(report["status"], "aguardando_proximo_fechamento_informado")
        self.assertEqual(report["pit_updates_reported"], 1)
        self.assertEqual(report["network_gets_reported"], 156)
        self.assertFalse(report["audit_accepted"])
        self.assertFalse(report["worker_running_verified"])
        self.assertFalse(report["marketwide_top50_verified"])

    def test_complete_three_pits_with_two_distinct_updates(self):
        self.progress(phase="hourly_pit_verified", gets=312, updates=2)
        p = self.path / "exit5-resume.log"
        with p.open("a") as f:
            f.write(json.dumps({"status": "private_j1_two_distinct_updates_verified_not_top50"}) + "\n")
        self.audit()
        self.result()
        report = self.report()
        self.assertEqual(report["status"], "concluido_amostra_revisada_auditada")
        self.assertEqual(report["immutable_pit_snapshots_audited"], 3)
        self.assertEqual(report["closed_candles_audited"], 36100)
        self.assertFalse(report["marketwide_top50_verified"])

    def test_four_pits_and_churn_can_still_pass(self):
        self.progress(phase="hourly_pit_verified", gets=320, updates=3)
        with (self.path / "exit5-resume.log").open("a") as f:
            f.write(json.dumps({"status": "private_j1_two_distinct_updates_verified_not_top50"}) + "\n")
        self.audit(sample_asset_count=51, stored_closed_candle_rows=37000,
                   immutable_pit_snapshots=4)
        self.result()
        self.assertEqual(self.report()["status"], "concluido_amostra_revisada_auditada")

    def test_final_failure_log_takes_priority_over_old_waiting_phase(self):
        p = self.progress()
        with p.open("a") as f:
            f.write(json.dumps({"status": "provider_rate_limit_no_retry",
                                "provider_ret_code": 10006}) + "\n")
        self.assertEqual(self.report()["status"], "worker_reportou_falha_sem_recibo")

    def test_final_success_log_without_receipt_never_passes(self):
        p = self.progress()
        with p.open("a") as f:
            f.write(json.dumps({"status": "private_j1_two_distinct_updates_verified_not_top50"}) + "\n")
        self.assertEqual(self.report()["status"], "worker_reportou_conclusao_sem_recibo")

    def test_missing_minimum_history_rejected(self):
        self.audit(min_hours_per_asset=719)
        self.assertFalse(self.report()["audit_accepted"])

    def test_nonconsecutive_updates_rejected(self):
        self.audit(consecutive_snapshots_at_end=0)
        self.assertFalse(self.report()["audit_accepted"])

    def test_no_success_without_worker_success_record(self):
        self.progress(phase="hourly_pit_verified", updates=2)
        self.audit()
        self.result()
        self.assertEqual(self.report()["status"], "resultado_inconsistente_sem_aceite")

    def test_no_success_with_failed_exit_even_if_audit_green(self):
        self.progress()
        self.audit()
        self.result(resume=1)
        self.assertEqual(self.report()["status"], "falha_registrada_pelo_worker")

    def test_no_success_without_audit(self):
        self.progress()
        self.result()
        self.assertEqual(self.report()["status"], "resultado_inconsistente_sem_aceite")

    def test_no_success_with_missing_receipt(self):
        self.progress()
        self.audit()
        self.assertEqual(self.report()["status"], "auditoria_sem_recibo_final_sem_aceite")

    def test_incomplete_2_pits_rejected(self):
        self.progress()
        with (self.path / "exit5-resume.log").open("a") as f:
            f.write(json.dumps({"status": "private_j1_two_distinct_updates_verified_not_top50"}) + "\n")
        self.audit(immutable_pit_snapshots=2)
        self.result()
        self.assertFalse(self.report()["audit_accepted"])

    def test_bad_integrity_rejected(self):
        self.audit(sqlite_integrity_passed=False)
        self.assertFalse(self.report()["audit_accepted"])

    def test_no_optin(self):
        with self.assertRaises(PrivateJ1StatusError):
            observe_private_exit5(directory=self.path)

    def test_relative_path_rejected(self):
        with self.assertRaises(PrivateJ1StatusError):
            observe_private_exit5(directory=".", allow_private_readonly_status=True)

    def test_permissive_directory_rejected(self):
        self.path.chmod(0o755)
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_log_symlink_rejected(self):
        original = self.put("other.log", {"foo": "bar"})
        (self.path / "exit5-resume.log").symlink_to(original)
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_log_world_readable_rejected(self):
        self.progress().chmod(0o644)
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_log_hardlink_rejected(self):
        p = self.progress()
        os.link(p, self.path / "second.log")
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_oversize_log_rejected(self):
        p = self.progress()
        p.write_bytes(b"X" * 1_048_577)
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_invalid_json_log_rejected(self):
        p = self.progress()
        p.write_text("{malformed}\n")
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_duplicate_json_keys_rejected(self):
        p = self.progress()
        p.write_text('{"event":"a","event":"b"}\n')
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_quota_event_cannot_leak_raw_provider_body(self):
        p = self.progress()
        with p.open("a") as f:
            f.write(json.dumps({"status": "provider_rate_limit_no_retry",
                                "provider_ret_code": 10006,
                                "secret": "SENSITIVE_VALUE",
                                "symbol": "BTCUSDT"}) + "\n")
        report = self.report()
        self.assertEqual(report["provider_ret_code_reported"], 10006)
        self.assertEqual(report["worker_final_status_reported"], "provider_rate_limit_no_retry")
        self.assertNotIn("SENSITIVE_VALUE", json.dumps(report))
        self.assertNotIn("BTCUSDT", json.dumps(report))

    def test_worker_counter_rewind_rejected(self):
        p = self.progress(gets=156)
        with p.open("a") as f:
            f.write(json.dumps({"event": "private_j1_resume_progress",
                                "phase": "hourly_pit_verified",
                                "network_gets_attempted": 100,
                                "distinct_pit_updates_after_initial": 2}) + "\n")
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_boolean_exit_is_invalid(self):
        self.put("exit5-result.json", {"resume_exit_code": True, "audit_exit_code": 0})
        with self.assertRaises(PrivateJ1StatusError):
            self.report()

    def test_cli_sanitized_output(self):
        self.progress()
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--directory", str(self.path), "--allow-private-readonly-status"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "aguardando_proximo_fechamento_informado")

    def test_cli_rejects_bad_privacy_without_echoing_path(self):
        self.path.chmod(0o755)
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--directory", str(self.path), "--allow-private-readonly-status"])
        self.assertEqual(code, 1)
        self.assertNotIn(str(self.path), output.getvalue())


if __name__ == "__main__":
    unittest.main()