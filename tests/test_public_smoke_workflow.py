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


    def test_second_provider_probe_is_one_shot_owner_only(self):
        s = self.source
        for token in (
            "independent-provider-probe:",
            "github.event.issue.number == 23",
            "github.event.comment.body == '/probe-kraken-public-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "timeout-minutes: 2",
            "python3 scripts/probe_public_kraken.py --allow-public-network",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)


    def test_third_provider_schema_probe_requires_owner_and_exact_issue(self):
        s = self.source
        for token in (
            "kraken-market-schema:",
            "github.event.issue.number == 25",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-market-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_kraken_market_schema",
            "--allow-public-network --allow-kraken-schema-probe",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)
        self.assertNotRegex(s, r"(?m)^\s{2}(?:push|pull_request|schedule|workflow_dispatch):")


    def test_kraken_taxonomy_probe_needs_owner_exact_issue_and_one_get(self):
        s = self.source
        for token in (
            "kraken-asset-taxonomy:",
            "github.event.issue.number == 28",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-taxonomy-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 scripts/probe_public_kraken.py --allow-public-network --inspect-taxonomy",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)


    def test_public_kraken_volume_diagnostic_requires_owner_issue_and_two_flags(self):
        s = self.source
        for token in (
            "kraken-volume-diagnostic:",
            "github.event.issue.number == 36",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-volume-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "timeout-minutes: 2",
            "python3 -m scripts.probe_kraken_volume_units",
            "--allow-public-network --allow-volume-diagnostic",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)
        self.assertNotRegex(s, r"(?m)^\s{2}(?:push|pull_request|schedule|workflow_dispatch|repository_dispatch):")



    def test_vike_manifest_probe_is_keyless_owner_only_and_not_ci(self):
        s = self.source
        for token in (
            "vike-keyless-manifest:",
            "github.event.issue.number == 63",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-vike-keyless-manifest-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 scripts/probe_vike_public_manifest.py",
            "--allow-public-network --allow-vike-manifest-research",
            "timeout-minutes: 2",
            "persist-credentials: false",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)
        self.assertNotRegex(s, r"(?m)^\s{2}(?:push|pull_request|schedule|workflow_dispatch):")


    def test_hyperliquid_info_probe_only_owner_issue_and_opt_in(self):
        s = self.source
        for token in (
            "hyperliquid-native-btc-info:",
            "github.event.issue.number == 72",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-hyperliquid-info-btc-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_hyperliquid_native_info",
            "--allow-public-network --allow-hyperliquid-info-probe",
            "timeout-minutes: 2",
            "persist-credentials: false",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertIn("  contents: read", s)
        self.assertNotIn("issues: write", s)
        self.assertNotIn("secrets.", s)
        self.assertNotRegex(
            s, r"(?m)^\s{2}(?:push|pull_request|schedule|workflow_dispatch|repository_dispatch):"
        )


if __name__ == "__main__":
    unittest.main()
