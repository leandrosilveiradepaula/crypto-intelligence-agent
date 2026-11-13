"""J1/D331: classify one real 42-row style halt without logging market data.

The live D329 error remains unknown. These fixtures are alternative causes,
NOT a claim about the private frame that triggered the actual 14:00 failure.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_ws_supervisor import (
    WSRunBudget, _safe_ws_failure_class, supervise_ws_research,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_j1_n50_ws_hourly_attestation_d313 import (
    DECISION, MEMBERS, reviewed_scope,
)
from test_j1_n50_ws_server_bounded_trade_clock_d329 import postclose
from test_j1_n50_ws_owner_hour_d315 import FakeSession, FakeTime


class D331FailureTaxonomyTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "ws-confirmed.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.path)
        self.scope = reviewed_scope()

    def run_session(self, messages):
        clock = FakeTime()
        session = FakeSession(clock, market=tuple(messages))
        with patch("socket.create_connection",
                   side_effect=AssertionError("No live WS")), patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("No REST GET")
        ):
            outcome = supervise_ws_research(
                session_factory=lambda: session, scope=self.scope,
                journal=self.journal,
                budget=WSRunBudget(max_sessions=1, max_frames=120, max_seconds=65),
                clock=clock.clock, wall_ms=clock.wall_ms, sleeper=clock.sleep,
                allow_temporal_discard=True,
                allow_server_bounded_trade_clock=True,
                allow_declared_gaps=True,
            )
        self.assertTrue(session.closed)
        return outcome

    def audit(self):
        return self.journal.audit(
            scope=self.scope, decision_at_ms=DECISION,
            as_of_ms=DECISION + 5000,
            hour_evidence_symbols=tuple(sorted(MEMBERS)),
        )

    def assert_safe(self, report):
        self.assertEqual(report.sanitized_report()["http_gets"], 0)
        self.assertFalse(report.sanitized_report()["orders_sent"])
        raw = json.dumps(report.sanitized_report(), sort_keys=True)
        for member in MEMBERS:
            self.assertNotIn(member, raw)
        self.assertNotIn("secret", raw)

    def test_42_prefix_then_conflicting_confirmed_replay_is_distinct_and_stops(self):
        earlier = [postclose(member) for member in MEMBERS[:42]]
        repeat = deepcopy(earlier[0])
        repeat["data"][0]["timestamp"] = DECISION + 700
        report = self.run_session([*earlier, repeat, *[
            postclose(member) for member in MEMBERS[42:]
        ]])
        self.assertEqual(report.status, "ws_fail_closed_abstain")
        self.assertEqual(report.failure_category, "ws_journal_closed_replay_conflict")
        self.assertEqual(report.closed_events_appended, 42)
        self.assertEqual(report.accepted_postclose_trade_clock, 42)
        self.assertEqual(report.subscriptions_acknowledged, 1)
        self.assertEqual(self.audit().persisted_rows, 42)
        self.assertEqual(self.audit().hour_evidence_confirmed, 42)
        self.assertIsNone(self.audit().hour_evidence_sha256)
        self.assert_safe(report)

    def test_42_prefix_then_ohlc_conflict_is_distinct_and_stops(self):
        earlier = [postclose(member) for member in MEMBERS[:42]]
        invalid = postclose(MEMBERS[42])
        invalid["data"][0]["high"] = "1"
        report = self.run_session([*earlier, invalid])
        self.assertEqual(report.status, "ws_fail_closed_abstain")
        self.assertEqual(report.failure_category, "ws_closed_ohlcv_invalid")
        self.assertEqual(report.closed_events_appended, 42)
        self.assertEqual(report.accepted_postclose_trade_clock, 42)
        self.assertEqual(self.audit().persisted_rows, 42)
        self.assertEqual(self.audit().hour_evidence_confirmed, 42)
        self.assert_safe(report)

    def test_50_valid_closed_events_still_pass_observational_audit(self):
        report = self.run_session([postclose(member) for member in MEMBERS])
        self.assertEqual(report.status, "ws_budget_ended_research_only")
        self.assertIsNone(report.failure_category)
        self.assertEqual(report.closed_events_appended, 50)
        self.assertEqual(self.audit().hour_evidence_confirmed, 50)
        self.assertEqual(self.audit().persisted_rows, 50)
        self.assert_safe(report)

    def test_static_whitelist_is_specific_and_never_echoes_raw_exception(self):
        cases = (
            (DataGapError("conflicting replay of closed hour"),
             "ws_journal_closed_replay_conflict"),
            (DataGapError("offline kline gap exceeds declared budget: abstain"),
             "ws_journal_gap_limit"),
            (DataGapError("offline kline backfill or registry drift: abstain"),
             "ws_journal_backfill_or_registry_drift"),
            (DataGapError("offline predecessor was corrupted"),
             "ws_journal_predecessor_corrupt"),
            (DataGapError("offline journal write failed closed"),
             "ws_journal_write_invalid"),
            (DataGapError("offline candle record digest invalid"),
             "ws_journal_payload_integrity_invalid"),
            (DataValidationError("Bybit highPrice must be positive"),
             "ws_closed_ohlcv_invalid"),
            (DataValidationError("Bybit base-volume must be bounded exact decimal string"),
             "ws_closed_ohlcv_type_invalid"),
            (DataValidationError("offline WS open candle clock invalid"),
             "ws_open_candle_clock_invalid"),
            (DataValidationError("WS confirmation, UTC clock or scope chronology invalid"),
             "ws_closed_temporal_invalid"),
        )
        for error, name in cases:
            with self.subTest(name=name):
                self.assertEqual(_safe_ws_failure_class(error), name)
        for error in (
            DataGapError("conflicting replay of closed hour; secret BTCUSDT"),
            DataValidationError("Bybit highPrice must be positive; BTCUSDT"),
            DataValidationError("private/path/key=secret"),
            RuntimeError("secret"),
        ):
            self.assertEqual(_safe_ws_failure_class(error),
                             "invalid_or_gapped_market_data")
            self.assertNotIn("secret", _safe_ws_failure_class(error))
            self.assertNotIn("BTCUSDT", _safe_ws_failure_class(error))

    def test_classification_cannot_change_strict_default_ingestion(self):
        message = postclose(MEMBERS[0])
        from crypto_intelligence_agent.bybit_ws_offline_pipeline import (
            ingest_offline_ws_batch,
        )
        with self.assertRaises(DataValidationError):
            ingest_offline_ws_batch(
                frames=((json.dumps(message), DECISION+2_000),),
                scope=self.scope, journal=self.journal,
                require_ack=False, allow_temporal_discard=False,
            )
        self.assertEqual(self.audit().persisted_rows, 0)


if __name__ == "__main__":
    unittest.main()
