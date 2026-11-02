"""OPS16 UTC-close scheduling and one-shot workflow safeguards. No network."""
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_intelligence_agent.j1_ws_utc_close_probe import (
    plan_close_window, await_close_window, HOUR_MS,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.wait_j1_ws_utc_close import main


H = 500_000 * HOUR_MS


class CloseWindowTests(unittest.TestCase):
    def test_start_30_seconds_before_close(self):
        for delta in (1_000, 10_000, 900_000, 1_199_999):
            now = H + HOUR_MS - 30_000 - delta
            self.assertEqual(plan_close_window(now_utc_ms=now), (delta, H+HOUR_MS-30_000))

    def test_window_too_far_or_missed_abstains(self):
        for now in (H, H+HOUR_MS-30_001-1_200_000,
                    H+HOUR_MS-29_999, H+HOUR_MS-1):
            with self.subTest(now=now), self.assertRaises(DataValidationError):
                plan_close_window(now_utc_ms=now)

    def test_invalid_clocks_and_caps(self):
        for now in (None, True, 0, -1, 1.3, "2026-11-02"):
            with self.subTest(now=now), self.assertRaises(DataValidationError):
                plan_close_window(now_utc_ms=now)
        for kw in ({"lead_seconds": True}, {"lead_seconds": 46},
                   {"max_wait_seconds": 1201}, {"max_wait_seconds": -1},
                   {"max_wait_seconds": 1.5}):
            with self.subTest(kw=kw), self.assertRaises(DataValidationError):
                plan_close_window(now_utc_ms=H + HOUR_MS - 60_000, **kw)

    def test_single_sleep_at_exact_window(self):
        start = H + HOUR_MS - 60_000
        end = H + HOUR_MS - 30_000
        clocks = iter((start, end))
        sleeps = []
        target = await_close_window(clock_ms=lambda: next(clocks),
                                    sleeper=lambda seconds: sleeps.append(seconds))
        self.assertEqual(target, end)
        self.assertEqual(sleeps, [30])

    def test_clock_skew_and_late_wakeup_abstain(self):
        start = H + HOUR_MS - 60_000
        target = H + HOUR_MS - 30_000
        for observed in (target-1, target+5001, True, target+HOUR_MS):
            clocks = iter((start, observed))
            with self.subTest(observed=observed), self.assertRaises(DataValidationError):
                await_close_window(clock_ms=lambda: next(clocks),
                                   sleeper=lambda _: None)

    def test_cli_returns_sanitized_failure_with_no_network(self):
        from contextlib import redirect_stdout
        from io import StringIO
        out = StringIO()
        with patch("scripts.wait_j1_ws_utc_close.await_close_window",
                   side_effect=DataValidationError("private path /root/secret")), redirect_stdout(out):
            rc = main([])
        self.assertEqual(rc, 1)
        self.assertNotIn("secret", out.getvalue())
        self.assertIn("utc_close_window_abstain", out.getvalue())


class OwnerOnlyWorkflowTests(unittest.TestCase):
    def test_exact_owner_gate_and_single_probe(self):
        s = (Path(__file__).resolve().parents[1] /
             ".github/workflows/j1-ops16-ws-closed-once.yml").read_text()
        for key in (
            "  issue_comment:", "types: [created]",
            "github.event.issue.number == 429",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-j1-ws52-closed-once-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "persist-credentials: false", "permissions:\n  contents: read",
            "timeout-minutes: 23", "scripts.wait_j1_ws_utc_close",
            "--seconds 90 --max-frames 8192",
        ):
            self.assertIn(key, s)
        self.assertEqual(s.count("python3 -m scripts.probe_bybit_ws_linear_live"), 1)
        for forbidden in ("  push:", "  schedule:", "  pull_request:",
                          "workflow_dispatch:", "actions/upload-artifact",
                          "secrets.", "systemctl", "sqlite3", "curl ", "wget "):
            self.assertNotIn(forbidden, s)


if __name__ == "__main__":
    unittest.main()
