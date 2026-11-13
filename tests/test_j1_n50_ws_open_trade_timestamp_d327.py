"""D327: Ignore only non-final WS trade timestamp rollover anomalies.

The N50 05:00:02Z real incident: 569 frames, ACK=1 and
ws_open_candle_clock_invalid before any confirmed candle was stored.
No private frames captured. This is an adverse fixture, not a claim
to reconstruct the rejected provider message.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.bybit_ws_supervisor import (
    WSRunBudget, supervise_ws_research,
)
from crypto_intelligence_agent.market_data import DataValidationError
from test_j1_n50_ws_hourly_attestation_d313 import (
    MEMBERS, DECISION, T, candle, reviewed_scope,
)
from test_j1_n50_ws_owner_hour_d315 import FakeSession, FakeTime


def received_row(symbol, *, confirm=False, trade_ms=None):
    frame=candle(symbol,confirm=confirm)
    if trade_ms is not None:
        frame["data"][0]["timestamp"]=trade_ms
    return frame


class N50NonfinalRolloverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal=SQLiteOfflineClosedStreamJournal.create(
            Path(self.tmp.name)/"ws-confirmed.sqlite")
        self.scope=reviewed_scope()

    def ingest(self, *messages, as_of=DECISION+2000):
        frames=tuple(
            (json.dumps(message,separators=(",",":")),as_of)
            for message in messages
        )
        return ingest_offline_ws_batch(
            frames=frames,scope=self.scope,journal=self.journal,
            require_ack=False,
        )

    def test_stale_or_future_last_trade_in_nonfinal_update_is_not_data(self):
        early=received_row(MEMBERS[0],trade_ms=T-1000)
        late=received_row(MEMBERS[0],trade_ms=DECISION+900)
        out=self.ingest(early,late)
        self.assertEqual(out.frames,2)
        self.assertEqual(out.ignored_open_trade_clock,2)
        self.assertEqual(out.open_updates,0)
        self.assertEqual(out.appended,0)
        self.assertEqual(out.sanitized_report()["ignored_open_trade_clock"],2)
        self.assertFalse(out.sanitized_report()["orders_sent"])
        audit=self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+2100)
        self.assertEqual(audit.persisted_rows,0)
        self.assertNotIn(MEMBERS[0],json.dumps(out.sanitized_report()))

    def test_closed_candle_remains_strict_even_after_ignored_open(self):
        self.ingest(received_row(MEMBERS[0],trade_ms=DECISION+1000))
        # Same temporal anomaly with confirm=true must be rejected.
        untrusted=received_row(MEMBERS[0],confirm=True,trade_ms=DECISION+1000)
        with self.assertRaises(DataValidationError):
            self.ingest(untrusted)
        self.assertEqual(self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+2100
        ).persisted_rows,0)
        good=self.ingest(candle(MEMBERS[0]))
        self.assertEqual(good.appended,1)
        self.assertEqual(good.ignored_open_trade_clock,0)

    def test_wrong_topic_interval_grid_and_ohlc_remain_fatal(self):
        bads=[]
        wrong_interval=received_row(MEMBERS[0])
        wrong_interval["data"][0]["interval"]="30"
        bads.append(wrong_interval)
        misaligned=received_row(MEMBERS[0])
        misaligned["data"][0]["start"]+=1
        bads.append(misaligned)
        wrong_end=received_row(MEMBERS[0])
        wrong_end["data"][0]["end"]+=1
        bads.append(wrong_end)
        bad_symbol=received_row(MEMBERS[0])
        bad_symbol["topic"]="kline.60.NOTRANKEDUSDT"
        bads.append(bad_symbol)
        bad_ohlc=received_row(MEMBERS[0])
        bad_ohlc["data"][0]["low"]="-1"
        bads.append(bad_ohlc)
        for index,bad in enumerate(bads):
            with self.subTest(case=index),self.assertRaises(DataValidationError):
                self.ingest(bad)
        self.assertEqual(self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+2100
        ).persisted_rows,0)

    def test_realistic_one_session_50_closes_after_open_clock_anomaly(self):
        now=FakeTime()
        open_rollover=received_row(
            MEMBERS[0],trade_ms=DECISION+2_000,
        )
        frames=(open_rollover,)+(tuple(candle(symbol) for symbol in MEMBERS))
        session=FakeSession(now,market=frames)
        with patch(
            "socket.create_connection",side_effect=AssertionError("network prohibited"),
        ),patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("REST prohibited"),
        ):
            result=supervise_ws_research(
                session_factory=lambda:session,
                scope=self.scope,journal=self.journal,
                budget=WSRunBudget(max_sessions=1,max_frames=120,max_seconds=65),
                clock=now.clock,wall_ms=now.wall_ms,sleeper=now.sleep,
            )
        self.assertEqual(result.status,"ws_budget_ended_research_only")
        self.assertIsNone(result.failure_category)
        self.assertEqual(result.sessions_fully_acknowledged,1)
        self.assertEqual(result.subscriptions_acknowledged,1)
        self.assertEqual(result.ignored_open_trade_clock,1)
        self.assertEqual(result.closed_events_appended,50)
        self.assertEqual(result.frames_seen,52)
        self.assertTrue(session.closed)
        audit=self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+5000,
            hour_evidence_symbols=tuple(sorted(MEMBERS)),
        )
        self.assertEqual(audit.hour_evidence_confirmed,50)
        self.assertEqual(audit.persisted_rows,50)
        self.assertEqual(audit.missing_24h_symbols,50)
        sanitized=json.dumps(result.sanitized_report())
        self.assertIn('"ignored_open_trade_clock": 1',sanitized)
        self.assertIn('"http_gets": 0',sanitized)
        for symbol in MEMBERS:
            self.assertNotIn(symbol,sanitized)
        self.assertNotIn('"orders_sent": true',sanitized)


if __name__=="__main__":
    unittest.main()
