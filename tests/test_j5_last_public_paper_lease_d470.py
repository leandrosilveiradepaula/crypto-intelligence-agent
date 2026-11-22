"""D470: archived Bybit D466 and D469 owner-only diagnostics in J5, not live."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.j5_last_public_paper_lease_d470 import (
    LastPaperLeaseUnavailable, read_last_paper_lease,
)
from scripts import serve_j5_local_readonly as server

NOW = 1_800_000_000_000


def legacy(**updates):
    # D466's diagnostic has these keys; D469 adds a fixed extension.
    report = {
        "schema_version": "d459-operator-public-lease-diagnostic-v1",
        "observed_at_ms": NOW - 7200000,
        "primary_result": "returned",
        "primary_status": "finite_public_paper_research_degraded",
        "kline_lease_status": "ws_budget_ended_research_only",
        "ticker_lease_status": "not_reported",
        "kline_subscription_acks": 1,
        "ticker_subscription_acks": 1,
        "accepted_confirmed_close_callbacks": 50,
        "accepted_public_ticker_callbacks": 51045,
        "kline_failure_category": "none_or_unknown",
        "kline_confirmed_events_appended": 50,
        "kline_postclose_trade_clock_accepted": 50,
        "kline_temporal_discard_count": 0,
        "historical_rest_validated_closed_candles": 1200,
        "paper_contract_public_gets": 0,
        "paper_contract_rules_unchanged": 0,
        "paper_contract_rule_changes_denied": 0,
        "real_orders_sent": False,
        "protected_positions_at_venue": False,
    }
    report.update(updates)
    return report


def extended(**updates):
    report = legacy(
        ticker_failure_category="frame_budget_exceeded",
        ticker_frames_seen=51050,
        ticker_sessions_attempted=1,
        ticker_reconnects=0,
        paper_research_cohort_contracts=50,
        paper_research_cohort_complete=True,
        paper_relative_btc_hypotheses=2,
        paper_pending_open_count=0,
        paper_cohort_researched_count=1,
    )
    report.update(updates)
    return report


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "POSIX nonroot owner only")
class LastLeaseOwnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cia-d470-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home.chmod(0o700)
        self.path = self.home / "paper-last-public-lease-d459.json"
        self.write(legacy())

    def write(self, report):
        self.path.write_text(json.dumps(report, sort_keys=True), encoding="ascii")
        self.path.chmod(0o600)

    def read(self, now=NOW):
        return read_last_paper_lease(directory=self.home, now_ms=now)

    def test_real_archived_d466_shape_is_historical_and_degraded_not_live(self):
        v = self.read()
        self.assertEqual(v["status"], "finite_public_paper_research_degraded")
        self.assertEqual(v["historical_rest_candles_reported"], 1200)
        self.assertEqual(v["confirmed_ws_closes_reported"], 50)
        self.assertEqual(v["paper_close_callbacks_reported"], 50)
        self.assertEqual(v["public_ticker_callbacks_reported"], 51045)
        self.assertEqual(v["ticker_lease_status"], "not_reported")
        self.assertEqual(v["ticker_failure_category"], "none_or_unknown")
        self.assertFalse(v["last_lease_recent"])
        self.assertIsNone(v["paper_research_cohort_complete"])
        for name in (
            "same_hour_ws_cohort_integrity_independently_verified",
            "current_ticker_coverage_verified", "current_kline_coverage_verified",
            "native_stop_verified", "real_fills_verified", "orders_sent",
            "approved_for_live_use",
        ):
            self.assertFalse(v[name], name)

    def test_d469_extended_diagnostics_keep_abstention_and_research_separate(self):
        self.write(extended(
            ticker_lease_status="lease_abstained",
            ticker_failure_category="sequence_regression",
        ))
        v = self.read()
        self.assertEqual(v["ticker_lease_status"], "lease_abstained")
        self.assertEqual(v["ticker_failure_category"], "sequence_regression")
        self.assertTrue(v["paper_research_cohort_complete"])
        self.assertEqual(v["paper_relative_btc_hypotheses"], 2)
        self.assertEqual(v["paper_cohort_researched_count"], 1)
        self.assertFalse(v["current_ticker_coverage_verified"])

    def test_paper_consumer_fault_is_reported_without_claiming_venue_error(self):
        self.write(extended(
            ticker_lease_status="lease_abstained",
            ticker_failure_category="paper_cycle_callback_failed",
            paper_relative_btc_hypotheses=0,
        ))
        value = self.read()
        self.assertEqual(value["ticker_failure_category"],
                         "paper_cycle_callback_failed")
        self.assertEqual(value["paper_relative_btc_hypotheses"], 0)
        self.assertFalse(value["current_ticker_coverage_verified"])
        self.assertFalse(value["orders_sent"])

    def test_recent_complete_session_is_still_not_a_current_feed(self):
        self.write(extended(
            observed_at_ms=NOW-1000,
            primary_status="finite_public_paper_research_closed",
            ticker_lease_status="lease_completed",
            ticker_failure_category="none_or_unknown",
        ))
        v = self.read()
        self.assertTrue(v["last_lease_recent"])
        self.assertFalse(v["current_ticker_coverage_verified"])
        self.assertFalse(v["native_stop_verified"])

    def test_corrupted_future_stale_forged_or_inconsistent_state_rejected(self):
        bad = (
            legacy(observed_at_ms=NOW+6000),
            legacy(observed_at_ms=NOW-8*86400000),
            legacy(real_orders_sent=True),
            legacy(protected_positions_at_venue=True),
            legacy(primary_status="finite_public_paper_research_closed"),
            legacy(primary_result="raised_exception"),
            legacy(accepted_confirmed_close_callbacks=51),
            legacy(ticker_subscription_acks=2),
            legacy(historical_rest_validated_closed_candles=1201),
            legacy(kline_failure_category="secret-from-provider"),
            extended(ticker_failure_category="secret-from-provider"),
            extended(paper_research_cohort_complete="yes"),
            extended(paper_relative_btc_hypotheses=-1),
            extended(paper_research_cohort_contracts=51),
            legacy(source_private_path="/root/secret"),
            legacy(kline_confirmed_events_appended=True),
        )
        for v in bad:
            with self.subTest(value=v):
                self.write(v)
                with self.assertRaises(LastPaperLeaseUnavailable):
                    self.read()

    def test_duplicate_json_wrong_permissions_symlink_and_bad_clock(self):
        self.path.write_text('{"a":1,"a":2}', encoding="ascii")
        self.path.chmod(0o600)
        with self.assertRaises(LastPaperLeaseUnavailable):
            self.read()
        self.write(legacy())
        self.path.chmod(0o644)
        with self.assertRaises(LastPaperLeaseUnavailable):
            self.read()
        self.path.unlink()
        target = self.home / "foreign.json"
        target.write_text(json.dumps(legacy()), encoding="ascii")
        target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(LastPaperLeaseUnavailable):
            self.read()
        with self.assertRaises(LastPaperLeaseUnavailable):
            self.read(now=0)


class LastLeaseServerContractTests(unittest.TestCase):
    def test_separate_owner_optin_and_no_public_route(self):
        text = Path(server.__file__).read_text()
        for expected in (
            'self.path == "/api/last-public-paper-lease"',
            "last_public_paper_lease_directory: Path | None = None",
            "--allow-last-public-paper-lease-loopback",
            "--last-public-paper-lease-directory",
            "read_last_paper_lease(",
            '"last_public_paper_lease_nonroot_required"',
            "max_bytes=4096",
        ):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
