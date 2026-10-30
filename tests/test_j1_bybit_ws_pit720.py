"""J1 #346: 720 synthetic closed hours across PIT epochs, never provider proof.

The fixture deliberately refreshes dataclass metadata in memory; it does NOT
assert that old reviewed registry manifests are valid 30 days later. The
historical Top50 and rights gates remain independent.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, HISTORICAL_HOURS, SQLiteOfflineClosedStreamJournal,
    parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_j1_bybit_closed_stream_cache import DECISION, SYMBOLS, message, scope

DAY_MS = 24 * HOUR_MS
DECISION_720 = DECISION + 34 * DAY_MS
FIRST = DECISION_720 - HISTORICAL_HOURS * HOUR_MS
PER_EPOCH_HOURS = 120  # Five days; less than the maximum 7-day metadata age.


def fixture_epochs():
    baseline = scope()
    result = []
    for i in range(6):
        # A refreshed snapshot only becomes usable after the previous close.
        observed = (FIRST - HOUR_MS if i == 0 else
                    FIRST + i * PER_EPOCH_HOURS * HOUR_MS + 3000)
        contracts = tuple(replace(m, observed_at_ms=observed)
                          for m in baseline.contracts)
        result.append(replace(baseline, observed_at_ms=observed,
                              contracts=contracts))
    return tuple(result)


def checked_event(symbol, hour_index, epochs):
    opened = FIRST + hour_index * HOUR_MS
    allowed = epochs[hour_index // PER_EPOCH_HOURS]
    return parse_offline_confirmed_kline(
        message(symbol, opened), scope=allowed,
        received_at_ms=opened + HOUR_MS + 2000,
    )


def insert_checked(db, event):
    db.execute("INSERT INTO confirmed VALUES (?,?,?,?,?,?)", (
        event.symbol, event.open_ms, event.received_ms,
        event.registry_sha256, event.payload, event.digest,
    ))


class OfflinePIT720Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "history.sqlite"
        cls.journal = SQLiteOfflineClosedStreamJournal.create(cls.path)
        cls.epochs = fixture_epochs()
        # Test-only fast fixture seed: real appends still use the journal's
        # atomic append(); no private owner DB or network is accessed.
        with closing(sqlite3.connect(cls.path)) as db, db:
            for h in range(HISTORICAL_HOURS):
                for symbol in SYMBOLS:
                    insert_checked(db, checked_event(symbol, h, cls.epochs))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def audit(self, *, epochs=None, scope_override=None, as_of_ms=DECISION_720 + 4000,
              path=None):
        actual_epochs = self.epochs if epochs is None else epochs
        return SQLiteOfflineClosedStreamJournal(path or self.path).audit(
            scope=scope_override or actual_epochs[-1],
            historical_scopes=actual_epochs,
            decision_at_ms=DECISION_720,
            as_of_ms=as_of_ms,
        )

    def test_full_720h_2_symbols_6_causal_epochs(self):
        report = self.audit()
        fields = report.sanitized_report()
        self.assertEqual(report.persisted_rows, 1440)
        self.assertEqual((report.complete_24h_symbols, report.missing_24h_symbols),
                         (2, 0))
        self.assertEqual((report.complete_720h_symbols, report.missing_720h_symbols),
                         (2, 0))
        self.assertEqual(report.missing_720h_hour_slots, 0)
        self.assertEqual(report.pit_scope_count, 6)
        self.assertEqual(fields["historical_720h_status"],
                         "offline_720h_complete_not_marketwide")
        self.assertEqual(len(report.history_720h_digest_sha256), 64)
        self.assertEqual(report, self.audit())
        self.assertTrue(report.rank_digest_sha256)
        for field in ("source_authenticated", "marketwide_top50_verified",
                      "canonical_ohlcv_approved", "rights_for_live_authorized",
                      "orders_sent"):
            self.assertFalse(fields[field])
        self.assertEqual(fields["network_requests"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(fields))
        # Without explicit PIT epochs, the original 24h API remains fail-closed.
        with self.assertRaises(DataGapError):
            self.journal.audit(scope=self.epochs[-1], decision_at_ms=DECISION_720,
                               as_of_ms=DECISION_720 + 4000)

    def test_recent_24h_complete_is_not_30d_complete(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "recent.sqlite"
            SQLiteOfflineClosedStreamJournal.create(p)
            with closing(sqlite3.connect(self.path)) as source, \
                    closing(sqlite3.connect(p)) as dest, dest:
                rows = source.execute(
                    "SELECT symbol,open_ms,received_ms,registry_sha256,payload,digest "
                    "FROM confirmed WHERE open_ms>=?",
                    (DECISION_720 - 24 * HOUR_MS,),
                ).fetchall()
                dest.executemany("INSERT INTO confirmed VALUES (?,?,?,?,?,?)", rows)
            result = self.audit(path=p)
            self.assertEqual(result.persisted_rows, 48)
            self.assertIsNotNone(result.rank_digest_sha256)
            self.assertEqual(result.rank_digest_sha256, self.audit().rank_digest_sha256)
            self.assertEqual((result.complete_720h_symbols, result.missing_720h_symbols),
                             (0, 2))
            self.assertEqual(result.missing_720h_hour_slots, 2 * (720 - 24))
            self.assertIsNone(result.history_720h_digest_sha256)
            self.assertEqual(result.sanitized_report()["historical_720h_status"],
                             "offline_720h_incomplete_abstain")

    def test_pit_omission_order_future_and_registry_drift_rejected(self):
        with self.assertRaises(DataGapError):
            self.audit(epochs=self.epochs[:2] + self.epochs[3:])
        with self.assertRaises(DataValidationError):
            self.audit(epochs=(self.epochs[1], self.epochs[0]) + self.epochs[2:])
        future = replace(self.epochs[-1], observed_at_ms=DECISION_720 + 1000)
        with self.assertRaises(DataValidationError):
            self.audit(epochs=self.epochs[:-1] + (future,))
        drift = replace(self.epochs[2], registry_sha256="f" * 64)
        with self.assertRaises(DataValidationError):
            self.audit(epochs=self.epochs[:2] + (drift,) + self.epochs[3:])
        newest = self.epochs[-1]
        changed = replace(newest, contracts=(
            replace(newest.contracts[0], tick_size=Decimal("0.02")),
            newest.contracts[1],
        ))
        with self.assertRaises(DataValidationError):
            self.audit(epochs=self.epochs[:-1] + (changed,))
        with self.assertRaises(DataValidationError):
            self.audit(epochs=list(self.epochs))

    def test_future_receipt_cannot_be_used_for_decision(self):
        result = self.audit(as_of_ms=DECISION_720 + 1000)
        self.assertIsNone(result.rank_digest_sha256)
        self.assertIsNone(result.history_720h_digest_sha256)
        self.assertEqual(result.missing_24h_symbols, 2)
        self.assertEqual(result.missing_720h_hour_slots, 2)
        self.assertEqual(result.missing_720h_symbols, 2)

    def test_recomputed_digest_cannot_hide_epoch_tampering_or_gap(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "changed.sqlite"
            with closing(sqlite3.connect(self.path)) as original, \
                    closing(sqlite3.connect(p)) as altered:
                original.backup(altered)
            at = FIRST + 121 * HOUR_MS
            with closing(sqlite3.connect(p)) as db, db:
                payload = db.execute(
                    "SELECT payload FROM confirmed WHERE symbol=? AND open_ms=?",
                    (SYMBOLS[0], at),
                ).fetchone()[0]
                corrupted = json.loads(payload)
                corrupted["scope_observed_ms"] = self.epochs[0].observed_at_ms
                raw = json.dumps(corrupted, sort_keys=True, ensure_ascii=True,
                                 separators=(",", ":"))
                digest = sha256(raw.encode("ascii")).hexdigest()
                db.execute("UPDATE confirmed SET payload=?,digest=? "
                           "WHERE symbol=? AND open_ms=?",
                           (raw, digest, SYMBOLS[0], at))
            with self.assertRaises(DataGapError):
                self.audit(path=p)
            with closing(sqlite3.connect(p)) as db, db:
                db.execute("DELETE FROM confirmed WHERE symbol=? AND open_ms=?",
                           (SYMBOLS[0], FIRST + 100 * HOUR_MS))
            with self.assertRaises(DataGapError):
                self.audit(path=p)

    def test_append_replay_still_safe_when_scope_rotates(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "border.sqlite"
            journal = SQLiteOfflineClosedStreamJournal.create(p)
            before = checked_event("BTCUSDT", 119, self.epochs)
            after = checked_event("BTCUSDT", 120, self.epochs)
            self.assertEqual(journal.append(before), "appended")
            self.assertEqual(journal.append(after), "appended")
            self.assertEqual(journal.append(before), "idempotent")
            report = self.audit(path=p)
            self.assertEqual(report.persisted_rows, 2)
            self.assertEqual(report.complete_720h_symbols, 0)
            self.assertEqual(report.missing_720h_symbols, 2)
            self.assertIsNone(report.rank_digest_sha256)


if __name__ == "__main__":
    unittest.main()
