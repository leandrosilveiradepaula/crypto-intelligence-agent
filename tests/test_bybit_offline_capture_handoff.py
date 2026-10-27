"""J1/WU55: synthetic 2-GET handoff into existing Bybit research SQLite.

This is a TEST ONLY. Fixture transport intentionally has no HTTP client and
cannot be used as a live capture runner. The owner-run BTCUSDT bytes from #213
were never retained and cannot be reconstructed from hashes.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.probe_bybit_private_ohlcv import INSTRUMENT_URL, _kline_url
from test_bybit_research_storage import sample


class _OfflineFixtureTransport:
    """One exact instrument GET and one exact kline GET, in order, no sockets."""

    def __init__(self, instrument_raw: bytes, kline_raw: bytes, *, start: int, end: int):
        self._requests = (
            (INSTRUMENT_URL, instrument_raw),
            (_kline_url(start, end), kline_raw),
        )
        self.requests_attempted = 0

    def get(self, url: str) -> bytes:
        if (type(url) is not str or self.requests_attempted >= 2
                or url != self._requests[self.requests_attempted][0]):
            raise DataValidationError("offline fixture GET budget or endpoint rejected")
        value = self._requests[self.requests_attempted][1]
        self.requests_attempted += 1
        if type(value) is not bytes or not 1 <= len(value) <= 131_072:
            raise DataValidationError("invalid bounded synthetic response")
        return value


class OfflineBybitHandoffTests(unittest.TestCase):
    def test_two_synthetic_reads_round_trip_into_noncanonical_store(self):
        instrument, kline, manifest = sample()
        fake = _OfflineFixtureTransport(instrument, kline,
                                        start=manifest.start_open_ms,
                                        end=manifest.end_open_ms)
        with TemporaryDirectory() as folder:
            store = SQLiteBybitResearchStore(Path(folder) / "offline.sqlite")
            # This test never creates a network object, even if HTTP is broken.
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                with patch("socket.create_connection",
                           side_effect=AssertionError("network")):
                    raw_instrument = fake.get(INSTRUMENT_URL)
                    raw_kline = fake.get(_kline_url(
                        manifest.start_open_ms, manifest.end_open_ms))
                    staged = store.commit_raw_pair(
                        instrument_raw=raw_instrument,
                        kline_raw=raw_kline,
                        manifest=manifest,
                        capture_environment="offline_fixture",
                    )
                    replayed = store.replay_page(
                        symbol=manifest.symbol, interval=manifest.interval,
                        start_open_ms=manifest.start_open_ms,
                        end_open_ms=manifest.end_open_ms,
                    )
            self.assertEqual(fake.requests_attempted, 2)
            self.assertEqual(staged, replayed)
            self.assertEqual(len(staged.candles), 3)
            self.assertEqual(staged.base_unit, "BTC")
            self.assertEqual(staged.quote_unit, "USDT")
            self.assertEqual(staged.input_origin,
                             "unverified_fixture_or_private_research")
            for flag in ("provider_origin_authenticated",
                         "canonical_ohlcv_approved",
                         "historical_top50_approved", "rights_authorized",
                         "live_trading_authorized"):
                self.assertFalse(getattr(staged, flag))
            report = store.quality_report(
                symbol=manifest.symbol, interval=manifest.interval,
                start_open_ms=manifest.start_open_ms,
                end_open_ms=manifest.end_open_ms,
            )
            self.assertTrue(report.complete_for_offline_staging_only)
            self.assertFalse(report.rights_authorized)
            self.assertFalse(report.canonical_ohlcv_approved)
            self.assertFalse(report.live_trading_authorized)
            with self.assertRaises(DataValidationError):
                fake.get(INSTRUMENT_URL)

    def test_fake_transport_rejects_unapproved_endpoint_and_order(self):
        instrument, kline, manifest = sample()
        fake = _OfflineFixtureTransport(instrument, kline,
                                        start=manifest.start_open_ms,
                                        end=manifest.end_open_ms)
        for forbidden in ("https://api.bytbit.invalid/v5/market/kline",
                          "https://api.bybit.com/v5/order/create",
                          _kline_url(manifest.start_open_ms,
                                     manifest.end_open_ms)):
            with self.subTest(url=forbidden), self.assertRaises(DataValidationError):
                fake.get(forbidden)
        self.assertEqual(fake.requests_attempted, 0)

    def test_failed_second_fixture_read_never_creates_partial_page(self):
        instrument, kline, manifest = sample()
        fake = _OfflineFixtureTransport(instrument, kline,
                                        start=manifest.start_open_ms,
                                        end=manifest.end_open_ms)
        with TemporaryDirectory() as folder:
            store = SQLiteBybitResearchStore(Path(folder) / "offline.sqlite")
            fake.get(INSTRUMENT_URL)
            with self.assertRaises(DataValidationError):
                fake.get("https://api.bybit.com/v5/market/kline?wrong=1")
            quality = store.quality_report(
                symbol=manifest.symbol, interval=manifest.interval,
                start_open_ms=manifest.start_open_ms,
                end_open_ms=manifest.end_open_ms,
            )
            self.assertEqual(quality.persisted_candles, 0)
            self.assertFalse(quality.complete_for_offline_staging_only)
            self.assertEqual(fake.requests_attempted, 1)

    def test_corrupt_synthetic_kline_rejected_atomically(self):
        instrument, kline, manifest = sample()
        payload = json.loads(kline)
        payload["result"]["list"][1][5] = "NaN"
        fake = _OfflineFixtureTransport(
            instrument, json.dumps(payload).encode("utf-8"),
            start=manifest.start_open_ms, end=manifest.end_open_ms,
        )
        with TemporaryDirectory() as folder:
            store = SQLiteBybitResearchStore(Path(folder) / "offline.sqlite")
            a = fake.get(INSTRUMENT_URL)
            b = fake.get(_kline_url(manifest.start_open_ms, manifest.end_open_ms))
            with self.assertRaises(DataValidationError):
                store.commit_raw_pair(
                    instrument_raw=a, kline_raw=b, manifest=manifest)
            quality = store.quality_report(
                symbol=manifest.symbol, interval=manifest.interval,
                start_open_ms=manifest.start_open_ms,
                end_open_ms=manifest.end_open_ms,
            )
            self.assertEqual(quality.persisted_candles, 0)
            self.assertFalse(quality.rights_authorized)


if __name__ == "__main__":
    unittest.main()
