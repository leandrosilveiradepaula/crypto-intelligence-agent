"""Offline WS2 causal replay; no network calls or private data."""
from __future__ import annotations
import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.bybit_closed_stream_cache import SQLiteOfflineClosedStreamJournal, HOUR_MS
from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from test_j1_bybit_closed_stream_cache import scope, message, DECISION

ACK = {'success': True, 'ret_msg': 'subscribe', 'conn_id': 'fake', 'op': 'subscribe'}

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.dir = TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.j = SQLiteOfflineClosedStreamJournal.create(Path(self.dir.name)/'events.sqlite')
        self.scope = scope()
        self.first = DECISION-24*HOUR_MS
    def frames(self, symbols=('BTCUSDT','ETHUSDT'), hours=24):
        yield (json.dumps(ACK), self.first)
        for h in range(hours):
            start = self.first+h*HOUR_MS
            for symbol in symbols:
                yield (json.dumps(message(symbol,start)), start+HOUR_MS+2000)
    def run_batch(self, frames):
        return ingest_offline_ws_batch(frames=frames, scope=self.scope, journal=self.j)
    def test_complete_24h_and_replay(self):
        result=self.run_batch(self.frames())
        self.assertEqual(result.appended,48)
        self.assertEqual(self.j.audit(scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+4000).missing_24h_symbols,0)
        repeated=self.run_batch(self.frames())
        self.assertEqual(repeated.identical_replays,48)
        self.assertEqual(repeated.appended,0)
        self.assertFalse(repeated.sanitized_report()['marketwide_top50_verified'])
    def test_disconnection_preserves_incomplete(self):
        self.run_batch(self.frames(symbols=('BTCUSDT',)))
        report=self.j.audit(scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+4000)
        self.assertIsNone(report.rank_digest_sha256)
        self.assertEqual(report.missing_24h_symbols,1)
        second=self.run_batch(self.frames(symbols=('ETHUSDT',)))
        self.assertEqual(second.appended,24)
        self.assertIsNotNone(self.j.audit(scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+4000).rank_digest_sha256)
    def test_gap_fails_closed(self):
        t=self.first
        packets=[(json.dumps(ACK),t), (json.dumps(message('BTCUSDT',t)),t+HOUR_MS+2000), (json.dumps(message('BTCUSDT',t+2*HOUR_MS)),t+3*HOUR_MS+2000)]
        with self.assertRaises(DataGapError): self.run_batch(packets)
        self.assertEqual(self.j.audit(scope=self.scope,decision_at_ms=DECISION,as_of_ms=DECISION+4000).persisted_rows,1)
    def test_ack_must_precede_data(self):
        t=self.first
        with self.assertRaises(DataValidationError): self.run_batch([(json.dumps(message('BTCUSDT',t)),t+HOUR_MS+2000)])
    def test_duplicate_json_is_rejected(self):
        with self.assertRaises(DataValidationError): self.run_batch([(json.dumps(ACK),self.first),('{"topic":"x","topic":"y"}',self.first)])
    def test_open_btc_does_not_append(self):
        t=self.first
        result=self.run_batch([(json.dumps(ACK),t),(json.dumps(message('BTCUSDT',t,confirmed=False)),t+HOUR_MS+2000)])
        self.assertEqual(result.open_updates,1)
        self.assertEqual(result.appended,0)
    def test_unreviewed_symbol_rejected(self):
        t=self.first
        with self.assertRaises(DataValidationError): self.run_batch([(json.dumps(ACK),t),(json.dumps(message('DOGEUSDT',t)),t+HOUR_MS+2000)])
if __name__ == '__main__': unittest.main()
