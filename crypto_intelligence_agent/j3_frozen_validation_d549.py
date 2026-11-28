"""D549: frozen financial validation on the original two reserved 18d windows.

No new data collection, strategy selection, or claim of statistical/financial
approval. The contract is a reproducibility boundary, not proof that nobody
has previously seen the reserved data. An external pre-registered digest is
required before either reserved replay.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from .j3_long_history_d528 import DAY, HOUR_MS, canonical
from .market_data import DataValidationError

SCHEMA = "d549-frozen-short-financial-validation-v1"
HORIZONS = (48, 168)
DEVELOPMENT_HORIZONS = (48, 168, 720, 1440, 2160)
STOPS = (150,)
MAINTENANCE = (50, 100, 150)
PARTITIONS = ("validation", "holdout")
MAX_REPORT_BYTES = 128 * 1024 * 1024
MAX_CONTRACT_BYTES = 16384
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,95}\Z")
_KEYS = {
    "schema_version", "source_report_sha256", "plan_sha256", "profile_revision",
    "policy_sha256", "engine_sha256", "matrix_sha256", "entry_experiments_sha256",
    "exit_experiments_sha256", "cutoff_ms", "partition_ranges_ms",
    "strategy_names", "exit_variants", "horizons_hours", "stop_grid_bps",
    "maintenance_stress_bps", "requested_days", "resolution",
    "no_selection_between_partitions",
}


def require(ok):
    if not ok:
        raise DataValidationError("D549 frozen validation contract mismatch")


def digest(raw):
    require(type(raw) is bytes)
    return sha256(raw).hexdigest()


def _sha(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _names(value, count):
    return (type(value) is list and len(value) == count
            and all(type(v) is str and _NAME.fullmatch(v) is not None for v in value)
            and len(set(value)) == count)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def decode_json(raw, limit):
    require(type(raw) is bytes and 2 <= len(raw) <= limit)
    def reject(_):
        raise DataValidationError("D549 nonfinite JSON")
    try:
        result = json.loads(raw, object_pairs_hook=_unique, parse_constant=reject)
        require(type(result) is dict)
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise DataValidationError("D549 invalid JSON") from exc


def ranges(cutoff):
    require(type(cutoff) is int and cutoff > 365 * DAY and cutoff % DAY == 0)
    return {"development": [cutoff - 365 * DAY, cutoff - 36 * DAY],
            "validation": [cutoff - 36 * DAY, cutoff - 18 * DAY],
            "holdout": [cutoff - 18 * DAY, cutoff]}


def _json_policy(value):
    # Same Decimal/enum serialization as the existing D529 report CLI.
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def policy_fingerprint(policy):
    require(policy.leverage.for_new_positions == 50)
    return digest(canonical({
        "research": _json_policy(asdict(policy.research)),
        "exits": _json_policy(asdict(policy.exits)),
        "margin_quote": str(policy.margin_quote),
        "leverage": 50,
    }))


def engine_fingerprint():
    """Conservative source/interpreter pin, not a signed runtime attestation.

    Read only the bounded project Python source tree; reject symlinked
    source files/directories. An unrelated Python change also invalidates
    the protocol, intentionally, rather than allowing a silent engine swap.
    """
    root = Path(__file__).resolve().parents[1]
    files = []
    for name in ("crypto_intelligence_agent", "scripts"):
        folder = root / name
        require(folder.is_dir() and not folder.is_symlink())
        for p in folder.rglob("*.py"):
            require(not p.is_symlink() and p.is_file()
                    and not any(q.is_symlink() for q in p.parents if q != root and root in q.parents))
            files.append(p)
            require(len(files) <= 2000)
    require(bool(files))
    h = sha256(canonical({"python": list(sys.version_info[:3])}))
    total = 0
    for p in sorted(files, key=lambda q: q.relative_to(root).as_posix()):
        with p.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        total += len(raw)
        require(len(raw) <= 4 * 1024 * 1024 and total <= 64 * 1024 * 1024)
        h.update(canonical([p.relative_to(root).as_posix(), digest(raw)]) + b"\n")
    return h.hexdigest()


def _fingerprints(plan, policy, matrix_raw, entry_raw, exit_raw):
    return {"plan_sha256": plan.digest, "policy_sha256": policy_fingerprint(policy),
            "engine_sha256": engine_fingerprint(),
            "matrix_sha256": digest(matrix_raw),
            "entry_experiments_sha256": digest(entry_raw),
            "exit_experiments_sha256": digest(exit_raw)}


def _report_keys(summary):
    return {(x["strategy"], x["exit_variant"], x["horizon_hours"], x["stop_bps"])
            for x in summary["rows"]}


def expected_grid(strategies, exits, horizons):
    return {(s, e, h, stop) for s in strategies for e in exits
            for h in horizons for stop in STOPS}


def validate_contract(raw, expected_sha):
    require(_sha(expected_sha) and digest(raw) == expected_sha)
    c = decode_json(raw, MAX_CONTRACT_BYTES)
    require(raw == canonical(c) and set(c) == _KEYS
            and c["schema_version"] == SCHEMA
            and all(_sha(c[k]) for k in ("source_report_sha256", "plan_sha256",
                "profile_revision", "policy_sha256", "engine_sha256", "matrix_sha256",
                "entry_experiments_sha256", "exit_experiments_sha256"))
            and _names(c["strategy_names"], 8)
            and _names(c["exit_variants"], 6)
            and c["exit_variants"] == sorted(c["exit_variants"])
            and "owner_baseline" in c["exit_variants"]
            and c["horizons_hours"] == list(HORIZONS)
            and c["stop_grid_bps"] == list(STOPS)
            and c["maintenance_stress_bps"] == list(MAINTENANCE)
            and c["requested_days"] == 365 and c["resolution"] == "5m"
            and c["no_selection_between_partitions"] is True
            and c["partition_ranges_ms"] == ranges(c["cutoff_ms"]))
    return c


def build_contract(report_raw, *, plan, owner_policy, profile_revision,
                   matrix_raw, entry_raw, exit_raw):
    """Derive the fixed 96-case grid from the completed D547 development report.

    D542 validation is used only for integrity, never to pick profitable rows.
    The caller verifies the owner profile revision before/after loading it.
    """
    from .j3_financial_evidence_d542 import summarize_financial_replay
    from .j3_exit_research_d531 import parse_exit_experiments

    d = decode_json(report_raw, MAX_REPORT_BYTES)
    require(d.get("partition") == "development"
            and d.get("requested_days") == 365 and d.get("resolution") == "5m"
            and d.get("preserve_recent_90d") is True
            and d.get("separate_open_mark") is True
            and d.get("target_diagnostics") is True
            and d.get("observed_funding") is True
            and d.get("exposure_diagnostics") is True
            and d.get("horizons_require_longest_complete_path") is True
            and d.get("research_max_horizon_hours") == 2160
            and d.get("horizons_hours") == list(DEVELOPMENT_HORIZONS)
            and d.get("stop_grid_bps") == list(STOPS)
            and d.get("maintenance_stress_bps") == list(MAINTENANCE)
            and d.get("partition_ranges_ms") == ranges(plan.cutoff_ms)
            and d.get("decision_range_ms") == [plan.cutoff_ms - 365 * DAY,
                plan.cutoff_ms - 36 * DAY - 2160 * HOUR_MS]
            and _sha(profile_revision) and d.get("profile_revision") == profile_revision
            and d.get("common_research_filters") == _json_policy(asdict(owner_policy.research))
            and d.get("common_exit_policy") == _json_policy(asdict(owner_policy.exits)))
    fp = _fingerprints(plan, owner_policy, matrix_raw, entry_raw, exit_raw)
    manifest = d.get("manifest")
    require(type(manifest) is dict and all(manifest.get(k) == fp[k] for k in
            ("plan_sha256", "matrix_sha256", "entry_experiments_sha256",
             "exit_experiments_sha256")))
    names = manifest.get("selected_strategy_names")
    require(_names(names, 8))
    variants = sorted(parse_exit_experiments(exit_raw, owner_policy.exits))
    require(_names(variants, 6))
    summary = summarize_financial_replay(d)
    require(summary["scenario_count"] == 240 and _report_keys(summary) ==
            expected_grid(names, variants, DEVELOPMENT_HORIZONS))
    raw = canonical({
        "schema_version": SCHEMA, "source_report_sha256": digest(report_raw),
        "profile_revision": profile_revision, **fp,
        "cutoff_ms": plan.cutoff_ms, "partition_ranges_ms": ranges(plan.cutoff_ms),
        "strategy_names": names, "exit_variants": variants,
        "horizons_hours": list(HORIZONS), "stop_grid_bps": list(STOPS),
        "maintenance_stress_bps": list(MAINTENANCE), "requested_days": 365,
        "resolution": "5m", "no_selection_between_partitions": True,
    })
    validate_contract(raw, digest(raw))
    return raw


def bind_replay(raw, expected_sha, *, plan, owner_policy, matrix_raw, entry_raw,
                exit_raw, partition, days, resolution, horizons, stops, strategies,
                research_max_horizon_hours, confirm_frozen_hypotheses,
                preserve_recent_90d, separate_open_mark, target_diagnostics,
                observed_funding, maintenance_grid, exposure_diagnostics):
    """Called by D529 before any reserved trade, mark, or funding read."""
    c = validate_contract(raw, expected_sha)
    fp = _fingerprints(plan, owner_policy, matrix_raw, entry_raw, exit_raw)
    require(partition in PARTITIONS and days == 365 and resolution == "5m"
            and list(horizons) == c["horizons_hours"]
            and list(stops) == c["stop_grid_bps"]
            and type(strategies) in (tuple, list) and list(strategies) == c["strategy_names"]
            and list(maintenance_grid) == c["maintenance_stress_bps"]
            and research_max_horizon_hours == max(HORIZONS)
            and all(x is True for x in (confirm_frozen_hypotheses, preserve_recent_90d,
                separate_open_mark, target_diagnostics, observed_funding))
            and exposure_diagnostics is False
            and c["cutoff_ms"] == plan.cutoff_ms
            and all(c[k] == v for k, v in fp.items()))
    return c


def verify_reserved_report(report):
    """Check report binding and exact reserved grid; no provenance claim."""
    part = report.get("partition")
    require(part in PARTITIONS)
    c = validate_contract(canonical(report.get("financial_validation_contract")),
                          report.get("financial_validation_contract_sha256"))
    manifest = report.get("manifest")
    require(type(manifest) is dict
            and all(manifest.get(k) == c[k] for k in ("plan_sha256", "matrix_sha256",
                "entry_experiments_sha256", "exit_experiments_sha256"))
            and manifest.get("selected_strategy_names") == c["strategy_names"]
            and report.get("profile_revision") == c["profile_revision"]
            and report.get("partition_ranges_ms") == c["partition_ranges_ms"]
            and report.get("decision_range_ms") == [c["partition_ranges_ms"][part][0],
                c["partition_ranges_ms"][part][1] - max(HORIZONS) * HOUR_MS]
            and report.get("requested_days") == c["requested_days"]
            and report.get("resolution") == c["resolution"]
            and report.get("horizons_hours") == c["horizons_hours"]
            and report.get("stop_grid_bps") == c["stop_grid_bps"]
            and report.get("maintenance_stress_bps") == c["maintenance_stress_bps"]
            and report.get("research_max_horizon_hours") == max(HORIZONS)
            and report.get("scenario_count") == 96
            and all(report.get(k) is True for k in ("preserve_recent_90d",
                "separate_open_mark", "target_diagnostics", "observed_funding",
                "horizons_require_longest_complete_path"))
            and report.get("exposure_diagnostics", False) is False)
    return c
