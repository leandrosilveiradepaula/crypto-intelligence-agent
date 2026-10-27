"""WU54 adversarial offline tests: never promotes research data to financial feed."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_local_json_audit import LocalBybitCaptureManifest
from crypto_intelligence_agent.bybit_research_storage import (
    BybitResearchStoredPage, SQLiteBybitResearchStore, INPUT_ORIGIN,
    SCHEMA_VERSION,
)
from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError, DuplicateCandleError,
)
from crypto_intelligence_agent.storage import SQLiteMarketDataStore
from test_bybit_instrument_volume_contract import (
    HOUR, NOW, START, END, instrument, kline,
)


def sample(*, offset=0, symbol="BTCUSDT"):
    now = NOW + offset * HOUR
    meta = instrument(symbol=symbol)
    meta["time"] = now - 50
    prices = kline(symbol=symbol)
    for row in prices["result"]["list"]:
        row[0] = str(int(row[0]) + offset * HOUR)
    manifest = LocalBybitCaptureManifest(
        symbol=symbol, interval="1h", registry_variant="expanded-10",
        start_open_ms=START + offset * HOUR,
        end_open_ms=END + offset * HOUR,
        capture_started_ms=now - 100,
        instrument_received_ms=now,
        kline_received_ms=now + 500,
        capture_finished_ms=now + 700,
    )
    return (
        json.dumps(meta).encode("utf-8"),
        json.dumps(prices).encode("utf-8"),
        manifest,
    )


class BybitResearchStoreTests(unittest.TestCase):
    def setUp(self):
        self.work = TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.db_path = Path(self.work.name) / "private-bybit-research.sqlite"
        self.store = SQLiteBybitResearchStore(self.db_path)

    def commit(self, sample_values=None, **kwargs):
        a, b, manifest = sample() if sample_values is None else sample_values
        return self.store.commit_raw_pair(
            instrument_raw=a, kline_raw=b, manifest=manifest, **kwargs,
        )

    def test_exact_decimal_replay_and_units_without_canonical_conversion(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            result = self.commit()
        self.assertIsInstance(result, BybitResearchStoredPage)
        self.assertNotIsInstance(result.candles[0], ClosedCandle)
        self.assertEqual(result.exchange, "bybit_v5")
        self.assertEqual(result.market, "linear_perpetual")
        self.assertEqual(result.input_origin, INPUT_ORIGIN)
        self.assertEqual(result.base_unit, "BTC")
        self.assertEqual(result.quote_unit, "USDT")
        self.assertNotEqual(result.quote_unit, "USD")
        self.assertEqual(result.capture_environment, "offline_fixture")
        self.assertEqual(result.registry_sha256.__len__(), 64)
        self.assertEqual(result.candles[0].open, Decimal("100.0000000000001"))
        self.assertEqual(
            result.candles[0].documented_base_volume,
            Decimal("1.123456789123456789"),
        )
        self.assertEqual(
            result.candles[0].documented_quote_turnover,
            Decimal("99.987654321987654321"),
        )
        self.assertNotEqual(
            result.candles[0].close * result.candles[0].documented_base_volume,
            result.candles[0].documented_quote_turnover,
        )
        self.assertEqual(result, self.store.replay_page(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END,
        ))
        for name in ("provider_origin_authenticated", "canonical_ohlcv_approved",
                     "historical_top50_approved", "rights_authorized",
                     "live_trading_authorized"):
            self.assertFalse(getattr(result, name))
        with self.assertRaises(FrozenInstanceError):
            result.candles[0].close = Decimal(1)

    def test_separate_sqlite_schema_and_reject_existing_canonical_file(self):
        with sqlite3.connect(self.db_path) as db:
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertEqual(tables, {
                "bybit_research_meta", "bybit_research_pages",
                "bybit_research_candles",
            })
            meta = db.execute(
                "SELECT schema_version, input_origin FROM bybit_research_meta"
            ).fetchone()
            self.assertEqual(meta, (SCHEMA_VERSION, INPUT_ORIGIN))
            self.assertNotIn("candles", tables)
            self.assertNotIn("checkpoints", tables)
        path = Path(self.work.name) / "canonical.sqlite"
        SQLiteMarketDataStore(path)
        with self.assertRaisesRegex(DataValidationError, "canonical"):
            SQLiteBybitResearchStore(path)
        with sqlite3.connect(path) as db:
            self.assertFalse(db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='bybit_research_pages'"
            ).fetchone())

    def test_identical_byte_replays_are_idempotent_even_after_extension(self):
        first = self.commit()
        self.assertEqual(first, self.commit())
        second = self.commit(sample(offset=3))
        self.assertEqual(first, self.commit())
        self.assertEqual(second, self.store.replay_page(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START + 3 * HOUR,
            end_open_ms=END + 3 * HOUR,
        ))
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM bybit_research_pages"
            ).fetchone()[0], 2)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM bybit_research_candles"
            ).fetchone()[0], 6)
        report = self.store.quality_report(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END + 3 * HOUR,
        )
        self.assertEqual(report.expected_candles, 6)
        self.assertEqual(report.persisted_candles, 6)
        self.assertEqual(report.missing_open_times_ms, ())
        self.assertTrue(report.complete_for_offline_staging_only)
        self.assertIsNone(report.conflicting_duplicates)
        self.assertFalse(report.canonical_ohlcv_approved)
        self.assertFalse(report.rights_authorized)
        self.assertFalse(report.live_trading_authorized)

    def test_byte_change_and_economic_conflict_cannot_overwrite_page(self):
        original = sample()
        prior = self.commit(original)
        a, b, manifest = original
        whitespace_changed = (a + b" ", b, manifest)
        with self.assertRaisesRegex(DuplicateCandleError, "conflicting"):
            self.commit(whitespace_changed)
        changed = json.loads(b)
        changed["result"]["list"][0][6] = "100.000000000000000001"
        with self.assertRaises(DuplicateCandleError):
            self.commit((a, json.dumps(changed).encode(), manifest))
        with self.assertRaises(DuplicateCandleError):
            self.commit(original, capture_environment="private_local_unverified")
        self.assertEqual(self.store.replay_page(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END,
        ), prior)

    def test_gap_overlap_and_registry_scope_mixing_fail_closed(self):
        self.commit()
        with self.assertRaises(DataGapError):
            self.commit(sample(offset=4))
        with self.assertRaises(DataGapError):
            self.commit(sample(offset=1))
        with self.assertRaises(DataValidationError):
            self.commit(sample(offset=3), capture_environment="private_local_unverified")
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM bybit_research_pages"
            ).fetchone()[0], 1)

    def test_empty_missing_ranges_are_explicit_not_fake_zero_conflicts(self):
        with self.assertRaises(DataGapError):
            self.store.replay_page(
                symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END,
            )
        quality = self.store.quality_report(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END,
        )
        self.assertEqual(quality.expected_candles, 3)
        self.assertEqual(quality.persisted_candles, 0)
        self.assertEqual(quality.missing_open_times_ms,
                         (START, START+HOUR, START+2*HOUR))
        self.assertFalse(quality.complete_for_offline_staging_only)

    def test_rollback_if_middle_candle_insert_fails(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute(f"""
                CREATE TRIGGER abort_middle BEFORE INSERT
                ON bybit_research_candles
                WHEN NEW.open_time_ms={START+HOUR}
                BEGIN SELECT RAISE(ABORT, 'deliberate synthetic fault'); END;
            """)
        with self.assertRaises(sqlite3.IntegrityError):
            self.commit()
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM bybit_research_pages"
            ).fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM bybit_research_candles"
            ).fetchone()[0], 0)
            db.execute("DROP TRIGGER abort_middle")
        self.assertEqual(len(self.commit().candles), 3)

    def test_sqlite_busy_fails_without_advancing_page_or_retry(self):
        locker = sqlite3.connect(self.db_path, timeout=0)
        try:
            locker.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError):
                self.commit()
        finally:
            locker.rollback()
            locker.close()
        self.assertEqual(self.store.quality_report(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END,
        ).persisted_candles, 0)
        self.assertEqual(len(self.commit().candles), 3)

    def test_corrupted_stored_row_cannot_be_replayed_as_valid(self):
        self.commit()
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """UPDATE bybit_research_candles SET documented_quote_turnover=?
                   WHERE open_time_ms=?""",
                ("999", START),
            )
        with self.assertRaisesRegex(DataGapError, "digest"):
            self.store.replay_page(
                symbol="BTCUSDT", interval="1h",
                start_open_ms=START, end_open_ms=END,
            )
        with self.assertRaises(DuplicateCandleError):
            self.commit()

    def test_disallowed_manifest_and_environment_are_rejected_before_db_write(self):
        a, b, manifest = sample()
        for broken in (None, {}, "claimed_real_exchange"):
            with self.subTest(type=type(broken)):
                with self.assertRaises(DataValidationError):
                    self.store.commit_raw_pair(
                        instrument_raw=a, kline_raw=b, manifest=broken,
                    )
        for env in ("production", "api_authenticated", True, None, ""):
            with self.subTest(environment=env):
                with self.assertRaises(DataValidationError):
                    self.commit(capture_environment=env)
        for inp in (None, "abc", b"", b"a" * 131073):
            with self.subTest(payload=type(inp)):
                with self.assertRaises(DataValidationError):
                    self.store.commit_raw_pair(
                        instrument_raw=inp, kline_raw=b, manifest=manifest,
                    )
        self.assertEqual(self.store.quality_report(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END,
        ).persisted_candles, 0)

    def test_strict_json_unclosed_gap_stale_and_malformed_quotes_reject(self):
        a, b, manifest = sample()
        dup = b'{"retCode":0,"retCode":0}'
        with self.assertRaises(DataValidationError):
            self.commit((dup, b, manifest))
        payload = json.loads(b)
        payload["result"]["list"][1][0] = payload["result"]["list"][0][0]
        with self.assertRaises(DataGapError):
            self.commit((a, json.dumps(payload).encode(), manifest))
        payload = json.loads(b)
        payload["result"]["list"][0][6] = "NaN"
        with self.assertRaises(DataValidationError):
            self.commit((a, json.dumps(payload).encode(), manifest))
        # Even a self-claimed capture cannot make an in-progress candle closed.
        newer = LocalBybitCaptureManifest(
            symbol=manifest.symbol, interval=manifest.interval,
            registry_variant=manifest.registry_variant,
            start_open_ms=manifest.start_open_ms,
            end_open_ms=manifest.end_open_ms,
            capture_started_ms=manifest.capture_started_ms,
            instrument_received_ms=manifest.instrument_received_ms,
            kline_received_ms=END-1,
            capture_finished_ms=manifest.capture_finished_ms,
        )
        with self.assertRaises(DataValidationError):
            self.commit((a, b, newer))
        future_payload = json.loads(a)
        future_payload["time"] = NOW - 40_000
        with self.assertRaises(DataValidationError):
            self.commit((json.dumps(future_payload).encode(), b, manifest))
        self.assertEqual(self.store.quality_report(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END,
        ).persisted_candles, 0)

    def test_quote_usdc_kept_distinct_and_cross_symbol_isolated(self):
        first = self.commit()
        second = self.commit(sample(symbol="BTCUSDC"))
        self.assertEqual(first.quote_unit, "USDT")
        self.assertEqual(second.quote_unit, "USDC")
        self.assertFalse(second.canonical_ohlcv_approved)
        self.assertEqual(self.store.quality_report(
            symbol="BTCUSDC", interval="1h",
            start_open_ms=START, end_open_ms=END,
        ).persisted_candles, 3)

    def test_replay_bounds_path_validation_and_no_implicit_network(self):
        for bad in (":memory:", "", self.db_path.parent):
            with self.subTest(path=str(bad)):
                with self.assertRaises(ValueError):
                    SQLiteBybitResearchStore(bad)
        for bounds in ((START+1, END), (START, END-1), (END, START),
                       (START, START+10_001*HOUR)):
            with self.subTest(bounds=bounds):
                with self.assertRaises(DataValidationError):
                    self.store.quality_report(
                        symbol="BTCUSDT", interval="1h",
                        start_open_ms=bounds[0], end_open_ms=bounds[1],
                    )
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            self.commit()
        self.assertFalse(self.store.replay_page(
            symbol="BTCUSDT", interval="1h",
            start_open_ms=START, end_open_ms=END,
        ).live_trading_authorized)


if __name__ == "__main__":
    unittest.main()
