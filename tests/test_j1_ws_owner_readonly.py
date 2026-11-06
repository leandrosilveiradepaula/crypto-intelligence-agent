"""OPS1 read-only owner WS observer: no real sockets or REST calls."""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS as H, SQLiteOfflineClosedStreamJournal,
    parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient
from crypto_intelligence_agent.bybit_ws_owner_pilot import _catalog_scope, _write_new_scope
from crypto_intelligence_agent.j1_ws_owner_readonly import audit_owner_ws_journal
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from test_bybit_paginated_universe_research import instrument_row, instrument_page
from test_j1_bybit_closed_stream_cache import message

T = 1793534405000  # existing expanded-52 fixture PIT capture
DECISION = (T // H + 25) * H
SEEN = DECISION + 4000


class OwnerWSReadonlyTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix" or os.geteuid() == 0:
            self.skipTest("POSIX nonroot owner-only audit")
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        self.directory.chmod(0o700)
        registry = load_reviewed_registry("expanded-52", as_of_ms=T)
        bases = tuple(m.base for m in registry.assets)
        symbols = tuple(b + "USDT" for b in bases)
        def transport(url, limit):
            from urllib.parse import parse_qs, urlsplit
            cursor = parse_qs(urlsplit(url).query).get("cursor", [None])[0]
            if cursor is None:
                return json.dumps(instrument_page(
                    [instrument_row(s) for s in symbols[:26]],
                    ms=T - 200, cursor="second")).encode("ascii")
            if cursor == "second":
                return json.dumps(instrument_page(
                    [instrument_row(s) for s in symbols[26:]],
                    ms=T - 200, cursor="")).encode("ascii")
            raise AssertionError("unexpected page")
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            scope, pages = _catalog_scope(client=BoundedBybitPublicClient(transport=transport),
                                          clock_ms=lambda: T)
        self.assertEqual((len(scope.contracts), pages), (52, 2))
        self.scope = scope
        _write_new_scope(self.directory / "ws-reviewed-scope.json", scope)
        self.path = self.directory / "ws-confirmed.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.path)

    def audit(self, *, decision=DECISION, at=SEEN, optin=True, directory=None):
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            return audit_owner_ws_journal(
                directory=self.directory if directory is None else directory,
                decision_at_ms=decision, observed_at_ms=at,
                allow_private_readonly_audit=optin,
            )

    def put(self, index, symbols=None):
        start = DECISION - (24 - index) * H
        for contract in self.scope.contracts if symbols is None else self.scope.contracts[:symbols]:
            event = parse_offline_confirmed_kline(
                message(contract.symbol, start), scope=self.scope,
                received_at_ms=start + H + 2000,
            )
            self.journal.append(event)

    def test_default_no_io_and_missing_directory(self):
        with patch("crypto_intelligence_agent.j1_ws_owner_readonly._read_epoch_chain",
                   side_effect=AssertionError("private read forbidden")):
            self.assertEqual(self.audit(optin=False)["status"], "owner_gate_required")
            self.assertEqual(self.audit(decision=DECISION + 1)["status"], "owner_gate_required")
        self.assertEqual(self.audit(directory=self.directory / "missing")["status"],
                         "owner_directory_unavailable")

    def test_fresh_scope_but_no_candles_reports_incomplete(self):
        r = self.audit()
        self.assertEqual(r["status"], "reviewed_ws_sample_incomplete")
        self.assertEqual(r["reviewed_scope_members"], 52)
        self.assertEqual((r["complete_24h_members"], r["missing_24h_members"]),(0,52))
        self.assertEqual(r["scope_epochs"], 1)
        for field in ("worker_running_verified", "source_authenticated",
                      "marketwide_top50_verified", "canonical_ohlcv_approved",
                      "live_trading_authorized", "orders_sent"):
            self.assertFalse(r[field])
        self.assertNotIn("BTCUSDT",json.dumps(r))

    def test_24h_full_window_reuses_strict_pit_journal_audit(self):
        for index in range(24):
            self.put(index)
        before = self.path.stat().st_size
        r = self.audit()
        self.assertEqual(r["status"],"reviewed_ws_sample_complete_unverified")
        self.assertEqual((r["persisted_rows"],r["complete_24h_members"],
                          r["missing_24h_members"]),(1248,52,0))
        self.assertEqual(r["scope_age_ms"],SEEN-T)
        self.assertIsNotNone(r["rank_digest_sha256"])
        self.assertEqual(self.path.stat().st_size,before)
        self.assertEqual(r,self.audit())
        self.assertEqual(r["database_mutation_statements"],0)
        self.assertFalse(r["worker_running_verified"])

    def test_partial_and_future_hours_do_not_fill_missing(self):
        for index in range(23):
            self.put(index,symbols=2)
        r=self.audit()
        self.assertEqual(r["status"],"reviewed_ws_sample_incomplete")
        self.assertEqual(r["complete_24h_members"],0)
        self.assertIsNone(r["rank_digest_sha256"])
        self.assertEqual(self.audit(decision=DECISION+H,at=DECISION+H+4000)["status"],
                         "reviewed_ws_sample_incomplete")

    def test_tampered_digest_and_missing_journal_veto(self):
        self.put(0,symbols=1)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE confirmed SET digest=? WHERE symbol=?",
                         ("0"*64,self.scope.contracts[0].symbol))
        self.assertEqual(self.audit()["status"],"journal_audit_abstain")
        self.path.unlink()
        self.assertEqual(self.audit()["status"],"journal_missing_or_invalid")

    def test_snapshot_coming_after_close_cannot_rewrite_past(self):
        original=self.directory/"ws-reviewed-scope.json"
        # Replacing scope with forged bytes or a symlink must not be accepted.
        raw=original.read_bytes()
        original.write_bytes(raw.replace(b"j1-owner-ws-reviewed-scope-v1",
                                         b"j1-owner-ws-reviewed-scope-v9"))
        self.assertEqual(self.audit()["status"],"scope_missing_or_invalid")
        original.write_bytes(raw)
        original.unlink()
        original.symlink_to(self.path)
        self.assertEqual(self.audit()["status"],"scope_missing_or_invalid")

    def test_expired_scope_fail_closed_and_rejects_clock_leak(self):
        self.assertEqual(self.audit(at=DECISION+60_001)["status"],"owner_gate_required")
        later=DECISION+24*H
        self.assertEqual(self.audit(decision=later,at=later+4000)["status"],
                         "scope_stale")


if __name__=="__main__":
    unittest.main()
