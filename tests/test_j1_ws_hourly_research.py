"""J1/OPS1 hourly research: no sockets, HTTP, orders or private REST database."""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from crypto_intelligence_agent.bybit_paginated_universe_research import BybitInstrumentScanResearch
from crypto_intelligence_agent.bybit_ws_hourly_research import replay_offline_ws_closed_hour
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from test_j1_bybit_closed_stream_cache import DECISION, scope as two_scope, message

ACK = {"success": True, "ret_msg": "subscribe", "conn_id": "fixture", "op": "subscribe"}


class WSLocalHourlyRankTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "ws-fixture.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.path)
        self.scope = two_scope()
        self.start = DECISION - 24 * HOUR_MS

    def batch(self, *, hour, symbols=("BTCUSDT", "ETHUSDT"), turnover=None, confirmed=True):
        frames = [(json.dumps(ACK), hour + 100)]
        for symbol in symbols:
            data = message(symbol, hour, turnover=(
                turnover.get(symbol, "2.50") if turnover is not None
                else ("3.50" if symbol == "BTCUSDT" else "2.50")
            ), confirmed=confirmed)
            frames.append((json.dumps(data), hour + HOUR_MS + 2000))
        return frames

    def run_hour(self, hour, *, scope=None, symbols=("BTCUSDT", "ETHUSDT"),
                 max_assets=2, turnover=None, confirmed=True):
        return replay_offline_ws_closed_hour(
            frames=self.batch(hour=hour, symbols=symbols, turnover=turnover, confirmed=confirmed),
            scope=scope or self.scope, journal=self.journal,
            closed_hour_ms=hour + HOUR_MS,
            as_of_ms=hour + HOUR_MS + 4000, max_assets=max_assets,
        )

    def test_24_closed_hours_then_3_consecutive_local_decisions_no_get(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            for offset in range(23):
                result = self.run_hour(self.start + offset * HOUR_MS)
                self.assertEqual(result.status, "offline_closed_hour_incomplete_abstain")
                with self.assertRaises(DataGapError):
                    result.selected_symbols()
            results = []
            for offset in range(23, 27):
                result = self.run_hour(self.start + offset * HOUR_MS)
                self.assertEqual(result.status, "offline_reviewed_hour_ready_not_marketwide")
                self.assertEqual(result.selected_symbols(), ("BTCUSDT", "ETHUSDT"))
                self.assertEqual(result.sanitized_report()["network_requests"], 0)
                results.append(result)
        self.assertEqual(results[-1].journal_rows, 54)
        self.assertEqual(results[-1].reviewed_scope_assets, 2)
        self.assertEqual(results[-1].complete_24h_assets, 2)
        self.assertEqual(results[-1].missing_24h_assets, 0)
        raw = json.dumps(results[-1].sanitized_report())
        self.assertNotIn("BTCUSDT", raw)
        self.assertNotIn("3.50", raw)
        self.assertFalse(results[-1].sanitized_report()["historical_720h_proven_by_ws"])
        self.assertFalse(results[-1].sanitized_report()["marketwide_top50_verified"])
        self.assertEqual(len({x.closed_hour_ms for x in results}), 4)

    def test_missing_52nd_member_must_abstain_even_when_50_have_candles(self):
        # The 52-base registry was first reviewed on 2026-10-29. Do NOT
        # backdate that identity claim into an earlier synthetic hour.
        fresh_first = self.start + 72 * HOUR_MS
        observed = fresh_first - 2 * HOUR_MS
        registry = load_reviewed_registry("expanded-52", as_of_ms=observed)
        symbols = tuple(asset.base + "USDT" for asset in registry.assets)
        self.assertEqual(len(symbols), 52)
        contracts = tuple(BybitLinearInstrumentResearch(
            symbol=s, base_coin=s[:-4], quote_coin="USDT", settle_coin="USDT",
            observed_at_ms=observed, launch_time_ms=observed - 7 * 86_400_000,
            max_leverage=Decimal("50"), tick_size=Decimal("0.01"),
            quantity_step=Decimal("0.001"), registry_sha256=registry.sha256_digest,
        ) for s in symbols)
        scan = BybitInstrumentScanResearch(observed, registry.sha256_digest,
                                           1, len(symbols), observed, contracts)
        reviewed = OfflineReviewedStreamScope.from_scan(scan, registry_variant="expanded-52")
        for i in range(24):
            hour = fresh_first + i * HOUR_MS
            got = self.run_hour(hour, scope=reviewed, symbols=symbols[:-1], max_assets=50)
        self.assertEqual(got.complete_24h_assets, 51)
        self.assertEqual(got.missing_24h_assets, 1)
        self.assertEqual(got.selected_assets, 0)
        self.assertIsNone(got.rank_digest_sha256)
        with self.assertRaises(DataGapError):
            got.selected_symbols()
        # A late replay is NOT entitled to pretend it received the candle
        # near its original closing time; the existing parser rejects staleness.
        old = fresh_first
        late = old + 3 * HOUR_MS + 2000
        with self.assertRaises(DataValidationError):
            replay_offline_ws_closed_hour(
                frames=[(json.dumps(ACK), late - 100),
                        (json.dumps(message(symbols[-1], old)), late)],
                scope=reviewed, journal=self.journal,
                closed_hour_ms=old+HOUR_MS,
                as_of_ms=old+HOUR_MS+4000, max_assets=50,
            )
        # Offline replay of previously recorded, authentic-looking CLOSED
        # fixtures fills the remaining 24h and permits a reviewed-sample rank.
        last_member_frames = [(json.dumps(ACK), fresh_first - 100)]
        for i in range(24):
            t = fresh_first + i * HOUR_MS
            last_member_frames.append((json.dumps(message(symbols[-1], t)),
                                       t+HOUR_MS+2000))
        got = replay_offline_ws_closed_hour(
            frames=last_member_frames, scope=reviewed, journal=self.journal,
            closed_hour_ms=fresh_first+24*HOUR_MS,
            as_of_ms=fresh_first+24*HOUR_MS+4000, max_assets=50,
        )
        self.assertEqual(got.status, "offline_reviewed_hour_ready_not_marketwide")
        self.assertEqual(got.reviewed_scope_assets, 52)
        self.assertEqual(got.complete_24h_assets, 52)
        self.assertEqual(got.selected_assets, 50)
        self.assertEqual(len(set(got.selected_symbols())), 50)
        self.assertFalse(got.sanitized_report()["marketwide_top50_verified"])
        # No repeated 52-by-24 REST scan: just 52 new closed WS events/hour.
        for i in range(24, 27):
            t = fresh_first + i * HOUR_MS
            got = self.run_hour(t, scope=reviewed, symbols=symbols, max_assets=50)
            self.assertEqual(got.appended_this_batch, 52)
            self.assertEqual(got.status, "offline_reviewed_hour_ready_not_marketwide")
            self.assertEqual(got.sanitized_report()["network_requests"], 0)

    def test_rolling_volume_changes_selection_without_more_rest_calls(self):
        for offset in range(24):
            got = self.run_hour(self.start + offset*HOUR_MS, max_assets=1)
        self.assertEqual(got.selected_symbols(), ("BTCUSDT",))
        next_hour = self.start + 24*HOUR_MS
        flipped = self.run_hour(next_hour, max_assets=1,
                                turnover={"BTCUSDT":"0", "ETHUSDT":"900"})
        self.assertEqual(flipped.selected_symbols(), ("ETHUSDT",))
        self.assertNotEqual(got.rank_digest_sha256, flipped.rank_digest_sha256)
        self.assertEqual(flipped.sanitized_report()["network_requests"], 0)

    def test_replay_idempotent_and_registry_drift_fails_closed(self):
        hour = self.start
        one = self.run_hour(hour)
        same = self.run_hour(hour)
        self.assertEqual(one.appended_this_batch, 2)
        self.assertEqual(same.appended_this_batch, 0)
        self.assertEqual(same.idempotent_replays, 2)
        from dataclasses import replace
        drift = replace(self.scope, registry_sha256="f" * 64)
        with self.assertRaises((DataValidationError, DataGapError)):
            self.run_hour(hour+HOUR_MS, scope=drift)

    def test_missing_ack_open_frames_and_invalid_clock_fail_closed(self):
        hour = self.start
        report = self.run_hour(hour, confirmed=False)
        self.assertEqual(report.appended_this_batch, 0)
        self.assertEqual(report.ignored_open_updates, 2)
        self.assertEqual(report.status, "offline_closed_hour_incomplete_abstain")
        with self.assertRaises(DataValidationError):
            replay_offline_ws_closed_hour(
                frames=self.batch(hour=hour)[1:], scope=self.scope,
                journal=self.journal, closed_hour_ms=hour+HOUR_MS,
                as_of_ms=hour+HOUR_MS+4000, max_assets=2,
            )
        with self.assertRaises(DataValidationError):
            replay_offline_ws_closed_hour(
                frames=[], scope=self.scope, journal=self.journal,
                closed_hour_ms=hour+HOUR_MS, as_of_ms=hour+HOUR_MS-1,
                max_assets=2,
            )
        with self.assertRaises(DataValidationError):
            replay_offline_ws_closed_hour(
                frames=[], scope=self.scope, journal=self.journal,
                closed_hour_ms=hour+HOUR_MS, as_of_ms=hour+HOUR_MS+4000,
                max_assets=51,
            )

    def test_gap_and_bad_frame_have_no_false_positive_rank(self):
        self.run_hour(self.start)
        later = self.start + 2*HOUR_MS
        with self.assertRaises(DataGapError):
            self.run_hour(later)
        self.assertEqual(self.journal.audit(
            scope=self.scope, decision_at_ms=self.start + HOUR_MS,
            as_of_ms=self.start + HOUR_MS + 4000,
        ).persisted_rows, 2)
        self.run_hour(self.start + HOUR_MS)
        fixed = self.run_hour(later)
        self.assertEqual(fixed.appended_this_batch, 2)
        self.assertEqual(fixed.status, "offline_closed_hour_incomplete_abstain")


if __name__ == "__main__":
    unittest.main()