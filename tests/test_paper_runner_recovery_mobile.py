"""J5 #389: recovered local PAPER runner shown without implying native stop."""
from decimal import Decimal as D
from pathlib import Path
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_runner_journal import (
    start_paper_runner_journal, append_paper_runner_mark,
)
from crypto_intelligence_agent.paper_runner_trailing import (
    PaperRunnerMark, PaperRunnerTrailPolicy,
)
from scripts.inspect_paper_positions import (
    TEMPLATE, main, multi_paper_snapshot, render_paper_positions,
)
from test_paper_runner_journal import DurablePaperRunnerTests, T, policy, tick


class RecoveredRunnerMobileTests(unittest.TestCase):
    def setUp(self):
        self.fixture = DurablePaperRunnerTests(methodName="test_restart_replay_preserves_ratchet_and_terminal_trigger")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.start()
        self.fixture.append("102", 1)
        self.fixture.append("103", 2)
        self.selected = (inspect_paper_position(self.fixture.position_path, self.fixture.id),)
        self.runner = (self.fixture.id, self.fixture.load(2))

    def test_json_and_html_are_observation_only(self):
        snap = multi_paper_snapshot(self.selected, runner_observation=self.runner)
        p = snap["positions"][0]
        self.assertEqual(p["recovered_runner"]["state"], "TRACKING")
        self.assertEqual(p["recovered_runner"]["observed_tick_count"], 3)
        self.assertFalse(p["native_stop_verified"])
        self.assertFalse(p["trailing_stop_active"])
        self.assertFalse(p["recovered_runner"]["native_stop_verified"])
        self.assertFalse(snap["orders_sent"])
        html = render_paper_positions(
            self.selected, TEMPLATE.read_text(encoding="utf-8"),
            runner_observation=self.runner,
        )
        self.assertIn('data-field="runner-recovery"', html)
        self.assertIn("trailing hipotético", html)
        self.assertIn("nenhum stop nativo ou fill", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("https://", html)
        self.assertIsNone(multi_paper_snapshot(self.selected)["positions"][0]["recovered_runner"])

    def test_trigger_is_not_native_stop(self):
        report = self.fixture.append("102", 3)
        new_snap = multi_paper_snapshot(
            self.selected, runner_observation=(self.fixture.id, report))
        state = new_snap["positions"][0]["recovered_runner"]
        self.assertEqual(state["state"], "TRIGGERED_HYPOTHETICAL_ONLY")
        self.assertFalse(state["native_stop_verified"])
        self.assertFalse(state["trailing_stop_active"])

    def test_wrong_runner_identity_and_incomplete_fills_fail_closed(self):
        with self.assertRaises(DataValidationError):
            multi_paper_snapshot(self.selected, runner_observation=("fixture_other", self.runner[1]))
        with self.assertRaises(DataValidationError):
            multi_paper_snapshot(self.selected, runner_observation=(self.fixture.id, object()))

    def test_cli_requires_full_explicit_policy_and_selected_position(self):
        base = ["--journal", str(self.fixture.position_path),
                "--position-id", self.fixture.id, "--format", "json"]
        with self.assertRaises(SystemExit):
            main(base + ["--runner-journal", str(self.fixture.path)])
        with self.assertRaises(SystemExit):
            main(base + ["--runner-journal", str(self.fixture.path),
                         "--runner-position-id", "fixture_wrong",
                         "--runner-activation-bps", "100",
                         "--runner-trail-distance-bps", "50",
                         "--runner-max-tick-gap-ms", "5000",
                         "--runner-max-last-tick-age-ms", "5000",
                         "--runner-as-of-ms", str(T+2100)])

    def test_cli_outputs_read_only_json_and_html(self):
        import tempfile
        from contextlib import redirect_stdout
        import io
        base = [
            "--journal", str(self.fixture.position_path),
            "--position-id", self.fixture.id,
            "--runner-journal", str(self.fixture.path),
            "--runner-position-id", self.fixture.id,
            "--runner-activation-bps", "100",
            "--runner-trail-distance-bps", "50",
            "--runner-max-tick-gap-ms", "5000",
            "--runner-max-last-tick-age-ms", "5000",
            "--runner-as-of-ms", str(T+2100),
        ]
        # Fixture policy is activation=100, distance=50, gap=5000, age=5000.
        before = (self.fixture.position_path.read_bytes(), self.fixture.path.read_bytes())
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            for fmt in ("json", "html"):
                output = io.StringIO()
                with redirect_stdout(output):
                    main(base + ["--format", fmt])
                rendered = output.getvalue()
                if fmt == "json":
                    self.assertEqual(json.loads(rendered)["positions"][0]["recovered_runner"]["state"], "TRACKING")
                else:
                    self.assertIn('data-field="runner-recovery"', rendered)
        self.assertEqual(before, (self.fixture.position_path.read_bytes(), self.fixture.path.read_bytes()))

    def test_corrupt_and_stale_journal_fail_without_output(self):
        import sqlite3
        args = [
            "--journal", str(self.fixture.position_path),
            "--position-id", self.fixture.id,
            "--runner-journal", str(self.fixture.path),
            "--runner-position-id", self.fixture.id,
            "--runner-activation-bps", "100", "--runner-trail-distance-bps", "50",
            "--runner-max-tick-gap-ms", "5000", "--runner-max-last-tick-age-ms", "5000",
            "--runner-as-of-ms", str(T+9000),
        ]
        with self.assertRaises(DataValidationError):
            main(args)
        with sqlite3.connect(self.fixture.path) as db:
            db.execute("UPDATE paper_runner_state SET digest='invalid'")
        with self.assertRaises(DataValidationError):
            main(args[:-1] + [str(T+2100)])


if __name__ == "__main__":
    unittest.main()
