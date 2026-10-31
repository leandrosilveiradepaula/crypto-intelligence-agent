"""PRE8: same-snapshot, all-or-nothing PAPER position-incident regression suite."""
from contextlib import closing, redirect_stdout
from decimal import Decimal as D
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_portfolio_incident_audit import (
    audit_selected_paper_portfolio_incidents,
)
from crypto_intelligence_agent.paper_runner_incident_audit import (
    PaperIncidentCode, PaperIncidentSeverity,
    audit_paper_runner_incident,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderEventKind
from scripts.audit_selected_paper_portfolio_incidents import main
from test_paper_position_reservations import T, e, exit_order, opened_order, plan


class SelectedPaperPortfolioIncidentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "selected-paper.sqlite"
        self.store = SQLitePaperPositionJournal(self.path)
        self.ids = ("fixture_pre8_first", "fixture_pre8_second")
        for n, pid in enumerate(self.ids):
            self.store.create_position(
                position_id=pid,
                opening_intent=opened_order(
                    intent_id=f"fixture_pre8_open_{n}",
                    fixture_signal_id=f"fixture_pre8_signal_{n}",
                    symbol="BTCUSDT" if n == 0 else "ETHUSDT",
                ),
                opening_events=(e(f"pre8_open_fill_{n}", PaperOrderEventKind.FILL, 1, "100"),),
                exit_plan=plan(),
                plan_version=f"fixture_pre8_plan_{n}",
                synthetic_lot_step_units=D(1),
                as_of_ms=T+1,
            )

    def audit(self, ids=None, at=T+6, max_age=1000, **kw):
        return audit_selected_paper_portfolio_incidents(
            self.path, self.ids if ids is None else ids,
            as_of_ms=at, max_checkpoint_age_ms=max_age, **kw)

    def test_one_snapshot_two_instruments_no_financial_totals(self):
        current = self.store.load(self.ids[0])
        for n, amount in enumerate(("50", "30", "14"), start=1):
            intent = exit_order(f"pre8_partial_{n}", amount, current.as_of_ms-T,
                                cap=str(current.confirmed_remaining_units))
            current = self.store.reserve_exit(self.ids[0], n, intent, as_of_ms=current.as_of_ms)
            current = self.store.append_exit_events(
                self.ids[0], intent.intent_id,
                (e(f"pre8_fill_{n}", PaperOrderEventKind.FILL,
                   current.as_of_ms-T+1, amount),), as_of_ms=current.as_of_ms+1)
        self.assertEqual(current.confirmed_remaining_units, D(6))
        before = self.path.read_bytes()
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            report = self.audit()
        self.assertEqual(before, self.path.read_bytes())
        out = report.sanitized_report()
        self.assertEqual(out["schema_version"], "paper_portfolio_incidents_v1")
        self.assertEqual(out["selected_count"], 2)
        self.assertEqual(out["observed_count"], 2)
        self.assertEqual(out["review_count"], 2)
        self.assertEqual(out["blocked_count"], 0)
        self.assertEqual(out["severity"], "REVIEW")
        self.assertEqual([x["ordinal"] for x in out["positions"]], [1, 2])
        self.assertEqual(
            [x["incident_code"] for x in out["positions"]],
            ["RUNNER_UNPROTECTED", "PARTIALS_INCOMPLETE"])
        self.assertEqual(out["positions"][0]["residual_paper_units"], "6")
        self.assertEqual(out["positions"][1]["residual_paper_units"], "100")
        self.assertTrue(out["same_auto4_snapshot"])
        self.assertFalse(out["portfolio_financial_totals_available"])
        for key in ("orders_sent", "native_stop_verified", "live_trading_authorized",
                    "approved_for_live_use", "exchange_reconciliation_confirmed",
                    "financial_pnl_available"):
            self.assertFalse(out[key])
        dumped = json.dumps(out, ensure_ascii=False)
        for secret in (str(self.path), "BTCUSDT", "ETHUSDT", *self.ids,
                       "fixture_pre8_open_0", "fixture_pre8_open_1"):
            self.assertNotIn(secret, dumped)
        self.assertEqual(out, self.audit().sanitized_report())
        single = audit_paper_runner_incident(self.path, self.ids[0])
        self.assertEqual(out["positions"][0]["incident_code"], single.code.value)
        self.assertEqual(out["positions"][0]["severity"], single.severity.value)

    def test_unknown_blocks_one_slot_without_inventing_account_or_trades(self):
        pending = exit_order("pre8_unknown", "50", 1)
        self.store.reserve_exit(self.ids[0], 1, pending, as_of_ms=T+1)
        self.store.append_exit_events(
            self.ids[0], pending.intent_id,
            (e("pre8_unknown_event", PaperOrderEventKind.UNKNOWN, 2),),
            as_of_ms=T+2)
        result = self.audit().sanitized_report()
        self.assertEqual(result["severity"], "BLOCKED")
        self.assertEqual(result["blocked_count"], 1)
        self.assertEqual(result["review_count"], 1)
        self.assertEqual(result["positions"][0]["incident_code"], "PARTIALS_INCOMPLETE")
        self.assertTrue(result["positions"][0]["reconciliation_required"])

    def test_age_and_future_are_blocked_without_false_healthy_status(self):
        stale = self.audit(at=T+10000, max_age=500).sanitized_report()
        self.assertEqual(stale["blocked_count"], 2)
        self.assertEqual(stale["severity"], "BLOCKED")
        self.assertEqual(stale["positions"][0]["incident_code"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("causal_fresh_checkpoint", stale["positions"][1]["evidence_missing"])
        future = self.audit(at=T, max_age=500).sanitized_report()
        self.assertEqual(future["blocked_count"], 2)

    def test_corrupted_one_member_blocks_entire_batch_without_leak(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE paper_positions SET digest='broken' WHERE position_id=?",
                         (self.ids[1],))
        report = self.audit().sanitized_report()
        self.assertEqual(report["severity"], "BLOCKED")
        self.assertEqual(report["selected_count"], 2)
        self.assertEqual(report["observed_count"], 0)
        self.assertEqual(report["positions"], [])
        self.assertEqual(report["batch_block_code"], "INVALID_OR_INCONSISTENT_SELECTED_JOURNALS")
        self.assertFalse(report["same_auto4_snapshot"])
        self.assertNotIn(self.ids[1], json.dumps(report))

    def test_missing_auto2_or_auto4_is_an_entire_batch_block(self):
        missing = self.path.parent / "missing.sqlite"
        self.assertFalse(missing.exists())
        result = self.audit(opening_order_path=missing).sanitized_report()
        self.assertEqual(result["observed_count"], 0)
        self.assertEqual(result["severity"], "BLOCKED")
        self.assertFalse(missing.exists())
        other = audit_selected_paper_portfolio_incidents(
            missing, self.ids, as_of_ms=T+10, max_checkpoint_age_ms=100)
        self.assertEqual(other.sanitized_report()["observed_count"], 0)
        self.assertFalse(missing.exists())

    def test_duplicates_empty_too_many_and_invalid_cutoffs_rejected(self):
        for ids in ((), (self.ids[0], self.ids[0]),
                    tuple(f"fixture_pre8_many_{i}" for i in range(129))):
            with self.subTest(ids=len(ids)), self.assertRaises(DataValidationError):
                self.audit(ids=ids)
        for cutoff, age in ((T+1, 0), (T+1, -1), (T+1, 604800001),
                            (T+1, True), (-1, 5), (T+1.0, 5)):
            with self.subTest(cutoff=cutoff, age=age), self.assertRaises(DataValidationError):
                self.audit(at=cutoff, max_age=age)

    def test_cli_bounded_selection_and_no_sensitive_stdout(self):
        buf = StringIO()
        with redirect_stdout(buf):
            main(["--position-journal", str(self.path),
                  "--position-id", self.ids[1], "--position-id", self.ids[0],
                  "--as-of-ms", str(T+6), "--max-checkpoint-age-ms", "1000"])
        payload = json.loads(buf.getvalue())
        self.assertEqual([p["ordinal"] for p in payload["positions"]], [1, 2])
        self.assertEqual(payload["observed_count"], 2)
        self.assertNotIn(str(self.path), buf.getvalue())
        self.assertNotIn(self.ids[0], buf.getvalue())
        self.assertNotIn(self.ids[1], buf.getvalue())
        with self.assertRaises(SystemExit):
            main(["--enable-live"])


if __name__ == "__main__":
    unittest.main()
