"""J1/D328: never mistake temporal closed WS rejects for confirmed candles.

Actual 2026-11-13 10:59:31-11:00:02Z: ACK=1, 412 frames,
ignored_open_trade_clock=2 and ws_closed_temporal_invalid, 0 persisted.
The precise failed subpredicate was NOT logged; these tests cover three
plausible non-evidence candidates without claiming to identify it.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.j1_n50_ws_temporal_quarantine import (
    TRADE_OUT_OF_HOUR, PREMATURE_CLOSE, STALE_PREVIOUS_CLOSE,
    classify_non_evidence_closed_frame,
)
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget, supervise_ws_research
from crypto_intelligence_agent.market_data import DataValidationError
from test_j1_n50_ws_hourly_attestation_d313 import (
    MEMBERS, DECISION, T, candle, reviewed_scope,
)
from test_j1_n50_ws_owner_hour_d315 import FakeSession, FakeTime


def late_prior(symbol):
    row=candle(symbol)
    row["data"][0]["start"]-=HOUR_MS
    row["data"][0]["end"]-=HOUR_MS
    row["data"][0]["timestamp"]-=HOUR_MS
    return row


def early_confirm(symbol):
    row=candle(symbol)
    row["ts"]=DECISION-250
    return row


def trade_clock_invalid(symbol):
    row=candle(symbol)
    row["data"][0]["timestamp"]=DECISION+200
    return row


def frames(*entries, at=DECISION+2_000):
    return tuple((json.dumps(msg,separators=(",",":")),at) for msg in entries)


class TemporalClosedQuarantineTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.journal=SQLiteOfflineClosedStreamJournal.create(
            Path(tmp.name)/"ws-confirmed.sqlite")
        self.scope=reviewed_scope()

    def ingest(self,*msgs,at=DECISION+2_000):
        return ingest_offline_ws_batch(
            frames=frames(*msgs,at=at),scope=self.scope,
            journal=self.journal,require_ack=False,
            allow_temporal_discard=True,
        )

    def audit(self):
        return self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,
            as_of_ms=DECISION+3000,
            hour_evidence_symbols=tuple(sorted(MEMBERS)),
        )

    def test_only_temporal_non_evidence_valid_envelopes_are_discarded(self):
        cases=(
            (trade_clock_invalid(MEMBERS[0]),DECISION+2000,TRADE_OUT_OF_HOUR),
            (early_confirm(MEMBERS[1]),DECISION-100,PREMATURE_CLOSE),
            (late_prior(MEMBERS[2]),DECISION+2000,STALE_PREVIOUS_CLOSE),
        )
        for msg,at,expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_non_evidence_closed_frame(
                    msg,scope=self.scope,received_at_ms=at),expected)
                with self.assertRaises(DataValidationError):
                    # D313 strict parser is NEVER relaxed, only the ingester
                    # may decline to treat this as evidence at all.
                    parse_offline_confirmed_kline(
                        msg,scope=self.scope,received_at_ms=at)
                out=self.ingest(msg,at=at)
                self.assertEqual(out.appended,0)
                self.assertEqual(out.discarded_closed_temporal[expected],1)
                self.assertEqual(sum(out.discarded_closed_temporal),1)
        self.assertEqual(self.audit().persisted_rows,0)
        self.assertEqual(self.audit().hour_evidence_confirmed,0)

    def test_ignored_temporal_then_50_valid_closed_reaches_only_local_50(self):
        messages=[
            late_prior(MEMBERS[0]),
            trade_clock_invalid(MEMBERS[1]),
            *[candle(sym) for sym in MEMBERS],
        ]
        result=self.ingest(*messages)
        self.assertEqual(result.frames,52)
        self.assertEqual(result.appended,50)
        self.assertEqual(result.discarded_closed_temporal,(1,0,1))
        self.assertEqual(result.identical_replays,0)
        self.assertEqual(self.audit().persisted_rows,50)
        self.assertEqual(self.audit().hour_evidence_confirmed,50)
        self.assertEqual(self.audit().missing_24h_symbols,50)
        serialized=json.dumps(result.sanitized_report())
        for sym in MEMBERS:
            self.assertNotIn(sym,serialized)
        for marker in ("discarded_closed_stale","discarded_closed_trade_clock"):
            self.assertIn(marker,serialized)
        self.assertNotIn("api.bybit.com",serialized)

    def test_invalid_integrity_envelope_or_scope_is_never_quarantined(self):
        invalids=[]
        bad=trade_clock_invalid(MEMBERS[0])
        bad["data"][0]["interval"]="30"
        invalids.append(bad)
        bad=trade_clock_invalid(MEMBERS[0])
        bad["data"][0]["start"]+=1
        invalids.append(bad)
        bad=trade_clock_invalid(MEMBERS[0])
        bad["data"][0]["high"]="1"
        invalids.append(bad)
        bad=trade_clock_invalid(MEMBERS[0])
        bad["topic"]="kline.60.NOTINCOHORTUSDT"
        invalids.append(bad)
        bad=trade_clock_invalid(MEMBERS[0])
        bad["data"][0]["volume"]="-2"
        invalids.append(bad)
        bad=trade_clock_invalid(MEMBERS[0])
        bad["ts"]=DECISION+5000
        invalids.append(bad)
        for msg in invalids:
            with self.subTest(case=msg.get("topic")):
                self.assertIsNone(classify_non_evidence_closed_frame(
                    msg,scope=self.scope,received_at_ms=DECISION+2000))
                with self.assertRaises(DataValidationError):
                    self.ingest(msg)
        self.assertEqual(self.audit().persisted_rows,0)

    def test_real_50_topic_session_can_progress_after_stale_closed_frame(self):
        clock=FakeTime()
        bad=late_prior(MEMBERS[0])
        session=FakeSession(clock,market=(bad,)+tuple(candle(sym) for sym in MEMBERS))
        with patch("socket.create_connection",
                   side_effect=AssertionError("network blocked")),patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("HTTP blocked"),
        ):
            result=supervise_ws_research(
                session_factory=lambda:session,
                scope=self.scope,journal=self.journal,
                budget=WSRunBudget(max_sessions=1,max_frames=120,max_seconds=65),
                clock=clock.clock,wall_ms=clock.wall_ms,sleeper=clock.sleep,
                allow_temporal_discard=True)
        self.assertEqual(result.status,"ws_budget_ended_research_only")
        self.assertEqual(result.failure_category,None)
        self.assertEqual(result.closed_events_appended,50)
        self.assertEqual(result.discarded_closed_temporal,(0,0,1))
        self.assertEqual(self.audit().persisted_rows,50)
        self.assertEqual(self.audit().hour_evidence_confirmed,50)
        self.assertTrue(session.closed)
        self.assertFalse(result.sanitized_report()["orders_sent"])

    def test_unapproved_offline_ingest_stays_strict(self):
        with self.assertRaises(DataValidationError):
            ingest_offline_ws_batch(
                frames=frames(trade_clock_invalid(MEMBERS[0])),
                scope=self.scope,journal=self.journal,
                require_ack=False,
            )
        self.assertEqual(self.audit().persisted_rows,0)

    def test_untouched_closed_clock_unchanged(self):
        good=candle(MEMBERS[0])
        self.assertIsNone(classify_non_evidence_closed_frame(
            good,scope=self.scope,received_at_ms=DECISION+2000))
        accepted=self.ingest(good)
        self.assertEqual(accepted.appended,1)
        self.assertEqual(accepted.discarded_closed_temporal,(0,0,0))
        self.assertEqual(self.audit().persisted_rows,1)


if __name__=="__main__":
    unittest.main()
