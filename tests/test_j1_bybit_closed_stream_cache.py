"""J1 #326: offline fixture closed WebSocket 1h, no real IO or venue calls."""
from __future__ import annotations

from copy import deepcopy
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
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from crypto_intelligence_agent.bybit_paginated_universe_research import BybitInstrumentScanResearch
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry

DECISION = 1793282400000  # 2026-10-29 14:00 UTC, exactly closed-hour grid
SCOPE_MS = DECISION - 26 * HOUR_MS
SYMBOLS = ("BTCUSDT", "ETHUSDT")


def scope():
    registry = load_reviewed_registry("expanded-13", as_of_ms=SCOPE_MS)
    contracts = tuple(BybitLinearInstrumentResearch(
        symbol=s, base_coin=s[:-4], quote_coin="USDT", settle_coin="USDT",
        observed_at_ms=SCOPE_MS, launch_time_ms=SCOPE_MS - 4 * 86_400_000,
        max_leverage=Decimal("50"), tick_size=Decimal("0.01"),
        quantity_step=Decimal("0.001"), registry_sha256=registry.sha256_digest,
    ) for s in SYMBOLS)
    scan = BybitInstrumentScanResearch(SCOPE_MS, registry.sha256_digest,
                                       1, 2, SCOPE_MS, contracts)
    return OfflineReviewedStreamScope.from_scan(scan, registry_variant="expanded-13")


def message(symbol, open_ms, *, turnover="2.50", confirmed=True):
    return {
        "topic": f"kline.60.{symbol}", "type": "snapshot", "ts": open_ms + HOUR_MS + 1200,
        "data": [{
            "start": open_ms, "end": open_ms + HOUR_MS - 1,
            "interval": "60", "open": "10.00", "high": "12.00",
            "low": "9.00", "close": "11.00", "volume": "1.5",
            "turnover": turnover, "confirm": confirmed,
            "timestamp": open_ms + HOUR_MS - 500,
        }],
    }


def event(symbol, open_ms, allowed=None, **kwargs):
    return parse_offline_confirmed_kline(
        message(symbol, open_ms, **kwargs), scope=allowed or scope(),
        received_at_ms=open_ms + HOUR_MS + 2000,
    )


class OfflineBybitClosedStreamTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "stream-fixture.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.path)
        self.scope = scope()
        self.first = DECISION - 24 * HOUR_MS

    def audit(self, when=DECISION+4000):
        return self.journal.audit(scope=self.scope, decision_at_ms=DECISION,
                                  as_of_ms=when)

    def seed(self, symbols=SYMBOLS, hours=24):
        for offset in range(hours):
            for symbol in symbols:
                start = self.first + offset * HOUR_MS
                self.assertEqual(self.journal.append(event(
                    symbol, start, self.scope,
                    turnover=("3.50" if symbol == "BTCUSDT" else "2.50"),
                )), "appended")

    def test_confirmed_event_reuses_strict_kline_decimal_contract(self):
        e = event("BTCUSDT", self.first, self.scope)
        data = json.loads(e.payload)
        self.assertEqual(data["turnover_usdt"], "2.50")
        self.assertEqual(data["volume_base"], "1.5")
        self.assertEqual(data["schema"], "j1-bybit-ws-closed-fixture-v1")
        self.assertEqual(e.digest, sha256(e.payload.encode("ascii")).hexdigest())
        self.assertEqual(self.journal.append(e), "appended")
        self.assertEqual(self.journal.append(e), "idempotent")

    def test_bad_frames_fail_closed(self):
        base = message("BTCUSDT", self.first)
        def fail(modifier):
            m = deepcopy(base)
            modifier(m)
            with self.assertRaises(DataValidationError):
                parse_offline_confirmed_kline(
                    m, scope=self.scope, received_at_ms=self.first+HOUR_MS+2000,
                )
        for mutation in (
            lambda m: m["data"][0].update(confirm=False),
            lambda m: m.update(topic="kline.60.OTHERUSDT"),
            lambda m: m.update(topic="kline.5.BTCUSDT"),
            lambda m: m.update(type="delta"),
            lambda m: m.update(ts=True),
            lambda m: m.update(data=[]),
            lambda m: m["data"].append(m["data"][0]),
            lambda m: m["data"][0].update(interval="1"),
            lambda m: m["data"][0].update(high="8"),
            lambda m: m["data"][0].update(turnover="NaN"),
            lambda m: m["data"][0].update(volume="-1"),
            lambda m: m["data"][0].update(open=1.0),
            lambda m: m["data"][0].update(start=self.first+1),
            lambda m: m["data"][0].update(end=self.first+HOUR_MS),
            lambda m: m["data"][0].update(timestamp=self.first-1),
            lambda m: m["data"][0].update(unexpected="extra"),
            lambda m: m.update(unexpected="extra"),
            lambda m: m["data"][0].update(turnover="9"*100),
        ):
            with self.subTest(mutation=mutation):
                fail(mutation)
        with self.assertRaises(DataValidationError):
            parse_offline_confirmed_kline(
                base, scope=self.scope, received_at_ms=self.first+HOUR_MS+500,
            )
        with self.assertRaises(DataValidationError):
            parse_offline_confirmed_kline(
                base, scope=self.scope, received_at_ms=self.first+HOUR_MS+121_000,
            )
        self.assertEqual(self.audit().persisted_rows, 0)

    def test_complete_two_symbol_closed_24h_is_sample_only(self):
        self.seed()
        a = self.audit()
        self.assertEqual(a.persisted_rows, 48)
        self.assertEqual(a.observed_symbols, 2)
        self.assertEqual(a.missing_24h_symbols, 0)
        self.assertEqual(a.complete_24h_symbols, 2)
        self.assertEqual(a.status, "offline_reviewed_24h_complete_not_top50")
        self.assertIsNotNone(a.rank_digest_sha256)
        result = a.sanitized_report()
        for field in ("source_authenticated", "marketwide_top50_verified",
                      "rights_for_live_authorized", "canonical_ohlcv_approved",
                      "orders_sent"):
            self.assertFalse(result[field])
        self.assertEqual(result["network_requests"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn("turnover_usdt", json.dumps(result))
        self.assertEqual(
            SQLiteOfflineClosedStreamJournal(self.path).audit(
                scope=self.scope, decision_at_ms=DECISION,
                as_of_ms=DECISION+4000,
            ), a,
        )

    def test_missing_candle_or_unreviewed_member_never_yields_partial_ranking(self):
        self.seed(("BTCUSDT",))
        result = self.audit()
        self.assertEqual(result.missing_24h_symbols, 1)
        self.assertEqual(result.complete_24h_symbols, 1)
        self.assertIsNone(result.rank_digest_sha256)
        self.assertEqual(result.status, "offline_closed_stream_incomplete_abstain")
        with self.assertRaises(DataValidationError):
            event("DOGEUSDT", self.first, self.scope)

    def test_gap_and_out_of_order_after_disconnect_reject_without_changes(self):
        self.assertEqual(self.journal.append(event("BTCUSDT", self.first, self.scope)), "appended")
        with self.assertRaises(DataGapError):
            self.journal.append(event("BTCUSDT", self.first+2*HOUR_MS, self.scope))
        with self.assertRaises(DataGapError):
            self.journal.append(event("BTCUSDT", self.first-HOUR_MS, self.scope))
        self.assertEqual(self.audit().persisted_rows, 1)
        self.assertEqual(self.journal.append(event("BTCUSDT", self.first+HOUR_MS, self.scope)), "appended")
        self.assertEqual(self.audit().persisted_rows, 2)

    def test_conflicting_replay_is_not_latest_price_correction(self):
        one = event("BTCUSDT", self.first, self.scope)
        self.journal.append(one)
        with self.assertRaises(DataGapError):
            self.journal.append(event("BTCUSDT", self.first, self.scope, turnover="2.51"))
        self.assertEqual(self.audit().persisted_rows, 1)

    def test_recomputed_digest_cannot_hide_invalid_ohlc_or_clock(self):
        e = event("BTCUSDT", self.first, self.scope)
        self.journal.append(e)
        def modify(mutator, recompute):
            with closing(sqlite3.connect(self.path)) as db, db:
                current = db.execute("SELECT payload FROM confirmed").fetchone()[0]
                data = json.loads(current)
                mutator(data)
                raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                db.execute("UPDATE confirmed SET payload=?, digest=?", (
                    raw, sha256(raw.encode("ascii")).hexdigest() if recompute else e.digest,
                ))
            with self.assertRaises(DataGapError):
                self.audit()
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("UPDATE confirmed SET payload=?, digest=?", (e.payload, e.digest))
        modify(lambda d: d.update(close="900"), True)
        modify(lambda d: d.update(open_ms=self.first+1), True)
        modify(lambda d: d.update(turnover_usdt="NaN"), True)
        modify(lambda d: d.update(close="11.01"), False)
        self.assertEqual(self.audit().persisted_rows, 1)

    def test_registry_identity_and_scope_mismatch_rejected(self):
        self.journal.append(event("BTCUSDT", self.first, self.scope))
        other = replace(self.scope, registry_sha256="f"*64)
        with self.assertRaises(DataGapError):
            self.journal.audit(scope=other, decision_at_ms=DECISION,
                               as_of_ms=DECISION+4000)
        other = replace(self.scope, observed_at_ms=self.scope.observed_at_ms+1000)
        with self.assertRaises(DataGapError):
            self.journal.audit(scope=other, decision_at_ms=DECISION,
                               as_of_ms=DECISION+4000)

    def test_as_of_clock_and_synthetic_rolling_ticker_not_accepted(self):
        self.seed()
        with self.assertRaises(DataValidationError):
            self.audit(DECISION-1)
        # A close confirmed after the requested as-of can NEVER inform that rank.
        result = self.audit(DECISION+1000)
        self.assertEqual(result.status, "offline_closed_stream_incomplete_abstain")
        self.assertIsNone(result.rank_digest_sha256)

    def test_offline_cli_fixture_full_and_disconnect_are_sanitized(self):
        from scripts.probe_offline_bybit_closed_stream import run_mock
        good = run_mock()
        bad = run_mock(inject_disconnect=True)
        self.assertEqual(good["persisted_rows"], 48)
        self.assertEqual(good["complete_24h_symbols"], 2)
        self.assertIsNotNone(good["rank_digest_sha256"])
        self.assertEqual(bad["persisted_rows"], 36)
        self.assertEqual(bad["status"], "offline_closed_stream_incomplete_abstain")
        self.assertIsNone(bad["rank_digest_sha256"])
        self.assertEqual(good["network_requests"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(good))

    def test_unsafe_sqlite_trigger_is_not_accepted(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TRIGGER bogus AFTER INSERT ON confirmed "
                       "BEGIN UPDATE meta SET value='bad'; END")
        with self.assertRaises(DataGapError):
            self.journal.append(event("BTCUSDT", self.first, self.scope))
        with self.assertRaises(DataGapError):
            self.audit()

    def test_existing_target_and_corrupt_schema_are_never_overwritten(self):
        with self.assertRaises(FileExistsError):
            SQLiteOfflineClosedStreamJournal.create(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE meta SET value='invalid'")
        with self.assertRaises(DataGapError):
            self.audit()
        with self.assertRaises(DataGapError):
            self.journal.append(event("BTCUSDT", self.first, self.scope))

    def test_foreign_symbol_rejected_even_with_a_valid_event_digest(self):
        normal = event("BTCUSDT", self.first, self.scope)
        self.journal.append(normal)
        modified = json.loads(normal.payload)
        modified["symbol"] = "DOGEUSDT"
        raw = json.dumps(modified, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE confirmed SET payload=?, digest=?", (raw, sha256(raw.encode()).hexdigest()))
        with self.assertRaises(DataGapError):
            self.audit()


if __name__ == "__main__":
    unittest.main()
