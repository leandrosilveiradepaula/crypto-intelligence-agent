"""OPS31: one claim, nonrepeating timer, bound shadow report, and safety gates."""
from __future__ import annotations
from datetime import timedelta
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main, skipUnless
from crypto_intelligence_agent.j1_ops31_shadow_timer import (
    CLAIM_NAME, launch_shadow_once, timer_schedule,
    _validated_shadow_report, no_competing_collectors,
)
from scripts.render_j1_ops31_shadow_timer import render_units

TARGET = "2026-11-05T04:00:00Z"
SHA = "a" * 40
BANDS = {"within_interval": 0, "overrun_1ms": 0,
         "overrun_2_to_1000ms": 0, "overrun_1001_to_5000ms": 0,
         "overrun_over_5000ms": 0}


def report(**changes):
    d = {
        "status": "shadow_closes_observed_quarantined",
        "frames_seen": 29, "postack_market_frames": 26,
        "preack_discarded": 1, "topics_observed": 2,
        "unique_closed": 2, "duplicate_closes": 0,
        "open_rows": 10, "pong_frames": 1,
        "closed_timestamp_bands": {**BANDS, "overrun_2_to_1000ms": 2},
        "open_timestamp_bands": {**BANDS, "within_interval": 10},
        "rest_gets": 0, "storage_writes": 0, "orders_sent": False,
        "source_authenticated": False, "canonical_ohlcv_approved": False,
        "marketwide_top50_verified": False,
        "continuous_collector_authorized": False,
        "live_trading_authorized": False,
    }
    d.update(changes)
    return d


class OPS31Tests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.state = root / "state"
        self.repo.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.calls = []

    def runner(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0, stdout=json.dumps(report()),
            stderr="PRIVATE_PRICE_PAYLOAD")

    def launch(self, **changes):
        args = {
            "target_utc": TARGET, "expected_sha": SHA,
            "repo_root": str(self.repo), "python_bin": "/usr/bin/python3",
            "state_dir": str(self.state),
            "now": lambda: timer_schedule(TARGET)[1],
            "ntp_check": lambda: True, "git_check": lambda *_: True,
            "concurrency_check": lambda: True,
            "owner_check": lambda: True, "runner": self.runner,
        }
        args.update(changes)
        return launch_shadow_once(**args)

    def test_exact_utc_schedule_and_invalid_target(self):
        close, start = timer_schedule(TARGET)
        self.assertEqual((close - start).total_seconds(), 60)
        self.assertEqual(start.isoformat(), "2026-11-05T03:59:00+00:00")
        for x in ("2026-11-05T04:01:00Z", "bad",
                  "2026-02-30T04:00:00Z", "*-*-* 04:00:00"):
            with self.subTest(x=x), self.assertRaises(ValueError):
                timer_schedule(x)

    @skipUnless(os.name == "posix", "POSIX claim")
    def test_success_claim_before_child_and_no_retry(self):
        def child(args, **kwargs):
            self.assertTrue((self.state / CLAIM_NAME).is_file())
            return self.runner(args, **kwargs)
        z = self.launch(runner=child)
        self.assertEqual(z.status, "shadow_observed_quarantined")
        self.assertEqual((z.frames_seen, z.unique_closed,
                          z.closed_overrun, z.open_overrun), (29, 2, 2, 0))
        self.assertEqual(len(self.calls), 1)
        argv, kwargs = self.calls[0]
        self.assertIn("scripts.observe_j1_ws_shadow_once", argv)
        self.assertIn("--allow-public-websocket", argv)
        self.assertIn("--confirm-region-and-personal-research", argv)
        self.assertEqual(argv.count("--topic"), 2)
        self.assertEqual(kwargs["timeout"], 205)
        self.assertEqual(kwargs["cwd"], self.repo)
        self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual((self.state / CLAIM_NAME).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.launch().status, "already_attempted_abstain")
        self.assertEqual(len(self.calls), 1)
        serialized = json.dumps(z.sanitized_report())
        for private in ("PRIVATE_PRICE_PAYLOAD", SHA, str(self.repo),
                        "BTCUSDT", "ETHUSDT"):
            self.assertNotIn(private, serialized)

    @skipUnless(os.name == "posix", "POSIX claim")
    def test_preflight_rejects_without_consuming_claim(self):
        cases = (
            ({"owner_check": lambda: False}, "config_abstain"),
            ({"ntp_check": lambda: False}, "ntp_unsynced_abstain"),
            ({"git_check": lambda *_: False}, "sha_or_tree_abstain"),
            ({"concurrency_check": lambda: False},
             "competing_or_unknown_service_abstain"),
            ({"expected_sha": "bad"}, "config_abstain"),
            ({"now": lambda: timer_schedule(TARGET)[1] -
             timedelta(seconds=1)}, "window_abstain"),
            ({"now": lambda: timer_schedule(TARGET)[1] +
             timedelta(seconds=16)}, "window_abstain"),
        )
        for opts, expected in cases:
            with self.subTest(status=expected):
                self.assertEqual(self.launch(**opts).status, expected)
                self.assertFalse((self.state / CLAIM_NAME).exists())
                self.assertFalse(self.calls)

    @skipUnless(os.name == "posix", "POSIX permissions")
    def test_insecure_or_symlink_state_rejected(self):
        self.state.chmod(0o755)
        self.assertEqual(self.launch().status, "state_permissions_abstain")
        self.state.chmod(0o700)
        self.state.rmdir()
        self.state.symlink_to(self.repo)
        self.assertEqual(self.launch().status, "state_permissions_abstain")
        self.assertFalse(self.calls)

    @skipUnless(os.name == "posix", "POSIX claim")
    def test_exception_consumes_once_claim_without_retry(self):
        def fail(*args, **kw):
            self.calls.append((args, kw))
            raise TimeoutError("private value")
        z = self.launch(runner=fail)
        self.assertEqual(z.status, "shadow_child_failed_abstain")
        self.assertTrue(z.launched)
        self.assertTrue((self.state / CLAIM_NAME).exists())
        self.assertEqual(self.launch().status, "already_attempted_abstain")
        self.assertEqual(len(self.calls), 1)

    @skipUnless(os.name == "posix", "POSIX claim")
    def test_valid_abstention_remains_abstention(self):
        r = self.launch(runner=lambda *a, **kw: SimpleNamespace(
            returncode=1,
            stdout=json.dumps(report(
                status="shadow_no_ack_abstain", unique_closed=0,
                closed_timestamp_bands=BANDS, preack_discarded=20,
                postack_market_frames=0, topics_observed=0,
                open_rows=0, open_timestamp_bands=BANDS)),
            stderr="PRIVATE"))
        self.assertEqual(r.status, "shadow_abstained")
        self.assertEqual(r.observer_status, "shadow_no_ack_abstain")

    def test_report_is_strictly_sanitized_and_cross_checked(self):
        for change in (
            {"orders_sent": True}, {"storage_writes": True},
            {"rest_gets": 1}, {"canonical_ohlcv_approved": True},
            {"source_authenticated": True},
            {"continuous_collector_authorized": True},
            {"frames_seen": 99999}, {"preack_discarded": 999},
            {"unique_closed": 3}, {"unique_closed": True},
            {"closed_timestamp_bands": BANDS},
            {"closed_timestamp_bands": {**BANDS, "overrun_1ms": 10}},
            {"open_timestamp_bands": {"private": 3}},
            {"postack_market_frames": 0}, {"topics_observed": 3},
            {"status": "PRIVATE_payload"},
        ):
            with self.subTest(field=list(change)):
                self.assertIsNone(_validated_shadow_report(
                    report(**change), returncode=0))
        self.assertIsNone(_validated_shadow_report(report(
            status="shadow_closes_observed_quarantined",
            unique_closed=0, closed_timestamp_bands=BANDS), returncode=0))
        self.assertIsNone(_validated_shadow_report(report(
            status="shadow_no_closed_candle_unverified"), returncode=0))
        self.assertIsNotNone(_validated_shadow_report(report(
            status="shadow_preack_budget_abstain", frames_seen=129,
            postack_market_frames=0, preack_discarded=129,
            unique_closed=0, closed_timestamp_bands=BANDS,
            open_rows=0, open_timestamp_bands=BANDS,
            topics_observed=0), returncode=1))
        self.assertIsNone(_validated_shadow_report(report(), returncode=1))
        self.assertIsNone(_validated_shadow_report(report(
            status="shadow_no_ack_abstain"), returncode=0))
        self.assertIsNotNone(_validated_shadow_report(report(), returncode=0))

    def test_service_guard_denies_unknown_or_active(self):
        def unavailable(args, **kw):
            return SimpleNamespace(returncode=4, stdout="unknown\n")
        self.assertTrue(no_competing_collectors(run=unavailable))
        def active(args, **kw):
            if args[-1] == "cia-j1-ws-owner.service":
                return SimpleNamespace(returncode=0, stdout="active\n")
            return unavailable(args, **kw)
        self.assertFalse(no_competing_collectors(run=active))
        def active_old_timer(args, **kw):
            if args[-1] == "cia-j1-ops26-retest3.timer":
                return SimpleNamespace(returncode=0, stdout="active\n")
            return unavailable(args, **kw)
        self.assertFalse(no_competing_collectors(run=active_old_timer))
        self.assertFalse(no_competing_collectors(run=lambda *a, **kw:
                         SimpleNamespace(returncode=1, stdout="garbled")))
        self.assertFalse(no_competing_collectors(run=lambda *a, **kw:
                         (_ for _ in ()).throw(OSError("test"))))

    def test_render_is_one_shot_and_hardened(self):
        args = {
            "owner": "cia-probe", "target_utc": TARGET, "expected_sha": SHA,
            "repo_root": "/home/cia-probe/agent/repo",
            "python_bin": "/home/cia-probe/agent/ws-venv/bin/python",
            "state_dir": "/home/cia-probe/agent/ops31-shadow-claims",
        }
        service, timer = render_units(**args)
        self.assertIn("User=cia-probe", service)
        self.assertIn("Restart=no", service)
        self.assertIn("ReadWritePaths=" + args["state_dir"], service)
        # Generated systemd units target POSIX VPS even when tests run Windows.
        self.assertIn("WorkingDirectory=" + args["repo_root"], service)
        self.assertIn("ExecStart=" + args["python_bin"], service)
        self.assertNotIn(chr(92), service)
        self.assertNotIn(chr(92), timer)
        self.assertIn("--expected-sha " + SHA, service)
        self.assertIn("OnCalendar=2026-11-05 03:59:00 UTC", timer)
        self.assertIn("Persistent=false", timer)
        self.assertIn("Unit=cia-j1-ops31-shadow-once.service", timer)
        self.assertNotIn("OnUnitActiveSec", timer)
        self.assertNotIn("OnBootSec", timer)
        for change in (
            {"owner": "root"}, {"owner": "cia-probe;touch"},
            {"expected_sha": "bad"},
            {"target_utc": "*-*-* 04:00:00"},
            {"python_bin": "/bin/sh --bad"},
            {"state_dir": args["repo_root"] + "/nested"},
        ):
            with self.subTest(field=list(change)), self.assertRaises(ValueError):
                render_units(**(args | change))


if __name__ == "__main__":
    main()
