"""J1/EXIT: one vertical orchestrator, 30d real-shaped fixtures, 1h replay.

All data are synthetic; transport/venue/rights remain disabled.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from crypto_intelligence_agent.bybit_research_cycle import (
    BybitResearchRawPage, stage_offline_bybit_research_cycle,
    append_offline_bybit_hourly_update,
)
from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from crypto_intelligence_agent.bybit_local_json_audit import LocalBybitCaptureManifest
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_bybit_paginated_universe_research import instrument_page, instrument_row
from test_j1_bybit_exit_vertical import (
    T, DECISION, H, SYMBOLS, selection, kline,
)


def fake_page(symbol, begin, hours, at):
    instrument = instrument_page([
        instrument_row(symbol, launchTime=str(T - 1000*H))
    ], ms=at-50, cursor="")
    candles = kline(symbol, begin, hours, "1000")
    manifest = LocalBybitCaptureManifest(
        symbol=symbol, interval="1h", registry_variant="expanded-13",
        start_open_ms=begin, end_open_ms=begin+hours*H,
        capture_started_ms=at-1000,
        instrument_received_ms=at,
        kline_received_ms=at+1000,
        capture_finished_ms=at+2000,
    )
    return BybitResearchRawPage(
        json.dumps(instrument).encode("ascii"),
        json.dumps(candles).encode("ascii"),
        manifest,
    )


def full_history():
    beginning = DECISION - 720*H
    return {
        symbol: tuple(
            fake_page(symbol, beginning + i*72*H, 72, T)
            for i in range(10)
        ) for symbol in SYMBOLS
    }


class BybitResearchCycleTests(unittest.TestCase):
    def test_single_pipeline_full_30d_then_one_hour_two_symbols(self):
        original = selection()
        later = selection(at_ms=T+H, volumes=(
            ("BTCUSDT", "30"), ("ETHUSDT", "1"),
        ))
        with TemporaryDirectory() as folder:
            store = SQLiteBybitResearchStore(Path(folder) / "research.sqlite")
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                first = stage_offline_bybit_research_cycle(
                    selection=original, history=full_history(), store=store,
                )
                replayed = stage_offline_bybit_research_cycle(
                    selection=original, history=full_history(), store=store,
                )
            self.assertEqual(first, replayed)
            self.assertEqual(first.fully_covered_sample_assets, 2)
            self.assertEqual(first.historical_hours_per_asset, 720)
            self.assertEqual(first.validated_closed_1h_rows, 1440)
            self.assertEqual(first.immutable_pages_replayed, 20)
            self.assertFalse(first.observed_universe_is_marketwide_top50)
            self.assertFalse(first.rights_for_live_authorized)
            self.assertFalse(first.orders_sent)
            extra = {symbol: fake_page(symbol, DECISION, 1, T+H)
                     for symbol in SYMBOLS}
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                next_hour = append_offline_bybit_hourly_update(
                    previous=original, updated=later, hourly_pages=extra,
                    store=store,
                )
            self.assertEqual(next_hour.validated_closed_1h_rows, 1442)
            self.assertEqual(next_hour.historical_hours_per_asset, 721)
            self.assertEqual(store.replay_pit_research_snapshot(T), original)
            self.assertEqual(store.replay_pit_research_snapshot(T+H), later)
            for symbol in SYMBOLS:
                q = store.quality_report(
                    symbol=symbol, interval="1h",
                    start_open_ms=DECISION-720*H, end_open_ms=DECISION+H,
                )
                self.assertTrue(q.complete_for_offline_staging_only)
                self.assertEqual(q.persisted_candles, 721)
                self.assertFalse(q.canonical_ohlcv_approved)

    def test_preflight_fails_before_any_history_write(self):
        original = selection()
        with TemporaryDirectory() as folder:
            store = SQLiteBybitResearchStore(Path(folder) / "research.sqlite")
            parts = full_history()
            parts["ETHUSDT"] = parts["ETHUSDT"][:-1]
            with self.assertRaises(DataGapError):
                stage_offline_bybit_research_cycle(
                    selection=original, history=parts, store=store,
                )
            for symbol in SYMBOLS:
                quality = store.quality_report(
                    symbol=symbol, interval="1h",
                    start_open_ms=DECISION-720*H, end_open_ms=DECISION,
                )
                self.assertEqual(quality.persisted_candles, 0)
            with self.assertRaises(DataGapError):
                store.replay_pit_research_snapshot(T)

    def test_unauthorized_extra_unknown_symbol_rejected_before_write(self):
        original = selection()
        with TemporaryDirectory() as folder:
            store = SQLiteBybitResearchStore(Path(folder) / "research.sqlite")
            parts = full_history()
            parts["SOLUSDT"] = parts["ETHUSDT"]
            with self.assertRaises(DataValidationError):
                stage_offline_bybit_research_cycle(
                    selection=original, history=parts, store=store,
                )
            with self.assertRaises(DataGapError):
                store.replay_pit_research_snapshot(T)

    def test_hourly_update_rejects_missed_hour_and_membership_change(self):
        original = selection()
        later = selection(at_ms=T+2*H)
        with TemporaryDirectory() as folder:
            store = SQLiteBybitResearchStore(Path(folder) / "research.sqlite")
            stage_offline_bybit_research_cycle(
                selection=original, history=full_history(), store=store,
            )
            wrong = {s: fake_page(s, DECISION+H, 1, T+2*H) for s in SYMBOLS}
            with self.assertRaises(DataValidationError):
                append_offline_bybit_hourly_update(
                    previous=original, updated=later,
                    hourly_pages=wrong, store=store,
                )
            with self.assertRaises(DataGapError):
                store.replay_pit_research_snapshot(T+2*H)


if __name__ == "__main__":
    unittest.main()
