"""Offline contract of persistent LOCAL BTC/ETH market research collection."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from crypto_intelligence_agent.crypto_asset_registry import load_registry_json
from crypto_intelligence_agent.kraken_candle_validation import (
    stage_kraken_trade_candles,
)
from crypto_intelligence_agent.kraken_public_readonly import (
    KrakenCapturedCandleResearchPage, KrakenCurrentResearchSnapshot,
)
from crypto_intelligence_agent.kraken_price_archive import SQLiteKrakenPriceOnlyArchive
from crypto_intelligence_agent.market_data import (
    DataGapError, DataValidationError, DuplicateCandleError, ExchangeAccessError,
)
from crypto_intelligence_agent.private_kraken_research import (
    LocalResearchError, _REPO_ROOT, _REGISTRY_PATH, capture_private_research,
)

REGISTRY = load_registry_json(_REGISTRY_PATH.read_bytes())
HOUR = 3_600_000
NOW = REGISTRY.observed_at_ms + 2 * HOUR
TOP = (NOW // HOUR) * HOUR
START, END = TOP - 4 * HOUR, TOP - HOUR


def instrument(symbol, base, *, category=None, pair=None):
    return {
        "symbol": symbol, "base": base, "quote": "USD",
        "pair": pair or (base + ":USD"), "category": category,
        "tradfi": False, "type": "flexible_futures", "tradeable": True,
        "suspended": False, "isExpired": False, "tickSize": "1", "contractSize": 1,
    }


def ticker(symbol, quote):
    return {
        "symbol": symbol, "tag": "perpetual", "postOnly": False,
        "suspended": False, "volumeQuote": Decimal(quote),
    }


def market(*, btc=True, forged=False, start=NOW + 20, end=NOW + 80):
    contracts = [instrument("PF_ETHUSD", "ETH"),
                 instrument("PF_AAPLXUSD", "AAPLX", category="xStocks")]
    if btc:
        contracts.append(instrument(
            "PF_XBTUSD", "AAPLX" if forged else "BTC",
            pair="AAPLX:USD" if forged else "XBT:USD",
        ))
    tickers = [
        ticker("PF_XBTUSD", "123456789.0123456789"),
        ticker("PF_ETHUSD", "103456789.0123456789"),
        ticker("PF_AAPLXUSD", "9999999999999999"),
    ]
    return KrakenCurrentResearchSnapshot(
        captured_start_ms=start, captured_end_ms=end,
        instruments=tuple(contracts), tickers=tuple(tickers),
    )


def price_page(*, price_change=0, observed=NOW + 400, gap=False):
    rows = [
        {"time": START + i * HOUR,
         "open": str(Decimal("101.123456789123456789") + price_change),
         "high": "120", "low": "90",
         "close": "105.987654321987654321",
         "volume": "77.123456789987654321"}
        for i in range(3)
    ]
    if gap:
        rows.pop(1)
        rows.append({
            "time": END, "open": "101", "high": "120", "low": "90",
            "close": "105", "volume": "77",
        })
    return KrakenCapturedCandleResearchPage(
        observed_at_ms=observed,
        staged=stage_kraken_trade_candles(
            {"candles": rows, "more_candles": False},
            symbol="PF_XBTUSD", interval="1h",
            start_open_ms=START, end_open_ms=END,
            observed_at_ms=observed,
        ),
    )


class Reader:
    def __init__(self, *, market_value=None, page=None, error=None):
        self.market = market_value if market_value is not None else market()
        self.page = page
        self.error = error
        self.calls = []

    def current_market_snapshot(self):
        self.calls.append("instruments_and_tickers")
        if self.error is not None:
            raise self.error
        return self.market

    def staged_closed_candles(self, *, symbol, interval, start_open_ms, end_open_ms):
        self.calls.append("chart")
        assert (symbol, interval, start_open_ms, end_open_ms) == (
            "PF_XBTUSD", "1h", START, END)
        return price_page() if self.page is None else self.page


def collect(path, reader, *, now=NOW, decide=NOW + 200, **kwargs):
    values = iter((now, decide))
    return capture_private_research(
        db_path=path, client=reader,
        clock_ms=lambda: next(values),
        allow_public_network=True, allow_private_persistence=True, **kwargs,
    )


class PrivateLocalResearchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "user_private.sqlite"

    def tearDown(self):
        self.folder.cleanup()

    def test_local_same_db_persists_real_registry_selection_and_price_only(self):
        client = Reader()
        result = collect(self.db, client)
        self.assertEqual(client.calls, ["instruments_and_tickers", "chart"])
        self.assertEqual(result.eligible_contracts, 2)
        self.assertEqual(result.selected_bases_limit, 2)
        self.assertEqual(result.private_price_candles_added, 3)
        self.assertEqual(result.price_candles_in_window, 3)
        self.assertTrue(result.price_window_complete)
        self.assertFalse(result.canonical_ohlcv_approved)
        self.assertFalse(result.historical_top50_approved)
        self.assertFalse(result.public_or_commercial_rights_approved)
        self.assertFalse(result.orders_sent)
        self.assertFalse(hasattr(result, "database_path"))
        self.assertEqual(result.registry_sha256, REGISTRY.sha256_digest)
        self.assertTrue(self.db.is_file())
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM universe_snapshots").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_prices").fetchone()[0], 3)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM candles").fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM checkpoints").fetchone()[0], 0)
            fields = [r[1] for r in conn.execute(
                "PRAGMA table_info(kraken_research_prices)").fetchall()]
            self.assertFalse(any("volume" in field for field in fields))
        archive = SQLiteKrakenPriceOnlyArchive(self.db)
        rows = archive.prices_as_of(
            symbol="PF_XBTUSD", interval="1h", start_open_ms=START,
            end_open_ms=END, as_of_ms=NOW + 400,
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].open, Decimal("101.123456789123456789"))
        self.assertEqual(rows[0].first_observed_at_ms, NOW + 400)
        self.assertFalse(rows[0].canonical_ohlcv)
        self.assertFalse(hasattr(rows[0], "quote_volume"))

    def test_expanded_ten_base_manifest_is_explicit_and_preserves_price_only(self):
        reader = Reader()
        result = collect(self.db, reader, registry_variant="expanded-10")
        self.assertEqual(result.selected_bases_limit, 10)
        # Fake exchange holds only BTC+ETH; the other eight are NOT invented.
        self.assertEqual(result.eligible_contracts, 2)
        self.assertEqual(result.private_price_candles_added, 3)
        self.assertTrue(result.price_window_complete)
        self.assertFalse(result.historical_top50_approved)
        self.assertFalse(result.canonical_ohlcv_approved)
        self.assertEqual(reader.calls, ["instruments_and_tickers", "chart"])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 0)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM kraken_research_prices").fetchone()[0], 3)

    def test_expanded_registry_revision_rejects_unrecognized_choice_pre_network(self):
        reader = Reader()
        with self.assertRaises(DataValidationError):
            collect(self.db, reader, registry_variant="arbitrary-external.json")
        self.assertEqual(reader.calls, [])
        self.assertFalse(self.db.exists())

    def test_cross_session_replay_is_idempotent(self):
        self.assertEqual(collect(self.db, Reader()).private_price_candles_added, 3)
        replay = collect(self.db, Reader())
        self.assertEqual(replay.private_price_candles_added, 0)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_price_pages").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_prices").fetchone()[0], 3)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM universe_snapshots").fetchone()[0], 1)

    def test_conflicting_replay_fails_without_corrupting_existing_prices(self):
        collect(self.db, Reader())
        bad = Reader(page=price_page(price_change=1))
        with self.assertRaises(DuplicateCandleError):
            collect(self.db, bad)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_prices").fetchone()[0], 3)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM kraken_research_price_pages").fetchone()[0], 1)

    def test_requires_both_optins_before_disk_or_network(self):
        reader = Reader()
        for a, b in ((False, False), (True, False), (False, True)):
            with self.subTest(a=a, b=b), self.assertRaises(LocalResearchError):
                capture_private_research(
                    db_path=self.db, allow_public_network=a,
                    allow_private_persistence=b, client=reader,
                    clock_ms=lambda: NOW)
        self.assertEqual(reader.calls, [])
        self.assertFalse(self.db.exists())

    def test_private_directory_and_repo_path_preflight_without_network(self):
        reader = Reader()
        for wrong in (
            self.folder.name + "/relative.txt",
            "some/relative.sqlite", _REPO_ROOT / "research.sqlite",
            Path("/tmp") / "world_readable.sqlite",
        ):
            with self.subTest(wrong=str(wrong)), self.assertRaises(LocalResearchError):
                collect(wrong, reader)
        self.assertEqual(reader.calls, [])
        self.assertFalse(self.db.exists())

    def test_rejects_public_existing_db_permissions_before_get(self):
        self.db.touch()
        os.chmod(self.db, 0o644)
        reader = Reader()
        with self.assertRaises(LocalResearchError):
            collect(self.db, reader)
        self.assertEqual(reader.calls, [])

    def test_registry_stale_and_future_fail_without_api_or_db(self):
        reader = Reader()
        with self.assertRaises(LocalResearchError):
            collect(self.db, reader, now=REGISTRY.observed_at_ms - 1)
        with self.assertRaises(LocalResearchError):
            collect(self.db, reader,
                    now=REGISTRY.observed_at_ms + 8 * 86_400_000)
        self.assertEqual(reader.calls, [])
        self.assertFalse(self.db.exists())

    def test_no_btc_eligibility_stops_before_chart_and_database(self):
        for market_value in (market(btc=False), market(forged=True)):
            reader = Reader(market_value=market_value)
            with self.subTest(market_value=repr(market_value)[:80]):
                with self.assertRaises(LocalResearchError):
                    collect(self.db, reader)
                self.assertEqual(reader.calls, ["instruments_and_tickers"])
        self.assertFalse(self.db.exists())

    def test_invalid_clock_after_metadata_stops_before_chart(self):
        reader = Reader(market_value=market(start=NOW - 1))
        with self.assertRaises(LocalResearchError):
            collect(self.db, reader)
        self.assertEqual(reader.calls, ["instruments_and_tickers"])
        reader = Reader()
        with self.assertRaises(LocalResearchError):
            collect(self.db, reader, decide=NOW + 50)
        self.assertEqual(reader.calls, ["instruments_and_tickers"])
        self.assertFalse(self.db.exists())

    def test_bad_chart_rejected_before_any_database_creation(self):
        from dataclasses import replace
        ok = price_page()
        bad = replace(ok, staged=replace(
            ok.staged, candles=ok.staged.candles[:2]))
        reader = Reader(page=bad)
        with self.assertRaises(DataGapError):
            collect(self.db, reader)
        self.assertEqual(reader.calls, ["instruments_and_tickers", "chart"])
        self.assertFalse(self.db.exists())

    def test_exchange_access_error_never_retried(self):
        client = Reader(error=ExchangeAccessError("HTTP451"))
        with self.assertRaises(ExchangeAccessError):
            collect(self.db, client)
        self.assertEqual(client.calls, ["instruments_and_tickers"])
        self.assertFalse(self.db.exists())

    def test_help_and_disabled_cli_without_network_or_leaking_path(self):
        root = Path(__file__).resolve().parent.parent
        help_result = subprocess.run(
            [sys.executable, "-m", "scripts.collect_private_kraken_research", "--help"],
            cwd=root, text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--allow-private-persistence", help_result.stdout)
        disabled = subprocess.run(
            [sys.executable, "-m", "scripts.collect_private_kraken_research",
             "--database", str(self.db)],
            cwd=root, text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(disabled.returncode, 1)
        self.assertEqual(json.loads(disabled.stdout)["status"], "double_opt_in_required")
        self.assertNotIn(str(self.db), disabled.stdout)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
