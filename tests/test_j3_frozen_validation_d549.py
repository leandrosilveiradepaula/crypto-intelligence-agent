"""Synthetic D549 protocol and D529 integration; never read real reserved data."""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal as D
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j3_financial_evidence_d542 import summarize_financial_replay
from crypto_intelligence_agent.j3_compact_financial_d544 import compact_financial_summary
from crypto_intelligence_agent.j3_exit_research_d531 import parse_exit_experiments
from crypto_intelligence_agent.j3_frozen_validation_d549 import (
    build_contract, validate_contract, digest, ranges, HORIZONS, STOPS,
    MAINTENANCE, DEVELOPMENT_HORIZONS,
)
from crypto_intelligence_agent.j3_funding_replay_d537 import ObservedFundingHistory
from crypto_intelligence_agent.j3_long_history_d528 import DAY, HOUR_MS, canonical
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay
from crypto_intelligence_agent.market_data import DataValidationError
from scripts import run_j3_frozen_validation_d549 as cli
from test_j3_long_replay_d529 import OWNER, PLAN, END, bars
from test_j3_financial_evidence_d542 import report, row, metrics

ROOT = Path(__file__).resolve().parents[1]
MATRIX = (ROOT / "docs/examples/d530_entry_controls_matrix.json").read_bytes()
ENTRY = (ROOT / "docs/examples/d532_squeeze_optimization.json").read_bytes()
EXIT = (ROOT / "docs/examples/d533_runner_experiments.json").read_bytes()
NAMES = ("squeeze_bb_20_2_strict", "squeeze_bb_20_2_strict_rsi", "sq_w04_v2",
         "sq_w04_v15", "sq_sma_30_60", "sq_sma_10_30", "sq_ema_9_21", "sq_pivot")
VARIANTS = sorted(parse_exit_experiments(EXIT, OWNER.exits))
REVISION = "b" * 64


def serialize(d):
    return json.dumps(d, default=str, sort_keys=True, separators=(",", ":")).encode()


def development(plan=PLAN):
    d = report()
    item = row(metrics(12, 1, 2), metrics(14, 2, 3))
    for group in (item, *item["by_month"].values()):
        for order in ("adverse_first", "favorable_first"):
            a = group[order]
            for k, v in list(a.items()):
                if k.startswith("stress_100bps_"):
                    a[k.replace("100bps", "150bps")] = v
            a.update({"fully_exited_count": 3, "unrealized_gross_quote": "1",
                      "open_after_assumed_exit_cost_quote": "1",
                      "realized_after_incurred_cost_quote":
                          str(D(a["conditional_before_funding_quote"]) - 1)})
    item["exposure_diagnostics"] = {
        o: {"path_count": 4, "peak_concurrent_paths": 1, "peak_concurrent_assets": 1,
            "top_5_positive_path_share_percent": "100",
            "pre_funding_net_without_top_5_positive_paths_quote": "0"}
        for o in ("adverse_first", "favorable_first")
    }
    d.update({"resolution": "5m", "preserve_recent_90d": True,
              "separate_open_mark": True, "target_diagnostics": True,
              "exposure_diagnostics": True, "horizons_require_longest_complete_path": True,
              "research_max_horizon_hours": 2160, "scenario_count": 240,
              "horizons_hours": list(DEVELOPMENT_HORIZONS),
              "maintenance_stress_bps": list(MAINTENANCE),
              "partition_ranges_ms": ranges(plan.cutoff_ms),
              "decision_range_ms": [plan.cutoff_ms - 365 * DAY,
                  plan.cutoff_ms - 36 * DAY - 2160 * HOUR_MS],
              "profile_revision": REVISION,
              "common_research_filters": asdict(OWNER.research),
              "common_exit_policy": asdict(OWNER.exits),
              "manifest": {"plan_sha256": plan.digest, "matrix_sha256": digest(MATRIX),
                  "entry_experiments_sha256": digest(ENTRY),
                  "exit_experiments_sha256": digest(EXIT),
                  "selected_strategy_names": list(NAMES)},
              "scenarios": [{"horizon_hours": h, "stop_bps": 150, "exit_variant": v,
                   "common_covered_symbol_hours": 100,
                   "rows": [dict(deepcopy(item), name=n) for n in NAMES]}
                  for h in DEVELOPMENT_HORIZONS for v in VARIANTS]})
    return d


def freeze(plan=PLAN, source=None):
    return build_contract(serialize(development(plan)) if source is None else source,
        plan=plan, owner_policy=OWNER, profile_revision=REVISION,
        matrix_raw=MATRIX, entry_raw=ENTRY, exit_raw=EXIT)


def reserved(raw, partition="validation", plan=PLAN):
    d = development(plan)
    c = validate_contract(raw, digest(raw))
    d.update({"partition": partition, "scenario_count": 96,
              "exposure_diagnostics": False,
              "horizons_hours": list(HORIZONS),
              "research_max_horizon_hours": max(HORIZONS),
              "decision_range_ms": [c["partition_ranges_ms"][partition][0],
                  c["partition_ranges_ms"][partition][1] - max(HORIZONS) * HOUR_MS],
              "financial_validation_contract": c,
              "financial_validation_contract_sha256": digest(raw)})
    d["scenarios"] = [s for s in d["scenarios"] if s["horizon_hours"] in HORIZONS]
    return json.loads(serialize(d))


def replay_args(raw):
    return dict(home=Path("."), plan=PLAN, owner_policy=OWNER, matrix_raw=MATRIX,
        entry_experiments_raw=ENTRY, exit_experiments_raw=EXIT,
        strategy_names=NAMES, days=365, partition="validation",
        horizons=HORIZONS, stops=STOPS, resolution="5m",
        research_max_horizon_hours=max(HORIZONS), confirm_frozen_hypotheses=True,
        target_diagnostics=True, separate_open_mark=True, preserve_recent_90d=True,
        observed_funding=True, maintenance_stress_bps=MAINTENANCE,
        frozen_financial_validation=raw, expected_frozen_sha256=digest(raw))


class FrozenValidationTests(unittest.TestCase):
    def test_freeze_exact_grid_and_original_reserve(self):
        raw = freeze()
        self.assertEqual(raw, freeze())
        c = validate_contract(raw, digest(raw))
        self.assertEqual(c["partition_ranges_ms"]["validation"], [END-36*DAY, END-18*DAY])
        self.assertEqual(c["partition_ranges_ms"]["holdout"], [END-18*DAY, END])
        self.assertEqual(c["strategy_names"], list(NAMES))
        self.assertEqual(c["source_report_sha256"], digest(serialize(development())))
        self.assertEqual(c["horizons_hours"], [48, 168])

    def test_reject_wrong_source_or_configuration(self):
        for key, value in (("resolution", "1h"), ("partition", "validation"),
                           ("preserve_recent_90d", False), ("profile_revision", "c"*64),
                           ("decision_range_ms", [END-365*DAY, END])):
            with self.subTest(key=key), self.assertRaises(DataValidationError):
                freeze(source=serialize(dict(development(), **{key: value})))
        with self.assertRaises(DataValidationError):
            build_contract(serialize(development()), plan=PLAN, owner_policy=OWNER,
                profile_revision=REVISION, matrix_raw=MATRIX+b" ", entry_raw=ENTRY, exit_raw=EXIT)
        with self.assertRaises(DataValidationError):
            validate_contract(freeze(), "0"*64)

    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_changed_parameters_rejected_before_any_market_read(self, read):
        raw = freeze()
        args = replay_args(raw)
        for delta in ({"expected_frozen_sha256": "0"*64},
                      {"matrix_raw": MATRIX+b" "}, {"entry_experiments_raw": ENTRY+b" "},
                      {"exit_experiments_raw": EXIT+b" "}, {"resolution": "1h"},
                      {"strategy_names": NAMES[::-1]}, {"stops": (100,)},
                      {"horizons": (48, 72)}, {"preserve_recent_90d": False},
                      {"confirm_frozen_hypotheses": False},
                      {"owner_policy": SimpleNamespace(**dict(vars(OWNER), margin_quote=D(2)))},
                      {"partition": "development"}, {"observed_funding": False},
                      {"frozen_financial_validation": None, "expected_frozen_sha256": None}):
            with self.subTest(keys=list(delta)), self.assertRaises(DataValidationError):
                run_long_replay(**dict(args, **delta))
        read.assert_not_called()

    @patch("crypto_intelligence_agent.j3_long_replay_d529.ObservedFundingHistory.load")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.entry_events")
    @patch("crypto_intelligence_agent.j3_long_replay_d529.read_window")
    def test_real_engine_reserved_boundary_with_synthetic_data(self, read, events, load):
        raw = freeze()
        start, end = ranges(END)["validation"]
        def get(home, plan, symbol, interval, a, b, **kw):
            self.assertLessEqual(b, end)
            if interval == "5m":
                self.assertGreaterEqual(a, start)
            return bars(symbol, max(a, END-40*DAY), b, interval)
        read.side_effect = get

        def candidate(cs, cfg):
            for i in range(24, len(cs)):
                t = cs[i].close_time_ms + 1
                if start+5*DAY <= t <= end-168*HOUR_MS and cs[i].close > cs[i-23].open:
                    return {t: "LONG"}
            return {}
        events.side_effect = candidate

        def source(home, plan, symbol, a, b, resolution):
            self.assertGreaterEqual(a, start)
            self.assertLessEqual(b, end)
            self.assertEqual(resolution, "5m")
            return ObservedFundingHistory(start=a, end=b, resolution=resolution,
                funding={"query_coverage_complete": True,
                    "rows": tuple((t, ".0001") for t in range(a, b, HOUR_MS))},
                mark={"query_coverage_complete": True,
                    "rows": tuple((t, "100", "110", "90", "100")
                                  for t in range(a, b, 300000))})
        load.side_effect = source
        d = run_long_replay(**replay_args(raw))
        d["profile_revision"] = REVISION
        summary = summarize_financial_replay(json.loads(serialize(d)))
        self.assertEqual(summary["partition"], "validation")
        self.assertEqual(summary["scenario_count"], 96)
        self.assertGreater(summary["fully_matched_scenario_count"], 0)
        self.assertFalse(summary["out_of_sample_results_validated"])
        self.assertEqual(d["decision_range_ms"], [start, end-168*HOUR_MS])

    def test_summary_cannot_mix_partitions_or_change_grid(self):
        raw = freeze()
        for p in ("validation", "holdout"):
            d = reserved(raw, p)
            s = summarize_financial_replay(d)
            self.assertEqual(s["partition"], p)
            self.assertEqual(s["scenario_count"], 96)
            s["source_report_sha256"] = "c"*64
            compact = compact_financial_summary(s)
            self.assertEqual(compact[0]["partition"], p)
            self.assertTrue(all(x["descriptive_top_mean"] == []
                                for x in compact if x["kind"] == "d544_horizon"))
        for delta in ({"financial_validation_contract_sha256": "0"*64},
                      {"partition": "development"}, {"profile_revision": "c"*64},
                      {"decision_range_ms": [END-36*DAY, END]},
                      {"financial_validation_contract": None}):
            with self.assertRaises(DataValidationError):
                summarize_financial_replay(dict(reserved(raw), **delta))
        d = reserved(raw)
        d["scenarios"][0]["rows"][0]["name"] = "unexpected_strategy"
        with self.assertRaises(DataValidationError):
            summarize_financial_replay(d)

    def test_cli_freeze_then_validation_then_holdout_no_retry(self):
        real = replace(PLAN, source_mode="public_rest_observed_unverified")
        raw = freeze(real)
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "d528-history-fixture"
            reports = Path(tmp) / "reports"
            home.mkdir()
            reports.mkdir()
            (reports / cli.DEVELOPMENT_NAME).write_bytes(serialize(development(real)))
            def publish(path, name, data):
                with (path / name).open("xb") as stream:
                    stream.write(data)
            with patch.object(cli, "_private_directory", side_effect=lambda p: p), \
                 patch.object(cli, "read_private", side_effect=lambda p,n,l: (p/n).read_bytes()), \
                 patch.object(cli, "publish_once", side_effect=publish), \
                 patch.object(cli.os, "getuid", return_value=1000, create=True), \
                 patch.object(cli.os, "geteuid", return_value=1000, create=True), \
                 patch.object(cli.os, "umask"), \
                 patch.object(cli, "owner_lock", side_effect=lambda p: nullcontext()), \
                 patch.object(cli, "load_plan", return_value=real), \
                 patch.object(cli, "snapshot", return_value={"revision": REVISION}), \
                 patch.object(cli, "read_owner_paper_policy", return_value=OWNER), \
                 patch.object(cli, "run_long_replay") as run:
                args = SimpleNamespace(directory=home, report_directory=reports,
                    policy_file=Path("."), matrix_file=ROOT/"docs/examples/d530_entry_controls_matrix.json",
                    entry_experiments_file=ROOT/"docs/examples/d532_squeeze_optimization.json",
                    exit_experiments_file=ROOT/"docs/examples/d533_runner_experiments.json",
                    confirm_reserved_protocol=True, action="freeze", expected_contract_sha256=None)
                code, result = cli.run(args)
                self.assertEqual(code, 0)
                self.assertEqual(result["contract_sha256"], digest(raw))
                run.assert_not_called()
                args.action = "holdout"
                args.expected_contract_sha256 = digest(raw)
                with self.assertRaises((DataValidationError, OSError)):
                    cli.run(args)
                run.assert_not_called()
                args.action = "validation"
                args.expected_contract_sha256 = "0"*64
                with self.assertRaises(DataValidationError):
                    cli.run(args)
                run.assert_not_called()
                args.expected_contract_sha256 = digest(raw)
                run.side_effect = lambda **kw: reserved(raw, kw["partition"], real)
                self.assertEqual(cli.run(args)[0], 0)
                self.assertEqual(run.call_count, 1)
                with self.assertRaises(DataValidationError):
                    cli.run(args)
                args.action = "holdout"
                self.assertEqual(cli.run(args)[0], 0)
                self.assertEqual(run.call_count, 2)
                with self.assertRaises(DataValidationError):
                    cli.run(args)
                self.assertEqual(run.call_count, 2)

    @unittest.skipUnless(os.name == "posix", "POSIX private atomic artifact")
    def test_publication_never_replaces(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            cli.publish_once(p, "claim.json", b"first")
            with self.assertRaises(FileExistsError):
                cli.publish_once(p, "claim.json", b"second")
            self.assertEqual((p/"claim.json").read_bytes(), b"first")
            self.assertEqual((p/"claim.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
