"""Owner-only D549 protocol, run only after the completed D547 fine report.

No network, service activation, profile changes, or automatic retries.
Freeze once in the same private report directory as annual5m-d547.json.
Register the returned digest externally before either reserved replay.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from crypto_intelligence_agent.j3_combination_research_d520 import MAX_MATRIX_BYTES
from crypto_intelligence_agent.j3_entry_research_d530 import MAX_BYTES as MAX_ENTRY_BYTES
from crypto_intelligence_agent.j3_exit_research_d531 import MAX_BYTES as MAX_EXIT_BYTES
from crypto_intelligence_agent.j3_financial_evidence_d542 import summarize_financial_replay
from crypto_intelligence_agent.j3_frozen_validation_d549 import (
    build_contract, decode_json, digest, validate_contract, MAX_REPORT_BYTES,
    MAX_CONTRACT_BYTES, HORIZONS, STOPS, MAINTENANCE, require, engine_fingerprint,
)
from crypto_intelligence_agent.j3_long_history_d528 import load_plan, canonical
from crypto_intelligence_agent.j3_long_replay_d529 import run_long_replay
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _owner_file, _private_directory
from crypto_intelligence_agent.market_data import MarketDataError
from crypto_intelligence_agent.paper_profile_d487 import snapshot
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy
from scripts.run_j3_long_history_d528 import owner_lock

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_NAME = "annual5m-d547.json"
CONTRACT_NAME = "d549-contract.json"


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_private(home, name, limit):
    with os.fdopen(_owner_file(home, name), "rb") as stream:
        before = os.fstat(stream.fileno())
        require(2 <= before.st_size <= limit)
        raw = stream.read(limit + 1)
        require(len(raw) == before.st_size
                and _identity(before) == _identity(os.fstat(stream.fileno())))
    return raw


def _bounded(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(2 <= len(raw) <= limit)
    return raw


def _exists(home, name):
    return (home / name).exists() or (home / name).is_symlink()


def publish_once(home, name, raw):
    """Same-filesystem atomic publication, no replacement of an old artifact."""
    fd, temp = tempfile.mkstemp(prefix=".d549-stage-", dir=home)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, home / name)
    finally:
        os.unlink(temp)
    dirfd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)


def run(args):
    os.umask(0o077)
    home = _private_directory(args.directory)
    reports = _private_directory(args.report_directory)
    require(home != reports and home.name.startswith("d528-history")
            and not any(x.startswith("j1-") for x in (*home.parts, *reports.parts))
            and os.getuid() == os.geteuid() != 0)
    require(args.confirm_reserved_protocol)
    matrix = _bounded(args.matrix_file, MAX_MATRIX_BYTES)
    entry = _bounded(args.entry_experiments_file, MAX_ENTRY_BYTES)
    exits = _bounded(args.exit_experiments_file, MAX_EXIT_BYTES)
    with owner_lock(home):
        plan = load_plan(home)
        require(plan.source_mode == "public_rest_observed_unverified")
        revision = snapshot(args.policy_file)["revision"]
        policy = read_owner_paper_policy(args.policy_file)
        require(snapshot(args.policy_file)["revision"] == revision)
        source = read_private(reports, DEVELOPMENT_NAME, MAX_REPORT_BYTES)
        raw = build_contract(source, plan=plan, owner_policy=policy,
            profile_revision=revision, matrix_raw=matrix, entry_raw=entry, exit_raw=exits)
        contract_sha = digest(raw)
        c = validate_contract(raw, contract_sha)

        if args.action == "freeze":
            require(args.expected_contract_sha256 is None
                    and not any(_exists(reports, name) for name in (
                        CONTRACT_NAME, "d549-validation-claim.json", "d549-holdout-claim.json",
                        "d549-validation.json", "d549-holdout.json")))
            require(snapshot(args.policy_file)["revision"] == revision
                    and load_plan(home).digest == plan.digest)
            publish_once(reports, CONTRACT_NAME, raw)
            return 0, {"status": "contract_frozen_register_digest_before_replay",
                       "contract_sha256": contract_sha,
                       "source_report_sha256": c["source_report_sha256"],
                       "partition_ranges_ms": c["partition_ranges_ms"],
                       "scenario_count_per_partition": 96,
                       "reserved_market_data_read": False}

        require(args.expected_contract_sha256 == contract_sha
                and read_private(reports, CONTRACT_NAME, MAX_CONTRACT_BYTES) == raw)
        part = args.action
        claim_name = f"d549-{part}-claim.json"
        output_name = f"d549-{part}.json"
        require(not _exists(reports, claim_name) and not _exists(reports, output_name))
        if part == "validation":
            require(not _exists(reports, "d549-holdout-claim.json")
                    and not _exists(reports, "d549-holdout.json"))
        else:
            # No sign/profit gate and no parameter selection from validation.
            prior_claim = decode_json(read_private(reports, "d549-validation-claim.json",
                                                   MAX_CONTRACT_BYTES), MAX_CONTRACT_BYTES)
            require(prior_claim == {"partition": "validation", "contract_sha256": contract_sha})
            prior = decode_json(read_private(reports, "d549-validation.json", MAX_REPORT_BYTES),
                                MAX_REPORT_BYTES)
            require(prior.get("partition") == "validation"
                    and prior.get("financial_validation_contract_sha256") == contract_sha)
            summarize_financial_replay(prior)
        require(snapshot(args.policy_file)["revision"] == revision
                and load_plan(home).digest == plan.digest)
        # Claim is durable before any reserved market data is read.
        # Failure or crash leaves the claim; never silently rerun a partition.
        publish_once(reports, claim_name, canonical({
            "partition": part, "contract_sha256": contract_sha,
        }))
        report = run_long_replay(home=home, plan=plan, owner_policy=policy,
            matrix_raw=matrix, entry_experiments_raw=entry, exit_experiments_raw=exits,
            strategy_names=tuple(c["strategy_names"]), days=365, partition=part,
            horizons=HORIZONS, stops=STOPS, resolution="5m",
            research_max_horizon_hours=max(HORIZONS), confirm_frozen_hypotheses=True,
            target_diagnostics=True, separate_open_mark=True, preserve_recent_90d=True,
            observed_funding=True, maintenance_stress_bps=MAINTENANCE,
            frozen_financial_validation=raw, expected_frozen_sha256=contract_sha)
        require(snapshot(args.policy_file)["revision"] == revision
                and load_plan(home).digest == plan.digest)
        require(engine_fingerprint() == c["engine_sha256"])
        report["profile_revision"] = revision
        serialized = json.dumps(report, default=str, sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode("utf-8")
        require(len(serialized) <= MAX_REPORT_BYTES)
        result = decode_json(serialized, MAX_REPORT_BYTES)
        summary = summarize_financial_replay(result)
        require(summary["partition"] == part
                and summary["financial_validation_contract_sha256"] == contract_sha)
        publish_once(reports, output_name, serialized)
        return 0, {"status": "reserved_conditional_report_completed", "partition": part,
                   "contract_sha256": contract_sha, "report_sha256": digest(serialized),
                   "scenario_count": summary["scenario_count"],
                   "fully_matched_scenario_count": summary["fully_matched_scenario_count"]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--action", choices=("freeze", "validation", "holdout"), required=True)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--report-directory", type=Path, required=True)
    p.add_argument("--policy-file", type=Path, required=True)
    p.add_argument("--matrix-file", type=Path,
                   default=ROOT / "docs/examples/d530_entry_controls_matrix.json")
    p.add_argument("--entry-experiments-file", type=Path,
                   default=ROOT / "docs/examples/d532_squeeze_optimization.json")
    p.add_argument("--exit-experiments-file", type=Path,
                   default=ROOT / "docs/examples/d533_runner_experiments.json")
    p.add_argument("--expected-contract-sha256")
    p.add_argument("--confirm-reserved-protocol", action="store_true")
    a = p.parse_args(argv)
    try:
        code, result = run(a)
    except (MarketDataError, OSError, ValueError, TypeError, ArithmeticError,
            AttributeError, KeyError, sqlite3.Error, RecursionError) as exc:
        code, result = 1, {"status": "d549_stopped", "error_type": type(exc).__name__,
                          "automatic_retry": False}
    result.update({"public_gets": 0, "profile_modified": False, "j1_touched": False,
                   "orders_sent": False, "winner_selected": False,
                   "out_of_sample_results_validated": False,
                   "independent_data_access_attested": False,
                   "liquidation_verified": False, "portfolio_simulated": False})
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
