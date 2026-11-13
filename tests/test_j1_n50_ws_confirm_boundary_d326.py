"""D326: post-confirm UTC boundary and sanitized WS rejection categories."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_ws_supervisor import (
    WSRunBudget, _safe_ws_failure_class, supervise_ws_research,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_j1_n50_ws_hourly_attestation_d313 import (
    MEMBERS, DECISION, candle, reviewed_scope,
)
from test_j1_n50_ws_owner_hour_d315 import FakeSession, FakeTime


def edge(symbol, ms=DECISION+20):
    frame=candle(symbol)
    frame["ts"]=ms
    return frame


class WSConfirmBoundaryTests(unittest.TestCase):
    def setUp(self):
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.journal=SQLiteOfflineClosedStreamJournal.create(
            Path(folder.name)/"ws-confirmed.sqlite")
        self.scope=reviewed_scope()

    def test_true_confirm_exactly_at_boundary_preserves_receipt_and_sqlite(self):
        frame=edge(MEMBERS[0],DECISION)
        event=parse_offline_confirmed_kline(
            frame,scope=self.scope,received_at_ms=DECISION)
        self.assertEqual(event.received_ms,DECISION)
        self.assertEqual(self.journal.append(event),"appended")
        self.assertEqual(self.journal.append(event),"idempotent")
        audited=self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+1500,
            hour_evidence_symbols=tuple(sorted(MEMBERS)))
        self.assertEqual(audited.hour_evidence_confirmed,1)
        self.assertEqual(audited.persisted_rows,1)
        self.assertEqual(audited.missing_24h_symbols,50)
        self.assertIsNone(audited.rank_digest_sha256)

    def test_subsecond_confirm_is_allowed_with_true_original_clock(self):
        event=parse_offline_confirmed_kline(
            edge(MEMBERS[1],DECISION+40),scope=self.scope,
            received_at_ms=DECISION+90)
        self.assertEqual(event.received_ms,DECISION+90)
        self.assertEqual(self.journal.append(event),"appended")
        audit=self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+2000,
            hour_evidence_symbols=tuple(sorted(MEMBERS)))
        self.assertEqual(audit.hour_evidence_confirmed,1)
        self.assertNotIn(MEMBERS[1],json.dumps(audit.sanitized_report()))

    def test_preclose_future_clock_stale_and_open_candle_still_rejected(self):
        for name,frame,receipt in (
            ("preclose_server",edge(MEMBERS[0],DECISION-1),DECISION+90),
            ("future_server",edge(MEMBERS[0],DECISION+90),DECISION+30),
            ("preclose_receipt",edge(MEMBERS[0],DECISION+20),DECISION-1),
            ("stale_receipt",edge(MEMBERS[0],DECISION+121_000),DECISION+121_100),
        ):
            with self.subTest(name=name),self.assertRaises(DataValidationError):
                parse_offline_confirmed_kline(
                    frame,scope=self.scope,received_at_ms=receipt)
        frame=edge(MEMBERS[0])
        frame["data"][0]["confirm"]=False
        with self.assertRaises(DataValidationError):
            parse_offline_confirmed_kline(
                frame,scope=self.scope,received_at_ms=DECISION+50)
        self.assertEqual(self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+2000,
        ).persisted_rows,0)

    def test_safe_categories_never_reveal_untrusted_exception(self):
        cases={
            "offline WS open candle clock invalid":"ws_open_candle_clock_invalid",
            "WS confirmation, UTC clock or scope chronology invalid":"ws_closed_temporal_invalid",
            "offline WS duplicate or malformed hour":"ws_row_duplicate_hour_invalid",
            "offline WS unsubscribed or malformed topic":"ws_envelope_invalid",
        }
        for msg,expected in cases.items():
            self.assertEqual(_safe_ws_failure_class(DataValidationError(msg)),expected)
        secret="secret/123/BTCUSDT?apikey=123"
        self.assertEqual(_safe_ws_failure_class(DataValidationError(secret)),
                         "invalid_or_gapped_market_data")
        self.assertNotIn(secret,_safe_ws_failure_class(DataValidationError(secret)))

    def test_post_ack_bad_open_row_classified_without_market_content(self):
        now=FakeTime()
        bad=candle(MEMBERS[0],confirm=False)
        bad["data"][0]["interval"]="30"
        session=FakeSession(now,market=(bad,))
        result=supervise_ws_research(
            session_factory=lambda:session,scope=self.scope,journal=self.journal,
            budget=WSRunBudget(max_sessions=1,max_frames=80,max_seconds=80),
            clock=now.clock,wall_ms=now.wall_ms,sleeper=now.sleep)
        self.assertEqual(result.status,"ws_fail_closed_abstain")
        self.assertEqual(result.failure_category,"ws_open_candle_clock_invalid")
        self.assertEqual(result.subscriptions_acknowledged,1)
        self.assertEqual(result.closed_events_appended,0)
        self.assertEqual(result.frames_seen,2)
        self.assertNotIn(MEMBERS[0],json.dumps(result.sanitized_report()))


if __name__=="__main__":
    unittest.main()
