"""J1/EXIT: end-to-end no-network PIT 24h -> SQLite snapshots -> 30d replay.

Strict fixtures imitate GET responses; they are never provider observations.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_pit_research import (
    HOUR_MS as H, select_bybit_reviewed_sample_pit,
)
from crypto_intelligence_agent.bybit_local_json_audit import LocalBybitCaptureManifest
from crypto_intelligence_agent.bybit_research_series import inspect_existing_bybit_research_series
from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError, DuplicateCandleError
from test_bybit_paginated_universe_research import instrument_row, instrument_page

T = 1793000000000
DECISION = (T // H) * H
SYMBOLS = ("BTCUSDT", "ETHUSDT")


def rows_for(symbol, first_open_ms, count, volume):
    return [
        [str(first_open_ms + i * H), "100", "105", "95", "101",
         "1.25", str(volume)]
        for i in range(count - 1, -1, -1)
    ]


def kline(symbol, first_open_ms, count, volume):
    return {
        "retCode": 0,
        "result": {
            "category": "linear", "symbol": symbol,
            "list": rows_for(symbol, first_open_ms, count, volume),
        },
    }


def pages(at_ms=T):
    first = instrument_row("BTCUSDT", launchTime=str(T - 1000 * H))
    second = instrument_row("ETHUSDT", launchTime=str(T - 1000 * H))
    return (
        instrument_page([first], ms=at_ms - 300, cursor="next"),
        instrument_page([second], ms=at_ms - 200, cursor=""),
    )


def selection(at_ms=T, volumes=(("BTCUSDT", "10"), ("ETHUSDT", "20")),
              source_pages=None, payloads=None, cutoff=None, max_candidates=50):
    point = (at_ms // H) * H if cutoff is None else cutoff
    result = select_bybit_reviewed_sample_pit(
        instrument_pages=pages(at_ms) if source_pages is None else source_pages,
        requested_cursors=(None, "next"),
        kline_pages=({sym: kline(sym, point - 24 * H, 24, amount)
                      for sym, amount in volumes} if payloads is None else payloads),
        observed_at_ms=at_ms,
        decision_at_ms=point,
        max_candidates=max_candidates,
    )
    return result


class BybitPITExitTests(unittest.TestCase):
    def test_rank_only_closed_documented_usdt_with_pit_timestamp(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            out = selection()
        self.assertEqual([m.symbol for m in out.ranked], ["ETHUSDT", "BTCUSDT"])
        self.assertEqual([m.observed_turnover_24h_usdt for m in out.ranked],
                         [Decimal("480"), Decimal("240")])
        self.assertEqual(out.decision_at_ms, DECISION)
        self.assertEqual(out.observed_at_ms, T)
        self.assertEqual(out.candidates_with_full_24h_count, 2)
        self.assertEqual(out.instrument_page_count, 2)
        self.assertFalse(out.verified_market_top50)
        self.assertFalse(out.rights_for_live_authorized)
        self.assertFalse(out.canonical_ohlcv_approved)
        self.assertFalse(out.orders_sent)
        self.assertEqual(out, selection(volumes=(("ETHUSDT", "20"), ("BTCUSDT", "10"))))
        tie = selection(volumes=(("ETHUSDT", "10"), ("BTCUSDT", "10")))
        self.assertEqual([x.symbol for x in tie.ranked], list(SYMBOLS))
        self.assertEqual(len(selection(max_candidates=1).ranked), 1)

    def test_reject_partial_wrong_or_future_kline_and_untrusted_scan(self):
        required = {
            symbol: kline(symbol, DECISION - 24*H, 24, "1")
            for symbol in SYMBOLS
        }
        variants = []
        missing = deepcopy(required)
        missing.pop("ETHUSDT")
        variants.append(missing)
        extra = deepcopy(required)
        extra["SOLUSDT"] = kline("SOLUSDT", DECISION-24*H, 24, "1")
        variants.append(extra)
        duplicate = deepcopy(required)
        duplicate["BTCUSDT"]["result"]["list"][1][0] = duplicate["BTCUSDT"]["result"]["list"][0][0]
        variants.append(duplicate)
        outoforder = deepcopy(required)
        outoforder["BTCUSDT"]["result"]["list"][0][0] = str(DECISION)
        variants.append(outoforder)
        nan = deepcopy(required)
        nan["ETHUSDT"]["result"]["list"][3][6] = "NaN"
        variants.append(nan)
        short = deepcopy(required)
        short["BTCUSDT"]["result"]["list"].pop()
        variants.append(short)
        for variant in variants:
            with self.subTest(cases=len(variant)), self.assertRaises(
                (DataGapError, DataValidationError)
            ):
                selection(payloads=variant)
        for invalid in (DECISION - H, DECISION + H, DECISION + 1, True):
            with self.subTest(invalid=invalid), self.assertRaises(DataValidationError):
                selection(cutoff=invalid)
        with self.assertRaises(DataValidationError):
            selection(max_candidates=True)
        non_terminal = pages()[:1]
        with self.assertRaises(DataValidationError):
            select_bybit_reviewed_sample_pit(
                instrument_pages=non_terminal,
                requested_cursors=(None,),
                kline_pages=required, observed_at_ms=T,
                decision_at_ms=DECISION,
            )

    def test_prelisting_and_insufficient_listed_history_fail_closed(self):
        group = list(pages())
        shortened = deepcopy(group[1])
        shortened["result"]["list"][0]["launchTime"] = str(DECISION - 4*H)
        group[1] = shortened
        answer = selection(source_pages=tuple(group),
                           payloads={"BTCUSDT": kline("BTCUSDT", DECISION-24*H, 24, "1")})
        self.assertEqual(len(answer.ranked), 1)
        self.assertEqual(answer.insufficient_listing_history_count, 1)
        self.assertFalse(answer.verified_market_top50)
        # A future-listed contract is never backdated into a historical rank.
        group[1]["result"]["list"][0]["launchTime"] = str(T + H)
        with self.assertRaises(DataValidationError):
            selection(source_pages=tuple(group))

    def test_immutable_pit_sqlite_snapshots_conflicts_corruption_and_two_hours(self):
        with TemporaryDirectory() as folder:
            db_file = Path(folder) / "bybit-research.sqlite"
            store = SQLiteBybitResearchStore(db_file)
            first = selection()
            store.commit_pit_research_snapshot(first)
            store.commit_pit_research_snapshot(first)
            self.assertEqual(store.replay_pit_research_snapshot(T), first)
            with self.assertRaises(DuplicateCandleError):
                store.commit_pit_research_snapshot(replace(first, ranked=tuple(reversed(first.ranked))))
            with self.assertRaises(DataGapError):
                store.replay_pit_research_snapshot(T + 1)
            second = selection(at_ms=T+H, volumes=(("BTCUSDT", "30"), ("ETHUSDT", "1")))
            store.commit_pit_research_snapshot(second)
            self.assertEqual(store.replay_pit_research_snapshot(T+H), second)
            self.assertEqual([x.symbol for x in second.ranked], ["BTCUSDT", "ETHUSDT"])
            with self.assertRaises(DataValidationError):
                store.commit_pit_research_snapshot(selection(at_ms=T-H))
            with sqlite3.connect(db_file) as db:
                db.execute("UPDATE bybit_research_pit_snapshots SET content_json='{}' WHERE observed_at_ms=?", (T,))
            with self.assertRaises(DataGapError):
                store.replay_pit_research_snapshot(T)

    def test_30_days_two_assets_existing_sqlite_storage_replay(self):
        cutoff = DECISION
        first_open = cutoff - 720*H
        with TemporaryDirectory() as folder:
            path = Path(folder) / "research.sqlite"
            store = SQLiteBybitResearchStore(path)
            store.commit_pit_research_snapshot(selection())
            for symbol in SYMBOLS:
                raw_instrument = instrument_page([
                    instrument_row(symbol, launchTime=str(T-1000*H))
                ], ms=T-50, cursor="")
                instrument_bytes = json.dumps(raw_instrument).encode("ascii")
                for index in range(10):
                    start = first_open + index*72*H
                    end = start+72*H
                    candles = kline(symbol, start, 72, "1000")
                    kline_bytes = json.dumps(candles).encode("ascii")
                    manifest = LocalBybitCaptureManifest(
                        symbol=symbol, interval="1h", registry_variant="expanded-13",
                        start_open_ms=start, end_open_ms=end,
                        capture_started_ms=T-1000,
                        instrument_received_ms=T,
                        kline_received_ms=T+1000,
                        capture_finished_ms=T+2000,
                    )
                    with patch("socket.create_connection", side_effect=AssertionError("network")):
                        saved = store.commit_raw_pair(
                            instrument_raw=instrument_bytes,
                            kline_raw=kline_bytes, manifest=manifest,
                        )
                    self.assertEqual(len(saved.candles), 72)
                    if index == 0:
                        self.assertEqual(saved, store.commit_raw_pair(
                            instrument_raw=instrument_bytes,
                            kline_raw=kline_bytes, manifest=manifest,
                        ))
                audit = store.quality_report(
                    symbol=symbol, interval="1h",
                    start_open_ms=first_open, end_open_ms=cutoff,
                )
                self.assertEqual(audit.expected_candles, 720)
                self.assertEqual(audit.persisted_candles, 720)
                self.assertEqual(audit.missing_open_times_ms, ())
                self.assertTrue(audit.complete_for_offline_staging_only)
                self.assertFalse(audit.canonical_ohlcv_approved)
                self.assertFalse(audit.rights_authorized)
            path.chmod(0o600)
            for symbol in SYMBOLS:
                result = inspect_existing_bybit_research_series(
                    path, symbol=symbol, interval="1h",
                    start_open_ms=first_open, end_open_ms=cutoff,
                    as_of_ms=T+5000,
                )
                self.assertEqual(len(result.candles), 720)
                self.assertEqual(result.page_count, 10)
                self.assertFalse(result.canonical_ohlcv_approved)
            self.assertEqual(store.replay_pit_research_snapshot(T), selection())


if __name__ == "__main__":
    unittest.main()
