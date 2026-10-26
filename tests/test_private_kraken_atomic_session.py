"""J1/WU43 atomic rollback across universe and all Kraken price-only pages.

All test data synthetic, all SQLite files private and temporary, no network.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.kraken_price_archive import SQLiteKrakenPriceOnlyArchive
from crypto_intelligence_agent.market_data import DataGapError, DuplicateCandleError
from crypto_intelligence_agent.private_kraken_research import capture_private_research
from test_private_kraken_research import (
    MultiReader, NOW, START, END, HOUR, collect,
)


def make_page(reader, symbol):
    return reader.staged_closed_candles(
        symbol=symbol, interval="1h",
        start_open_ms=START, end_open_ms=END,
    )


def counts(path: Path) -> tuple[int, int, int, int]:
    with sqlite3.connect(path) as conn:
        return tuple(conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                     for table in (
                         "universe_snapshots", "kraken_research_prices",
                         "kraken_research_price_pages", "candles",
                     ))


def existing_snapshot(archive: SQLiteKrakenPriceOnlyArchive):
    with sqlite3.connect(archive._path) as conn:
        row = conn.execute(
            """SELECT observed_at_ms, selection_rule_version, source
               FROM universe_snapshots""",
        ).fetchone()
    assert row is not None
    return archive.universe_snapshot(
        observed_at_ms=row[0], selection_rule_version=row[1], source=row[2],
    )


class ResearchSessionAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.db = Path(self.folder.name) / "private_session.sqlite"

    def tearDown(self):
        self.folder.cleanup()

    def test_late_eth_conflict_rolls_back_btc_and_new_universe_in_existing_db(self):
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        # Direct SQLite fixture creation honors the private-collector 0600 preflight.
        os.chmod(self.db, 0o600)
        seed = MultiReader()
        seed.current_market_snapshot()
        make_page(seed, "PF_XBTUSD")  # advance fake observation time
        eth = make_page(seed, "PF_ETHUSD")
        first = eth.staged.candles[0]
        corrupted = replace(
            eth, staged=replace(
                eth.staged,
                candles=(replace(first, open=first.open + Decimal(1)),
                         *eth.staged.candles[1:]),
            ),
        )
        self.assertEqual(archive.commit_price_only(corrupted), 3)
        self.assertEqual(counts(self.db), (0, 3, 1, 0))
        with self.assertRaises(DuplicateCandleError):
            collect(self.db, MultiReader(), registry_variant="expanded-10",
                    max_price_symbols=3)
        # The pre-WU43 collector would have persisted the new universe and
        # BTC page before failing on ETH. The new all-or-nothing collector must
        # retain only the already valid pre-existing ETH evidence.
        self.assertEqual(counts(self.db), (0, 3, 1, 0))
        self.assertEqual(archive.prices_as_of(
            symbol="PF_XBTUSD", interval="1h",
            start_open_ms=START, end_open_ms=END, as_of_ms=NOW + 900), ())
        self.assertEqual(len(archive.prices_as_of(
            symbol="PF_ETHUSD", interval="1h",
            start_open_ms=START, end_open_ms=END, as_of_ms=NOW + 900)), 3)

    def test_snapshot_conflict_rolls_back_without_any_price_page_write(self):
        baseline = collect(self.db, MultiReader(), registry_variant="expanded-10",
                           max_price_symbols=3)
        self.assertTrue(baseline.price_window_complete)
        self.assertEqual(counts(self.db), (1, 9, 3, 0))
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        # Direct SQLite fixture creation honors the private-collector 0600 preflight.
        os.chmod(self.db, 0o600)
        snapshot = existing_snapshot(archive)
        tampered = replace(
            snapshot, eligible=(
                replace(snapshot.eligible[0],
                        quote_volume=snapshot.eligible[0].quote_volume + Decimal(1)),
                *snapshot.eligible[1:],
            ),
        )
        reader = MultiReader()
        reader.current_market_snapshot()
        page = make_page(reader, "PF_XBTUSD")
        with self.assertRaises(DuplicateCandleError):
            archive.commit_research_session(tampered, (page,))
        self.assertEqual(counts(self.db), (1, 9, 3, 0))

    def test_successful_single_transaction_and_replay_do_not_duplicate(self):
        first = collect(self.db, MultiReader(), registry_variant="expanded-10",
                        max_price_symbols=3)
        self.assertEqual(first.private_price_candles_added, 9)
        self.assertEqual(counts(self.db), (1, 9, 3, 0))
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        # Direct SQLite fixture creation honors the private-collector 0600 preflight.
        os.chmod(self.db, 0o600)
        snapshot = existing_snapshot(archive)
        before = archive.prices_as_of(
            symbol="PF_XBTUSD", interval="1h",
            start_open_ms=START, end_open_ms=END, as_of_ms=NOW + 1000)
        self.assertEqual(len(before), 3)
        second = collect(self.db, MultiReader(), registry_variant="expanded-10",
                         max_price_symbols=3)
        self.assertEqual(second.private_price_candles_added, 0)
        self.assertTrue(second.price_window_complete)
        self.assertEqual(counts(self.db), (1, 9, 3, 0))
        self.assertEqual(
            archive.prices_as_of(
                symbol="PF_XBTUSD", interval="1h",
                start_open_ms=START, end_open_ms=END, as_of_ms=NOW + 1000),
            before,
        )
        self.assertEqual(existing_snapshot(archive), snapshot)

    def test_standalone_legacy_writers_still_atomic_and_idempotent(self):
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        # Direct SQLite fixture creation honors the private-collector 0600 preflight.
        os.chmod(self.db, 0o600)
        reader = MultiReader()
        reader.current_market_snapshot()
        page = make_page(reader, "PF_XBTUSD")
        self.assertEqual(archive.commit_price_only(page), 3)
        self.assertEqual(archive.commit_price_only(page), 0)
        self.assertEqual(counts(self.db), (0, 3, 1, 0))
        collect_result = collect(
            self.db, MultiReader(), registry_variant="expanded-10",
            max_price_symbols=1,
        )
        self.assertEqual(collect_result.private_price_candles_added, 0)
        self.assertEqual(counts(self.db), (1, 3, 1, 0))

    def test_duplicate_symbol_batch_preflight_never_writes_snapshot(self):
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        # Direct SQLite fixture creation honors the private-collector 0600 preflight.
        os.chmod(self.db, 0o600)
        # Create just a universe snapshot through the already-valid pipeline
        # and then remove only its rows to simulate an unpopulated research DB.
        collect(self.db, MultiReader(), registry_variant="expanded-10",
                max_price_symbols=1)
        snapshot = existing_snapshot(archive)
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM universe_snapshots")
            conn.execute("DELETE FROM kraken_research_price_pages")
            conn.execute("DELETE FROM kraken_research_prices")
        self.assertEqual(counts(self.db), (0, 0, 0, 0))
        reader = MultiReader()
        reader.current_market_snapshot()
        page = make_page(reader, "PF_XBTUSD")
        with self.assertRaises(DataGapError):
            archive.commit_research_session(snapshot, (page, page))
        self.assertEqual(counts(self.db), (0, 0, 0, 0))

    def test_invalid_batch_shape_rejected_without_database_mutation(self):
        collect(self.db, MultiReader(), registry_variant="expanded-10",
                max_price_symbols=1)
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        # Direct SQLite fixture creation honors the private-collector 0600 preflight.
        os.chmod(self.db, 0o600)
        snapshot = existing_snapshot(archive)
        before = counts(self.db)
        reader = MultiReader()
        reader.current_market_snapshot()
        page = make_page(reader, "PF_XBTUSD")
        for bad in ((), [page], (page,) * 6, None):
            with self.subTest(batch=str(type(bad))), self.assertRaises(DataGapError):
                archive.commit_research_session(snapshot, bad)
        with self.assertRaises(DataGapError):
            archive.commit_research_session(object(), (page,))
        self.assertEqual(counts(self.db), before)


if __name__ == "__main__":
    unittest.main()
