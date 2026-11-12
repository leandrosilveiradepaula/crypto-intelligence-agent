"""J3/D302: 50×25 actual SQLite transaction fixtures, no fill or hindsight."""
from __future__ import annotations

from contextlib import closing
from decimal import Context, Decimal, localcontext
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import (
    SCHEMA, STATUS, FILE_NAME, HOUR_MS, _binding,
)
from crypto_intelligence_agent.j1_n50_managed_cycle import (
    ACTIVE_SCHEMA, _pointer_write,
)
from crypto_intelligence_agent.j3_n50_expost_onehour import (
    evaluate_n50_expost_marks,
)
from scripts.audit_bybit_marketwide_closed24h import _digest

T = 1_800_000_000_000 // HOUR_MS * HOUR_MS
FIRST = T + HOUR_MS
LAST = T + 2 * HOUR_MS
NOW = LAST + 180_000
SYMS = tuple(["BTCUSDT"]+[f"TST{i:02d}USDT" for i in range(1,50)])


def manifest():
    data={
        "schema_version":SCHEMA, "status":STATUS,
        "closed_hour_end_ms":T,
        "catalog_pre_observed_at_ms":T+65_000,
        "catalog_post_observed_at_ms":T+120_000,
        "pool_candidate_count":370,
        "candidate_pool_digest_sha256":"b"*64,
        "closed24h_rank_digest_sha256":"c"*64,
        "ranked_research_symbols_only":list(SYMS),
        "scope_digest_sha256":"",
        "provisional_research_only":True,
        "marketwide_top50_verified":False,
        "independent_crypto_identity_verified":False,
        "live_trading_authorized":False,"orders_sent":False,
    }
    data["scope_digest_sha256"]=_binding(data)
    return data


def create(root: Path, *, hours=2):
    for parent in (root,root/"epochs",root/"lease"):
        parent.mkdir(mode=0o700, exist_ok=True)
        parent.chmod(0o700)
    epoch=root/"epochs"/f"epoch-{T:013d}"
    scope_dir=epoch/"scope"
    journal=epoch/"journal"
    for path in (epoch,scope_dir,journal):
        path.mkdir(mode=0o700)
        path.chmod(0o700)
    scope=manifest()
    sfile=scope_dir/FILE_NAME
    sfile.write_text(json.dumps(scope),encoding="ascii")
    sfile.chmod(0o600)
    _pointer_write(root,{
        "schema_version":ACTIVE_SCHEMA,
        "epoch_id":epoch.name,
        "scope_digest_sha256":scope["scope_digest_sha256"],
        "catalog_post_observed_at_ms":scope["catalog_post_observed_at_ms"],
    },decision=T)
    dbpath=journal/"j1-rest-hourly-research.sqlite"
    end=FIRST if hours==1 else LAST
    with closing(sqlite3.connect(dbpath)) as db:
        db.executescript("""
        CREATE TABLE scope(id INTEGER PRIMARY KEY,
            scope_digest TEXT,members_json TEXT,initial_end_ms INTEGER,halted_reason TEXT);
        CREATE TABLE cursor(symbol TEXT PRIMARY KEY,next_open_ms INTEGER);
        CREATE TABLE candles(symbol TEXT,open_ms INTEGER,open TEXT,high TEXT,low TEXT,
            close TEXT,base_volume TEXT,quote_turnover TEXT,
            received_at_ms INTEGER,digest_sha256 TEXT,PRIMARY KEY(symbol,open_ms));
        CREATE TABLE published_hour(end_ms INTEGER PRIMARY KEY,
            observed_at_ms INTEGER,scope_digest TEXT,observed_contracts INTEGER);
        """)
        db.execute("INSERT INTO scope VALUES(1,?,?,?,NULL)",
                   (scope["scope_digest_sha256"],json.dumps(SYMS,separators=(",",":")),FIRST))
        for closed in (FIRST,LAST)[:hours]:
            db.execute("INSERT INTO published_hour VALUES(?,?,?,50)",
                       (closed,closed+120_000,scope["scope_digest_sha256"]))
        for idx,symbol in enumerate(SYMS):
            db.execute("INSERT INTO cursor VALUES(?,?)",(symbol,end))
            with localcontext(Context(prec=80)):
                base=Decimal(100+idx)
                close=base + Decimal(idx)/Decimal(10)
                for i in range(24+(1 if hours==2 else 0)):
                    opened=FIRST-24*HOUR_MS+i*HOUR_MS
                    if i<24:
                        op=base
                        cl=close
                        seen=FIRST+90_000
                    else:
                        op=close
                        cl=(op+2 if idx>=45 else op-2 if idx<5 else op)
                        seen=LAST+90_000
                    high=max(op,cl)+10
                    low=min(op,cl)-10
                    values=tuple(format(v,"f") for v in (
                        op,high,low,cl,Decimal(10),Decimal(100),
                    ))
                    db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (symbol,opened,*values,seen,
                                _digest([symbol,(str(opened),*values)])))
        db.commit()
    dbpath.chmod(0o600)
    return dbpath



def create_halted_archive(root: Path) -> Path:
    """Extend the sealed real-layout 2h fixture to 3 receipts + 6 partial rows."""
    dbpath=create(root,hours=2)
    third=LAST+HOUR_MS
    fourth=third+HOUR_MS
    with closing(sqlite3.connect(dbpath)) as db:
        with db:
            scope=manifest()
            db.execute(
                "INSERT INTO published_hour VALUES(?,?,?,50)",
                (third,third+120_000,scope["scope_digest_sha256"]),
            )
            db.execute("UPDATE scope SET halted_reason='provider_denied_owner_review'")
            for i,symbol in enumerate(SYMS):
                previous=db.execute(
                    "SELECT close FROM candles WHERE symbol=? AND open_ms=?",
                    (symbol,FIRST),
                ).fetchone()
                assert previous is not None
                op=Decimal(previous[0])
                cl=op+Decimal("0.5")
                raw=tuple(format(x,"f") for x in (
                    op, op+3, op-3, cl, Decimal(10), Decimal(100)
                ))
                db.execute(
                    "INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (symbol,LAST,*raw,third+90_000,
                     _digest([symbol,(str(LAST),*raw)])),
                )
                cursor=third
                if i<6:
                    extra=tuple(format(x,"f") for x in (
                        cl, cl+3, cl-3, cl+Decimal("0.25"),
                        Decimal(10), Decimal(100)
                    ))
                    db.execute(
                        "INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (symbol,third,*extra,fourth+90_000,
                         _digest([symbol,(str(third),*extra)])),
                    )
                    cursor=fourth
                db.execute(
                    "UPDATE cursor SET next_open_ms=? WHERE symbol=?",
                    (cursor,symbol),
                )
    return dbpath


@unittest.skipUnless(os.name=="posix", "POSIX-only owner SQLite replay")
class J3N50ExpostTests(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"private"

    def inspect(self, **kwargs):
        opts={
            "root_directory":self.root,"now_ms":NOW,"owner_ok":True,
            "allow_private_readonly_audit":True,
        }
        opts.update(kwargs)
        return evaluate_n50_expost_marks(**opts)

    def test_prefix_ranks_only_before_first_checkpoint_and_outcomes_after(self):
        create(self.root)
        out=self.inspect(include_private_symbols=True)
        self.assertEqual(out["status"],"expost_reference_only",out)
        self.assertTrue(out["journal_integrity_verified"])
        self.assertEqual(out["audited_contracts"],50)
        self.assertEqual(out["observed_candles_per_contract"],25)
        self.assertEqual((out["prior_closed_end_ms"],out["outcome_closed_end_ms"]),
                         (FIRST,LAST))
        self.assertEqual(out["top_prior_return_sample_count"],5)
        self.assertEqual(out["bottom_prior_return_sample_count"],5)
        self.assertEqual(out["private_mark_observations"][0]["symbol"],"TST49USDT")
        self.assertEqual(out["private_mark_observations"][-1]["symbol"],"BTCUSDT")
        self.assertEqual(len(out["private_mark_observations"]),50)
        self.assertTrue(out["snapshot_digest_sha256"])
        self.assertFalse(out["approved_for_signals"])
        self.assertFalse(out["financial_backtest_approved"])
        self.assertFalse(out["fill_prices_verified"])
        self.assertFalse(out["intrabar_liquidation_validated"])
        self.assertFalse(out["orders_sent"])
        self.assertEqual(out["network_requests"],0)
        self.assertEqual(out["database_mutation_statements"],0)
        self.assertGreater(Decimal(out["top_tail_long_expost_net_mark_sum_quote"]),0)
        self.assertGreater(Decimal(out["bottom_tail_short_expost_net_mark_sum_quote"]),0)

    def test_later_outcome_never_changes_previous_selection(self):
        db=create(self.root)
        before=self.inspect(include_private_symbols=True)
        previous_ranks=[x["symbol"] for x in before["private_mark_observations"]]
        with closing(sqlite3.connect(db)) as con:
            with con:
                row=con.execute("SELECT open,base_volume,quote_turnover FROM candles "
                                "WHERE symbol=? AND open_ms=?",
                                ("TST49USDT",FIRST)).fetchone()
                op=Decimal(row[0])
                close=op-Decimal(15)
                raw=(
                    format(op,"f"),format(op+10,"f"),format(close-10,"f"),
                    format(close,"f"),row[1],row[2],
                )
                con.execute(
                    "UPDATE candles SET open=?,high=?,low=?,close=?,"
                    "base_volume=?,quote_turnover=?,digest_sha256=? "
                    "WHERE symbol=? AND open_ms=?",
                    (*raw,_digest(["TST49USDT",(str(FIRST),*raw)]),
                     "TST49USDT",FIRST),
                )
        after=self.inspect(include_private_symbols=True)
        self.assertEqual(after["status"],"expost_reference_only",after)
        self.assertEqual([x["symbol"] for x in after["private_mark_observations"]],
                         previous_ranks)
        self.assertNotEqual(after["snapshot_digest_sha256"],
                            before["snapshot_digest_sha256"])
        self.assertNotEqual(after["top_tail_long_expost_net_mark_sum_quote"],
                            before["top_tail_long_expost_net_mark_sum_quote"])

    def test_fee_slippage_adversity_is_exact_and_never_credited(self):
        create(self.root)
        low=self.inspect(entry_fee_bps=Decimal(0),
                         exit_fee_bps=Decimal(0),
                         entry_slippage_bps=Decimal(0),
                         exit_slippage_bps=Decimal(0))
        high=self.inspect(entry_fee_bps=Decimal(10),
                          exit_fee_bps=Decimal(10),
                          entry_slippage_bps=Decimal(10),
                          exit_slippage_bps=Decimal(10))
        self.assertEqual(high["status"],"expost_reference_only")
        self.assertEqual(Decimal(high["hypothetical_total_cost_per_asset_quote"]),
                         Decimal("0.4"))
        self.assertEqual(
            Decimal(low["top_tail_long_expost_net_mark_sum_quote"])
            - Decimal(high["top_tail_long_expost_net_mark_sum_quote"]),
            Decimal(2),
        )
        self.assertEqual(
            Decimal(low["all50_long_expost_net_mark_sum_quote"])
            - Decimal(high["all50_long_expost_net_mark_sum_quote"]),
            Decimal(20),
        )
        self.assertFalse(high["fees_and_funding_venue_verified"])

    def test_no_two_published_checkpoints_cannot_claim_next_bar(self):
        create(self.root,hours=1)
        out=self.inspect()
        self.assertEqual(out["status"],"two_checkpoints_required",out)
        self.assertFalse(out["journal_integrity_verified"])
        self.assertEqual(out["audited_contracts"],0)

    def test_default_output_private_mark_values_not_exposed(self):
        create(self.root)
        out=self.inspect()
        self.assertEqual(out["status"],"expost_reference_only")
        self.assertEqual(out["private_mark_observations"],[])
        self.assertNotIn("BTCUSDT",json.dumps(out))
        self.assertNotIn("TST49USDT",json.dumps(out))

    def test_cursor_or_checksum_tamper_fail_closed(self):
        db=create(self.root)
        with closing(sqlite3.connect(db)) as con:
            with con:
                con.execute("UPDATE candles SET digest_sha256='bad' WHERE rowid=1")
        out=self.inspect(include_private_symbols=True)
        self.assertNotEqual(out["status"],"expost_reference_only")
        self.assertEqual(out["private_mark_observations"],[])

    def test_first_publication_causal_receipt_after_first_checkpoint_denied(self):
        db=create(self.root)
        with closing(sqlite3.connect(db)) as con:
            with con:
                con.execute("UPDATE candles SET received_at_ms=? WHERE rowid=1",
                            (LAST+90_000,))
        out=self.inspect()
        self.assertEqual(out["status"],"blocked",out)
        self.assertFalse(out["journal_integrity_verified"])

    def test_gap_or_aged_scope_refuses_return(self):
        create(self.root)
        old=self.inspect(now_ms=T+49*HOUR_MS)
        self.assertNotEqual(old["status"],"expost_reference_only")
        self.assertEqual(self.inspect(now_ms=True)["status"],"blocked")

    def test_optin_owner_and_bad_notional_block_before_private_read(self):
        with patch("crypto_intelligence_agent.j3_n50_expost_onehour._pointer_read",
                   side_effect=AssertionError("private read forbidden")):
            self.assertEqual(self.inspect(allow_private_readonly_audit=False)
                             ["status"],"optin_required")
            self.assertEqual(self.inspect(owner_ok=False)["status"],"blocked")
            self.assertEqual(self.inspect(hypothetical_notional_quote=Decimal("NaN"))
                             ["status"],"blocked")
            self.assertEqual(self.inspect(entry_fee_bps=Decimal("-1"))
                             ["status"],"blocked")
            self.assertEqual(self.inspect(tail_count=26)["status"],"blocked")

    def test_private_symbols_are_never_trade_intents(self):
        create(self.root)
        out=self.inspect(include_private_symbols=True,tail_count=8)
        self.assertEqual(out["top_prior_return_sample_count"],8)
        self.assertEqual(out["bottom_prior_return_sample_count"],8)
        self.assertFalse(out["live_trading_authorized"])
        self.assertEqual(out["number_of_profitable_fills_verified"],0)
        self.assertTrue(all(row["hypothetical_reference_not_an_order"] is True
                            for row in out["private_mark_observations"]))


    def test_halted_archive_is_research_only_and_preserves_original_default(self):
        create_halted_archive(self.root)
        now=T+4*HOUR_MS+180_000
        normal=self.inspect(now_ms=now)
        self.assertNotEqual(normal["status"],"expost_reference_only")
        archived=self.inspect(now_ms=now,allow_archived_halted_research=True)
        self.assertEqual(
            archived["status"],"archived_halted_expost_reference_only",archived,
        )
        self.assertTrue(archived["halted_archive_source_verified"])
        self.assertEqual(archived["audited_contracts"],50)
        self.assertEqual(archived["observed_candles_per_contract"],25)
        self.assertEqual(archived["prior_closed_end_ms"],LAST)
        self.assertEqual(archived["outcome_closed_end_ms"],LAST+HOUR_MS)
        self.assertFalse(archived["orders_sent"])
        self.assertFalse(archived["financial_backtest_approved"])
        self.assertFalse(archived["approved_for_signals"])
        self.assertFalse(archived["fees_and_funding_venue_verified"])
        self.assertEqual(archived["private_mark_observations"],[])
        self.assertNotIn("BTCUSDT",json.dumps(archived))

    def test_expired_archived_manifest_can_be_replayed_without_new_get(self):
        create_halted_archive(self.root)
        archived=self.inspect(
            now_ms=T+60*HOUR_MS+180_000,
            allow_archived_halted_research=True,
        )
        self.assertEqual(
            archived["status"],"archived_halted_expost_reference_only",
            archived,
        )
        self.assertEqual(archived["network_requests"],0)

    def test_archived_corrupted_partial_row_is_never_research_ready(self):
        dbpath=create_halted_archive(self.root)
        with closing(sqlite3.connect(dbpath)) as db:
            db.execute(
                "UPDATE candles SET digest_sha256='bad' "
                "WHERE open_ms=? AND symbol=?",
                (LAST+HOUR_MS,SYMS[0]),
            )
            db.commit()
        out=self.inspect(
            now_ms=T+4*HOUR_MS+180_000,
            allow_archived_halted_research=True,
        )
        self.assertEqual(out["status"],"unverified_halted_archive",out)
        self.assertFalse(out["halted_archive_source_verified"])
        self.assertFalse(out["orders_sent"])

    def test_archived_flag_requires_explicit_boolean_and_owner_optin(self):
        with patch(
            "crypto_intelligence_agent.j3_n50_expost_onehour._pointer_read",
            side_effect=AssertionError("must not read"),
        ):
            self.assertEqual(
                self.inspect(
                    allow_archived_halted_research=True,
                    allow_private_readonly_audit=False,
                )["status"],"optin_required",
            )
            self.assertEqual(
                self.inspect(allow_archived_halted_research=1)["status"],"blocked",
            )



if __name__ == "__main__":
    unittest.main()
