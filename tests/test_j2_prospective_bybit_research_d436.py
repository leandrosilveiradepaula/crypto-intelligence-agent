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

if __name__ == "__main__":
    unittest.main()
