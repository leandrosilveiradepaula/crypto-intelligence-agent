"""Regression for deterministic, off-by-default, no-retry VPS timer."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
import json

from crypto_intelligence_agent.j1_ops23_once_timer import (
    timer_date, launch_once, check_utc_synced, check_git_sha,
)
from scripts.render_j1_ops23_timer import render_units

TARGET = "2026-11-03T16:00:00Z"
SHA = "a" * 40


class TimerTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / "repo"
        self.state = base / "state"
        self.repo.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.python = "/usr/bin/python3"
        self.launch = timer_date(TARGET)[1]
        self.calls = []

    def fake_runner(self, argv, **kwargs):
        self.calls.append((tuple(argv), kwargs))
        report = dict(status="ws_rest_match_unverified", fields_compared=6,
                      fields_equal=6, rest_gets=1, ws_candle_approved=False,
                      canonical_ohlcv_approved=False, source_authenticated=False,
                      orders_sent=False, data_stored=False)
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")

    def execute(self, **updates):
        args = dict(target_utc=TARGET, expected_sha=SHA,
                    repo_root=str(self.repo), python_bin=self.python,
                    state_dir=str(self.state), now=lambda: self.launch,
                    ntp_check=lambda: True, git_check=lambda *_: True,
                    owner_check=lambda: True, runner=self.fake_runner)
        args.update(updates)
        return launch_once(**args)

    def test_calendar_is_exact_once_date_and_15min_lead(self):
        close, launch = timer_date(TARGET)
        self.assertEqual(close - launch, timedelta(minutes=15))
        self.assertEqual(launch.isoformat(), "2026-11-03T15:45:00+00:00")
        for bad in ("2026-11-03T16:01:00Z", "2026-11-03T16:00:00+00:00",
                    "2026-02-30T16:00:00Z", "2026-11-03T16:00:00", "bad",
                    "2026-11-03T16:00:00Z;touch /tmp/evil"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                timer_date(bad)

    def test_success_only_once_claim_before_probe(self):
        r = self.execute()
        self.assertEqual(r.status, "probe_completed_unverified")
        self.assertTrue(r.launched)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0][0][2], "scripts.wait_j1_ws_utc_close")
        self.assertEqual(self.calls[1][0][2], "scripts.probe_j1_ws_rest_one_candle")
        self.assertEqual(self.calls[0][1]["timeout"], 1200)
        self.assertEqual(self.calls[1][1]["timeout"], 120)
        self.assertFalse(self.calls[0][1].get("shell", False))
        report = json.dumps(r.sanitized_report())
        self.assertFalse(r.sanitized_report()["data_stored_by_supervisor"])
        self.assertFalse(r.sanitized_report()["live_trading_authorized"])
        self.assertNotIn(str(self.repo), report)
        self.assertNotIn(SHA, report)
        self.assertEqual((self.state / "ops22-one-shot-attempt.claim").stat().st_mode & 0o777, 0o600)
        r2 = self.execute()
        self.assertEqual(r2.status, "already_attempted_abstain")
        self.assertEqual(len(self.calls), 2)

    def test_missed_window_and_clock_jump_never_attempt(self):
        for delta in (-1, 16, 90, 3600):
            with self.subTest(delta=delta):
                result = self.execute(now=lambda d=delta: self.launch + timedelta(seconds=d))
                self.assertEqual(result.status, "window_abstain")
                self.assertFalse(self.calls)
                self.assertFalse((self.state / "ops22-one-shot-attempt.claim").exists())

    def test_unsynced_ntp_git_sha_and_owner_abstain(self):
        for update, expected in (
            ({"ntp_check": lambda: False}, "ntp_unsynced_abstain"),
            ({"git_check": lambda *_: False}, "sha_or_tree_abstain"),
            ({"owner_check": lambda: False}, "config_abstain"),
            ({"expected_sha": "wrong"}, "config_abstain"),
        ):
            with self.subTest(status=expected):
                self.assertEqual(self.execute(**update).status, expected)
                self.assertFalse(self.calls)

    def test_missing_insecure_and_symlink_state_rejected(self):
        self.state.chmod(0o755)
        self.assertEqual(self.execute().status, "state_permissions_abstain")
        self.state.chmod(0o700)
        self.state.rmdir()
        self.assertEqual(self.execute().status, "launcher_failure_abstain")
        self.state.symlink_to(self.repo)
        self.assertEqual(self.execute().status, "state_permissions_abstain")
        self.assertFalse(self.calls)

    def test_failed_wait_still_consumes_once_marker(self):
        def fail_wait(argv, **kw):
            self.calls.append(tuple(argv))
            return SimpleNamespace(returncode=1, stdout="sensitive", stderr="secret")
        r = self.execute(runner=fail_wait)
        self.assertEqual(r.status, "utc_wait_abstain")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.execute().status, "already_attempted_abstain")
        self.assertEqual(len(self.calls), 1)

    def test_invalid_probe_success_report_is_not_reported_as_success(self):
        def malformed(argv, **kwargs):
            self.calls.append(tuple(argv))
            if len(self.calls) == 1:
                return SimpleNamespace(returncode=0, stdout="{}", stderr="")
            return SimpleNamespace(returncode=0, stdout='{"status":"ws_rest_match_unverified","orders_sent":true}', stderr="")
        r = self.execute(runner=malformed)
        self.assertEqual(r.status, "probe_report_invalid_abstain")
        self.assertTrue(r.launched)

    def test_ntp_loss_between_wait_and_probe_abstains(self):
        calls = [True, False]
        result = self.execute(ntp_check=lambda: calls.pop(0))
        self.assertEqual(result.status, "ntp_lost_abstain")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.execute().status, "already_attempted_abstain")

    def test_failed_probe_returns_sanitized_status_no_retry(self):
        def fail_probe(argv, **kw):
            self.calls.append(tuple(argv))
            return SimpleNamespace(returncode=0 if len(self.calls) == 1 else 1,
                                   stdout="PRIVATE OHLCV", stderr="REDACT")
        r = self.execute(runner=fail_probe)
        self.assertEqual(r.status, "probe_abstained")
        self.assertTrue(r.launched)
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("PRIVATE", json.dumps(r.sanitized_report()))
        self.assertEqual(self.execute().status, "already_attempted_abstain")

    def test_rendered_units_no_schedule_recurrence_no_install(self):
        s, t = render_units(owner="cia-probe", target_utc=TARGET, expected_sha=SHA,
                            repo_root=str(self.repo), python_bin=self.python,
                            state_dir=str(self.state))
        self.assertIn("OnCalendar=2026-11-03 15:45:00 UTC", t)
        self.assertIn("Persistent=false", t)
        self.assertIn("AccuracySec=1s", t)
        self.assertIn("RandomizedDelaySec=0", t)
        self.assertNotIn("OnUnitActiveSec", t)
        self.assertNotIn("OnBootSec", t)
        self.assertNotIn("OnCalendar=*-", t)
        self.assertIn("Restart=no", s)
        self.assertIn("User=cia-probe", s)
        self.assertIn("ProtectSystem=strict", s)
        self.assertIn("--expected-sha " + SHA, s)
        self.assertNotIn("ExecStartPre=/bin/sh", s)

    def test_render_rejects_input_injection(self):
        common = dict(owner="cia-probe", target_utc=TARGET, expected_sha=SHA,
                      repo_root=str(self.repo), python_bin=self.python,
                      state_dir=str(self.state))
        for replace in ({"owner":"root;touch"}, {"owner":"root"},
                        {"target_utc":"*-*-* 15:45 UTC"},
                        {"expected_sha":"b" * 39},
                        {"repo_root":"/tmp/a/../bad"},
                        {"state_dir":str(self.repo / "children")},
                        {"python_bin":"/bin/sh --evil"}):
            with self.subTest(replace=replace), self.assertRaises(ValueError):
                render_units(**(common | replace))

    def test_ntp_and_git_git_dirty_fail_closed(self):
        def call(args, **kwargs):
            if args[0] == "timedatectl":
                return SimpleNamespace(returncode=0, stdout="no\n")
            if args[-2:] == ["--verify", "HEAD"]:
                return SimpleNamespace(returncode=0, stdout=SHA)
            return SimpleNamespace(returncode=0, stdout=" M dirty.txt")
        self.assertFalse(check_utc_synced(run=call))
        self.assertFalse(check_git_sha(self.repo, SHA, run=call))


if __name__ == "__main__":
    main()
