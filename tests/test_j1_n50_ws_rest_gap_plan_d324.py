"""D324: exact missing WebSocket hour targets, no GET and no REST writes."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, parse_offline_confirmed_kline, HOUR_MS,
)
from crypto_intelligence_agent.j1_n50_ws_rest_gap_plan import (
    MAX_GAP_GETS, plan_n50_ws_rest_gap_targets,
)
from test_j1_n50_ws_hourly_attestation_d313 import (
    MEMBERS, DECISION, T, candle, reviewed_scope, sealed,
)

AFTER = DECISION + 240_000


class N50WSRESTGapPlanTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"ws-confirmed.sqlite"
        self.journal=SQLiteOfflineClosedStreamJournal.create(self.path)
        self.scope=reviewed_scope()
        self.ranked=sealed(T)

    def append(self, n):
        for symbol in MEMBERS[:n]:
            event=parse_offline_confirmed_kline(
                candle(symbol),scope=self.scope,received_at_ms=DECISION+2000,
            )
            self.assertEqual(self.journal.append(event),"appended")

    def plan(self, **kwargs):
        args=dict(
            ranked_scope=self.ranked,ws_scope=self.scope,journal=self.journal,
            decision_at_ms=DECISION,observed_at_ms=AFTER,
        )
        args.update(kwargs)
        return plan_n50_ws_rest_gap_targets(**args)

    def test_50_closed_ws_contracts_generate_zero_rest_gets(self):
        self.append(50)
        result=self.plan()
        self.assertEqual(result.status,"ws_50_complete_no_rest_needed")
        self.assertEqual(result.confirmed_ws_contracts,50)
        self.assertEqual(result.missing_ws_contracts,0)
        self.assertEqual(result.planned_rest_gets,0)
        self.assertEqual(result.private_get_urls,())
        self.assertIsNone(result.plan_digest_sha256)
        self.assertFalse(result.sanitized_report()["published_rest_pit"])

    def test_one_missing_contract_issues_exact_one_hour_target_only(self):
        self.append(49)
        result=self.plan()
        self.assertEqual(result.status,"ws_rest_gap_targets_private_ready")
        self.assertEqual((result.confirmed_ws_contracts,result.missing_ws_contracts),
                         (49,1))
        self.assertEqual(result.planned_rest_gets,1)
        self.assertEqual(len(result.plan_digest_sha256),64)
        query=urlsplit(result.private_get_urls[0])
        self.assertEqual(query.scheme,"https")
        self.assertEqual(query.netloc,"api.bybit.com")
        params=parse_qs(query.query)
        self.assertEqual(params,{"category":["linear"],"symbol":[MEMBERS[-1]],
                                 "interval":["60"],"start":[str(T)],
                                 "end":[str(DECISION-1)],"limit":["1"]})
        sanitized=json.dumps(result.sanitized_report(),sort_keys=True)
        self.assertNotIn(MEMBERS[-1],sanitized)
        self.assertNotIn(MEMBERS[-1],repr(result))
        self.assertNotIn("api.bybit.com",sanitized)
        self.assertEqual(result.sanitized_report()["rest_gets_executed"],0)
        self.assertEqual(result.sanitized_report()["rest_rows_inserted_as_ws"],0)
        self.assertFalse(result.sanitized_report()["orders_sent"])

    def test_three_gaps_within_budget_four_refused(self):
        self.append(47)
        ok=self.plan()
        self.assertEqual(ok.missing_ws_contracts,3)
        self.assertEqual(ok.planned_rest_gets,3)
        self.assertEqual(len(ok.private_get_urls),3)
        self.assertEqual(tuple(parse_qs(urlsplit(url).query)["symbol"][0]
                               for url in ok.private_get_urls),
                         tuple(sorted(MEMBERS[-3:])))
        blocked=self.plan(max_gets=2)
        self.assertEqual(blocked.status,"ws_gaps_exceed_rest_budget_no_get")
        self.assertEqual(blocked.planned_rest_gets,0)
        self.assertEqual(blocked.private_get_urls,())
        self.assertIsNone(blocked.plan_digest_sha256)

    def test_four_or_fifty_gaps_do_not_generate_rest_requests(self):
        self.append(46)
        more=self.plan()
        self.assertEqual(more.status,"ws_gaps_exceed_rest_budget_no_get")
        self.assertEqual(more.missing_ws_contracts,4)
        self.assertEqual(more.private_get_urls,())
        empty=SQLiteOfflineClosedStreamJournal.create(Path(self.path.parent)/"empty.sqlite")
        nothing=self.plan(journal=empty)
        self.assertEqual(nothing.missing_ws_contracts,50)
        self.assertEqual(nothing.planned_rest_gets,0)

    def test_tampered_sqlite_or_drifted_scope_never_plan_gets(self):
        self.append(49)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE confirmed SET digest=? WHERE symbol=?",
                       ("b"*64,MEMBERS[0]))
        self.assertEqual(self.plan().status,"rest_gap_plan_integrity_abstain")
        restored=SQLiteOfflineClosedStreamJournal.create(
            Path(self.path.parent)/"separate.sqlite")
        bad=deepcopy(self.ranked)
        bad["scope_digest_sha256"]="0"*64
        self.assertEqual(self.plan(journal=restored,ranked_scope=bad).status,
                         "rest_gap_plan_integrity_abstain")

    def test_clock_batch_and_input_types_fail_closed(self):
        self.assertEqual(self.plan(observed_at_ms=DECISION+120_000).status,
                         "rest_gap_plan_integrity_abstain")
        self.assertEqual(self.plan(observed_at_ms=DECISION+900_001).status,
                         "rest_gap_plan_integrity_abstain")
        self.assertEqual(self.plan(max_gets=50).status,
                         "rest_gap_plan_integrity_abstain")
        self.assertEqual(self.plan(max_gets=True).status,
                         "rest_gap_plan_integrity_abstain")
        self.assertEqual(self.plan(decision_at_ms=DECISION+1).status,
                         "rest_gap_plan_integrity_abstain")
        self.assertEqual(self.plan(ranked_scope={}).status,
                         "rest_gap_plan_integrity_abstain")

    def test_old_audit_has_no_private_missing_fields_or_symbols(self):
        self.append(49)
        previous=self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=AFTER,
        )
        self.assertEqual(previous.private_missing_hour_members,())
        self.assertNotIn("private_missing_hour_members",previous.sanitized_report())
        current=self.journal.audit(
            scope=self.scope,decision_at_ms=DECISION,as_of_ms=AFTER,
            hour_evidence_symbols=tuple(sorted(MEMBERS)),
        )
        self.assertEqual(current.private_missing_hour_members,(MEMBERS[-1],))
        self.assertNotIn(MEMBERS[-1],repr(current))
        self.assertNotIn(MEMBERS[-1],json.dumps(current.sanitized_report()))


if __name__=="__main__":
    unittest.main()
