"""Static fail-closed checks for the owner-only disposable WS52 probe trigger."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/j1-ops8-ws52-one-shot.yml"


class PublicWS52WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_exact_single_owner_issue_comment_gate(self):
        s = self.workflow
        for line in (
            "  issue_comment:",
            "    types: [created]",
            "github.event.issue.number == 429",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-j1-ws52-github-once-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "github.repository == 'leandrosilveiradepaula/crypto-intelligence-agent'",
            "cancel-in-progress: false",
            "timeout-minutes: 3",
        ):
            with self.subTest(line=line):
                self.assertIn(line, s)
        self.assertNotIn("workflow_dispatch:", s)
        self.assertNotIn("  schedule:", s)
        self.assertNotIn("  push:", s)
        self.assertNotIn("  pull_request:", s)

    def test_readonly_ephemeral_no_artifacts_orders_or_secrets(self):
        s = self.workflow
        for good in (
            "permissions:\n  contents: read",
            "persist-credentials: false",
            "PYTHONDONTWRITEBYTECODE:",
            "websockets==15.0.1",
            "scripts.probe_bybit_ws_linear_live",
            "--seconds 45 --max-frames 8192",
        ):
            self.assertIn(good, s)
        for forbidden in (
            "upload-artifact", "actions/cache", "workflow_run", "secrets.",
            "GITHUB_TOKEN", "git push", "systemctl", "sqlite3", "collect_",
            "order.create", "curl ", "wget ", "--allow-private-persistence",
            "--allow-live-trading", "--allow-private-storage",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, s)

    def test_exact_one_public_probe_command(self):
        s = self.workflow
        self.assertEqual(s.count("python3 -m scripts.probe_bybit_ws_linear_live"), 1)
        self.assertEqual(s.count("--allow-public-websocket"), 1)
        self.assertEqual(s.count("--confirm-region-and-personal-research"), 1)


if __name__ == "__main__":
    unittest.main()
