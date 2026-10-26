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
        # The legacy Binance smoke has no DB. A separate, explicitly guarded
        # Kraken research job may use only a disposable private SQLite file.
        s = self.source.split("\n  independent-provider-probe:", 1)[0]
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



    def test_okx_private_probe_requires_exact_owner_issue_and_two_optins(self):
        s = self.source
        for token in (
            "okx-private-btc-conformance:",
            "github.event.issue.number == 107",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-okx-private-btc-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_okx_personal_candles",
            "--allow-public-network --allow-okx-personal-probe",
            "timeout-minutes: 2",
            "persist-credentials: false",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)
        self.assertNotRegex(s, r"(?m)^\\s{2}(?:push|pull_request|schedule|workflow_dispatch|repository_dispatch):")


    def test_private_kraken_price_only_uses_explicit_owner_issue(self):
        s = self.source
        for token in (
            "kraken-price-only-private:",
            "github.event.issue.number == 112",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-private-prices-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_kraken_price_archive",
            "--allow-public-network --allow-private-kraken-prices",
            "persist-credentials: false",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertIn("  contents: read", s)
        self.assertNotIn("contents: write", s)
        self.assertNotIn("secrets.", s)


    def test_btc_eth_private_universe_probe_is_owner_only(self):
        s = self.source
        for token in (
            "kraken-btc-eth-current-universe:",
            "github.event.issue.number == 115",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-btc-eth-current-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_kraken_btc_eth_universe",
            "--allow-public-network --allow-private-kraken-universe",
            "persist-credentials: false",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)


    def test_ten_crypto_bases_research_probe_is_owner_only(self):
        s = self.source
        for token in (
            "kraken-ten-base-research-universe:",
            "github.event.issue.number == 120",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-ten-crypto-bases-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_kraken_btc_eth_universe",
            "--allow-public-network --allow-private-kraken-universe",
            "--registry expanded-10",
            "persist-credentials: false",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertIn("  contents: read", s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)



    def test_three_private_chart_pages_are_owner_only_and_ephemeral(self):
        s = self.source
        for token in (
            "kraken-three-price-pages-private:",
            "github.event.issue.number == 122",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-three-private-price-pages-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.collect_private_kraken_research",
            '--database "$private_dir/research.sqlite"',
            "trap 'rm -rf", "chmod 700", "mktemp -d",
            "--allow-public-network --allow-private-persistence",
            "--registry expanded-10 --max-price-symbols 3",
            "persist-credentials: false",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertIn("  contents: read", s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)



    def test_dydx_private_probe_requires_exact_owner_only_issue_comment(self):
        s = self.source
        for token in (
            "dydx-private-btc-base-usd:",
            "github.event.issue.number == 128",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-dydx-private-btc-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_dydx_private_base_usd",
            "--allow-public-network --allow-private-dydx-probe",
            "persist-credentials: false",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("contents: write", s)
        self.assertNotIn("secrets.", s)



    def test_kraken_btc_24h_private_probe_owner_only_no_default_ci(self):
        s = self.source
        for token in (
            "kraken-btc-private-24h-history:",
            "github.event.issue.number == 130",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-kraken-btc-24h-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.collect_private_kraken_research",
            "--allow-public-network --allow-private-persistence",
            "--registry expanded-10 --max-price-symbols 1 --price-hours 24",
            "persist-credentials: false",
            "timeout-minutes: 2",
            "trap 'rm -rf \"$private_dir\"' EXIT",
        ):
            with self.subTest(token=token):
                self.assertIn(token, s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("contents: write", s)



    def test_bybit_private_btc_volume_probe_requires_owner_exact_comment(self):
        source = self.source
        for token in (
            "bybit-private-btc-base-quote:",
            "github.event.issue.number == 138",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-bybit-btc-volume-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "python3 -m scripts.probe_bybit_private_ohlcv",
            "--allow-public-network --allow-private-bybit-probe",
            "persist-credentials: false",
            "timeout-minutes: 2",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("secrets.", source)
        self.assertNotIn("contents: write", source)


if __name__ == "__main__":
    unittest.main()
