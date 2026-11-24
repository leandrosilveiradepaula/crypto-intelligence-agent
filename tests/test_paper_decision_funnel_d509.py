"""D509: actual completed lease diagnostic, no orders or fabricated signals."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.j5_paper_decision_funnel_d509 import (
    PaperDecisionUnavailable, read_paper_decision_funnel,
)

NOW = 1_795_529_200_000


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "owner-only POSIX evidence")
class PaperDecisionFunnelD509Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="cia-d509-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.home.chmod(0o700)
        self.file = self.home / "paper-last-public-lease-d459.json"
        self.payload = {
            "schema_version": "d459-operator-public-lease-diagnostic-v1",
            "observed_at_ms": NOW - 1000,
            "primary_result": "returned",
            "primary_status": "finite_public_paper_research_closed",
            "real_orders_sent": False,
            "protected_positions_at_venue": False,
            "accepted_confirmed_close_callbacks": 50,
            "paper_research_cohort_complete": True,
            "paper_cohort_researched_count": 1,
            "paper_relative_btc_hypotheses": 5,
            "paper_event_counts": {
                "paper_open_pending_armed": 0,
                "paper_position_created": 0,
                "configured_margin_does_not_fit_contract_lot": 1,
            },
        }

    def write(self, obj):
        self.file.write_text(json.dumps(obj, separators=(",", ":")), encoding="ascii")
        self.file.chmod(0o600)

    def test_reports_real_funnel_without_claiming_fill(self):
        self.write(self.payload)
        report = read_paper_decision_funnel(directory=self.home, now_ms=NOW)
        self.assertEqual(report["status"], "candidates_without_paper_fill")
        self.assertEqual(report["counters"]["accepted_confirmed_close_callbacks"], 50)
        self.assertEqual(report["counters"]["paper_relative_btc_hypotheses"], 5)
        self.assertEqual(
            report["paper_event_counts"]["configured_margin_does_not_fit_contract_lot"], 1,
        )
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["websocket_live_health_verified"])
        self.assertEqual(report["source"], "previous_completed_public_lease_only")

    def test_no_candidates_and_created_paper_position_are_distinct(self):
        no_candidate = deepcopy(self.payload)
        no_candidate["paper_relative_btc_hypotheses"] = 0
        self.write(no_candidate)
        self.assertEqual(
            read_paper_decision_funnel(directory=self.home, now_ms=NOW)["status"],
            "no_eligible_hypothesis_after_btc_filters",
        )
        produced = deepcopy(self.payload)
        produced["paper_event_counts"]["paper_position_created"] = 1
        self.write(produced)
        self.assertEqual(
            read_paper_decision_funnel(directory=self.home, now_ms=NOW)["status"],
            "paper_position_recorded_in_lease",
        )

    def test_stale_or_unavailable_does_not_claim_healthy_public_stream(self):
        with self.assertRaises(PaperDecisionUnavailable):
            read_paper_decision_funnel(directory=self.home, now_ms=NOW)
        self.payload["observed_at_ms"] = NOW - 25 * 60 * 60 * 1000
        self.write(self.payload)
        self.assertEqual(
            read_paper_decision_funnel(directory=self.home, now_ms=NOW)["status"],
            "last_lease_stale",
        )

    def test_rejects_unsafe_schema_file_and_untrusted_counter(self):
        self.write(self.payload)
        self.file.chmod(0o644)
        with self.assertRaises(PaperDecisionUnavailable):
            read_paper_decision_funnel(directory=self.home, now_ms=NOW)
        self.file.chmod(0o600)
        self.payload["paper_event_counts"]["client_password"] = 1
        self.write(self.payload)
        with self.assertRaises(PaperDecisionUnavailable):
            read_paper_decision_funnel(directory=self.home, now_ms=NOW)
        self.file.unlink()
        self.file.symlink_to(self.home / "nonexistent")
        with self.assertRaises(PaperDecisionUnavailable):
            read_paper_decision_funnel(directory=self.home, now_ms=NOW)


if __name__ == "__main__":
    unittest.main()
