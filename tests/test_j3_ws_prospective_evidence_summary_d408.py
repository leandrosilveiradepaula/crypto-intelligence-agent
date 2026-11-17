"""D408: prospective J2/J3 evidence review, no backtest or exchange claims."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.j3_ws_watchlist_forward_marks import _empty
from crypto_intelligence_agent.j3_ws_prospective_evidence_summary_d408 import (
    summarize_ws_prospective_references,
)
from crypto_intelligence_agent.market_data import DataValidationError

from test_j3_ws_watchlist_forward_marks import decision, evaluate

ROOT = Path(__file__).resolve().parents[1]


def score(h: int = 1, *, empty: bool = False, shift: int = 0) -> dict:
    _, frozen = decision()
    if empty:
        raw = _empty("no_observations_selected", selected=0, horizon_bars=h)
    else:
        raw = evaluate(frozen, horizon=h)
        assert raw["status"] == "ex_post_reference_marks_scored_not_a_backtest"
    raw.update(
        owner_local_decision_file_verified=True,
        decision_closed_end_ms=frozen.decision_end_ms + shift * HOUR_MS,
        future_closed_end_ms=frozen.decision_end_ms + (h + shift) * HOUR_MS,
        owner_ws_sqlite_readonly_replayed=True,
        database_accessed=True,
        prospective_registration_independently_verified=False,
    )
    return raw


class ProspectiveReferenceSummaryD408Tests(unittest.TestCase):
    def test_multiple_distinct_decisions_one_horizon_and_different_horizon(self):
        a=score(1)
        b=score(1,shift=1)
        c=score(4)
        report=summarize_ws_prospective_references((a,b,c))
        self.assertEqual(report["report_records_accepted"],3)
        self.assertEqual(report["distinct_decision_hours_in_supplied_files"],2)
        one=report["horizons"][0]
        self.assertEqual(one["horizon_hours"],1)
        self.assertEqual(one["scored_decisions"],2)
        self.assertEqual(one["matured_research_observations"],
                         a["matured_observations"]+b["matured_observations"])
        self.assertEqual(one["directionally_favorable"],
                         a["aligned_observations"]+b["aligned_observations"])
        self.assertIsNotNone(one["net_reference_bps_mean_per_observation"])
        four=report["horizons"][1]
        self.assertEqual(four["horizon_hours"],4)
        self.assertEqual(four["scored_decisions"],1)
        self.assertEqual(report["horizons"][2]["records"],0)
        self.assertIsNone(report["horizons"][2]["net_reference_bps_mean_per_observation"])
        self.assertFalse(report["all_decision_windows_present_verified"])
        self.assertFalse(report["cost_assumptions_consistent_across_decisions_verified"])
        for field in ("out_of_sample_results_validated",
                      "strategy_profitable_verified","approved_for_signals",
                      "approved_for_live_use","orders_sent","financial_backtest_approved"):
            self.assertFalse(report[field])
        self.assertNotIn("BTCUSDT",json.dumps(report))
        self.assertNotIn("ETHUSDT",json.dumps(report))

    def test_empty_decision_is_not_a_losing_trade(self):
        a=score(1,empty=True)
        output=summarize_ws_prospective_references((a,))
        row=output["horizons"][0]
        self.assertEqual(row["empty_decisions"],1)
        self.assertEqual(row["matured_research_observations"],0)
        self.assertIsNone(row["net_reference_bps_sum_under_individual_assumptions"])
        self.assertIsNone(row["net_reference_bps_mean_per_observation"])
        self.assertEqual(row["directionally_contrary"],0)

    def test_reject_duplicate_hours_in_same_horizon(self):
        a=score(1)
        with self.assertRaises(DataValidationError):
            summarize_ws_prospective_references((a,deepcopy(a)))

    def test_refuses_unvalidated_sources_and_unsafe_indicators(self):
        base=score(1)
        changes=(
            lambda r: r.update(orders_sent=True),
            lambda r: r.update(approved_for_signals=True),
            lambda r: r.update(financial_backtest_approved=True),
            lambda r: r.update(owner_local_decision_file_verified=False),
            lambda r: r.update(prospective_registration_independently_verified=True),
            lambda r: r.update(owner_ws_sqlite_readonly_replayed=False),
            lambda r: r.update(database_accessed=False),
            lambda r: r.update(network_requests=1),
            lambda r: r.update(horizon_bars=24),
            lambda r: r.update(future_closed_end_ms=r["future_closed_end_ms"]+1),
            lambda r: r.update(matured_observations=0),
            lambda r: r.update(net_reference_after_assumed_costs_bps_sum="Infinity"),
            lambda r: r.update(net_reference_after_assumed_costs_bps_sum="1e5000"),
            lambda r: r.update(selected_observations=11),
            lambda r: r.update(secret_api_key="dont-pass"),
        )
        for change in changes:
            item=deepcopy(base)
            change(item)
            with self.subTest(keys=tuple(item)), self.assertRaises(DataValidationError):
                summarize_ws_prospective_references((item,))
        with self.assertRaises(DataValidationError):
            summarize_ws_prospective_references(())

    def test_cli_reads_explicit_existing_json_files_and_writes_new_private_summary(self):
        a=score(1)
        b=score(4,empty=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            p1=root/"one.json"
            p2=root/"two.json"
            p1.write_text(json.dumps(a),encoding="ascii")
            p2.write_text(json.dumps(b),encoding="ascii")
            dest=root/"summary.json"
            cmd=[sys.executable,"-m",
                 "scripts.summarize_ws_prospective_evidence_d408",
                 "--score",str(p1),"--score",str(p2),
                 "--output",str(dest)]
            result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            actual=json.loads(dest.read_text(encoding="ascii"))
            self.assertEqual(actual["report_records_accepted"],2)
            self.assertEqual(actual["horizons"][1]["empty_decisions"],1)
            self.assertFalse(actual["approved_for_signals"])
            retry=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=20)
            self.assertEqual(retry.returncode,65)
            self.assertEqual(dest.read_text(encoding="ascii"),
                             json.dumps(actual,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n")
            self.assertNotIn(str(p1),retry.stderr)

    def test_cli_rejects_duplicate_score_path_and_bad_json(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"bad.json"
            file.write_text('{"status":"a","status":"b"}',encoding="ascii")
            cmd=[sys.executable,"-m","scripts.summarize_ws_prospective_evidence_d408"]
            for tail in (
                ["--score",str(file)],
                ["--score",str(file),"--score",str(file)],
            ):
                result=subprocess.run(cmd+tail,cwd=ROOT,capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,65)
                self.assertIn("D408:",result.stderr)


if __name__ == "__main__":
    unittest.main()
