"""J2/J3 #644: operational owner decision persistence, not proof of alpha."""
from __future__ import annotations

from contextlib import redirect_stdout
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent import j2_ws_prospective_ledger as ledger
from crypto_intelligence_agent.j3_ws_watchlist_forward_marks import (
    ForwardCostAssumptions,
)
from test_j2_n50_ws_descriptive_watchlist import source_ws, END, NOW

D = Decimal


def cost():
    return ForwardCostAssumptions(
        hypothetical_notional_quote_units=D("100"),
        entry_fee_bps=D("4"), exit_fee_bps=D("6"),
        entry_adverse_slippage_bps=D("2"),
        exit_adverse_slippage_bps=D("3"),
    )


def snapshot(end_ms=END, *, scope="b"*64, metadata="c"*64, future=False):
    src = source_ws()
    src["latest_closed_end_ms"] = end_ms
    src["ranked_scope_sha256"] = scope
    src["ws_metadata_sha256"] = metadata
    closes = {r["symbol"]: "100" for r in src["research_rows"]}
    if future:
        for row in src["research_rows"]:
            if row["last_closed_bar_breakout"] == "above_prior_23h_high":
                closes[row["symbol"]] = "101"
            if row["last_closed_bar_breakout"] == "below_prior_23h_low":
                closes[row["symbol"]] = "99"
        closes["BTCUSDT"] = "100.5"
    src["private_last_closes"] = closes
    return src


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0,
                     "owner-only ledger requires unprivileged POSIX user")
class OwnerLedgerCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="j2-ledger-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.ledger_root = Path(self.tmp.name)/"decisions"
        patcher = patch.object(ledger, "LEDGER_ROOT", self.ledger_root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run_capture(self, src=None):
        if src is None:
            src = snapshot()
        with patch.object(ledger.time, "time_ns",
                          return_value=NOW*1_000_000), \
             patch.object(ledger,"observe_active_private_ws_n50_24closed",
                          return_value=src) as owner:
            out = ledger.capture_owner_ws_decision_once(
                allow_private_readonly_research=True,
                allow_private_ledger_write=True,
            )
        owner.assert_called_once_with(
            allow_private_readonly_research=True,
            include_private_symbols=True,
            include_private_last_closes=True,
            now_ms=NOW,
        )
        return out

    def _run_score(self, horizon=1, src=None):
        current = END + horizon*HOUR_MS + 240_000
        if src is None:
            src = snapshot(END+horizon*HOUR_MS,future=True)
        with patch.object(ledger.time,"time_ns",
                          return_value=current*1_000_000), \
             patch.object(ledger,"observe_active_private_ws_n50_24closed",
                          return_value=src) as owner:
            out = ledger.score_owner_ws_decision_once(
                horizon_bars=horizon, costs=cost(),
                allow_private_readonly_research=True,
                allow_private_ledger_read=True,
            )
        owner.assert_called_once_with(
            allow_private_readonly_research=True,
            include_private_symbols=True,
            include_private_last_closes=True,
            now_ms=current,
        )
        return out

    def _file(self):
        return self.ledger_root/f"decision-{END}.json"

    def test_capture_once_and_grade_future_closed_reference_with_J3_costs(self):
        captured = self._run_capture()
        self.assertEqual(captured["status"],
                         "owner_local_decision_captured_not_independent_attestation")
        self.assertEqual(captured["capture_records_created"],1)
        self.assertGreater(captured["candidates_captured"],0)
        self.assertFalse(captured["prospective_registration_independently_verified"])
        self.assertFalse(captured["financial_backtest_approved"])
        self.assertFalse(captured["orders_sent"])
        self.assertEqual(stat.S_IMODE(self.ledger_root.stat().st_mode),0o700)
        p = self._file()
        self.assertTrue(p.is_file())
        self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
        stored = json.loads(p.read_bytes().decode("ascii"))
        self.assertIn("candidates",stored)
        self.assertEqual(stored["ws_metadata_sha256"],"c"*64)
        first_bytes = p.read_bytes()
        second = self._run_capture()
        self.assertEqual(second["status"],"owner_decision_hour_already_recorded")
        self.assertEqual(p.read_bytes(),first_bytes)
        result = self._run_score()
        self.assertEqual(result["status"],
                         "ex_post_reference_marks_scored_not_a_backtest")
        self.assertEqual(result["aligned_observations"],captured["candidates_captured"])
        self.assertEqual(result["matured_observations"],captured["candidates_captured"])
        self.assertTrue(result["owner_local_decision_file_verified"])
        self.assertFalse(result["prospective_registration_independently_verified"])
        self.assertFalse(result["financial_backtest_approved"])
        self.assertFalse(result["approved_for_signals"])
        self.assertFalse(result["orders_sent"])
        self.assertLess(
            D(result["net_reference_after_assumed_costs_bps_sum"]),
            D(result["gross_reference_bps_sum"]),
        )
        self.assertNotIn("BTCUSDT",json.dumps(result))
        self.assertNotIn("TST",json.dumps(result))
        self.assertNotIn("100",json.dumps(captured))

    def test_1_4_8h_share_original_decision_and_36h_rotation_not_fabricated(self):
        self.assertEqual(self._run_capture()["capture_records_created"],1)
        for horizon in (1,4,8):
            with self.subTest(horizon=horizon):
                res = self._run_score(horizon)
                self.assertEqual(res["horizon_bars"],horizon)
                self.assertEqual(res["status"],
                                 "ex_post_reference_marks_scored_not_a_backtest")
        metadata = snapshot(END+HOUR_MS,metadata="d"*64,future=True)
        res = self._run_score(src=metadata)
        self.assertEqual(res["status"],"owner_ws_metadata_changed_forward_abstain")
        scope = snapshot(END+HOUR_MS,scope="d"*64,future=True)
        res = self._run_score(src=scope)
        self.assertEqual(res["status"],"cohort_changed_forward_abstain")
        for horizon in (24,0,9,True):
            with self.subTest(horizon=horizon):
                res=ledger.score_owner_ws_decision_once(
                    horizon_bars=horizon,costs=cost(),
                    allow_private_readonly_research=True,
                    allow_private_ledger_read=True,
                )
                self.assertEqual(res["status"],
                                 "owner_score_horizon_not_supported_for_rotating_epoch")

    def test_missing_future_owner_snapshot_and_missing_file_abstain(self):
        self.assertEqual(self._run_score()["status"],"owner_score_abstain")
        self._run_capture()
        bad = snapshot(END+HOUR_MS,future=True)
        bad["status"] = "ws_24h_readonly_integrity_abstain"
        self.assertEqual(self._run_score(src=bad)["status"],"owner_score_abstain")
        bad = snapshot(END+HOUR_MS,future=True)
        bad["private_last_closes"].pop("BTCUSDT")
        self.assertEqual(self._run_score(src=bad)["status"],"owner_score_abstain")
        bad = snapshot(END+HOUR_MS,future=True)
        bad["private_last_closes"]["BTCUSDT"] = "NaN"
        self.assertEqual(self._run_score(src=bad)["status"],"owner_score_abstain")

    def test_symlink_hardlink_and_world_readable_record_abstain(self):
        self._run_capture()
        path = self._file()
        path.chmod(0o644)
        self.assertEqual(self._run_score()["status"],"owner_score_abstain")
        path.chmod(0o600)
        extra = self.ledger_root/"extra-hardlink"
        os.link(path,extra)
        self.assertEqual(self._run_score()["status"],"owner_score_abstain")
        extra.unlink()
        self.assertEqual(self._run_score()["status"],
                         "ex_post_reference_marks_scored_not_a_backtest")
        outside = Path(self.tmp.name)/"outside"
        path.rename(outside)
        os.symlink(outside,path)
        self.assertEqual(self._run_score()["status"],"owner_score_abstain")

    def test_digest_tamper_and_duplicate_key_abstain(self):
        self._run_capture()
        path = self._file()
        original = json.loads(path.read_text())
        for bad in (
            {**original, "ws_metadata_sha256":"f"*64},
            {**original, "registered_at_ms":END+200_000},
            {**original, "candidates":[{"symbol":"BROKENUSDT",
                 "direction":"LONG","decision_close":"1"}]},
        ):
            with self.subTest(case=list(bad)):
                path.write_text(json.dumps(
                    bad,sort_keys=True,separators=(",",":")
                ),encoding="ascii")
                self.assertEqual(self._run_score()["status"],"owner_score_abstain")
        with path.open("wb") as io:
            io.write(b'{"schema_version":"a","schema_version":"b"}')
        self.assertEqual(self._run_score()["status"],"owner_score_abstain")

    def test_inactive_owner_gates_and_no_network_or_sqlite_write(self):
        with patch.object(ledger, "observe_active_private_ws_n50_24closed",
                          side_effect=AssertionError("must not read")):
            self.assertEqual(ledger.capture_owner_ws_decision_once()["status"],
                             "owner_read_and_write_optin_required")
            self.assertEqual(ledger.score_owner_ws_decision_once(
                horizon_bars=1,costs=cost())["status"],"owner_read_optin_required")
        self.assertFalse(self.ledger_root.exists())
        with patch("socket.create_connection",
                   side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen",
                   side_effect=AssertionError("http")), \
             patch("sqlite3.connect",side_effect=AssertionError("new SQL")):
            self.assertEqual(self._run_capture()["capture_records_created"],1)
            self.assertGreater(self._run_score()["matured_observations"],0)

    def test_reject_scope_and_private_reference_poisoning_before_write(self):
        cases = [
            lambda src: src.update(status="ws_24h_readonly_integrity_abstain"),
            lambda src: src.update(audited_assets=49),
            lambda src: src["private_last_closes"].pop("BTCUSDT"),
            lambda src: src["private_last_closes"].update(BTCUSDT="0"),
            lambda src: src["research_rows"].pop(),
            lambda src: src.update(ws_metadata_sha256="MALFORMED"),
            lambda src: src["private_last_closes"].update(OTHERUSDT="99"),
        ]
        for mutate in cases:
            with self.subTest(case=str(mutate)):
                src=snapshot()
                mutate(src)
                self.assertEqual(
                    self._run_capture(src)["status"],"owner_capture_abstain")
                self.assertFalse(self.ledger_root.exists())


class CLIContractTests(unittest.TestCase):
    def test_cli_requires_explicit_capture_gate_and_censored_costs(self):
        from scripts.research_j2_ws_prospective_once import main
        with patch("scripts.research_j2_ws_prospective_once.capture_owner_ws_decision_once",
                   return_value={"status":"owner_read_and_write_optin_required",
                                 "orders_sent":False}) as capture, \
             patch("sys.stdout",new_callable=io.StringIO) as out:
            self.assertEqual(main(["capture"]),65)
        capture.assert_called_once_with(
            allow_private_readonly_research=False,
            allow_private_ledger_write=False,
        )
        self.assertNotIn("BTCUSDT",out.getvalue())

        with patch("scripts.research_j2_ws_prospective_once.score_owner_ws_decision_once",
                   return_value={"status":"owner_score_abstain","orders_sent":False}) as score, \
             patch("sys.stdout",new_callable=io.StringIO) as out:
            code = main([
                "score", "--allow-private-readonly-research",
                "--allow-private-ledger-read",
                "--horizon-bars","1",
                "--notional","100",
                "--entry-fee-bps","4",
                "--exit-fee-bps","6",
                "--entry-slippage-bps","2",
                "--exit-slippage-bps","3",
            ])
        self.assertEqual(code,65)
        args=score.call_args.kwargs
        self.assertEqual(args["horizon_bars"],1)
        self.assertEqual(args["costs"].entry_fee_bps,D("4"))
        self.assertEqual(args["costs"].hypothetical_notional_quote_units,D("100"))
        self.assertTrue(args["allow_private_readonly_research"])
        self.assertTrue(args["allow_private_ledger_read"])
        self.assertEqual(json.loads(out.getvalue())["status"],"owner_score_abstain")

    def test_cli_refuses_nan_fees_without_calling_score(self):
        from scripts.research_j2_ws_prospective_once import main
        with patch("scripts.research_j2_ws_prospective_once.score_owner_ws_decision_once",
                   side_effect=AssertionError("must not score")) as score, \
             patch("sys.stdout",new_callable=io.StringIO) as out:
            result=main([
                "score","--horizon-bars","1",
                "--notional","NaN",
                "--entry-fee-bps","4",
                "--exit-fee-bps","6",
                "--entry-slippage-bps","2",
                "--exit-slippage-bps","3",
            ])
        self.assertEqual(result,65)
        score.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "invalid_hypothetical_cost_assumptions")


if __name__ == "__main__":
    unittest.main()
