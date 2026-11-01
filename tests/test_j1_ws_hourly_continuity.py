"""Offline contract tests for OPS10 continuity gate."""
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import OfflineStreamAudit, HOUR_MS
from crypto_intelligence_agent.j1_ws_hourly_continuity import (
    checkpoint_from_audit, compare_closed_hours,
)
from crypto_intelligence_agent.market_data import DataValidationError


class HourlyContinuityTests(unittest.TestCase):
    def checkpoint(self, hour, missing=0, expected=2, observed_offset=1000):
        audit = OfflineStreamAudit(
            status="offline_fixture_only", persisted_rows=48,
            observed_symbols=expected, journal_digest_sha256="a" * 64,
            missing_24h_symbols=missing, complete_24h_symbols=expected-missing,
            rank_digest_sha256="b" * 64 if not missing else None,
        )
        return checkpoint_from_audit(
            audit=audit, decision_at_ms=hour * HOUR_MS,
            observed_at_ms=hour * HOUR_MS + observed_offset,
            expected_contracts=expected,
        )

    def test_consecutive_complete_hours(self):
        report = compare_closed_hours(self.checkpoint(500000), self.checkpoint(500001))
        self.assertTrue(report["complete_local_windows"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["worker_running_verified"])

    def test_missing_hour_abstains(self):
        self.assertEqual(compare_closed_hours(self.checkpoint(500000),
                                               self.checkpoint(500002))["status"],
                         "hourly_continuity_abstain")

    def test_missing_candle_abstains(self):
        self.assertFalse(compare_closed_hours(self.checkpoint(500000),
                                              self.checkpoint(500001, missing=1)
                                              )["complete_local_windows"])

    def test_scope_churn_abstains(self):
        self.assertFalse(compare_closed_hours(self.checkpoint(500000),
                                              self.checkpoint(500001, expected=3)
                                              )["complete_local_windows"])

    def test_reverse_time_abstains(self):
        self.assertFalse(compare_closed_hours(self.checkpoint(500001),
                                              self.checkpoint(500000)
                                              )["complete_local_windows"])

    def test_invalid_observation_clock_rejected(self):
        with self.assertRaises(DataValidationError):
            self.checkpoint(500000, observed_offset=0)

    def test_report_does_not_claim_origin(self):
        report = self.checkpoint(500000).sanitized_report()
        self.assertFalse(report["source_authenticated"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertNotIn("symbol", report)


if __name__ == "__main__":
    unittest.main()
