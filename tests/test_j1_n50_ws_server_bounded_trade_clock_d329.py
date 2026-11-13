"""D329: post-close trade clock is bounded server metadata, never a new bar."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from crypto_intelligence_agent.bybit_closed_stream_cache import SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.market_data import DataValidationError
from test_j1_n50_ws_hourly_attestation_d313 import MEMBERS, DECISION, T, candle, reviewed_scope

def postclose(symbol, *, offset=500, server=None):
    msg=candle(symbol)
    msg["data"][0]["timestamp"]=DECISION+offset
    if server is not None:
        msg["ts"]=server
    return msg

class D329ServerBoundedTradeMetadataTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.journal=SQLiteOfflineClosedStreamJournal.create(Path(tmp.name)/"ws-confirmed.sqlite")
        self.scope=reviewed_scope()

    def ingest(self,*msgs,at=DECISION+2000,compat=False,quarantine=True):
        return ingest_offline_ws_batch(
            frames=tuple((json.dumps(msg,separators=(",",":")),at) for msg in msgs),
            scope=self.scope,journal=self.journal,require_ack=False,
            allow_temporal_discard=quarantine,
            allow_server_bounded_trade_clock=compat)

    def audit(self):
        return self.journal.audit(scope=self.scope,decision_at_ms=DECISION,
                                  as_of_ms=DECISION+4000,
                                  hour_evidence_symbols=tuple(sorted(MEMBERS)))

    def test_50_postclose_candles_can_be_stored_only_by_explicit_owner_gate(self):
        messages=[postclose(s) for s in MEMBERS]
        with self.assertRaises(DataValidationError):
            parse_offline_confirmed_kline(messages[0],scope=self.scope,
                                          received_at_ms=DECISION+2000)
        result=self.ingest(*messages,compat=True)
        self.assertEqual(result.appended,50)
        self.assertEqual(result.accepted_postclose_trade_clock,50)
        self.assertEqual(result.discarded_closed_temporal,(0,0,0))
        self.assertEqual(self.audit().persisted_rows,50)
        self.assertEqual(self.audit().hour_evidence_confirmed,50)
        self.assertEqual(self.audit().missing_24h_symbols,50)
        self.assertFalse(result.sanitized_report()["live_trading_authorized"])
        self.assertNotIn(MEMBERS[0],json.dumps(result.sanitized_report()))
        event=parse_offline_confirmed_kline(
            messages[0],scope=self.scope,received_at_ms=DECISION+2000,
            allow_server_bounded_trade_clock=True)
        self.assertEqual(json.loads(event.payload)["trade_ms"],DECISION+500)
        self.assertEqual(self.journal.append(event),"idempotent")

    def test_legacy_parser_and_batch_stay_strict(self):
        msg=postclose(MEMBERS[0])
        with self.assertRaises(DataValidationError):
            self.ingest(msg,quarantine=False)
        result=self.ingest(msg)
        self.assertEqual(result.appended,0)
        self.assertEqual(result.discarded_closed_temporal,(1,0,0))
        self.assertEqual(result.discarded_trade_after_end_unbounded,1)
        with self.assertRaises(DataValidationError):
            self.ingest(msg,compat=True,quarantine=False)
        self.assertEqual(self.audit().persisted_rows,0)

    def test_earlier_than_start_or_later_than_server_remain_non_evidence(self):
        early=postclose(MEMBERS[0])
        early["data"][0]["timestamp"]=T-1
        late=postclose(MEMBERS[1],offset=1500)
        out=self.ingest(early,late,compat=True)
        self.assertEqual(out.appended,0)
        self.assertEqual(out.discarded_closed_temporal,(2,0,0))
        self.assertEqual(out.discarded_trade_before_start,1)
        self.assertEqual(out.discarded_trade_after_end_unbounded,1)
        self.assertEqual(self.audit().persisted_rows,0)

    def test_corrupt_envelope_ohlc_and_server_clock_still_fail(self):
        variants=[]
        bad=postclose(MEMBERS[0]);bad["data"][0]["interval"]="30";variants.append(bad)
        bad=postclose(MEMBERS[0]);bad["data"][0]["high"]="1";variants.append(bad)
        bad=postclose(MEMBERS[0]);bad["topic"]="kline.60.FAKEXYZUSDT";variants.append(bad)
        bad=postclose(MEMBERS[0],server=DECISION+3000);variants.append(bad)
        for bad in variants:
            with self.subTest(topic=bad["topic"],server=bad["ts"]):
                with self.assertRaises(DataValidationError):
                    self.ingest(bad,compat=True)
        premature=postclose(MEMBERS[0],server=DECISION-10)
        self.assertEqual(self.ingest(premature,compat=True,at=DECISION+100).appended,0)
        stale=postclose(MEMBERS[0],server=DECISION+120_950)
        self.assertEqual(self.ingest(stale,compat=True,at=DECISION+121_000).appended,0)
        self.assertEqual(self.audit().persisted_rows,0)

    def test_normal_intrahour_timestamp_unchanged(self):
        result=self.ingest(candle(MEMBERS[0]),compat=True)
        self.assertEqual(result.appended,1)
        self.assertEqual(result.accepted_postclose_trade_clock,0)
        self.assertEqual(self.audit().persisted_rows,1)

if __name__=="__main__":
    unittest.main()
