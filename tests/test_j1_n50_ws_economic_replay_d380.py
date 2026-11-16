"""D380: harmless confirmed WS repeats preserve first receipt; financial revisions fail.

All fixtures synthetic/offline, no public socket, REST, private DB or orders.
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.market_data import DataGapError
from test_j1_bybit_closed_stream_cache import event, scope, DECISION, HOUR_MS
from test_j1_n50_ws_hourly_attestation_d313 import (
    DECISION as N50_END, MEMBERS, reviewed_scope,
)
from test_j1_n50_ws_server_bounded_trade_clock_d329 import postclose


def changed_event(initial, **fields):
    payload = json.loads(initial.payload)
    payload.update(fields)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":"))
    return replace(initial, received_ms=payload["received_ms"],
                   payload=encoded,
                   digest=sha256(encoded.encode("ascii")).hexdigest())


class EconomicWSReplayTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "ws-confirmed.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.path)

    def first_payload(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT payload,digest FROM confirmed").fetchone()

    def test_transport_only_replay_is_idempotent_and_preserves_first_receipt(self):
        start = DECISION-HOUR_MS
        original = event("BTCUSDT", start, scope())
        self.assertEqual(self.journal.append(original), "appended")
        before = self.first_payload()
        o = json.loads(original.payload)
        candidate = changed_event(
            original, received_ms=o["received_ms"]+1000,
            server_ms=o["server_ms"]+200, trade_ms=o["trade_ms"]+100)
        self.assertNotEqual(candidate.digest, original.digest)
        self.assertEqual(self.journal.append(candidate), "idempotent")
        self.assertEqual(self.first_payload(), before)
        self.assertEqual(self.journal.append(original), "idempotent")
        self.assertEqual(self.first_payload(), before)

    def test_real_economic_or_scope_revision_still_fails_without_writes(self):
        start = DECISION-HOUR_MS
        original = event("BTCUSDT", start, scope())
        self.journal.append(original)
        old = json.loads(original.payload)
        before = self.first_payload()
        cases = (
            {"close":"11.01"},
            {"high":"12.01"},
            {"volume_base":"1.6"},
            {"turnover_usdt":"2.51"},
            {"scope_observed_ms":old["scope_observed_ms"]+100},
            {"registry_sha256":"b"*64},
            {"server_ms":old["server_ms"]-100},
            {"trade_ms":old["trade_ms"]-100},
            {"received_ms":old["received_ms"]-100},
        )
        for changed in cases:
            with self.subTest(changed=tuple(changed)):
                candidate = changed_event(original, **changed)
                with self.assertRaises(DataGapError):
                    self.journal.append(candidate)
                self.assertEqual(self.first_payload(), before)

    def test_n50_postclose_repeated_metadata_preserves_exact_50_hour(self):
        scope50 = reviewed_scope()
        incoming = [postclose(m) for m in MEMBERS]
        replay = deepcopy(incoming[0])
        replay["ts"] += 200
        replay["data"][0]["timestamp"] += 100
        frames = tuple((json.dumps(msg), N50_END+2000) for msg in incoming) + (
            (json.dumps(replay), N50_END+3000),
        )
        result = ingest_offline_ws_batch(
            frames=frames, scope=scope50, journal=self.journal,
            require_ack=False, allow_declared_gap=True,
            allow_temporal_discard=True, allow_server_bounded_trade_clock=True,
        )
        self.assertEqual(result.appended, 50)
        self.assertEqual(result.identical_replays, 1)
        audit = self.journal.audit(
            scope=scope50, decision_at_ms=N50_END,
            as_of_ms=N50_END+5000,
            hour_evidence_symbols=tuple(sorted(MEMBERS)),
        )
        self.assertEqual(audit.persisted_rows, 50)
        self.assertEqual(audit.hour_evidence_confirmed, 50)
        self.assertIsNotNone(audit.hour_evidence_sha256)
        self.assertFalse(result.sanitized_report()["orders_sent"])
        changed = deepcopy(replay)
        changed["data"][0]["turnover"] = "16.51"
        with self.assertRaises(DataGapError):
            ingest_offline_ws_batch(
                frames=((json.dumps(changed), N50_END+4000),),
                scope=scope50, journal=self.journal,
                require_ack=False, allow_declared_gap=True,
                allow_temporal_discard=True, allow_server_bounded_trade_clock=True,
            )
        self.assertEqual(self.journal.audit(
            scope=scope50, decision_at_ms=N50_END,
            as_of_ms=N50_END+5000,
            hour_evidence_symbols=tuple(sorted(MEMBERS)),
        ).persisted_rows, 50)


if __name__=="__main__":
    unittest.main()
