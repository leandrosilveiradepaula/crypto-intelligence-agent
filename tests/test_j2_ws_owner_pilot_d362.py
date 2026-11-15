"""D362 / #658: root pilot remains gated; test the public shell contract offline."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "vps" / "j2_ws_prospective_owner_pilot_d362_once.sh"
SHA = "a"*40


class OwnerPilotD362ContractTests(unittest.TestCase):
    def test_script_is_syntactically_valid(self):
        self.assertTrue(SCRIPT.is_file())
        if os.name != "posix" or shutil.which("bash") is None:
            self.skipTest("bash is unavailable on this runner")
        done = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_narrow_modes_and_guards_are_present(self):
        data = SCRIPT.read_text(encoding="utf-8")
        for needle in (
            "--preflight-os", "--confirm-owner-capture", "--score-once",
            "test \"$(/usr/bin/id -u)\" -eq 0",
            "test \"$(/usr/bin/hostname)\" = \"$HOST\"",
            "NTPSynchronized", "UnitFileState", "ActiveState",
            "/usr/sbin/runuser", "cia-probe", "/usr/bin/git",
            "rev-parse HEAD", "status --porcelain", "test ! -L",
            "j2_ws_owner_preflight.py", "test_j2_ws_owner_preflight.py",
            "test_j2_ws_prospective_ledger.py", "test_j2_n50_ws_private_screen.py",
            "owner_cli preflight", "owner_cli capture", "owner_cli score",
            "safe_report", "PILOT_JSON", "D362_CAPTURE_ABSTAIN_NO_RETRY",
            "D362_SCORE_ABSTAIN_NO_RETRY", "object_pairs_hook=distinct",
            "D362_NET_REFERENCE_COSTED_BPS_SUM", "D362_GROSS_REFERENCE_BPS_SUM",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, data)

    def test_does_not_mutate_n50_or_enable_trading(self):
        data = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("systemctl enable", data)
        self.assertNotIn("systemctl restart", data)
        self.assertNotIn("systemctl start", data)
        self.assertNotIn("systemctl stop", data)
        self.assertNotIn("systemd-run", data)
        self.assertNotIn("sudo ", data)
        self.assertNotIn("run_j1_current_ranked_epoch_once", data)
        self.assertNotIn("order/create", data)
        self.assertNotIn("--allow-public-network", data)
        self.assertNotIn("curl ", data)
        self.assertNotIn(" rm -rf ", data)
        self.assertIn("approved_for_signals", data)
        self.assertIn("orders_sent", data)

    @unittest.skipUnless(os.name == "posix" and os.geteuid() != 0,
                         "non-root denial requires POSIX nonroot runner")
    def test_any_mode_refuses_before_network_or_code_staging(self):
        for args in (
            ["--preflight-os", SHA],
            ["--confirm-owner-capture", SHA],
            ["--score-once", SHA, "1", "100", "4", "6", "2", "3"],
        ):
            with self.subTest(mode=args[0]):
                p = subprocess.run(["bash", str(SCRIPT), *args],
                                   capture_output=True, text=True, timeout=5)
                self.assertEqual(p.returncode, 77)
                self.assertEqual(p.stdout.strip(), "D362_BLOCKED_ROOT_REQUIRED")
                self.assertNotIn("github.com", p.stdout + p.stderr)

    def test_invalid_sha_fails_before_host_or_code_access(self):
        if os.name != "posix" or shutil.which("bash") is None:
            self.skipTest("POSIX bash unavailable")
        p = subprocess.run(["bash", str(SCRIPT), "--confirm-owner-capture", "not-a-sha"],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 77)
        self.assertEqual(p.stdout.strip(), "D362_BLOCKED_SHA40_REQUIRED")

    def test_unknown_mode_fails_without_side_effects(self):
        if os.name != "posix" or shutil.which("bash") is None:
            self.skipTest("POSIX bash unavailable")
        p = subprocess.run(["bash", str(SCRIPT), "--deploy-all", SHA],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 77)
        self.assertEqual(p.stdout.strip(), "D362_BLOCKED_MODE")


    def test_sanitizer_keeps_only_aggregates_and_rejects_duplicate_keys(self):
        import json
        import sys

        source = SCRIPT.read_text(encoding="utf-8")
        code = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        fixture = {
            "schema_version": "j3-ws-watchlist-forward-reference-v1",
            "status": "ex_post_reference_marks_scored_not_a_backtest",
            "horizon_bars": 1,
            "selected_observations": 2,
            "matured_observations": 2,
            "gross_reference_bps_sum": "15.25",
            "net_reference_after_assumed_costs_bps_sum": "-10.5",
            "same_side_btc_excess_reference_bps_sum": "7.125",
            "assumed_total_cost_quote_units": "0.12",
            "prospective_registration_independently_verified": False,
            "financial_backtest_approved": False,
            "out_of_sample_results_validated": False,
            "approved_for_signals": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "database_mutation_statements": 0,
            "systemd_modified": False,
            "private_symbol": "BTCUSDT",
        }
        def run(raw):
            return subprocess.run(
                [sys.executable, "-B", "-", "score"], input=code,
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "PILOT_JSON": raw},
            )
        ok = run(json.dumps(fixture))
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("D362_NET_REFERENCE_COSTED_BPS_SUM=-10.5", ok.stdout)
        self.assertIn("D362_GROSS_REFERENCE_BPS_SUM=15.25", ok.stdout)
        self.assertNotIn("BTCUSDT", ok.stdout)
        bad = dict(fixture, net_reference_after_assumed_costs_bps_sum="NaN")
        refused = run(json.dumps(bad))
        self.assertEqual(refused.returncode, 77)
        self.assertEqual(refused.stdout.strip(), "D362_REPORT_REJECTED")
        duplicated = '{"orders_sent":true,' + json.dumps(fixture)[1:]
        rejected = run(duplicated)
        self.assertEqual(rejected.returncode, 77)
        self.assertEqual(rejected.stdout.strip(), "D362_REPORT_REJECTED")


if __name__ == "__main__":
    unittest.main()
