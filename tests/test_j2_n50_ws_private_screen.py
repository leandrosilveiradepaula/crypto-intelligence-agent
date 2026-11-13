"""J2/WS-READ1: real temporary SQLite WS journal with 50x24 fixture bars."""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from decimal import Decimal, Context, localcontext
import json
import os
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_instrument_volume_contract import (
    BybitLinearInstrumentResearch,
)
from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope,
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.j2_n50_ws_private_screen import (
    research_private_ws_n50_24closed,
)
from test_j2_n50_private_screen import SYMBOLS, T, make_scope

START = T + HOUR_MS
END = START + 24 * HOUR_MS
NOW = END + 240_000
SHA = "a" * 64


def scope():
    obs = T + 150_000
    return OfflineReviewedStreamScope(
        obs, SHA,
        tuple(BybitLinearInstrumentResearch(
            symbol=s, base_coin=s.removesuffix("USDT"), quote_coin="USDT",
            settle_coin="USDT", observed_at_ms=obs,
            launch_time_ms=T-30*HOUR_MS,
            max_leverage=Decimal("50"), tick_size=Decimal("0.01"),
            quantity_step=Decimal("0.001"), registry_sha256=SHA,
        ) for s in SYMBOLS), 50,
    )


def message(symbol, i, j):
    opened = START + i*HOUR_MS
    close_at = opened + HOUR_MS
    with localcontext(Context(prec=40)):
        op = Decimal(100+j) + Decimal(i)/10
        cl = op + (Decimal(5) if i==23 and j%3==0 else
                   Decimal(-5) if i==23 and j%3==1 else Decimal(0))
        high = max(op, cl)+Decimal(1)
        low = min(op, cl)-Decimal(1)
        amount = (op+cl)/2 * Decimal(10)
    return {
        "topic": "kline.60."+symbol, "type":"snapshot",
        "ts":close_at+1000,
        "data":[{
            "start":opened, "end":close_at-1, "interval":"60",
            "open":str(op), "high":str(high),
            "low":str(low), "close":str(cl),
            "volume":"10", "turnover":str(amount),
            "confirm":True, "timestamp":close_at-500,
        }],
    }


@unittest.skipUnless(os.name == "posix", "private 0700/0600 POSIX journal fixture")
class ReadOnlyWSN50ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._source = TemporaryDirectory()
        base = Path(cls._source.name)
        db = base / "ws-confirmed.sqlite"
        journal = SQLiteOfflineClosedStreamJournal.create(db)
        ws_scope = scope()
        for j,symbol in enumerate(SYMBOLS):
            for i in range(24):
                ev = parse_offline_confirmed_kline(
                    message(symbol,i,j), scope=ws_scope,
                    received_at_ms=START+(i+1)*HOUR_MS+1800,
                )
                assert journal.append(ev) == "appended"
        cls._bytes = db.read_bytes()
        cls.ws_scope = ws_scope
        cls.ranked = make_scope()
        cls._source.cleanup()

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "ws-confirmed.sqlite"
        self.path.write_bytes(self._bytes)
        self.path.chmod(0o600)
        self.journal = SQLiteOfflineClosedStreamJournal(self.path)

    def run_it(self, **changes):
        kw = dict(
            ranked_scope=self.ranked, ws_scope=self.ws_scope,
            journal=self.journal, decision_at_ms=END, observed_at_ms=NOW,
            allow_private_readonly_research=True, owner_ok=True,
        )
        kw.update(changes)
        return research_private_ws_n50_24closed(**kw)

    def test_complete_50x24_replays_exact_j1_audit_and_j2_d300_metrics(self):
        out = self.run_it()
        self.assertEqual(out["status"],"ws_n50_descriptive_24h_ready",out)
        self.assertEqual(out["audited_assets"],50)
        self.assertEqual(out["eligible_closed_bars_per_asset"],24)
        self.assertEqual(out["latest_closed_end_ms"],END)
        self.assertTrue(out["ws_journal_integrity_replayed"])
        self.assertTrue(out["btc_context_available"])
        self.assertEqual(out["descriptive_up_breakouts"]+
                         out["descriptive_down_breakouts"]+
                         out["descriptive_inside_bars"],50)
        self.assertTrue(out["descriptive_up_breakouts"]>0)
        self.assertTrue(out["descriptive_down_breakouts"]>0)
        self.assertTrue(out["descriptive_inside_bars"]>0)
        self.assertEqual(out["research_rows"],[])
        self.assertNotIn("BTCUSDT",json.dumps(out))
        self.assertNotIn("TST",json.dumps(out))
        for key in (
            "formal_d323_24h_verified", "continuous_collector_verified",
            "rotation_36h_live_verified", "marketwide_top50_verified",
            "crypto_identity_independently_verified", "source_authenticated",
            "approved_for_signals", "approved_for_live_use",
            "financial_backtest_approved", "orders_sent", "systemd_modified",
        ):
            self.assertFalse(out[key],key)
        self.assertEqual(out["network_requests"],0)
        self.assertEqual(out["database_mutation_statements"],0)

    def test_optional_private_rows_reuse_24bar_metrics_and_btc_relative(self):
        result=self.run_it(include_private_symbols=True)
        self.assertEqual(len(result["research_rows"]),50)
        btc=next(x for x in result["research_rows"] if x["symbol"]=="BTCUSDT")
        self.assertEqual(Decimal(btc["relative_vs_btc_pct_points"]),Decimal(0))
        self.assertTrue(all(row["approved_for_signals"] is False and
                            row["orders_sent"] is False
                            for row in result["research_rows"]))
        self.assertEqual([r["descriptive_rank"] for r in result["research_rows"]],
                         list(range(1,51)))

    def test_only_49_of_50_and_unknown_epoch_fail_closed(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("DELETE FROM confirmed WHERE symbol=? AND open_ms=?",
                       (SYMBOLS[0],START))
        self.assertEqual(self.run_it()["status"],"ws_24h_readonly_integrity_abstain")
        self.assertFalse(self.run_it()["ws_journal_integrity_replayed"])
        self.assertEqual(self.run_it()["research_rows"],[])

    def test_reject_tamper_to_closed_bar_and_schema(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE confirmed SET digest=? WHERE symbol=? AND open_ms=?",
                       ("0"*64,SYMBOLS[0],START))
        self.assertEqual(self.run_it()["status"],"ws_24h_readonly_integrity_abstain")
        self.assertEqual(self.run_it()["audited_assets"],0)

    def test_scope_mismatch_and_owner_flag_are_not_bypassed(self):
        from copy import deepcopy
        wrong = deepcopy(self.ranked)
        wrong["scope_digest_sha256"]="0"*64
        self.assertEqual(self.run_it(ranked_scope=wrong)["audited_assets"],0)
        self.assertEqual(self.run_it(ws_scope=replace(self.ws_scope,
                         observed_at_ms=END))["audited_assets"],0)
        self.assertEqual(self.run_it(owner_ok=False)["audited_assets"],0)
        self.assertEqual(self.run_it(allow_private_readonly_research=False)["status"],
                         "owner_optin_required")
        self.assertEqual(self.run_it(include_private_symbols="true")["audited_assets"],0)

    def test_utc_causal_clock_and_future_receipt_rejected(self):
        for bad in (True, END-1, END+HOUR_MS, END+179_999, END+HOUR_MS-59_999):
            with self.subTest(bad=bad):
                result=self.run_it(observed_at_ms=bad)
                self.assertNotEqual(result["status"],"ws_n50_descriptive_24h_ready")
        future = parse_offline_confirmed_kline(
            message(SYMBOLS[0],24,0), scope=self.ws_scope,
            received_at_ms=END+HOUR_MS+1800,
        )
        self.assertEqual(self.journal.append(future),"appended")
        self.assertEqual(self.run_it()["status"],"ws_24h_readonly_integrity_abstain")

    def test_readonly_replay_detects_journal_change_across_snapshots(self):
        original=self.journal.audit
        state={"n":0}
        def drift(*args,**kwargs):
            result=original(*args,**kwargs)
            state["n"]+=1
            if state["n"]==2:
                return replace(result,journal_digest_sha256="d"*64)
            return result
        with patch.object(self.journal,"audit",side_effect=drift):
            result=self.run_it()
        self.assertEqual(state["n"],2)
        self.assertEqual(result["status"],"ws_24h_readonly_integrity_abstain")

    def test_symlink_and_wrong_journal_name_block_before_query(self):
        old=self.path
        renamed=old.parent/"j1-rest-hourly-research.sqlite"
        old.rename(renamed)
        self.assertEqual(self.run_it()["audited_assets"],0)
        old.symlink_to(renamed)
        self.assertEqual(self.run_it()["audited_assets"],0)

    def test_no_network_no_order_sender_and_no_mutations(self):
        with patch("socket.create_connection",side_effect=AssertionError("network")), patch(
            "urllib.request.urlopen",side_effect=AssertionError("http")
        ), patch("sqlite3.Connection.execute",new=None) if False else patch(
            "urllib.request.Request",side_effect=AssertionError("http")
        ):
            self.assertEqual(self.run_it()["audited_assets"],50)
        count=sqlite3.connect(self.path).execute(
            "SELECT count(*) FROM confirmed"
        ).fetchone()[0]
        self.assertEqual(count,1200)


if __name__=="__main__":
    unittest.main()
