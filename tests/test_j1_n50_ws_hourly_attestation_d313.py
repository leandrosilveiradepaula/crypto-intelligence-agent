"""D313: exact 50/50 WS closed-hour audit in a single SQLite replay.

Offline synthetic fixtures only; never contacts Bybit, writes REST,
restarts systemd or certifies continuous live trading/Top50 market coverage.
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

from crypto_intelligence_agent.bybit_instrument_volume_contract import (
    BybitLinearInstrumentResearch,
)
from crypto_intelligence_agent.bybit_closed_stream_cache import (
    OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    parse_offline_confirmed_kline, HOUR_MS,
)
from crypto_intelligence_agent.j1_n50_ws_hourly_attestation import (
    attest_n50_ws_hour_once,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_j1_n50_managed_cycle import T, sealed

MEMBERS = tuple(f"TST{i:02d}USDT" for i in range(50))
SCOPE_OBSERVED = T + 150_000
DECISION = T + HOUR_MS
OBSERVED = DECISION + 4000


def reviewed_scope():
    return OfflineReviewedStreamScope(
        SCOPE_OBSERVED, "a"*64,
        tuple(BybitLinearInstrumentResearch(
            symbol=s, base_coin=s[:-4], quote_coin="USDT", settle_coin="USDT",
            observed_at_ms=SCOPE_OBSERVED, launch_time_ms=T-30*HOUR_MS,
            max_leverage=Decimal("50"), tick_size=Decimal("0.01"),
            quantity_step=Decimal("0.001"), registry_sha256="a"*64,
        ) for s in MEMBERS),
        50,
    )


def candle(symbol, *, confirm=True):
    return {
        "topic":f"kline.60.{symbol}", "type":"snapshot", "ts": DECISION + 1200,
        "data":[{
            "start":T, "end":DECISION-1, "interval":"60",
            "open":"10", "high":"12", "low":"9", "close":"11",
            "volume":"1.5", "turnover":"16.5", "confirm":confirm,
            "timestamp":DECISION-500,
        }],
    }


class N50HourlyWSEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "ws-owner-research.sqlite"
        self.journal = SQLiteOfflineClosedStreamJournal.create(self.path)
        self.ws_scope = reviewed_scope()
        self.ranked = sealed(T)

    def append(self, n=50):
        for symbol in MEMBERS[:n]:
            event = parse_offline_confirmed_kline(
                candle(symbol), scope=self.ws_scope,
                received_at_ms=DECISION+2000,
            )
            self.assertEqual(self.journal.append(event), "appended")

    def attest(self, **changed):
        args = dict(
            ranked_scope=self.ranked, ws_scope=self.ws_scope,
            journal=self.journal, decision_at_ms=DECISION,
            observed_at_ms=OBSERVED,
        )
        args.update(changed)
        return attest_n50_ws_hour_once(**args)

    def test_fifty_confirmed_ws_candles_attest_exact_hour_not_24h_or_live(self):
        self.append(50)
        result = self.attest()
        self.assertEqual(result["status"],
                         "ws_hour_50_observed_local_only_not_marketwide")
        self.assertEqual((result["expected_contracts"],
                          result["confirmed_contracts"],
                          result["missing_contracts"]), (50,50,0))
        self.assertEqual(result["utc_closed_hour_end_ms"], DECISION)
        self.assertEqual(len(result["evidence_sha256"]), 64)
        audit = self.journal.audit(
            scope=self.ws_scope, decision_at_ms=DECISION,
            as_of_ms=OBSERVED, hour_evidence_symbols=tuple(sorted(MEMBERS)),
        )
        self.assertEqual(audit.hour_evidence_expected, 50)
        self.assertEqual(audit.hour_evidence_confirmed, 50)
        self.assertEqual(len(audit.hour_evidence_sha256), 64)
        self.assertEqual(audit.missing_24h_symbols, 50)
        self.assertIsNone(audit.rank_digest_sha256)
        self.assertIsNone(audit.sanitized_report()["rank_digest_sha256"])
        self.assertFalse(result["published_rest_pit"])
        self.assertFalse(result["continuous_collector_verified"])
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["orders_sent"])
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["database_mutation_statements"], 0)
        for symbol in MEMBERS:
            self.assertNotIn(symbol, json.dumps(result))

    def test_forty_nine_out_of_fifty_never_claims_completed_hour(self):
        self.append(49)
        result = self.attest()
        self.assertEqual(result["status"],"ws_closed_hour_incomplete_no_pit")
        self.assertEqual((result["confirmed_contracts"],
                          result["missing_contracts"]), (49,1))
        self.assertIsNone(result["evidence_sha256"])
        event = parse_offline_confirmed_kline(
            candle(MEMBERS[-1]), scope=self.ws_scope,
            received_at_ms=DECISION+2000,
        )
        self.assertEqual(self.journal.append(event), "appended")
        self.assertEqual(self.attest()["confirmed_contracts"],50)

    def test_open_candle_never_counts_and_invalid_frame_is_rejected(self):
        self.append(49)
        with self.assertRaises(DataValidationError):
            parse_offline_confirmed_kline(
                candle(MEMBERS[-1],confirm=False),
                scope=self.ws_scope, received_at_ms=DECISION+2000,
            )
        self.assertEqual(self.attest()["confirmed_contracts"],49)
        self.assertFalse(self.attest()["published_rest_pit"])

    def test_existing_audit_default_contract_unchanged(self):
        self.append(50)
        old = self.journal.audit(
            scope=self.ws_scope, decision_at_ms=DECISION,
            as_of_ms=OBSERVED,
        )
        self.assertIsNone(old.hour_evidence_expected)
        self.assertIsNone(old.hour_evidence_confirmed)
        self.assertIsNone(old.hour_evidence_sha256)
        self.assertNotIn("hour_evidence_expected", old.sanitized_report())
        self.assertEqual(old.observed_symbols, 50)

    def test_selected_member_list_rejects_duplicates_wrong_size_unreviewed(self):
        self.append(50)
        for names in (
            tuple(MEMBERS[:49]), tuple(MEMBERS)+("OTHERUSDT",),
            tuple(MEMBERS[:49])+("OTHERUSDT",),
            tuple(MEMBERS[:49])+(MEMBERS[0],),
            tuple(reversed(MEMBERS)),
            list(MEMBERS),
        ):
            with self.subTest(member_count=len(names)):
                with self.assertRaises(DataValidationError):
                    self.journal.audit(
                        scope=self.ws_scope, decision_at_ms=DECISION,
                        as_of_ms=OBSERVED, hour_evidence_symbols=names,
                    )

    def test_outdated_or_wrong_epoch_or_wrong_top50_never_attests(self):
        self.append(50)
        forged = deepcopy(self.ranked)
        forged["scope_digest_sha256"] = "0"*64
        self.assertEqual(self.attest(ranked_scope=forged)["status"],
                         "ws_closed_hour_abstain")
        self.assertEqual(self.attest(decision_at_ms=DECISION+HOUR_MS)["status"],
                         "ws_closed_hour_abstain")
        forged = deepcopy(self.ranked)
        forged["ranked_research_symbols_only"][0] = "OTHERUSDT"
        from crypto_intelligence_agent.j1_auto_research_epoch import _binding
        forged["scope_digest_sha256"] = _binding(forged)
        self.assertEqual(self.attest(ranked_scope=forged)["status"],
                         "ws_closed_hour_abstain")

    def test_sqlite_tamper_blocks_entire_proof_even_if_fifty_rows_present(self):
        self.append(50)
        self.assertEqual(self.attest()["confirmed_contracts"], 50)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE confirmed SET digest=? WHERE symbol=?",
                       ("b"*64, MEMBERS[0]))
        self.assertEqual(self.attest()["status"],"ws_closed_hour_abstain")

    def test_no_future_or_early_receipt_is_promoted(self):
        self.append(50)
        self.assertEqual(
            self.attest(observed_at_ms=DECISION+500)["status"],
            "ws_closed_hour_abstain",
        )
        self.assertEqual(
            self.attest(observed_at_ms=DECISION+1500)["status"],
            "ws_closed_hour_incomplete_no_pit",
        )
        self.assertEqual(
            self.attest(observed_at_ms=DECISION+150_000)["status"],
            "ws_closed_hour_abstain",
        )
        self.assertEqual(self.attest()["confirmed_contracts"],50)

    def test_duplicate_event_is_idempotent_but_changed_price_rejected(self):
        self.append(50)
        first = parse_offline_confirmed_kline(
            candle(MEMBERS[0]), scope=self.ws_scope,
            received_at_ms=DECISION+2000,
        )
        self.assertEqual(self.journal.append(first), "idempotent")
        mutated = candle(MEMBERS[0])
        mutated["data"][0]["turnover"] = "17"
        with self.assertRaises(DataGapError):
            self.journal.append(parse_offline_confirmed_kline(
                mutated, scope=self.ws_scope, received_at_ms=DECISION+2000,
            ))
        self.assertEqual(self.attest()["confirmed_contracts"],50)


if __name__ == "__main__":
    unittest.main()
