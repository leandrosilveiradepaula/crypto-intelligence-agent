"""D436: persisted confirmed closes drive a new J2 evaluation, safely."""
import unittest
from scripts.demo_j2_prospective_bybit_research_d436 import run

class D436Tests(unittest.TestCase):
    def test_public_launcher_requires_all_gates_before_transport(self):
        from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import run_authorized_public_kline_session
        from scripts.demo_j2_prospective_bybit_research_d436 import _scope, CONFIG
        from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as root:
            result, update = run_authorized_public_kline_session(
                journal_path=Path(root) / "never.sqlite", scope=_scope(), symbol="BTCUSDT",
                config=CONFIG, budget=WSRunBudget(max_seconds=1, max_frames=1),
                session_factory=lambda: (_ for _ in ()).throw(AssertionError("network")))
        self.assertEqual(result["status"], "explicit_public_research_optin_required")
        self.assertFalse(result["network_attempted"])
        self.assertIsNone(update)
    def test_replay_is_end_to_end_and_never_calls_financial_paths(self):
        first, restarted = run(), run()
        self.assertEqual(first, restarted)
        self.assertEqual(first["status"], "observed_long_hypothesis_not_authorized")
        self.assertEqual(first["closed_events_appended"], 1)
        self.assertTrue(first["journal_digest_sha256"])
        for key in ("approved_for_signals", "orders_sent", "risk_gate_called", "auto2_called", "auto4_called", "live_trading_authorized"):
            self.assertFalse(first[key])


    def test_supervised_fake_socket_end_to_end_and_restart(self):
        from scripts.demo_j2_prospective_bybit_research_d436 import run_supervised_cycle
        for side, status in (
            ("LONG", "observed_long_hypothesis_not_authorized"),
            ("SHORT", "observed_short_hypothesis_not_authorized"),
            ("FLAT", "observed_no_hypothesis"),
        ):
            with self.subTest(side=side):
                first = run_supervised_cycle(scenario=side)
                second = run_supervised_cycle(scenario=side)
                self.assertEqual(first, second)
                self.assertEqual(first["research"]["status"], status)
                self.assertFalse(first["research"]["network_attempted"])
                self.assertEqual(first["session"]["closed_events_appended"], 1)
                self.assertEqual(first["session"]["open_updates"], 1)
                self.assertEqual(first["journal_replay_append_count"], 0)
                if first["terminal"] is not None:
                    self.assertTrue(first["terminal"]["session_ended"])
                    self.assertEqual(first["terminal"]["status"], "observed_session_ended")
                for marker in ("orders_sent", "network_attempted"):
                    self.assertFalse(first[marker])

if __name__ == "__main__":
    unittest.main()
