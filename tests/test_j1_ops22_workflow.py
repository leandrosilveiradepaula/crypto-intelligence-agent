"""Static owner-only and bound checks for the public one-candle proof."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/j1-ops22-ws-rest-one-candle.yml"


class OwnerOnlyWSRestWorkflow(unittest.TestCase):
    def test_comment_is_the_only_trigger_and_owner_both_actors(self):
        s = WORKFLOW.read_text(encoding="utf-8")
        for item in (
            "  issue_comment:", "types: [created]",
            "github.event.issue.number == 429",
            "github.event.issue.pull_request == null",
            "github.event.comment.body == '/probe-j1-ws-rest-one-candle-once-v1'",
            "github.event.comment.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "github.repository == 'leandrosilveiradepaula/crypto-intelligence-agent'",
            "permissions:\n  contents: read",
            "persist-credentials: false",
            "timeout-minutes: 23",
            "cancel-in-progress: false",
        ):
            with self.subTest(item=item):
                self.assertIn(item, s)
        for forbidden in ("  push:", "  schedule:", "workflow_dispatch:",
                          "  pull_request:", "actions/upload-artifact",
                          "actions/cache", "secrets.", "systemctl",
                          "git push", "order.create", "sqlite3"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, s)

    def test_one_probe_after_one_bounded_clock_wait(self):
        s = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(s.count("python3 -m scripts.wait_j1_ws_utc_close"), 1)
        self.assertEqual(s.count("python3 -m scripts.probe_j1_ws_rest_one_candle"), 1)
        self.assertLess(s.index("scripts.wait_j1_ws_utc_close"),
                        s.index("scripts.probe_j1_ws_rest_one_candle"))
        self.assertIn("websockets==15.0.1", s)
        for item in ("--allow-public-network", "--allow-public-websocket",
                     "--allow-one-public-rest-get", "--confirm-region-and-personal-research"):
            self.assertIn(item, s)


if __name__ == "__main__":
    unittest.main()
