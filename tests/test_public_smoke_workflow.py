"""Static guardrails: on-demand public smoke must never become routine CI.

No external dependencies or network access are used by this test.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "public-feed-smoke.yml"


class PublicSmokeWorkflowSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_only_issue_comment_event_and_exact_owner_can_trigger(self):
        s = self.source
        self.assertIn("  issue_comment:", s)
        self.assertIn("types: [created]", s)
        for token in (
            "github.event.issue.number == 19",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/run-readonly-smoke-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotRegex(s, r"(?m)^\s{2}(?:push|pull_request|schedule|workflow_dispatch|repository_dispatch):")

    def test_runner_has_no_secrets_or_write_permissions(self):
        s = self.source
        self.assertIn("  contents: read", s)
        self.assertIn("persist-credentials: false", s)
        self.assertIn("runs-on: ubuntu-latest", s)
        self.assertIn("timeout-minutes: 3", s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)
        self.assertNotRegex(s, r"(?m)^\s+uses:\s+(?:docker|peter-evans/create-pull-request)")

    def test_smoke_is_bounded_and_explicitly_read_only(self):
        s = self.source
        for token in (
            "python3 -m crypto_intelligence_agent",
            "--mode live --allow-public-network",
            "--max-symbols 1 --candles 3 --page-size 3",
            "--interval 1h --max-clock-skew-ms 5000",
            "PYTHONDONTWRITEBYTECODE",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("--database", s)
        self.assertNotRegex(s, r"\b(?:order|withdraw|POST|DELETE|deploy)\b", msg="smoke must not contain trading or deployment verbs")


if __name__ == "__main__":
    unittest.main()
