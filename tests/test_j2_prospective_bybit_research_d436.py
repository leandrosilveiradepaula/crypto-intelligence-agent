"""D436: persisted confirmed closes drive a new J2 evaluation, safely."""
import unittest
from scripts.demo_j2_prospective_bybit_research_d436 import run

class D436Tests(unittest.TestCase):
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
